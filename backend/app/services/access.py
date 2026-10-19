"""Control de acceso: tags RFID (vehicular/peatonal) y QR de visitas."""
import re
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import events
from ..config import utcnow
from ..models import (AccesoLog, Edificio, EstadoVisita, Residente, Tag, TipoTag, Unidad, Vehiculo, Visita)


class AccesoError(Exception):
    """Regla de negocio incumplida. ``status``: 409 conflicto, 422 dato inválido."""

    def __init__(self, msg: str, status: int = 409):
        super().__init__(msg)
        self.status = status


_RE_UID = re.compile(r"[0-9A-F]{8,20}")  # UID RFID en hexadecimal: 4 a 10 bytes


def asignar_tag(db: Session, edificio: Edificio, unidad_id: int, uid: str,
                tipo: TipoTag, residente_id: int | None = None) -> Tag:
    unidad = db.get(Unidad, unidad_id)
    if not unidad or unidad.edificio_id != edificio.id:
        raise AccesoError("Unidad no existe en este edificio")
    uid = uid.strip().upper()
    if not _RE_UID.fullmatch(uid):
        raise AccesoError("UID inválido: entre 8 y 20 caracteres hexadecimales (0-9, A-F)", 422)
    if residente_id is not None:
        r = db.get(Residente, residente_id)
        if not r or r.edificio_id != edificio.id or r.unidad_id != unidad_id:
            raise AccesoError("El residente debe pertenecer al mismo departamento del tag", 422)
    if tipo == TipoTag.vehicular:
        # Límite físico: máx. estacionamientos asignados a la unidad (tope del edificio)
        limite = min(unidad.estacionamientos, edificio.max_estac_por_unidad)
        usados = db.scalar(select(func.count(Tag.id)).where(
            Tag.unidad_id == unidad_id, Tag.tipo == TipoTag.vehicular, Tag.activo.is_(True)))
        if usados >= limite:
            raise AccesoError(f"La unidad ya tiene {usados} tag(s) vehicular(es) (máx. {limite})")
    existente = db.scalar(select(Tag).where(Tag.edificio_id == edificio.id, Tag.uid == uid.upper()))
    if existente:
        raise AccesoError("UID ya registrado")
    tag = Tag(edificio_id=edificio.id, unidad_id=unidad_id, residente_id=residente_id,
              uid=uid.upper(), tipo=tipo)
    db.add(tag)
    db.flush()
    return tag


def normalizar_patente(p: str) -> str:
    return "".join(c for c in p.upper() if c.isalnum())


def registrar_vehiculo(db: Session, edificio: Edificio, unidad_id: int, patente: str,
                       descripcion: str = "", tag_id: int | None = None) -> Vehiculo:
    unidad = db.get(Unidad, unidad_id)
    if not unidad or unidad.edificio_id != edificio.id:
        raise AccesoError("Unidad no existe en este edificio")
    pat = normalizar_patente(patente)
    if not 5 <= len(pat) <= 7:
        raise AccesoError("Patente inválida")
    limite = min(unidad.estacionamientos, edificio.max_estac_por_unidad)
    usados = db.scalar(select(func.count(Vehiculo.id)).where(
        Vehiculo.unidad_id == unidad_id, Vehiculo.activo.is_(True)))
    if usados >= limite:
        raise AccesoError(f"La unidad ya tiene {usados} vehículo(s) (máx. {limite})")
    if db.scalar(select(Vehiculo.id).where(Vehiculo.edificio_id == edificio.id, Vehiculo.patente == pat)):
        raise AccesoError("Patente ya registrada")
    if tag_id:
        tag = db.get(Tag, tag_id)
        if not tag or tag.edificio_id != edificio.id or tag.unidad_id != unidad_id:
            raise AccesoError("Sticker no pertenece a la unidad")
    v = Vehiculo(edificio_id=edificio.id, unidad_id=unidad_id, patente=pat, descripcion=descripcion, tag_id=tag_id)
    db.add(v)
    db.flush()
    return v


def cupos_ocupados(db: Session, edificio_id: str, desde, hasta) -> int:
    return db.scalar(select(func.count(Visita.id)).where(
        Visita.edificio_id == edificio_id, Visita.usa_estacionamiento.is_(True),
        Visita.estado.in_([EstadoVisita.reservada, EstadoVisita.llego]),
        Visita.desde < hasta, Visita.hasta > desde)) or 0


