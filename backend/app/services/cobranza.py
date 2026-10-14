"""Comunicación de cobranza: estado de cuenta y recordatorios por WhatsApp y correo."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Cargo, Edificio, Residente, Unidad
from . import email, whatsapp


def morosos(db: Session, edificio_id: str) -> list[dict]:
    hoy = date.today()
    filas = db.execute(
        select(Unidad.id, Unidad.numero, Unidad.codigo_cobro, func.sum(Cargo.saldo),
               func.min(Cargo.vencimiento), func.sum(Cargo.saldo).filter(Cargo.vencimiento < hoy))
        .join(Cargo, Cargo.unidad_id == Unidad.id)
        .where(Unidad.edificio_id == edificio_id, Cargo.saldo > 0)
        .group_by(Unidad.id)).all()
    return [{"unidad_id": f[0], "numero": f[1], "codigo_cobro": f[2], "deuda": float(f[3]),
             "mas_antiguo": f[4].isoformat() if f[4] else None, "vencido": float(f[5] or 0),
             "dias_atraso": max(0, (hoy - f[4]).days) if f[4] else 0} for f in filas]


def texto_recordatorio(nombre: str, numero: str, deuda: float, codigo: str, extra: str = "") -> str:
    t = (f"Hola {nombre.split()[0]}, el depto {numero} registra un saldo de ${deuda:,.0f} en gastos comunes. "
         f"Para pagar por transferencia indique el código {codigo}.")
    return f"{t} {extra}".strip()


def enviar_recordatorios(db: Session, ed: Edificio, unidad_ids: list[int] | None,
                         canales: list[str], extra: str = "") -> dict:
    res = {"unidades": 0, "whatsapp": 0, "email": 0, "sin_contacto": []}
    for m in morosos(db, ed.id):
        if unidad_ids is not None and m["unidad_id"] not in unidad_ids:
            continue
        res["unidades"] += 1
        enviado = False
        for r in db.scalars(select(Residente).where(Residente.unidad_id == m["unidad_id"], Residente.activo.is_(True))):
            msg = texto_recordatorio(r.nombre, m["numero"], m["deuda"], m["codigo_cobro"], extra)
            if "whatsapp" in canales and r.telefono and whatsapp.enviar(r.telefono, msg):
                res["whatsapp"] += 1
                enviado = True
            if "email" in canales and r.email:
                from .. import tasks
                tasks.enviar_email.delay(r.email, f"Saldo pendiente — {ed.nombre}",
                                         email.render(email.PLANTILLA_CIRCULAR, edificio=ed.nombre,
                                                      asunto="Saldo pendiente", nombre=r.nombre, cuerpo=email.escape(msg)))
                res["email"] += 1
                enviado = True
        if not enviado:
            res["sin_contacto"].append(m["numero"])
    return res
