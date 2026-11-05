"""Vida de comunidad: portal "Mi Depto", comunicados, encomiendas, avisos de pago, disponibilidad de
espacios y enlace de WhatsApp para pases de visita.

Lectura para cualquier usuario del edificio (el residente sólo ve su unidad); escritura según rol:
conserjería registra y entrega encomiendas, el administrador publica comunicados y concilia pagos.
"""
from datetime import date, datetime, timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import events
from ..config import utcnow
from ..db import get_db
from ..models import (AvisoPago, Cargo, Comunicado, Edificio, Encomienda, EspacioComun, EstadoVisita, Pago,
                      Regla, ReservaEspacio, Residente, Rol, Tag, Unidad, Vehiculo, Visita)
from ..schemas import (AvisoPagoIn, ComunicadoIn, ComunicadoPatch, EncomiendaIn, EntregaIn, EspacioPatch,
                       InteresesIn, ResolverAvisoIn)
from ..security import Principal, current_user, require_roles, tenant_of
from ..services import finance
from ..services.reconciliation import _aplicar, pago_de_cartola_para

router = APIRouter(prefix="/edificios/{edificio_id}", tags=["comunidad"])
User = Annotated[Principal, Depends(current_user)]
Staff = Annotated[Principal, Depends(require_roles(Rol.admin, Rol.conserje))]
Admin = Annotated[Principal, Depends(require_roles(Rol.admin))]


def _ed(db: Session, user: Principal, edificio_id: str) -> Edificio:
    tenant_of(user, edificio_id)
    ed = db.get(Edificio, edificio_id)
    if not ed:
        raise HTTPException(404, "Edificio no existe")
    return ed


def _unidad(db: Session, user: Principal, ed: Edificio, unidad_id: int | None) -> Unidad:
    """Residente: sólo su unidad. Admin/conserje/superadmin: cualquiera del edificio."""
    yo = db.get(Residente, user.residente_id)
    if user.rol == Rol.residente:
        if unidad_id not in (None, yo.unidad_id):
            raise HTTPException(403, "Sólo puede operar sobre su unidad")
        unidad_id = yo.unidad_id
    if unidad_id is None:
        unidad_id = yo.unidad_id if yo and yo.edificio_id == ed.id else None
    if unidad_id is None:
        raise HTTPException(422, "unidad_id requerido")
    u = db.get(Unidad, unidad_id)
    if not u or u.edificio_id != ed.id:
        raise HTTPException(404, "Unidad no existe en este edificio")
    return u


def _z(d: datetime | None) -> str | None:
    return d.isoformat() + "Z" if d else None


# ---------------------------------------------------------------- comunicados (muro)
def _com(c: Comunicado) -> dict:
    return {"id": c.id, "titulo": c.titulo, "cuerpo": c.cuerpo, "categoria": c.categoria, "fijado": c.fijado,
            "publicado_at": _z(c.publicado_at), "vigente_hasta": _z(c.vigente_hasta)}


@router.get("/comunicados")
def listar_comunicados(edificio_id: str, user: User, todos: bool = False, db: Session = Depends(get_db)):
    """Muro: los fijados primero y luego los más recientes. Los vencidos sólo los ve el admin con ?todos=true."""
    ed = _ed(db, user, edificio_id)
    q = select(Comunicado).where(Comunicado.edificio_id == ed.id)
    if not (todos and user.rol in (Rol.admin, Rol.superadmin)):
        q = q.where(or_(Comunicado.vigente_hasta.is_(None), Comunicado.vigente_hasta >= utcnow()))
    return [_com(c) for c in db.scalars(q.order_by(Comunicado.fijado.desc(), Comunicado.publicado_at.desc(),
                                                   Comunicado.id.desc()).limit(100))]