def reservar_visita(db: Session, edificio: Edificio, unidad_id: int, nombre: str, desde, hasta,
                    patente: str = "", usa_estacionamiento: bool = True, usos_max: int = 2) -> Visita:
    if hasta <= desde:
        raise AccesoError("Rango horario inválido")
    if usa_estacionamiento and cupos_ocupados(db, edificio.id, desde, hasta) >= edificio.cupos_visitas:
        raise AccesoError("Sin cupos de estacionamiento de visitas en ese horario")
    v = Visita(edificio_id=edificio.id, unidad_id=unidad_id, nombre_visita=nombre, patente=normalizar_patente(patente),
               usa_estacionamiento=usa_estacionamiento, desde=desde, hasta=hasta,
               codigo_qr=secrets.token_urlsafe(24), usos_max=usos_max)
    db.add(v)
    db.flush()
    events.publish(db, edificio.id, "visita.reservada",
                   {"visita_id": v.id, "unidad_id": unidad_id, "nombre": nombre})
    return v


def liberar_no_show(db: Session, edificio: Edificio | None = None) -> int:
    """Libera reservas cuya llegada excedió la tolerancia (por defecto 20 min)."""
    ahora = utcnow()
    q = select(Visita).where(Visita.estado == EstadoVisita.reservada, Visita.usos == 0)
    if edificio:
        q = q.where(Visita.edificio_id == edificio.id)
    n = 0
    for v in db.scalars(q):
        ed = edificio or db.get(Edificio, v.edificio_id)
        if ahora > v.desde + timedelta(minutes=ed.tolerancia_visita_min):
            v.estado = EstadoVisita.no_show
            n += 1
            events.publish(db, v.edificio_id, "visita.no_show", {"visita_id": v.id, "unidad_id": v.unidad_id})
    return n


def validar_acceso(db: Session, edificio: Edificio, token: str, punto: str = "peatonal") -> tuple[bool, str]:
    """Decide si abrir. ``punto`` = 'vehicular' | 'peatonal'. Registra bitácora."""
    permitido, motivo = _decidir(db, edificio, token.strip(), punto)
    db.add(AccesoLog(edificio_id=edificio.id, token=token[:80], punto=punto, permitido=permitido, motivo=motivo))
    return permitido, motivo


def _decidir(db: Session, edificio: Edificio, token: str, punto: str) -> tuple[bool, str]:
    tag = db.scalar(select(Tag).where(Tag.edificio_id == edificio.id, Tag.uid == token.upper()))
    if tag:
        if not tag.activo:
            return False, "Tag desactivado"
        if tag.tipo == TipoTag.peatonal and punto == "vehicular":
            return False, "Tag peatonal no habilita acceso vehicular"
        if tag.residente_id:
            r = db.get(Residente, tag.residente_id)
            if r and not r.activo:
                return False, "Residente inactivo"
        events.publish(db, edificio.id, "acceso.residente", {"unidad_id": tag.unidad_id, "punto": punto})
        return True, "Residente"
    if punto == "vehicular":  # lector de patentes (LPR): el token es la patente leída
        veh = db.scalar(select(Vehiculo).where(Vehiculo.edificio_id == edificio.id,
                                               Vehiculo.patente == normalizar_patente(token)))
        if veh:
            if not veh.activo:
                return False, "Patente desactivada"
            events.publish(db, edificio.id, "acceso.residente",
                           {"unidad_id": veh.unidad_id, "punto": punto, "patente": veh.patente})
            return True, "Patente de residente"
    v = db.scalar(select(Visita).where(Visita.edificio_id == edificio.id, Visita.codigo_qr == token))
    if not v and punto == "vehicular":  # patente de visita con reserva vigente
        v = db.scalar(select(Visita).where(Visita.edificio_id == edificio.id, Visita.patente != "",
                                           Visita.patente == normalizar_patente(token),
                                           Visita.estado.in_([EstadoVisita.reservada, EstadoVisita.llego]),
                                           Visita.hasta >= utcnow()))
    if not v:
        return False, "Credencial desconocida"
    ahora = utcnow()
    if v.estado in (EstadoVisita.cancelada, EstadoVisita.no_show):
        return False, f"Reserva {v.estado.value}"
    if ahora < v.desde - timedelta(minutes=5) or ahora > v.hasta:
        return False, "Fuera de horario de la reserva"
    if v.usos >= v.usos_max:
        return False, "QR sin usos disponibles"
    v.usos += 1
    if v.estado == EstadoVisita.reservada:
        v.estado, v.llegada_at = EstadoVisita.llego, ahora
        events.publish(db, edificio.id, "visita.llego",
                       {"visita_id": v.id, "unidad_id": v.unidad_id, "nombre": v.nombre_visita})
    return True, "Visita"
