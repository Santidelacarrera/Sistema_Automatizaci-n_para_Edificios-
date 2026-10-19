"""Control de acceso: stickers UHF y llaveros RC522, patentes (LPR) y QR de visitas.

El portón abre sólo si ``decidir`` devuelve abrir=True; el resto queda en la bitácora con motivo.
"""
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import events
from ..config import utcnow
from ..models import (AccesoLog, Edificio, EstadoTag, EstadoVisita, LecturaPendiente, ModoAcceso, Residente,
                      Tag, TipoTag, Unidad, Vehiculo, Visita)
from .credenciales import CredencialInvalida, detectar_formato, normalizar

class AccesoError(Exception):
    """Regla de negocio incumplida. ``status``: 409 conflicto, 422 dato inválido."""

    def __init__(self, msg: str, status: int = 409):
        super().__init__(msg)
        self.status = status


@dataclass(frozen=True)
class Decision:
    """Resultado de una lectura. codigo: ok | denegada | duplicada | esperando."""
    abrir: bool
    motivo: str
    codigo: str = "denegada"



def asignar_tag(db: Session, edificio: Edificio, unidad_id: int, uid: str,
                tipo: TipoTag, residente_id: int | None = None, formato: str | None = None) -> Tag:
    unidad = db.get(Unidad, unidad_id)
    if not unidad or unidad.edificio_id != edificio.id:
        raise AccesoError("Unidad no existe en este edificio")
    if formato is None:  # stickers UHF vs llaveros RC522
        formato = "epc" if tipo == TipoTag.vehicular else "rc522"
    try:
        uid = normalizar(uid, formato)
    except CredencialInvalida as e:
        raise AccesoError(str(e), 422)
    if residente_id is not None:
        r = db.get(Residente, residente_id)
        if not r or r.edificio_id != edificio.id or r.unidad_id != unidad_id:
            raise AccesoError("El residente debe pertenecer al mismo departamento del tag", 422)
    if tipo == TipoTag.vehicular:
        # Límite físico: máx. estacionamientos asignados a la unidad (tope del edificio)
        limite = min(unidad.estacionamientos, edificio.max_estac_por_unidad)
        usados = db.scalar(select(func.count(Tag.id)).where(
            Tag.unidad_id == unidad_id, Tag.tipo == TipoTag.vehicular, Tag.estado == "activo"))
        if usados >= limite:
            raise AccesoError(f"La unidad ya tiene {usados} tag(s) vehicular(es) (máx. {limite})")
    existente = db.scalar(select(Tag).where(Tag.uid == uid))  # un código no puede estar en dos edificios
    if existente:
        raise AccesoError("Código ya registrado en el sistema (en este edificio o en otro)")
    tag = Tag(edificio_id=edificio.id, unidad_id=unidad_id, residente_id=residente_id,
              uid=uid, tipo=tipo, formato=formato)
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


def validar_acceso(db: Session, edificio: Edificio, token: str, punto: str = "peatonal",
                    tipo: str | None = None, confianza: float | None = None,
                    direccion: str | None = None) -> tuple[bool, str]:
    """Versión simple: (abrir, motivo). El endpoint usa ``decidir`` para conocer también el código."""
    d = decidir(db, edificio, token, punto, tipo, confianza, direccion)
    return d.abrir, d.motivo