@router.post("/comunicados", status_code=201)
def publicar_comunicado(edificio_id: str, body: ComunicadoIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    c = Comunicado(edificio_id=ed.id, autor_id=user.residente_id, **body.model_dump())
    db.add(c)
    db.flush()
    events.publish(db, ed.id, "comunicado.publicado", {"comunicado_id": c.id, "titulo": c.titulo})
    db.commit()
    return {"id": c.id}


@router.patch("/comunicados/{comunicado_id}")
def editar_comunicado(edificio_id: str, comunicado_id: int, body: ComunicadoPatch, user: Admin,
                      db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    c = db.get(Comunicado, comunicado_id)
    if not c or c.edificio_id != ed.id:
        raise HTTPException(404, "Comunicado no existe")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is None and k != "vigente_hasta":
            continue
        setattr(c, k, v)
    db.commit()
    return _com(c)


@router.delete("/comunicados/{comunicado_id}")
def retirar_comunicado(edificio_id: str, comunicado_id: int, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    c = db.get(Comunicado, comunicado_id)
    if not c or c.edificio_id != ed.id:
        raise HTTPException(404, "Comunicado no existe")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- encomiendas
def _enc(e: Encomienda, unidad: str) -> dict:
    return {"id": e.id, "unidad_id": e.unidad_id, "unidad": unidad, "transportista": e.transportista,
            "remitente": e.remitente, "descripcion": e.descripcion, "estado": e.estado,
            "recibida_at": _z(e.recibida_at), "entregada_at": _z(e.entregada_at), "retirada_por": e.retirada_por}


@router.post("/encomiendas", status_code=201)
def recibir_encomienda(edificio_id: str, body: EncomiendaIn, user: Staff, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    u = db.get(Unidad, body.unidad_id)
    if not u or u.edificio_id != ed.id:
        raise HTTPException(404, "Unidad no existe en este edificio")
    e = Encomienda(edificio_id=ed.id, unidad_id=u.id, recibida_por_id=user.residente_id,
                   **body.model_dump(exclude={"unidad_id"}))
    db.add(e)
    db.flush()
    events.publish(db, ed.id, "encomienda.recibida",
                   {"encomienda_id": e.id, "unidad_id": u.id, "transportista": e.transportista})
    db.commit()
    return {"id": e.id}


@router.get("/encomiendas")
def listar_encomiendas(edificio_id: str, user: User, estado: str | None = None, unidad_id: int | None = None,
                       limit: int = 100, db: Session = Depends(get_db)):
    """Conserjería ve todas; el residente sólo las de su unidad (aunque pida otra, recibe 403)."""
    ed = _ed(db, user, edificio_id)
    q = select(Encomienda, Unidad.numero).join(Unidad, Unidad.id == Encomienda.unidad_id).where(
        Encomienda.edificio_id == ed.id)
    if user.rol == Rol.residente:
        q = q.where(Encomienda.unidad_id == _unidad(db, user, ed, unidad_id).id)
    elif unidad_id:
        q = q.where(Encomienda.unidad_id == unidad_id)
    if estado in ("pendiente", "entregada"):
        q = q.where(Encomienda.estado == estado)
    rows = db.execute(q.order_by(Encomienda.estado.desc(), Encomienda.recibida_at.desc())
                      .limit(min(limit, 300))).all()
    return [_enc(e, n) for e, n in rows]


@router.post("/encomiendas/{encomienda_id}/entregar")
def entregar_encomienda(edificio_id: str, encomienda_id: int, body: EntregaIn, user: Staff,
                        db: Session = Depends(get_db)):
    """Registra fecha y hora exactas del retiro y quién firma. No se puede entregar dos veces."""
    ed = _ed(db, user, edificio_id)
    e = db.get(Encomienda, encomienda_id)
    if not e or e.edificio_id != ed.id:
        raise HTTPException(404, "Encomienda no existe")
    if e.estado == "entregada":
        raise HTTPException(409, "La encomienda ya fue entregada")
    e.estado, e.entregada_at, e.entregada_por_id = "entregada", utcnow(), user.residente_id
    e.retirada_por = body.retirada_por.strip()
    events.publish(db, ed.id, "encomienda.entregada", {"encomienda_id": e.id, "unidad_id": e.unidad_id})
    db.commit()
    return {"id": e.id, "estado": e.estado, "entregada_at": _z(e.entregada_at)}


# ---------------------------------------------------------------- avisos de pago por transferencia
def _aviso(a: AvisoPago, unidad: str) -> dict:
    return {"id": a.id, "unidad_id": a.unidad_id, "unidad": unidad, "monto": float(a.monto), "banco": a.banco,
            "nro_operacion": a.nro_operacion, "fecha_transferencia": a.fecha_transferencia.isoformat(),
            "estado": a.estado, "creado": _z(a.creado), "resuelto_at": _z(a.resuelto_at), "motivo": a.motivo}


@router.post("/avisos-pago", status_code=201)
def avisar_pago(edificio_id: str, body: AvisoPagoIn, user: User, db: Session = Depends(get_db)):
    """El residente informa banco y número de operación; el administrador lo concilia."""
    ed = _ed(db, user, edificio_id)
    u = _unidad(db, user, ed, body.unidad_id)
    if body.fecha_transferencia > date.today():
        raise HTTPException(422, "La fecha de la transferencia no puede ser futura")
    a = AvisoPago(edificio_id=ed.id, unidad_id=u.id, residente_id=user.residente_id, monto=body.monto,
                  banco=body.banco.strip(), nro_operacion=body.nro_operacion.strip(),
                  fecha_transferencia=body.fecha_transferencia)
    db.add(a)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ese número de operación ya fue informado para ese banco")
    return {"id": a.id, "estado": a.estado}


@router.get("/avisos-pago")
def listar_avisos(edificio_id: str, user: User, estado: str | None = None, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    q = select(AvisoPago, Unidad.numero).join(Unidad, Unidad.id == AvisoPago.unidad_id).where(
        AvisoPago.edificio_id == ed.id)
    if user.rol == Rol.conserje:
        raise HTTPException(403, "Permisos insuficientes")
    if user.rol == Rol.residente:
        q = q.where(AvisoPago.unidad_id == _unidad(db, user, ed, None).id)
    if estado in ("pendiente", "aprobado", "rechazado"):
        q = q.where(AvisoPago.estado == estado)
    return [_aviso(a, n) for a, n in db.execute(q.order_by(AvisoPago.id.desc()).limit(200)).all()]


@router.post("/avisos-pago/{aviso_id}/resolver")
def resolver_aviso(edificio_id: str, aviso_id: int, body: ResolverAvisoIn, user: Admin,
                   db: Session = Depends(get_db)):
    """Aprobar abona el monto a los cargos más antiguos (idempotente por aviso) y avisa al residente."""
    ed = _ed(db, user, edificio_id)
    a = db.get(AvisoPago, aviso_id)
    if not a or a.edificio_id != ed.id:
        raise HTTPException(404, "Aviso no existe")
    if a.estado != "pendiente":
        raise HTTPException(409, f"El aviso ya fue {a.estado}")
    if not body.aprobar and not body.motivo.strip():
        raise HTTPException(422, "Indica el motivo del rechazo")
    a.resuelto_at, a.motivo = utcnow(), body.motivo.strip()
    excedente, ya_conciliado = 0.0, False
    if body.aprobar:
        ref = f"aviso:{a.id}"
        if pago_de_cartola_para(db, ed.id, a.unidad_id, a.nro_operacion, float(a.monto)):
            ya_conciliado = True  # la cartola ya abonó este pago: aprobar el aviso no vuelve a abonar
        elif not db.scalar(select(Pago.id).where(Pago.edificio_id == ed.id, Pago.ref_banco == ref)):
            excedente = _aplicar(db, a.unidad_id, float(a.monto))
            db.add(Pago(edificio_id=ed.id, unidad_id=a.unidad_id, monto=a.monto, fecha=a.fecha_transferencia,
                        referencia=f"Transferencia {a.banco} op. {a.nro_operacion}"[:200], ref_banco=ref,
                        conciliado=True))
            db.flush()
            events.publish(db, ed.id, "pago.conciliado", {"unidad_id": a.unidad_id, "monto": float(a.monto),
                                                           "deuda": finance.deuda_unidad(db, a.unidad_id)})
        a.estado = "aprobado"
    else:
        a.estado = "rechazado"
    db.commit()
    return {"id": a.id, "estado": a.estado, "excedente": excedente, "ya_conciliado": ya_conciliado}


# ---------------------------------------------------------------- portal "Mi Depto"
@router.get("/mi-depto")
def mi_depto(edificio_id: str, user: User, unidad_id: int | None = None, db: Session = Depends(get_db)):
    """Todo lo que el residente consulta en una pantalla: cuenta, vehículos y tags, paquetes y avisos."""
    ed = _ed(db, user, edificio_id)
    u = _unidad(db, user, ed, unidad_id)
    ahora = utcnow()
    veh = db.scalars(select(Vehiculo).where(Vehiculo.unidad_id == u.id, Vehiculo.activo.is_(True))).all()
    tags_unidad = db.scalars(select(Tag).where(Tag.unidad_id == u.id)).all()
    patente_de_tag = {v.tag_id: v.patente for v in veh if v.tag_id}
    pend = db.execute(select(Encomienda).where(Encomienda.unidad_id == u.id, Encomienda.estado == "pendiente")
                      .order_by(Encomienda.recibida_at)).scalars().all()
    visitas = db.scalars(select(Visita).where(
        Visita.unidad_id == u.id, Visita.hasta >= ahora,
        Visita.estado.in_([EstadoVisita.reservada, EstadoVisita.llego])).order_by(Visita.desde)).all()
    avisos = db.execute(select(AvisoPago).where(AvisoPago.unidad_id == u.id)
                        .order_by(AvisoPago.id.desc()).limit(5)).scalars().all()
    return {
        "unidad": {"id": u.id, "numero": u.numero, "codigo_cobro": u.codigo_cobro,
                   "estacionamientos": u.estacionamientos},
        "cuenta": finance.estado_cuenta(db, u.id),
        "vehiculos": [{"id": v.id, "patente": v.patente, "descripcion": v.descripcion,
                       "sticker": v.tag_id is not None} for v in veh],
        "tags": [{"id": t.id, "uid": t.uid, "tipo": t.tipo.value, "estado": t.estado,
                  "patente": patente_de_tag.get(t.id, "")} for t in tags_unidad],
        "encomiendas_pendientes": [_enc(e, u.numero) for e in pend],
        "visitas_activas": [{"id": v.id, "nombre": v.nombre_visita, "patente": v.patente,
                             "desde": _z(v.desde), "hasta": _z(v.hasta), "estado": v.estado.value} for v in visitas],
        "avisos_pago": [_aviso(a, u.numero) for a in avisos],
        "comunicados": listar_comunicados(edificio_id, user, False, db)[:5],
    }


# ---------------------------------------------------------------- pase de visita por WhatsApp
@router.get("/visitas/{visita_id}/whatsapp")
def compartir_visita(edificio_id: str, visita_id: int, user: User, telefono: str = "",
                     db: Session = Depends(get_db)):
    """Mensaje listo y enlace wa.me para enviar el pase a la visita con un clic."""
    ed = _ed(db, user, edificio_id)
    v = db.get(Visita, visita_id)
    if not v or v.edificio_id != ed.id:
        raise HTTPException(404, "Visita no existe")
    _unidad(db, user, ed, v.unidad_id)
    unidad = db.get(Unidad, v.unidad_id)
    fin = f"{v.hasta:%d-%m-%Y %H:%M}"
    texto = (f"Hola {v.nombre_visita.split()[0]}, te invito al depto {unidad.numero} de {ed.nombre}. "
             f"Tu pase es válido del {v.desde:%d-%m-%Y %H:%M} al {fin}. "
             + (f"Patente registrada: {v.patente}. " if v.patente else "")
             + f"Muestra este código en la entrada: {v.codigo_qr}")
    digitos = "".join(ch for ch in telefono if ch.isdigit())
    base = f"https://wa.me/{digitos}" if digitos else "https://wa.me/"
    return {"mensaje": texto, "url": f"{base}?text={quote(texto)}", "codigo_qr": v.codigo_qr}


# ---------------------------------------------------------------- espacios: aforo y disponibilidad
@router.get("/espacios-comunes")
def espacios_comunes(edificio_id: str, user: User, db: Session = Depends(get_db)):
    """Espacios con su tarifa, aforo y horario permitido; visibles para el residente que reserva."""
    ed = _ed(db, user, edificio_id)
    horarios = {r.accion: r.params for r in db.scalars(select(Regla).where(
        Regla.edificio_id == ed.id, Regla.tipo == "horario", Regla.activa.is_(True)))}
    return [{"id": e.id, "nombre": e.nombre, "tarifa": float(e.tarifa), "aforo": e.aforo,
             "horario": horarios.get(e.accion)}
            for e in db.scalars(select(EspacioComun).where(EspacioComun.edificio_id == ed.id)
                                .order_by(EspacioComun.nombre))]


@router.get("/espacios-comunes/{espacio_id}/disponibilidad")
def disponibilidad(edificio_id: str, espacio_id: int, fecha: date, user: User, db: Session = Depends(get_db)):
    """Calendario del día: franjas ya reservadas (sin datos del vecino) y horario permitido por reglamento."""
    ed = _ed(db, user, edificio_id)
    e = db.get(EspacioComun, espacio_id)
    if not e or e.edificio_id != ed.id:
        raise HTTPException(404, "Espacio no existe")
    ini = datetime.combine(fecha, datetime.min.time())
    ocupadas = db.scalars(select(ReservaEspacio).where(
        ReservaEspacio.espacio_id == e.id, ReservaEspacio.estado == "confirmada",
        ReservaEspacio.desde < ini + timedelta(days=1), ReservaEspacio.hasta > ini)
        .order_by(ReservaEspacio.desde)).all()
    regla = db.scalar(select(Regla).where(Regla.edificio_id == ed.id, Regla.accion == e.accion,
                                          Regla.tipo == "horario", Regla.activa.is_(True)))
    dias = regla.params.get("dias") if regla else None
    return {"espacio": e.nombre, "fecha": fecha.isoformat(), "aforo": e.aforo, "tarifa": float(e.tarifa),
            "horario": {"desde": regla.params["desde"], "hasta": regla.params["hasta"]} if regla else None,
            "abierto": dias is None or fecha.weekday() in dias,
            "ocupadas": [{"desde": _z(r.desde), "hasta": _z(r.hasta)} for r in ocupadas]}


@router.patch("/espacios/{espacio_id}")
def editar_espacio(edificio_id: str, espacio_id: int, body: EspacioPatch, user: Admin,
                   db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    e = db.get(EspacioComun, espacio_id)
    if not e or e.edificio_id != ed.id:
        raise HTTPException(404, "Espacio no existe")
    if body.tarifa is not None:
        e.tarifa = body.tarifa
    if body.aforo is not None:
        e.aforo = body.aforo
    db.commit()
    return {"id": e.id, "tarifa": float(e.tarifa), "aforo": e.aforo}


# ---------------------------------------------------------------- morosidad: intereses
@router.post("/cobranza/intereses")
def cobrar_intereses(edificio_id: str, body: InteresesIn, user: Admin, db: Session = Depends(get_db)):
    """Carga un interés mensual sobre el capital vencido. Repetirlo para el mismo periodo no duplica."""
    ed = _ed(db, user, edificio_id)
    res = finance.aplicar_intereses(db, ed.id, body.periodo, body.tasa_mensual_pct)
    db.commit()
    return res


@router.get("/finanzas/resumen")
def resumen_finanzas(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    """Indicadores para el administrador y el comité: deuda total, vencida, morosidad y pagos pendientes."""
    ed = _ed(db, user, edificio_id)
    hoy = date.today()
    unidades = db.scalar(select(func.count(Unidad.id)).where(Unidad.edificio_id == ed.id)) or 0
    deuda = float(db.scalar(select(func.coalesce(func.sum(Cargo.saldo), 0)).where(
        Cargo.edificio_id == ed.id, Cargo.saldo > 0)) or 0)
    vencida = float(db.scalar(select(func.coalesce(func.sum(Cargo.saldo), 0)).where(
        Cargo.edificio_id == ed.id, Cargo.saldo > 0, Cargo.vencimiento < hoy)) or 0)
    morosas = db.scalar(select(func.count(func.distinct(Cargo.unidad_id))).where(
        Cargo.edificio_id == ed.id, Cargo.saldo > 0, Cargo.vencimiento < hoy)) or 0
    por_aprobar = db.scalar(select(func.count(AvisoPago.id)).where(
        AvisoPago.edificio_id == ed.id, AvisoPago.estado == "pendiente")) or 0
    return {"unidades": unidades, "unidades_morosas": morosas,
            "morosidad_pct": round(morosas / unidades * 100, 1) if unidades else 0.0,
            "deuda_total": deuda, "deuda_vencida": vencida, "avisos_pago_pendientes": por_aprobar}
