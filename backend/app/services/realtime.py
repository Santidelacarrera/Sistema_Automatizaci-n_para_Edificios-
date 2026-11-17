"""Gestor de conexiones WebSocket por edificio para eventos en tiempo real."""
from collections import defaultdict
import logging
from fastapi import WebSocket

log = logging.getLogger("edificio.realtime")


class ConnectionManager:
    """Mantiene salas WebSocket agrupadas por edificio_id."""

    def __init__(self) -> None:
        self._salas: dict[str, set[WebSocket]] = defaultdict(set)

    async def conectar(self, edificio_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._salas[edificio_id].add(ws)

    def desconectar(self, edificio_id: str, ws: WebSocket) -> None:
        sala = self._salas.get(edificio_id)
        if not sala:
            return
        sala.discard(ws)
        if not sala:
            self._salas.pop(edificio_id, None)

    def activos(self, edificio_id: str) -> int:
        return len(self._salas.get(edificio_id, ()))

    async def emitir(self, edificio_id: str, evento: dict) -> int:
        sala = list(self._salas.get(edificio_id, ()))
        enviados = 0
        for ws in sala:
            try:
                await ws.send_json(evento)
                enviados += 1
            except Exception as exc:
                log.debug("Desconectando WebSocket inactivo en %s: %s", edificio_id, exc)
                self.desconectar(edificio_id, ws)
        return enviados


realtime_manager = ConnectionManager()