def decidir(db: Session, edificio: Edificio, token: str, punto: str = "peatonal", tipo: str | None = None,
            confianza: float | None = None, direccion: str | None = None) -> Decision:
    """Decide si abrir y registra la bitácora.

    tipo:       'sticker' | 'patente' | None (None = comportamiento anterior: tag primero, luego patente).
    confianza:  confianza de la lectura de patente (0-1); bajo el umbral del edificio se rechaza.
    direccion:  'entrada' | 'salida' | None. Sólo se usa con anti-passback activo.
    """
    ahora = utcnow()
    token = (token or "").strip()
    # 1) QR de visita: credencial propia, sirve en cualquier punto y en cualquier modo.
    v = _visita_por_qr(db, edificio, token)
    if v:
        return _registrar(db, edificio, token, punto, "qr", _pasar_visita(db, edificio, v, ahora))
    try:
        fuente, valor = _credencial(token, punto, tipo)
    except CredencialInvalida as e:
        return _registrar(db, edificio, token[:80], punto, "", Decision(False, str(e), "denegada"))
    if fuente == "patente" and confianza is not None and confianza < edificio.umbral_confianza_patente:
        return _registrar(db, edificio, valor, punto, fuente, Decision(
            False, f"Confianza {confianza:.2f} bajo el umbral ({edificio.umbral_confianza_patente:.2f})", "denegada"))
    db.flush()  # que los intentos de esta misma transacción cuenten para el antirrebote
    if _duplicada(db, edificio, punto, valor, ahora):
        return _registrar(db, edificio, valor, punto, fuente, Decision(
            False, f"Lectura duplicada: misma credencial dentro de {edificio.antirrebote_s} s", "duplicada"))
    d = _autorizar(db, edificio, valor, punto, fuente, direccion, ahora)
    return _registrar(db, edificio, valor, punto, fuente, d)


def _credencial(token: str, punto: str, tipo: str | None) -> tuple[str, str]:
    """(fuente, valor canónico). Lanza CredencialInvalida si el formato no sirve para el tipo pedido."""
    if punto != "vehicular":
        if re.fullmatch(r"[0-9A-Fa-f\s]{8,20}", token):
            return "tag", normalizar(token, "rc522")
        return "tag", token.upper()  # se busca tal cual; si no existe, "credencial desconocida"
    if tipo == "sticker":
        formato = detectar_formato(token)
        if formato == "epc":
            return "sticker", normalizar(token, "epc")
        if formato == "wiegand":
            return "sticker", normalizar(token, "wiegand")
        raise CredencialInvalida("Código de sticker inválido: EPC hexadecimal o Wiegand W26/W34")
    if tipo == "patente":
        pat = normalizar_patente(token)
        if not 5 <= len(pat) <= 7:
            raise CredencialInvalida("Patente inválida")
        return "patente", pat
    return "auto", token.upper()  # tipo no informado: tag si existe, si no patente


def _duplicada(db: Session, edificio: Edificio, punto: str, valor: str, ahora) -> bool:
    """Antirrebote: la misma credencial en el mismo punto dentro de la ventana. Compara sólo con
    intentos no duplicados para que una lectura repetida no extienda la ventana indefinidamente."""
    if edificio.antirrebote_s <= 0:
        return False
    ultima = db.scalar(select(AccesoLog).where(
        AccesoLog.edificio_id == edificio.id, AccesoLog.punto == punto, AccesoLog.token == valor,
        AccesoLog.motivo.not_like("Lectura duplicada%"),
        AccesoLog.creado >= ahora - timedelta(seconds=edificio.antirrebote_s))
        .order_by(AccesoLog.id.desc()).limit(1))
    return ultima is not None


def _registrar(db: Session, edificio: Edificio, valor: str, punto: str, fuente: str, d: Decision) -> Decision:
    db.add(AccesoLog(edificio_id=edificio.id, token=valor[:80], punto=punto, fuente=fuente,
                     permitido=d.abrir, motivo=d.motivo[:160]))
    return d


