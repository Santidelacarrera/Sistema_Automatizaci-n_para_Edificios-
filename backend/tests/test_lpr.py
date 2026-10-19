"""Traductor LPR: formato, umbral de confianza, deduplicación y llamada real a /validar-acceso."""
import httpx
import pytest
from fastapi.testclient import TestClient

from integraciones.lpr import adaptadores
from integraciones.lpr.config import Config
from integraciones.lpr.lectura import Lectura, LecturaInvalida, validar
from integraciones.lpr.adaptadores import generico
from integraciones.lpr.traductor import Traductor

from conftest import login

CFG = Config(backend_url="http://testserver", edificio_id="edificio_a", device_key="keyA",
             token_camara="tok-camara", confianza_minima=0.85, dedup_segundos=30, adaptador="generico")


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _backend_que_no_debe_llamarse(request):
    raise AssertionError("no debió llamar al backend")


# ---------- formato ----------
def test_formato_generico_normaliza_patente():
    lec = validar(generico.parsear({"patente": "bb-cd 12", "confianza": 0.93, "camara": "entrada-1"}))
    assert lec.patente == "BBCD12" and lec.confianza == 0.93 and lec.camara == "entrada-1"


@pytest.mark.parametrize("payload", [
    {"patente": "BBCD12"},                                   # sin confianza
    {"patente": "BBCD12", "confianza": "alta"},              # confianza no numérica
    {"patente": "BBCD12", "confianza": 93},                  # escala 0-100: rechazada, no se adivina
    {"patente": "A", "confianza": 0.9},                      # patente demasiado corta
    {"patente": "BBCD12!!", "confianza": 0.9, "fecha": "ayer"},
])
def test_formato_generico_rechaza_lo_ambiguo(payload):
    with pytest.raises(LecturaInvalida):
        validar(generico.parsear(payload))


def test_adaptadores_de_marca_fallan_explicitamente():
    with pytest.raises(NotImplementedError):
        adaptadores.cargar("hikvision")({})
    with pytest.raises(NotImplementedError):
        adaptadores.cargar("dahua")({})
    with pytest.raises(RuntimeError):
        adaptadores.cargar("inventada")


def test_config_exige_variables_de_entorno():
    with pytest.raises(RuntimeError, match="LPR_DEVICE_KEY"):
        Config.desde_entorno({"LPR_BACKEND_URL": "http://x", "LPR_EDIFICIO_ID": "edificio_a",
                              "LPR_TOKEN_CAMARA": "t"})


# ---------- traductor (sin red) ----------
def test_baja_confianza_no_llama_al_backend():
    t = Traductor(CFG, http=httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(_backend_que_no_debe_llamarse)))
    res = t.procesar(Lectura("BBCD12", 0.60))
    assert res.estado == "rechazada_confianza" and res.abrir is False


def test_deduplicacion_dentro_y_fuera_de_la_ventana():
    llamadas = []

    def backend(request):
        llamadas.append(request)
        return httpx.Response(403, json={"detail": "Credencial desconocida"})
    reloj = Reloj()
    t = Traductor(CFG, http=httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(backend)), reloj=reloj)
    assert t.procesar(Lectura("BBCD12", 0.95)).estado == "enviada"
    assert t.procesar(Lectura("BBCD12", 0.95)).estado == "duplicada"
    reloj.t += 10
    assert t.procesar(Lectura("BBCD12", 0.95)).estado == "duplicada"
    reloj.t += 25
    assert t.procesar(Lectura("BBCD12", 0.95)).estado == "enviada"
    assert len(llamadas) == 2


def test_envia_clave_de_dispositivo_y_punto_vehicular():
    vistos = {}

    def backend(request):
        vistos["path"] = request.url.path
        vistos["key"] = request.headers["X-Device-Key"]
        vistos["cuerpo"] = request.read().decode()
        return httpx.Response(200, json={"abrir": True, "motivo": "Patente de residente"})
    t = Traductor(CFG, http=httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(backend)))
    res = t.procesar(Lectura("BBCD12", 0.95))
    assert res.abrir is True and vistos["path"] == "/api/v1/edificio_a/validar-acceso"
    assert vistos["key"] == "keyA" and '"punto":"vehicular"' in vistos["cuerpo"]


