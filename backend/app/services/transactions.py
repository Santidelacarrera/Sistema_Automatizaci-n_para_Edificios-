"""Serializa mutaciones relacionadas del tenant durante la transacción PostgreSQL."""
from sqlalchemy import select

from ..models import Edificio


def bloquear_edificio(db, edificio_id):
    return db.scalar(select(Edificio).where(Edificio.id == edificio_id).with_for_update()
                     .execution_options(populate_existing=True))
