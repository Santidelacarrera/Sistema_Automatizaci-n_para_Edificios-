"""Caché de lecturas frecuentes con Redis (cuando está disponible fuera de eager) y respaldo en memoria."""
import json
import time

from ..config import settings

_MEM: dict[str, tuple[float, str]] = {}


def _redis_client():
    if settings.celery_eager or not settings.redis_url:
        return None
    try:
        import redis
        return redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, decode_responses=True)
    except Exception:
        return None


def cache_get(clave: str):
    r = _redis_client()
    if r is not None:
        try:
            raw = r.get(f"edif:{clave}")
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass
    item = _MEM.get(clave)
    if item and item[0] > time.monotonic():
        return json.loads(item[1])
    _MEM.pop(clave, None)
    return None


def cache_set(clave: str, valor, ttl_s: int = 30) -> None:
    raw = json.dumps(valor, default=str)
    r = _redis_client()
    if r is not None:
        try:
            r.setex(f"edif:{clave}", ttl_s, raw)
            return
        except Exception:
            pass
    _MEM[clave] = (time.monotonic() + ttl_s, raw)


def cache_invalidate(prefijo: str) -> None:
    for k in [k for k in _MEM if k.startswith(prefijo)]:
        _MEM.pop(k, None)
    r = _redis_client()
    if r is not None:
        try:
            for key in r.scan_iter(match=f"edif:{prefijo}*"):
                r.delete(key)
        except Exception:
            pass
