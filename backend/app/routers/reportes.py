from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import hoy_local
from ..db import get_db
from ..models import Cargo, Pago, Residente, Rol, Unidad
from ..services.reports import pdf
from .operaciones import User, edificio, recurso

router = APIRouter(prefix="/edificios/{edificio_id}", tags=["reportes"])


def propia(db, user, eid, uid):
    if user.rol == Rol.conserje:
        raise HTTPException(403, "Permisos insuficientes")
    u = recurso(db, Unidad, eid, uid)
    if user.rol == Rol.residente and db.get(Residente, user.residente_id).unidad_id != u.id:
        raise HTTPException(403, "Sólo puede consultar su unidad")
    return u


def archivo(data, nombre):
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre}.pdf"',
                                                                 "Cache-Control": "no-store"})


@router.get("/unidades/{unidad_id}/estado-cuenta.pdf")
def estado_cuenta(edificio_id: str, unidad_id: int, user: User, db: Session = Depends(get_db)):
    ed = edificio(db, user, edificio_id)
    u = propia(db, user, edificio_id, unidad_id)
    cargos = db.scalars(select(Cargo).where(Cargo.edificio_id == edificio_id, Cargo.unidad_id == u.id)
                       .order_by(Cargo.periodo.desc(), Cargo.id.desc()).limit(1000)).all()
    data = pdf("Estado de cuenta", f"{ed.nombre} · Unidad {u.numero} · Emitido {hoy_local()}",
               ["Periodo", "Concepto", "Monto CLP", "Saldo CLP"],
               [[c.periodo, c.concepto, f"{c.monto:,.2f}", f"{c.saldo:,.2f}"] for c in cargos],
               [f"Saldo a favor disponible: CLP {u.saldo_favor:,.2f}",
                "Hasta 1000 cargos recientes. Documento informativo; no constituye factura tributaria."])
    return archivo(data, "estado-cuenta")


@router.get("/pagos/{pago_id}/comprobante.pdf")
def comprobante(edificio_id: str, pago_id: int, user: User, db: Session = Depends(get_db)):
    ed = edificio(db, user, edificio_id)
    p = recurso(db, Pago, edificio_id, pago_id)
    if not p.unidad_id:
        raise HTTPException(409, "Pago pendiente de asignación a unidad")
    u = propia(db, user, edificio_id, p.unidad_id)
    if p.duplicado_de_id:
        raise HTTPException(409, "Consulte el comprobante del pago original")
    data = pdf("Comprobante de registro de pago", f"{ed.nombre} · Unidad {u.numero}", ["Campo", "Valor"],
               [["Número", p.id], ["Fecha", p.fecha], ["Monto CLP", f"{p.monto:,.2f}"],
                ["Referencia", p.referencia or p.ref_banco],
                ["Estado", "Revertido" if p.revertido else "Conciliado" if p.conciliado else "Pendiente"]],
               ["Acredita el registro en la plataforma; no sustituye el comprobante bancario ni una factura tributaria."])
    return archivo(data, "comprobante")


@router.get("/finanzas/resumen.pdf")
def resumen_finanzas_pdf(edificio_id: str, user: User, db: Session = Depends(get_db)):
    """Exportación PDF del resumen financiero del edificio (05.40)."""
    if user.rol not in (Rol.admin, Rol.superadmin):
        raise HTTPException(403, "Solo administración puede exportar el resumen financiero")
    ed = edificio(db, user, edificio_id)
    cargos = db.scalars(select(Cargo).where(Cargo.edificio_id == edificio_id).order_by(Cargo.periodo.desc(), Cargo.id.desc()).limit(500)).all()
    pagos = db.scalars(select(Pago).where(
        Pago.edificio_id == edificio_id, Pago.conciliado.is_(True), Pago.revertido.is_(False), Pago.duplicado_de_id.is_(None),
    )).all()
    total_emitido = sum(float(c.monto) for c in cargos)
    total_pendiente = sum(float(c.saldo) for c in cargos)
    total_recaudado = sum(float(p.monto) for p in pagos)
    filas = [
        ["Cargos emitidos (recientes)", f"CLP {total_emitido:,.2f}"],
        ["Saldo pendiente por cobrar", f"CLP {total_pendiente:,.2f}"],
        ["Pagos conciliados acumulados", f"CLP {total_recaudado:,.2f}"],
    ]
    data = pdf(
        "Resumen Financiero",
        f"{ed.nombre} · Emitido {hoy_local()}",
        ["Indicador", "Monto"],
        filas,
        ["Reporte financiero interno generado por la plataforma."],
    )
    return archivo(data, f"resumen-finanzas-{edificio_id}")
