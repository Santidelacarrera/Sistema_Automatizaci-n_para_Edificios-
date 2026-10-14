"""Motor financiero: prorrata de gastos comunes con pandas."""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import events
from ..models import Cargo, LecturaMedidor, Unidad


def _redondear(x: float) -> float:
    return float(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def prorratear(unidades: pd.DataFrame, monto: float, base: str = "coeficiente",
               consumos: pd.Series | None = None) -> pd.Series:
    """Distribuye ``monto`` entre unidades. El residuo del redondeo va a la mayor cuota
    para que la suma sea exactamente ``monto``.

    unidades: índice unidad_id, columna 'coeficiente'.
    base: 'coeficiente' (copropiedad) o 'consumo' (medidores individuales).
    """
    if base == "consumo":
        if consumos is None or float(consumos.sum()) <= 0:
            raise ValueError("Sin consumos para prorratear por medidor")
        pesos = consumos.reindex(unidades.index).fillna(0.0)
    else:
        pesos = unidades["coeficiente"].astype(float)
    total = float(pesos.sum())
    if total <= 0:
        raise ValueError("Pesos de prorrata suman 0")
    cuotas = (pesos / total * monto).map(_redondear)
    diff = _redondear(monto) - float(cuotas.sum())
    if diff:
        cuotas.loc[cuotas.idxmax()] += diff
    return cuotas


def generar_cargos(db: Session, edificio_id: str, periodo: str, vencimiento: date,
                   gastos: list[dict]) -> dict:
    """gastos: [{"concepto","monto","tipo":"ordinario|extraordinario","base":"coeficiente|consumo","servicio":"agua"}]"""
    if db.scalar(select(func.count(Cargo.id)).where(
            Cargo.edificio_id == edificio_id, Cargo.periodo == periodo, Cargo.concepto.like("GC:%"))):
        raise ValueError(f"Ya se generaron gastos comunes para {periodo}")
    us = db.scalars(select(Unidad).where(Unidad.edificio_id == edificio_id)).all()
    if not us:
        raise ValueError("Edificio sin unidades")
    df = pd.DataFrame({"coeficiente": [float(u.coeficiente) for u in us]}, index=[u.id for u in us])
    total_unidad = pd.Series(0.0, index=df.index)
    for g in gastos:
        consumos = None
        if g.get("base") == "consumo":
            rows = db.execute(select(LecturaMedidor.unidad_id, LecturaMedidor.consumo).where(
                LecturaMedidor.edificio_id == edificio_id, LecturaMedidor.periodo == periodo,
                LecturaMedidor.servicio == g.get("servicio", "agua"))).all()
            consumos = pd.Series({r[0]: float(r[1]) for r in rows})
        cuotas = prorratear(df, float(g["monto"]), g.get("base", "coeficiente"), consumos)
        for uid, c in cuotas.items():
            if c:
                db.add(Cargo(edificio_id=edificio_id, unidad_id=int(uid), periodo=periodo,
                             concepto=f"GC:{g['tipo']}:{g['concepto']}", monto=c, saldo=c, vencimiento=vencimiento))
        total_unidad += cuotas
    db.flush()
    events.publish(db, edificio_id, "gastos.generados", {"periodo": periodo})
    return {"periodo": periodo, "total": float(total_unidad.sum()), "unidades": len(us)}


def deuda_unidad(db: Session, unidad_id: int) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(Cargo.saldo), 0)).where(Cargo.unidad_id == unidad_id)))
