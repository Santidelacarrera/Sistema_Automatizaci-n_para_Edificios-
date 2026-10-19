"""Endpoints de lectura/gestión que alimentan el panel web."""
from collections import defaultdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import events
from ..config import utcnow
from ..db import get_db
from ..models import (AccesoLog, Cargo, Edificio, EstadoVisita, Pago, Residente, Rol, Tag, Unidad,
                      Vehiculo, Visita)
from ..schemas import PagoIn, RecordatorioIn, VehiculoIn
from ..security import Principal, require_roles, tenant_of
from ..services import access, cobranza, diagnostico as diag, finance

router = APIRouter(prefix="/edificios/{edificio_id}", tags=["panel"])
Staff = Annotated[Principal, Depends(require_roles(Rol.admin, Rol.conserje))]
Admin = Annotated[Principal, Depends(require_roles(Rol.admin))]


def _ed(db: Session, user: Principal, edificio_id: str) -> Edificio:
    tenant_of(user, edificio_id)
    ed = db.get(Edificio, edificio_id)
    if not ed:
        raise HTTPException(404, "Edificio no existe")
    return ed


@router.get("/panel")
def panel(edificio_id: str, user: Staff, db: Session = Depends(get_db)):
    """Fachada: una entrada por unidad con deuda, residentes, vehículos y visitas activas."""
    ed = _ed(db, user, edificio_id)
    ahora = utcnow()
    deuda = dict(db.execute(select(Cargo.unidad_id, func.sum(Cargo.saldo)).where(
        Cargo.edificio_id == ed.id, Cargo.saldo > 0).group_by(Cargo.unidad_id)).all())
    vencida = dict(db.execute(select(Cargo.unidad_id, func.sum(Cargo.saldo)).where(
        Cargo.edificio_id == ed.id, Cargo.saldo > 0, Cargo.vencimiento < date.today())
        .group_by(Cargo.unidad_id)).all())
    res, veh, vis = defaultdict(list), defaultdict(list), defaultdict(int)
    for r in db.scalars(select(Residente).where(Residente.edificio_id == ed.id, Residente.activo.is_(True))):
        res[r.unidad_id].append({"id": r.id, "nombre": r.nombre, "telefono": r.telefono, "email": r.email})
    for v in db.scalars(select(Vehiculo).where(Vehiculo.edificio_id == ed.id, Vehiculo.activo.is_(True))):
        veh[v.unidad_id].append({"id": v.id, "patente": v.patente, "descripcion": v.descripcion,
                                 "sticker": v.tag_id is not None})
    for v in db.scalars(select(Visita).where(
            Visita.edificio_id == ed.id, Visita.hasta >= ahora,
            Visita.estado.in_([EstadoVisita.reservada, EstadoVisita.llego]))):
        vis[v.unidad_id] += 1
    unidades = db.scalars(select(Unidad).where(Unidad.edificio_id == ed.id)).all()
    ocupados = access.cupos_ocupados(db, ed.id, ahora, ahora)
    return {
        "edificio": {"id": ed.id, "nombre": ed.nombre, "cupos_visitas": ed.cupos_visitas,
                     "cupos_ocupados": ocupados},
        "unidades": [{"id": u.id, "numero": u.numero, "estacionamientos": u.estacionamientos,
                      "codigo_cobro": u.codigo_cobro, "deuda": float(deuda.get(u.id, 0)),
                      "vencida": float(vencida.get(u.id, 0)), "residentes": res[u.id],
                      "vehiculos": veh[u.id], "visitas_activas": vis[u.id]} for u in unidades],
    }


@router.get("/diagnostico")
def diagnostico(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    """Canales configurados y advertencias de despliegue. Sólo admin; nunca incluye secretos."""
    _ed(db, user, edificio_id)
    return diag.reporte()


@router.get("/accesos")
def accesos(edificio_id: str, user: Staff, limit: int = 50, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    rows = db.scalars(select(AccesoLog).where(AccesoLog.edificio_id == ed.id)
                      .order_by(AccesoLog.id.desc()).limit(min(limit, 200))).all()
    return [{"id": a.id, "token": a.token, "punto": a.punto, "fuente": a.fuente, "permitido": a.permitido,
             "motivo": a.motivo, "creado": a.creado.isoformat() + "Z"} for a in rows]


@router.get("/visitas")
def visitas(edificio_id: str, user: Staff, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    rows = db.execute(select(Visita, Unidad.numero).join(Unidad, Unidad.id == Visita.unidad_id).where(
        Visita.edificio_id == ed.id, Visita.hasta >= utcnow() - __import__("datetime").timedelta(hours=6))
        .order_by(Visita.desde)).all()
    return [{"id": v.id, "unidad": n, "nombre": v.nombre_visita, "patente": v.patente,
             "desde": v.desde.isoformat() + "Z", "hasta": v.hasta.isoformat() + "Z",
             "estado": v.estado.value, "usa_estacionamiento": v.usa_estacionamiento} for v, n in rows]


@router.post("/vehiculos", status_code=201)
def registrar_vehiculo(edificio_id: str, body: VehiculoIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    try:
        v = access.registrar_vehiculo(db, ed, body.unidad_id, body.patente, body.descripcion, body.tag_id)
    except access.AccesoError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return {"id": v.id, "patente": v.patente}


@router.delete("/vehiculos/{vehiculo_id}")
def baja_vehiculo(edificio_id: str, vehiculo_id: int, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    v = db.get(Vehiculo, vehiculo_id)
    if not v or v.edificio_id != ed.id:
        raise HTTPException(404, "Vehículo no existe")
    v.activo = False
    db.commit()
    return {"ok": True}


@router.get("/cobranza")
def ver_cobranza(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    lista = sorted(cobranza.morosos(db, ed.id), key=lambda m: -m["dias_atraso"])
    return {"morosos": lista, "total": sum(m["deuda"] for m in lista)}


@router.post("/cobranza/recordatorios")
def recordatorios(edificio_id: str, body: RecordatorioIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    return cobranza.enviar_recordatorios(db, ed, body.unidad_ids, body.canales, body.mensaje_extra)


@router.post("/pagos")
def registrar_pago(edificio_id: str, body: PagoIn, user: Admin, db: Session = Depends(get_db)):
    """Entrada para el sistema de pagos ya existente: abona, es idempotente y avisa al residente."""
    ed = _ed(db, user, edificio_id)
    u = db.get(Unidad, body.unidad_id)
    if not u or u.edificio_id != ed.id:
        raise HTTPException(404, "Unidad no existe en este edificio")
    if db.scalar(select(Pago.id).where(Pago.edificio_id == ed.id, Pago.ref_banco == body.ref_externa)):
        return {"duplicado": True}
    from ..services.reconciliation import _aplicar
    excedente = _aplicar(db, u.id, body.monto)
    db.add(Pago(edificio_id=ed.id, unidad_id=u.id, monto=body.monto, fecha=date.today(),
                referencia=body.referencia[:200], ref_banco=body.ref_externa, conciliado=True))
    db.flush()
    events.publish(db, ed.id, "pago.conciliado",
                   {"unidad_id": u.id, "monto": body.monto, "deuda": finance.deuda_unidad(db, u.id)})
    db.commit()
    return {"duplicado": False, "excedente": excedente}
