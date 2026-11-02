"""Deduplicación de patentes del traductor LPR.

La cámara suele repetir la misma lectura varias veces en pocos segundos. Se "reclama" la patente:
la primera lectura dentro de la ventana pasa; las siguientes se marcan como duplicadas.

- ``DedupMemoria``: un solo proceso (desarrollo o una sola réplica). Segura entre hilos.
- ``DedupRedis``: varias réplicas/procesos comparten la ventana. ``SET NX EX`` es atómico,
  así que dos procesos nunca envían la misma patente a la vez.

Seguridad: la deduplicación sólo evita llamadas repetidas; quien decide el acceso es el backend.
Si Redis falla, la lectura NO se descarta: se envía al backend (que sigue siendo fail-closed).
"""
import logging
import threading
import time

log = logging.getLogger("lpr")

PREFIJO = "lpr:dedup:"


class DedupMemoria:
    def __init__(self, ventana_segundos: int, reloj=time.monotonic):
        self.ventana = ventana_segundos
        self.reloj = reloj
        self._vistas: dict[str, float] = {}  # patente -> instante reclamado (monotónico)
        self._lock = threading.Lock()

    def reclamar(self, patente: str) -> bool:
        """True si la patente no se vio dentro de la ventana (y queda reclamada); False si es duplicada."""
        with self._lock:
            ahora = self.reloj()
            # limpieza simple: descarta lo vencido para que el dict no crezca sin límite
            self._vistas = {p: t for p, t in self._vistas.items() if ahora - t < self.ventana}
            if patente in self._vistas:
                return False
            self._vistas[patente] = ahora
            return True

    def liberar(self, patente: str) -> None:
        with self._lock:
            self._vistas.pop(patente, None)


class DedupRedis:
    def __init__(self, cliente, ventana_segundos: int, edificio_id: str):
        self.r = cliente
        self.ventana = max(1, int(ventana_segundos))
        self.prefijo = f"{PREFIJO}{edificio_id}:"

    def reclamar(self, patente: str) -> bool:
        try:
            return bool(self.r.set(self.prefijo + patente, "1", nx=True, ex=self.ventana))
        except Exception as e:  # Redis caído: no bloquear, el backend decide
            log.warning("redis no disponible para deduplicar (%s): se envía la lectura", e.__class__.__name__)
            return True

    def liberar(self, patente: str) -> None:
        try:
            self.r.delete(self.prefijo + patente)
        except Exception as e:
            log.warning("redis no disponible para liberar patente (%s)", e.__class__.__name__)


def crear(cfg, reloj=time.monotonic):
    """Elige el almacén según la configuración: Redis si hay LPR_REDIS_URL, si no memoria."""
    url = getattr(cfg, "redis_url", "") or ""
    if not url:
        return DedupMemoria(cfg.dedup_segundos, reloj=reloj)
    import redis  # dependencia ya presente en requirements.txt (Celery)
    cliente = redis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)
    return DedupRedis(cliente, cfg.dedup_segundos, cfg.edificio_id)
