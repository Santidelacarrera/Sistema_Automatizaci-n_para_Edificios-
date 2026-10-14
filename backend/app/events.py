"""Bus de eventos: persiste el evento y despacha handlers (Celery/Redis en producción)."""
from collections import defaultdict
from typing import Callable

from sqlalchemy.orm import Session

from .models import Evento

_handlers: dict[str, list[Callable]] = defaultdict(list)


def on(tipo: str):
    def deco(fn):
        _handlers[tipo].append(fn)
        return fn
    return deco


def publish(db: Session, edificio_id: str, tipo: str, payload: dict) -> None:
    db.add(Evento(edificio_id=edificio_id, tipo=tipo, payload=payload))
    db.flush()
    for h in _handlers.get(tipo, []):
        h(db, edificio_id, payload)