def _autorizar(db: Session, ed: Edificio, valor: str, punto: str, fuente: str, direccion: str | None, ahora) -> Decision:
    if punto != "vehicular":
        tag = _buscar_tag(db, ed, valor)
        if not tag:
            return Decision(False, "Credencial desconocida", "denegada")
        return _autorizar_sticker(db, ed, tag, punto, direccion, ahora)
    if fuente == "auto":  # tipo no informado: tag primero, luego patente (compatibilidad)
        tag = _buscar_tag(db, ed, valor)
        if tag:
            return _autorizar_sticker(db, ed, tag, punto, direccion, ahora)
        fuente, valor = "patente", normalizar_patente(valor)
    if fuente == "sticker":
        tag = _buscar_tag(db, ed, valor)
        if not tag:
            return Decision(False, "Sticker desconocido: no está registrado en este edificio", "denegada")
        return _autorizar_sticker(db, ed, tag, punto, direccion, ahora)
    if fuente == "tag":
        return Decision(False, "Credencial desconocida", "denegada")
    # patente
    veh = db.scalar(select(Vehiculo).where(Vehiculo.edificio_id == ed.id, Vehiculo.patente == valor))
    if not veh:
        return _autorizar_visita_patente(db, ed, valor, ahora)
    if not veh.activo:
        return Decision(False, "Patente desactivada", "denegada")
    if ed.modo_acceso == ModoAcceso.solo_sticker.value:
        return Decision(False, "Este edificio abre sólo con sticker", "denegada")
    if ed.modo_acceso == ModoAcceso.sticker_y_patente.value:
        return _correlacionar(db, ed, "patente", valor, veh, ahora, direccion)
    return _finalizar_vehiculo(db, ed, veh, "Patente de residente", direccion)


def _autorizar_sticker(db: Session, ed: Edificio, tag: Tag, punto: str, direccion, ahora) -> Decision:
    if tag.estado != EstadoTag.activo.value:
        motivo = {"perdido": "Sticker reportado perdido: no abre",
                  "bloqueado": "Sticker bloqueado: no abre"}.get(tag.estado, "Sticker inactivo")
        return Decision(False, motivo, "denegada")
    if tag.tipo == TipoTag.peatonal and punto == "vehicular":
        return Decision(False, "Tag peatonal no habilita acceso vehicular", "denegada")
    if tag.residente_id:
        r = db.get(Residente, tag.residente_id)
        if r and not r.activo:
            return Decision(False, "Residente inactivo", "denegada")
    if punto != "vehicular":
        return _finalizar_tag(db, ed, tag, "Residente", punto, ahora)
    veh = db.scalar(select(Vehiculo).where(Vehiculo.edificio_id == ed.id, Vehiculo.tag_id == tag.id,
                                           Vehiculo.activo.is_(True)))
    if ed.modo_acceso == ModoAcceso.solo_patente.value:
        return Decision(False, "Este edificio abre sólo con patente", "denegada")
    if ed.modo_acceso == ModoAcceso.sticker_y_patente.value:
        if not veh:
            return Decision(False, "Sticker sin vehículo asociado: asócialo a una patente en el panel", "denegada")
        return _correlacionar(db, ed, "sticker", tag.uid, veh, ahora, direccion, tag=tag)
    if veh is not None:
        return _finalizar_vehiculo(db, ed, veh, "Residente", direccion, tag=tag)
    return _finalizar_tag(db, ed, tag, "Residente", punto, ahora)


def _autorizar_visita_patente(db: Session, ed: Edificio, valor: str, ahora) -> Decision:
    if ed.modo_acceso in (ModoAcceso.solo_sticker.value, ModoAcceso.sticker_y_patente.value):
        return Decision(False, "Patente no registrada: las visitas usan su código QR", "denegada")
    v = db.scalar(select(Visita).where(Visita.edificio_id == ed.id, Visita.patente != "", Visita.patente == valor,
                                       Visita.estado.in_([EstadoVisita.reservada, EstadoVisita.llego]),
                                       Visita.hasta >= ahora))
    if not v:
        return Decision(False, "Patente no registrada en este edificio", "denegada")
    return _pasar_visita(db, ed, v, ahora)


def _buscar_tag(db: Session, ed: Edificio, valor: str) -> Tag | None:
    return db.scalar(select(Tag).where(Tag.edificio_id == ed.id, Tag.uid == valor))


