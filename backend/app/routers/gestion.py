"""Gestión de edificios, reversas, exportaciones y configuración de automatizaciones."""
import csv
import io
import secrets
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import hoy_local
from ..db import get_db
from ..models import AplicacionPago, Cargo, Edificio, Encomienda, Evento, Pago, Residente, Rol, Unidad
from ..operation_schemas import AutomatizacionIn, EdificioIn, EdificioPatch, ReversaIn
from ..operations_models import AutomatizacionConfig, Incidencia, OrdenTrabajo
from ..security import Principal, hash_clave_dispositivo, require_roles
from ..services.automation import ejecutar
from .operaciones import Admin, User, auditar, edificio, ficha, recurso

router = APIRouter(tags=["gestion"])
Global = Annotated[Principal, Depends(require_roles(Rol.superadmin))]


@router.post("/edificios", status_code=201)
def crear(ed: EdificioIn, user: Global, db: Session = Depends(get_db)):
    if db.get(Edificio, ed.id):
        raise HTTPException(409, "Identificador de edificio ya existe")
    e = Edificio(**ed.model_dump(), device_api_key=hash_clave_dispositivo(secrets.token_urlsafe(32)))
    db.add(e)
    db.flush()
    auditar(db, user, e.id, "edificio.creado", e.id)
    db.commit()
    return {"id": e.id, "nombre": e.nombre, "activo": e.activo}


@router.patch("/edificios/{edificio_id}")
def editar(edificio_id: str, body: EdificioPatch, user: Global, db: Session = Depends(get_db)):
    e = edificio(db, user, edificio_id, True)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(e, k, v)
    auditar(db, user, edificio_id, "edificio.configurado", e.id, cambios=body.model_dump(exclude_none=True))
    db.commit()
    return {"id": e.id, "nombre": e.nombre, "activo": e.activo}


@router.post("/auth/logout")
def logout(user: User, db: Session = Depends(get_db)):
    # Revoca todas las sesiones de este usuario, incluidas las anteriores al cambio de contraseña.
    r = db.scalar(select(Residente).where(Residente.id == user.residente_id).with_for_update())
    r.session_version += 1
    db.commit()
    return {"revocadas": True}


