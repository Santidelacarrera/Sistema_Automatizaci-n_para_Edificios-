"""Conciliación bancaria automática: match por RUT o código de cobro (regex)."""
import io
import re
from datetime import date, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events
from ..models import Cargo, Pago, Residente, Unidad
from .finance import deuda_unidad

RE_CODIGO = re.compile(r"\bCC[-\s]([A-Z0-9]+)[-\s]([A-Z0-9]+)\b", re.I)
RE_RUT = re.compile(r"\b(\d{1,2})\.?(\d{3})\.?(\d{3})-?([\dkK])\b")


def normalizar_rut(s: str) -> str:
    return re.sub(r"[.\-\s]", "", s).upper()


def leer_cartola(contenido: bytes | str) -> list[dict]:
    """CSV con columnas: fecha, descripcion, monto, id (opcional). Sólo abonos (>0)."""
    if isinstance(contenido, bytes):
        contenido = contenido.decode("utf-8-sig")
    df = pd.read_csv(io.StringIO(contenido), dtype=str).rename(columns=str.lower)
    for col in ("fecha", "descripcion", "monto"):
        if col not in df.columns:
            raise ValueError(f"Cartola sin columna '{col}'")
    movs = []
    for i, r in df.iterrows():
        monto = float(str(r["monto"]).replace(".", "").replace(",", ".")) if "," in str(r["monto"]) \
            else float(r["monto"])
        if monto <= 0:
            continue
        movs.append({"fecha": pd.to_datetime(r["fecha"], dayfirst=True).date(),
                     "descripcion": str(r["descripcion"]), "monto": monto,
                     "id": str(r.get("id") if "id" in df.columns and pd.notna(r.get("id")) else f"{r['fecha']}|{r['descripcion']}|{monto}|{i}")})
    return movs


def _buscar_unidad(db: Session, edificio_id: str, texto: str) -> Unidad | None:
    for m in RE_CODIGO.finditer(texto):
        u = db.scalar(select(Unidad).where(Unidad.edificio_id == edificio_id,
                                           Unidad.codigo_cobro == re.sub(r"\s", "-", m.group(0)).upper()))
        if u:
            return u
    for m in RE_RUT.finditer(texto):
        rut = normalizar_rut(m.group(0))
        for r in db.scalars(select(Residente).where(Residente.edificio_id == edificio_id)):
            if normalizar_rut(r.rut) == rut:
                return r.unidad
    return None


def _aplicar(db: Session, unidad_id: int, monto: float) -> float:
    """Abona a los cargos más antiguos primero. Devuelve el excedente (saldo a favor)."""
    cargos = db.scalars(select(Cargo).where(Cargo.unidad_id == unidad_id, Cargo.saldo > 0)
                        .order_by(Cargo.periodo, Cargo.id)).all()
    resto = monto
    for c in cargos:
        if resto <= 0:
            break
        abono = min(float(c.saldo), resto)
        c.saldo = float(c.saldo) - abono
        resto -= abono
    return round(resto, 2)


def conciliar(db: Session, edificio_id: str, movimientos: list[dict]) -> dict:
    res = {"conciliados": [], "sin_match": [], "duplicados": 0}
    for m in movimientos:
        if db.scalar(select(Pago.id).where(Pago.edificio_id == edificio_id, Pago.ref_banco == m["id"])):
            res["duplicados"] += 1  # idempotente: la misma cartola dos veces no duplica abonos
            continue
        u = _buscar_unidad(db, edificio_id, m["descripcion"])
        pago = Pago(edificio_id=edificio_id, unidad_id=u.id if u else None, monto=m["monto"],
                    fecha=m["fecha"] if isinstance(m["fecha"], date) else datetime.fromisoformat(str(m["fecha"])).date(),
                    referencia=m["descripcion"][:200], ref_banco=m["id"], conciliado=bool(u))
        db.add(pago)
        if u:
            excedente = _aplicar(db, u.id, m["monto"])
            res["conciliados"].append({"id": m["id"], "unidad": u.numero, "monto": m["monto"], "excedente": excedente})
            events.publish(db, edificio_id, "pago.conciliado",
                           {"unidad_id": u.id, "monto": m["monto"], "deuda": deuda_unidad(db, u.id)})
        else:
            res["sin_match"].append({"id": m["id"], "descripcion": m["descripcion"], "monto": m["monto"]})
    db.flush()
    return res
