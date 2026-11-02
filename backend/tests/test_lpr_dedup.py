"""Deduplicación del traductor LPR: memoria (un proceso) y Redis (varias réplicas)."""
import threading

import httpx

from integraciones.lpr import dedup
from integraciones.lpr.config import Config
from integraciones.lpr.lectura import Lectura
from integraciones.lpr.traductor import Traductor

CFG = Config(backend_url="http://testserver", edificio_id="edificio_a", device_key="clave",
             token_camara="tok-camara", confianza_minima=0.85, dedup_segundos=30, adaptador="generico")


class RedisFalso:
    """Doble mínimo de redis-py con SET NX EX atómico y expiración controlada por un reloj."""

    def __init__(self):
        self.datos: dict[str, float] = {}
        self.ahora = 0.0
        self._lock = threading.Lock()

    def set(self, clave, valor, nx=False, ex=None):
        with self._lock:
            vence = self.datos.get(clave)
            if vence is not None and vence <= self.ahora:
                del self.datos[clave]
            if nx and clave in self.datos:
                return None
            self.datos[clave] = self.ahora + (ex or 10**9)
            return True

    def delete(self, clave):
        with self._lock:
            return 1 if self.datos.pop(clave, None) is not None else 0


class RedisCaido:
    def set(self, *a, **k):
        raise ConnectionError("sin redis")

    def delete(self, *a, **k):
        raise ConnectionError("sin redis")


def _backend_ok(llamadas):
    def manejar(request):
        llamadas.append(request)
        return httpx.Response(200, json={"abrir": True, "motivo": "residente"})
    return manejar


def _traductor(dedup_obj, llamadas, backend=None):
    http = httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(backend or _backend_ok(llamadas)))
    return Traductor(CFG, http=http, dedup=dedup_obj)


def test_sin_redis_url_usa_memoria():
    assert isinstance(dedup.crear(CFG), dedup.DedupMemoria)


def test_config_lee_lpr_redis_url():
    env = {"LPR_BACKEND_URL": "http://api:8000", "LPR_EDIFICIO_ID": "e", "LPR_DEVICE_KEY": "k",
           "LPR_TOKEN_CAMARA": "t", "LPR_REDIS_URL": "redis://redis:6379/1"}
    assert Config.desde_entorno(env).redis_url == "redis://redis:6379/1"
    env.pop("LPR_REDIS_URL")
    assert Config.desde_entorno(env).redis_url == ""


def test_dos_replicas_comparten_la_ventana_en_redis():
    r = RedisFalso()
    llamadas = []
    a = _traductor(dedup.DedupRedis(r, 30, "edificio_a"), llamadas)
    b = _traductor(dedup.DedupRedis(r, 30, "edificio_a"), llamadas)
    assert a.procesar(Lectura("BBCD12", 0.95)).abrir is True
    assert b.procesar(Lectura("BBCD12", 0.95)).estado == "duplicada"
    assert len(llamadas) == 1


def test_redis_expira_la_ventana():
    r = RedisFalso()
    llamadas = []
    t = _traductor(dedup.DedupRedis(r, 30, "edificio_a"), llamadas)
    t.procesar(Lectura("BBCD12", 0.95))
    r.ahora += 31
    assert t.procesar(Lectura("BBCD12", 0.95)).estado == "enviada"
    assert len(llamadas) == 2


def test_redis_separa_edificios():
    r = RedisFalso()
    assert dedup.DedupRedis(r, 30, "edificio_a").reclamar("BBCD12") is True
    assert dedup.DedupRedis(r, 30, "edificio_b").reclamar("BBCD12") is True


def test_redis_caido_no_bloquea_y_el_backend_decide():
    llamadas = []
    t = _traductor(dedup.DedupRedis(RedisCaido(), 30, "edificio_a"), llamadas)
    assert t.procesar(Lectura("BBCD12", 0.95)).abrir is True
    assert len(llamadas) == 1


def test_backend_caido_libera_la_patente_en_redis():
    r = RedisFalso()

    def caido(request):
        raise httpx.ConnectError("caído")

    t = _traductor(dedup.DedupRedis(r, 30, "edificio_a"), [], backend=caido)
    assert t.procesar(Lectura("BBCD12", 0.95)).estado == "error_backend"
    assert r.datos == {}  # la siguiente lectura sí se enviará


def test_memoria_es_segura_entre_hilos():
    d = dedup.DedupMemoria(30)
    ganadores = []
    hilos = [threading.Thread(target=lambda: ganadores.append(d.reclamar("BBCD12"))) for _ in range(50)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert ganadores.count(True) == 1
