"""Suscriptores del bus de eventos: notificaciones en tiempo real al departamento."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import events
from .models import Residente
from .services import whatsapp

log = logging.getLogger(__name__)


def _notificar_unidad(db: Session, unidad_id: int, texto: str) -> None:
    for r in db.scalars(select(Residente).where(Residente.unidad_id == unidad_id, Residente.activo.is_(True))):
        if r.telefono:
            res = whatsapp.enviar(r.telefono, texto)
            if res.estado == "error":
                log.warning("Notificación WhatsApp a unidad %s no enviada: %s", unidad_id, res.motivo)


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
