"""Suscriptores del bus de eventos: notificaciones en tiempo real al departamento."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import events
from .models import Residente
from .services.notifications import notificar


def _notificar_unidad(db: Session, unidad_id: int, texto: str) -> None:
    from .models import Unidad
    unidad = db.get(Unidad, unidad_id)
    if unidad:
        residentes = db.scalars(select(Residente).where(Residente.unidad_id == unidad_id,
                                                        Residente.edificio_id == unidad.edificio_id)).all()
        notificar(db, unidad.edificio_id, residentes, "Actividad de su comunidad", texto)


@events.on("visita.llego")
def _llego(db, edificio_id, p):
    _notificar_unidad(db, p["unidad_id"], f"🚪 Llegó su visita: {p['nombre']}.")


@events.on("visita.no_show")
def _no_show(db, edificio_id, p):
    _notificar_unidad(db, p["unidad_id"], "Su reserva de estacionamiento de visita fue liberada por no presentación.")


@events.on("pago.conciliado")
def _pago(db, edificio_id, p):
    _notificar_unidad(db, p["unidad_id"],
                      f"✅ Recibimos su pago de ${p['monto']:,.0f}. Deuda actual: ${p['deuda']:,.0f}.")


@events.on("encomienda.recibida")
def _encomienda(db, edificio_id, p):
    de = f" de {p['transportista']}" if p.get("transportista") else ""
    _notificar_unidad(db, p["unidad_id"], f"📦 Llegó una encomienda{de} para su departamento. Retírela en conserjería.")
