"""Motor de reglas dinámico: normativa por comunidad evaluada ANTES de ejecutar una acción.

Tipos de regla (params en JSON):
  horario            {"desde": "10:00", "hasta": "22:00", "dias": [0..6]}   (0=lunes)
  max_por_mes        {"max": 2}                       por unidad, requiere ctx["usos_mes"]
  bloquear_morosos   {"deuda_max": 0}                 requiere ctx["deuda"]
  anticipacion       {"min_horas": 24, "max_dias": 30}
  multa_cancelacion  {"horas": 24, "monto": 15000}    no bloquea, sólo informa multa
"""
from dataclasses import dataclass, field
from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import utcnow
from .models import Regla


@dataclass
class Decision:
    permitido: bool = True
    motivos: list[str] = field(default_factory=list)
    multa: float = 0.0


def _t(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _horario(p, ctx):
    ini, fin = ctx["inicio"], ctx.get("fin", ctx["inicio"])
    if "dias" in p and ini.weekday() not in p["dias"]:
        return "Día no permitido para esta acción"
    if not (_t(p["desde"]) <= ini.time() and fin.time() <= _t(p["hasta"]) and ini.date() == fin.date()):
        return f"Horario permitido: {p['desde']}–{p['hasta']}"


def _max_por_mes(p, ctx):
    if ctx.get("usos_mes", 0) >= p["max"]:
        return f"Máximo {p['max']} por mes alcanzado"


def _bloquear_morosos(p, ctx):
    if ctx.get("deuda", 0) > p.get("deuda_max", 0):
        return "Unidad con deuda pendiente"


def _anticipacion(p, ctx):
    horas = (ctx["inicio"] - ctx.get("ahora", utcnow())).total_seconds() / 3600
    if "min_horas" in p and horas < p["min_horas"]:
        return f"Requiere al menos {p['min_horas']} h de anticipación"
    if "max_dias" in p and horas > p["max_dias"] * 24:
        return f"Máximo {p['max_dias']} días de anticipación"


_EVALUADORES = {"horario": _horario, "max_por_mes": _max_por_mes,
                "bloquear_morosos": _bloquear_morosos, "anticipacion": _anticipacion}


def evaluar(db: Session, edificio_id: str, accion: str, ctx: dict) -> Decision:
    reglas = db.scalars(select(Regla).where(
        Regla.edificio_id == edificio_id, Regla.accion == accion, Regla.activa.is_(True))).all()
    d = Decision()
    for r in reglas:
        if r.tipo == "multa_cancelacion":
            if ctx.get("cancelando") and "inicio" in ctx:
                horas = (ctx["inicio"] - ctx.get("ahora", utcnow())).total_seconds() / 3600
                if horas < r.params.get("horas", 0):
                    d.multa += float(r.params.get("monto", 0))
            continue
        fn = _EVALUADORES.get(r.tipo)
        if fn is None:  # regla desconocida: fallar cerrado
            d.permitido = False
            d.motivos.append(f"Regla desconocida: {r.tipo}")
            continue
        msg = fn(r.params, ctx)
        if msg:
            d.permitido = False
            d.motivos.append(msg)
    return d