@router.get("/edificios/{edificio_id}/pagos")
def pagos(edificio_id: str, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    if user.rol == Rol.conserje:
        raise HTTPException(403, "Permisos insuficientes")
    q = select(Pago).where(Pago.edificio_id == edificio_id, Pago.duplicado_de_id.is_(None))
    if user.rol == Rol.residente:
        q = q.where(Pago.unidad_id == db.get(Residente, user.residente_id).unidad_id)
    return [ficha(p, "id unidad_id monto fecha referencia ref_banco conciliado excedente revertido")
            for p in db.scalars(q.order_by(Pago.id.desc()).limit(200))]


@router.post("/edificios/{edificio_id}/pagos/{pago_id}/revertir")
def revertir(edificio_id: str, pago_id: int, body: ReversaIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    p = recurso(db, Pago, edificio_id, pago_id)
    if p.revertido or p.duplicado_de_id or not p.conciliado or not p.unidad_id:
        raise HTTPException(409, "El pago no admite reversa")
    aplicaciones = db.scalars(select(AplicacionPago).where(AplicacionPago.pago_id == p.id)).all()
    suma = sum((Decimal(str(a.monto)) for a in aplicaciones), Decimal("0")) + Decimal(str(p.excedente))
    if suma != p.monto:
        raise HTTPException(409, "Pago histórico sin desglose completo; requiere conciliación manual")
    u = recurso(db, Unidad, edificio_id, p.unidad_id)
    if u.saldo_favor < p.excedente:
        raise HTTPException(409, "El saldo a favor fue utilizado; requiere conciliación manual")
    for a in aplicaciones:
        c = recurso(db, Cargo, edificio_id, a.cargo_id)
        if c.saldo + a.monto > c.monto:
            raise HTTPException(409, "El cargo tiene ajustes posteriores; requiere conciliación manual")
        c.saldo += a.monto
    u.saldo_favor -= p.excedente
    p.revertido = True
    auditar(db, user, edificio_id, "pago.revertido", p.id, motivo=body.motivo)
    db.commit()
    return {"id": p.id, "revertido": True}


@router.get("/edificios/{edificio_id}/dashboard")
def dashboard(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    inicio = hoy_local().replace(day=1)
    def count(model, *where):
        return db.scalar(select(func.count(model.id)).where(model.edificio_id == edificio_id, *where))
    def suma(col, *where):
        return float(db.scalar(select(func.coalesce(func.sum(col), 0)).where(col.class_.edificio_id == edificio_id, *where)))
    unidades = count(Unidad)
    ocupadas = db.scalar(select(func.count(func.distinct(Residente.unidad_id))).where(
        Residente.edificio_id == edificio_id, Residente.activo.is_(True)))
    return {"unidades": unidades, "residentes": count(Residente, Residente.activo.is_(True)),
            "ocupacion_pct": round(100 * ocupadas / unidades, 1) if unidades else 0,
            "ingresos_mes": suma(Pago.monto, Pago.fecha >= inicio, Pago.conciliado.is_(True),
                                  Pago.revertido.is_(False), Pago.duplicado_de_id.is_(None)),
            "deuda": suma(Cargo.saldo), "saldo_favor": suma(Unidad.saldo_favor),
            "deuda_vencida": suma(Cargo.saldo, Cargo.vencimiento < hoy_local()),
            "incidencias_abiertas": count(Incidencia, Incidencia.estado.not_in(["resuelta", "cerrada"])),
            "incidencias_criticas": count(Incidencia, Incidencia.prioridad == "critica", Incidencia.estado.not_in(["resuelta", "cerrada"])),
            "ordenes_pendientes": count(OrdenTrabajo, OrdenTrabajo.estado == "pendiente"),
            "encomiendas_pendientes": count(Encomienda, Encomienda.estado == "pendiente")}


@router.get("/edificios/{edificio_id}/auditoria")
def auditoria(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    return [ficha(e, "id tipo payload creado") for e in db.scalars(select(Evento).where(
        Evento.edificio_id == edificio_id).order_by(Evento.id.desc()).limit(200))]


@router.get("/edificios/{edificio_id}/finanzas/exportar.csv")
def exportar(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["tipo", "id", "unidad_id", "fecha_periodo", "concepto", "monto", "saldo", "estado"])
    def seguro(valor):
        valor = str(valor)
        return "'" + valor if valor.lstrip().startswith(("=", "+", "-", "@")) else valor
    for c in db.scalars(select(Cargo).where(Cargo.edificio_id == edificio_id).order_by(Cargo.id)):
        writer.writerow(["cargo", c.id, c.unidad_id, c.periodo, seguro(c.concepto), c.monto, c.saldo, ""])
    for p in db.scalars(select(Pago).where(Pago.edificio_id == edificio_id, Pago.duplicado_de_id.is_(None)).order_by(Pago.id)):
        writer.writerow(["pago", p.id, p.unidad_id, p.fecha, seguro(p.referencia), p.monto, p.excedente,
                         "revertido" if p.revertido else "conciliado" if p.conciliado else "pendiente"])
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="movimientos.csv"'})


@router.get("/edificios/{edificio_id}/automatizaciones")
def config_automatizaciones(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    cfg = db.get(AutomatizacionConfig, edificio_id)
    return ficha(cfg, "activa recordatorios_pago contratos_dias max_notificaciones") if cfg else AutomatizacionIn().model_dump()


@router.put("/edificios/{edificio_id}/automatizaciones")
def guardar_automatizaciones(edificio_id: str, body: AutomatizacionIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    cfg = db.get(AutomatizacionConfig, edificio_id)
    if not cfg:
        cfg = AutomatizacionConfig(edificio_id=edificio_id)
        db.add(cfg)
    for k, v in body.model_dump().items():
        setattr(cfg, k, v)
    auditar(db, user, edificio_id, "automatizacion.configurada", edificio_id, **body.model_dump())
    db.commit()
    return body.model_dump()


@router.post("/edificios/{edificio_id}/automatizaciones/ejecutar")
def ejecutar_automatizaciones(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    result = ejecutar(db, edificio_id)
    auditar(db, user, edificio_id, "automatizacion.manual", edificio_id)
    db.commit()
    return result
