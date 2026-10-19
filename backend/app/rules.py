"""Motor de reglas dinámico: normativa por comunidad evaluada ANTES de ejecutar una acción.

Tipos de regla (params en JSON):
  horario            {"desde": "10:00", "hasta": "22:00", "dias": [0..6]}   (0=lunes)
  max_por_mes        {"max": 2}                       por unidad, requiere ctx["usos_mes"]
  bloquear_morosos   {"deuda_max": 0}                 requiere ctx["deuda"]
  anticipacion       {"min_horas": 24, "max_dias": 30}
  multa_cancelacion  {"horas": 24, "monto": 15000}    no bloquea, sólo informa multa
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import utcnow
from .models import EspacioComun, Regla


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


# ---------- validación al crear o editar (la evaluación de arriba asume datos válidos) ----------
TIPOS = {"horario": {"desde", "hasta", "dias"}, "max_por_mes": {"max"}, "bloquear_morosos": {"deuda_max"},
         "anticipacion": {"min_horas", "max_dias"}, "multa_cancelacion": {"horas", "monto"}}
_RE_HORA = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def _entero(v, lo: int, hi: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validar_params(tipo: str, p: dict) -> list[str]:
    """Errores legibles de los parámetros de una regla. Lista vacía = válidos."""
    if tipo not in TIPOS:
        return [f"Tipo de regla desconocido: {tipo}"]
    errs = [f"Parámetro no admitido en {tipo}: {k}" for k in p if k not in TIPOS[tipo]]
    if tipo == "horario":
        desde, hasta = p.get("desde"), p.get("hasta")
        if not (isinstance(desde, str) and _RE_HORA.fullmatch(desde) and isinstance(hasta, str) and _RE_HORA.fullmatch(hasta)):
            errs.append("Horario: 'desde' y 'hasta' deben ser horas HH:MM (00:00 a 23:59)")
        elif desde >= hasta:
            errs.append("Horario: 'desde' debe ser anterior a 'hasta' (no se admite cruzar la medianoche)")
        dias = p.get("dias")
        if dias is not None and (not isinstance(dias, list) or not dias or not all(_entero(d, 0, 6) for d in dias)):
            errs.append("Días: lista de 0 (lunes) a 6 (domingo), sin dejarla vacía")
    elif tipo == "max_por_mes" and not _entero(p.get("max"), 1, 31):
        errs.append("Máximo por mes: entero entre 1 y 31")
    elif tipo == "bloquear_morosos" and not (_numero(p.get("deuda_max", 0)) and p.get("deuda_max", 0) >= 0):
        errs.append("Deuda máxima permitida: número mayor o igual a 0")
    elif tipo == "anticipacion":
        if not p:
            errs.append("Anticipación: indica un mínimo de horas, un máximo de días o ambos")
        if "min_horas" in p and not _entero(p["min_horas"], 0, 24 * 365):
            errs.append("Anticipación mínima: entero de horas entre 0 y 8760")
        if "max_dias" in p and not _entero(p["max_dias"], 1, 365):
            errs.append("Anticipación máxima: entero de días entre 1 y 365")
        if _entero(p.get("min_horas"), 0, 8760) and _entero(p.get("max_dias"), 1, 365) \
                and p["min_horas"] > p["max_dias"] * 24:
            errs.append("La anticipación mínima no puede ser mayor que la máxima")
    elif tipo == "multa_cancelacion":
        if not _entero(p.get("horas"), 0, 24 * 90):
            errs.append("Multa por cancelación: horas de aviso como entero entre 0 y 2160")
        if not (_numero(p.get("monto")) and p["monto"] >= 0):
            errs.append("Multa por cancelación: monto mayor o igual a 0")
    return errs


def validar_regla(db: Session, edificio_id: str, accion: str, tipo: str, params: dict,
                  excluir_id: int | None = None) -> list[str]:
    """Valida una regla contra sus parámetros, el espacio al que aplica y las demás reglas del edificio."""
    errs = validar_params(tipo, params)
    if not db.scalar(select(EspacioComun.id).where(EspacioComun.edificio_id == edificio_id,
                                                   EspacioComun.accion == accion)):
        errs.append(f"No hay un espacio común con la acción '{accion}'")
    q = select(Regla.id).where(Regla.edificio_id == edificio_id, Regla.accion == accion, Regla.tipo == tipo)
    if excluir_id is not None:
        q = q.where(Regla.id != excluir_id)
    if db.scalar(q):
        errs.append(f"Ya existe una regla de tipo {tipo} para '{accion}'; edítala en lugar de crear otra")
    return errs