def test_backend_caido_deja_el_porton_cerrado_y_no_cachea():
    def caido(request):
        raise httpx.ConnectError("sin red")
    reloj = Reloj()
    t = Traductor(CFG, http=httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(caido)), reloj=reloj)
    res = t.procesar(Lectura("BBCD12", 0.95))
    assert res.estado == "error_backend" and res.abrir is False
    # la siguiente lectura de la misma patente sí se reintenta
    assert t.procesar(Lectura("BBCD12", 0.95)).estado == "error_backend"


def test_backend_500_no_abre(monkeypatch):
    t = Traductor(CFG, http=httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    res = t.procesar(Lectura("BBCD12", 0.95))
    assert res.estado == "error_backend" and res.abrir is False


# ---------- extremo a extremo contra el backend real (en memoria) ----------
def _registrar_patente(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    r = client.post("/edificios/edificio_a/vehiculos", headers=h,
                    json={"unidad_id": seed["edificio_a", "101"].id, "patente": "BBCD12", "descripcion": "Mazda 3"})
    assert r.status_code == 201, r.text


def test_lectura_de_residente_abre_contra_backend_real(client, seed):
    _registrar_patente(client, seed)
    t = Traductor(CFG, http=client)
    res = t.procesar(Lectura("BBCD12", 0.95))
    assert res.estado == "enviada" and res.abrir is True and res.motivo == "Patente de residente"


def test_patente_desconocida_no_abre_contra_backend_real(client, seed):
    t = Traductor(CFG, http=client)
    res = t.procesar(Lectura("ZZZZ99", 0.95))
    assert res.estado == "enviada" and res.abrir is False


def test_clave_de_otro_edificio_no_abre(client, seed):
    _registrar_patente(client, seed)
    otro = Config(**{**CFG.__dict__, "device_key": "keyB"})
    res = Traductor(otro, http=client).procesar(Lectura("BBCD12", 0.95))
    assert res.abrir is False and "401" in res.motivo


# ---------- servidor HTTP ----------
@pytest.fixture()
def servidor(client, seed, monkeypatch):
    from integraciones.lpr import servidor
    _registrar_patente(client, seed)
    servidor._estado.clear()
    servidor._estado["cfg"] = CFG
    servidor._estado["parsear"] = adaptadores.cargar("generico")
    servidor._estado["t"] = Traductor(CFG, http=client)
    yield TestClient(servidor.app)
    servidor._estado.clear()


def test_servidor_exige_token_de_camara(servidor):
    body = {"patente": "BBCD12", "confianza": 0.95}
    assert servidor.post("/lpr/evento", json=body).status_code == 401
    assert servidor.post("/lpr/evento", json=body, headers={"X-LPR-Token": "malo"}).status_code == 401


def test_servidor_abre_y_responde_sin_devolver_la_patente(servidor):
    r = servidor.post("/lpr/evento", json={"patente": "BBCD12", "confianza": 0.95},
                      headers={"X-LPR-Token": "tok-camara"})
    assert r.status_code == 202 and r.json()["abrir"] is True
    assert "BBCD12" not in r.text


def test_servidor_baja_confianza_y_formato_invalido(servidor):
    h = {"X-LPR-Token": "tok-camara"}
    baja = servidor.post("/lpr/evento", json={"patente": "BBCD12", "confianza": 0.4}, headers=h)
    assert baja.status_code == 202 and baja.json()["estado"] == "rechazada_confianza" and baja.json()["abrir"] is False
    assert servidor.post("/lpr/evento", json={"patente": "BBCD12", "confianza": 93}, headers=h).status_code == 422
