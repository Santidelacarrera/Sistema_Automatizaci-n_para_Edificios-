"""Motor financiero: prorrata de gastos comunes con pandas."""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import events
from ..models import Cargo, LecturaMedidor, Unidad


CONCEPTO_FONDO = "GC:fondo_reserva:Fondo de Reserva"
PREFIJO_INTERES = "Interés mora"


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
                   gastos: list[dict], fondo_reserva_pct: float = 0) -> dict:
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
    if fondo_reserva_pct > 0:  # aporte al fondo de reserva: % de los gastos ordinarios, por coeficiente
        base_ord = sum(float(g["monto"]) for g in gastos if g.get("tipo", "ordinario") == "ordinario")
        if base_ord > 0:
            fondo = prorratear(df, round(base_ord * fondo_reserva_pct / 100), "coeficiente")
            for uid, c in fondo.items():
                if c:
                    db.add(Cargo(edificio_id=edificio_id, unidad_id=int(uid), periodo=periodo,
                                 concepto=CONCEPTO_FONDO, monto=c, saldo=c, vencimiento=vencimiento))
            total_unidad += fondo
    db.flush()
    events.publish(db, edificio_id, "gastos.generados", {"periodo": periodo})
    return {"periodo": periodo, "total": float(total_unidad.sum()), "unidades": len(us)}


def deuda_unidad(db: Session, unidad_id: int) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(Cargo.saldo), 0)).where(Cargo.unidad_id == unidad_id)))


def categoria_cargo(concepto: str) -> str:
    """Agrupa un cargo para el desglose del estado de cuenta."""
    c = concepto.lower()
    if concepto == CONCEPTO_FONDO:
        return "fondo_reserva"
    if concepto.startswith(PREFIJO_INTERES) or c.startswith("multa"):
        return "intereses_multas"
    if c.startswith("gc:"):
        return "agua" if ("agua" in c or "calefac" in c) else "cuota_base"
    return "otros"  # reservas de espacios u otros cargos manuales


def estado_cuenta(db: Session, unidad_id: int) -> dict:
    """Estado de cuenta en tiempo real: al día o moroso, monto exacto y desglose por categoría."""
    hoy = date.today()
    cargos = db.scalars(select(Cargo).where(Cargo.unidad_id == unidad_id, Cargo.saldo > 0)
                        .order_by(Cargo.periodo, Cargo.id)).all()
    desglose = {k: 0.0 for k in ("cuota_base", "agua", "fondo_reserva", "intereses_multas", "otros")}
    vencida = 0.0
    for c in cargos:
        desglose[categoria_cargo(c.concepto)] += float(c.saldo)
        if c.vencimiento and c.vencimiento < hoy:
            vencida += float(c.saldo)
    return {"estado": "moroso" if vencida > 0 else "al_dia", "deuda": round(sum(desglose.values()), 2),
            "vencida": round(vencida, 2), "desglose": {k: round(v, 2) for k, v in desglose.items()},
            "cargos": [{"id": c.id, "periodo": c.periodo, "concepto": c.concepto.split(":")[-1],
                        "saldo": float(c.saldo),
                        "vencimiento": c.vencimiento.isoformat() if c.vencimiento else None} for c in cargos]}


def aplicar_intereses(db: Session, edificio_id: str, periodo: str, tasa_mensual_pct: float,
                      hoy: date | None = None) -> dict:
    """Interés simple mensual sobre el capital vencido (excluye intereses y multas previos).
    Idempotente: una unidad recibe como máximo un cargo ``Interés mora <periodo>``."""
    hoy = hoy or date.today()
    concepto = f"{PREFIJO_INTERES} {periodo}"
    filas = db.execute(
        select(Cargo.unidad_id, func.sum(Cargo.saldo)).where(
            Cargo.edificio_id == edificio_id, Cargo.saldo > 0, Cargo.vencimiento < hoy,
            ~Cargo.concepto.like(f"{PREFIJO_INTERES}%"), ~Cargo.concepto.like("Multa%"))
        .group_by(Cargo.unidad_id)).all()
    generados, omitidos, total = 0, 0, 0.0
    for uid, capital in filas:
        if db.scalar(select(Cargo.id).where(Cargo.unidad_id == uid, Cargo.concepto == concepto)):
            omitidos += 1
            continue
        interes = _redondear(float(capital) * tasa_mensual_pct / 100)
        if interes <= 0:
            continue
        db.add(Cargo(edificio_id=edificio_id, unidad_id=uid, periodo=periodo, concepto=concepto,
                     monto=interes, saldo=interes, vencimiento=hoy + timedelta(days=30)))
        generados += 1
        total += interes
    db.flush()
    return {"periodo": periodo, "unidades": generados, "ya_aplicados": omitidos, "total": total}