def _correlacionar(db: Session, ed: Edificio, fuente: str, valor: str, veh: Vehiculo, ahora,
                   direccion, tag: Tag | None = None) -> Decision:
    """Modo sticker_y_patente: cada lectura espera a su par dentro de la ventana, y ambas deben ser del mismo vehículo."""
    punto = "vehicular"
    ventana = timedelta(seconds=ed.ventana_coincidencia_s)
    db.execute(delete(LecturaPendiente).where(LecturaPendiente.edificio_id == ed.id,
                                              LecturaPendiente.creado < ahora - ventana))
    otra = db.scalar(select(LecturaPendiente).where(
        LecturaPendiente.edificio_id == ed.id, LecturaPendiente.punto == punto,
        LecturaPendiente.fuente != fuente, LecturaPendiente.creado >= ahora - ventana)
        .order_by(LecturaPendiente.id.desc()).limit(1))
    if otra is None:
        db.add(LecturaPendiente(edificio_id=ed.id, punto=punto, fuente=fuente, valor=valor,
                                vehiculo_id=veh.id, creado=ahora))
        falta = "la patente" if fuente == "sticker" else "el sticker"
        return Decision(False, f"Esperando {falta}: no llegó dentro de {ed.ventana_coincidencia_s} s", "esperando")
    db.delete(otra)  # cada lectura sirve una sola vez
    if otra.vehiculo_id is None:
        return Decision(False, "La otra lectura no corresponde a un vehículo registrado", "denegada")
    if otra.vehiculo_id != veh.id:
        return Decision(False, "El sticker pertenece a otro vehículo: la patente leída no coincide (posible clonación)", "denegada")
    return _finalizar_vehiculo(db, ed, veh, "Sticker y patente coinciden", direccion, tag=tag)


def _finalizar_vehiculo(db: Session, ed: Edificio, veh: Vehiculo, motivo: str, direccion, tag: Tag | None = None) -> Decision:
    ap = _anti_passback(ed, veh, direccion)
    if ap:
        return ap
    if tag is None and veh.tag_id:
        tag = db.get(Tag, veh.tag_id)
    if tag is not None:
        tag.ultima_lectura = utcnow()
    events.publish(db, ed.id, "acceso.residente", {"unidad_id": veh.unidad_id, "punto": "vehicular", "patente": veh.patente})
    return Decision(True, motivo, "ok")


def _finalizar_tag(db: Session, ed: Edificio, tag: Tag, motivo: str, punto: str, ahora) -> Decision:
    tag.ultima_lectura = ahora
    events.publish(db, ed.id, "acceso.residente", {"unidad_id": tag.unidad_id, "punto": punto})
    return Decision(True, motivo, "ok")


def _anti_passback(ed: Edificio, veh: Vehiculo, direccion: str | None) -> Decision | None:
    """Con anti-passback activo y dirección informada: no se entra dos veces seguidas sin salir."""
    if not ed.anti_passback or direccion not in ("entrada", "salida"):
        return None
    if direccion == "entrada":
        if veh.adentro:
            return Decision(False, "Anti-passback: el vehículo figura adentro (la última pasada fue entrada)", "denegada")
        veh.adentro = True
    else:
        veh.adentro = False
    return None


def _visita_por_qr(db: Session, ed: Edificio, token: str):
    return db.scalar(select(Visita).where(Visita.edificio_id == ed.id, Visita.codigo_qr == token))


def _pasar_visita(db: Session, ed: Edificio, v: Visita, ahora) -> Decision:
    if v.estado in (EstadoVisita.cancelada, EstadoVisita.no_show):
        return Decision(False, f"Reserva {v.estado.value}", "denegada")
    if ahora < v.desde - timedelta(minutes=5) or ahora > v.hasta:
        return Decision(False, "Fuera de horario de la reserva", "denegada")
    if v.usos >= v.usos_max:
        return Decision(False, "QR sin usos disponibles", "denegada")
    v.usos += 1
    if v.estado == EstadoVisita.reservada:
        v.estado, v.llegada_at = EstadoVisita.llego, ahora
        events.publish(db, ed.id, "visita.llego",
                       {"visita_id": v.id, "unidad_id": v.unidad_id, "nombre": v.nombre_visita})
    return Decision(True, "Visita", "ok")
