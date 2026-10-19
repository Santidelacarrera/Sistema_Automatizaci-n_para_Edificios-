"""Envíos con resultado explícito (enviado / encolado / no configurado / error) y diagnóstico admin."""
import smtplib
from datetime import date

import httpx
import pytest

from app.config import settings
from app.services import email, finance, whatsapp
from app.services.resultado import ENCOLADO, ENVIADO, ERROR, NO_CONFIGURADO

from conftest import login

SECRETO_EVO = "apikey-evolution-secreta-123"
SECRETO_SMTP = "smtp-clave-secreta-456"


@pytest.fixture()
def wa_configurado(monkeypatch):
    monkeypatch.setattr(settings, "evolution_url", "http://evo.local")
    monkeypatch.setattr(settings, "evolution_instance", "edificio-a")
    monkeypatch.setattr(settings, "evolution_apikey", SECRETO_EVO)


@pytest.fixture()
def smtp_configurado(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.local")
    monkeypatch.setattr(settings, "smtp_user", "usuario")
    monkeypatch.setattr(settings, "smtp_password", SECRETO_SMTP)


@pytest.fixture()
def sin_wa_ni_smtp(monkeypatch):
    monkeypatch.setattr(settings, "evolution_url", "")
    monkeypatch.setattr(settings, "evolution_instance", "")
    monkeypatch.setattr(settings, "evolution_apikey", "")
    monkeypatch.setattr(settings, "smtp_host", "")


def _respuesta(status):
    return httpx.Response(status, request=httpx.Request("POST", "http://evo.local"))


def _con_deuda(db):
    finance.generar_cargos(db, "edificio_a", "2020-01", date(2020, 2, 1),
                           [{"concepto": "GC", "monto": 100000, "tipo": "ordinario"}])
    db.commit()


# ---------- WhatsApp ----------
def test_whatsapp_sin_configurar_dice_que_falta(monkeypatch):
    monkeypatch.setattr(settings, "evolution_url", "")
    monkeypatch.setattr(settings, "evolution_instance", "")
    monkeypatch.setattr(settings, "evolution_apikey", "")
    res = whatsapp.enviar("56911112222", "hola")
    assert res.estado == NO_CONFIGURADO
    assert "EVOLUTION_URL" in res.motivo and "EVOLUTION_APIKEY" in res.motivo


def test_whatsapp_sin_telefono_no_intenta_enviar(wa_configurado, monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("no debió llamar a la red"))
    res = whatsapp.enviar("", "hola")
    assert res.estado == NO_CONFIGURADO and "teléfono" in res.motivo


def test_whatsapp_enviado_error_http_y_red(wa_configurado, monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _respuesta(201))
    assert whatsapp.enviar("56911112222", "hola").estado == ENVIADO

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _respuesta(400))
    res = whatsapp.enviar("56911112222", "hola")
    assert res.estado == ERROR and "400" in res.motivo and not res.transitorio

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _respuesta(503))
    assert whatsapp.enviar("56911112222", "hola").transitorio

    def caida(*a, **k):
        raise httpx.ConnectError("sin red")
    monkeypatch.setattr(httpx, "post", caida)
    res = whatsapp.enviar("56911112222", "hola")
    assert res.estado == ERROR and res.transitorio and "ConnectError" in res.motivo
    assert SECRETO_EVO not in res.motivo


# ---------- correo ----------
def test_correo_sin_smtp_no_configurado(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    res = email.enviar("ana@x.cl", "Asunto", "<p>hola</p>")
    assert res.estado == NO_CONFIGURADO and "SMTP_HOST" in res.motivo


class _SMTPOk:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, *a):
        pass

    def send_message(self, msg):
        pass


def _smtp_que_falla(error):
    class Falla(_SMTPOk):
        def login(self, *a):
            raise error

        def send_message(self, msg):
            raise error
    return Falla


def test_correo_enviado(smtp_configurado, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _SMTPOk)
    assert email.enviar("ana@x.cl", "Asunto", "<p>hola</p>").estado == ENVIADO


def test_correo_errores_smtp(smtp_configurado, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _smtp_que_falla(smtplib.SMTPAuthenticationError(535, b"mal")))
    res = email.enviar("ana@x.cl", "Asunto", "<p>hola</p>")
    assert res.estado == ERROR and "credenciales" in res.motivo and not res.transitorio
    assert SECRETO_SMTP not in res.motivo

    monkeypatch.setattr(smtplib, "SMTP", _smtp_que_falla(OSError("sin ruta")))
    res = email.enviar("ana@x.cl", "Asunto", "<p>hola</p>")
    assert res.estado == ERROR and res.transitorio

    monkeypatch.setattr(smtplib, "SMTP", _smtp_que_falla(smtplib.SMTPRecipientsRefused({"ana@x.cl": (550, b"no")})))
    res = email.enviar("ana@x.cl", "Asunto", "<p>x</p>")
    assert res.estado == ERROR and "destinatario" in res.motivo


def test_correo_sin_destinatario(smtp_configurado):
    res = email.enviar("", "Asunto", "<p>x</p>")
    assert res.estado == NO_CONFIGURADO and "correo registrado" in res.motivo


# ---------- endpoints ----------
def test_recordatorios_explican_por_que_no_se_enviaron(client, seed, db, sin_wa_ni_smtp):
    _con_deuda(db)
    h = login(client, "edificio_a", "ana@x.cl")
    body = client.post("/edificios/edificio_a/cobranza/recordatorios", headers=h,
                       json={"canales": ["whatsapp", "email"]}).json()
    assert body["whatsapp"] == 0 and body["email"] == 0
    assert body["no_enviados"] == len(body["detalle"]) > 0
    assert {(d["canal"], d["estado"]) for d in body["detalle"]} == {("whatsapp", NO_CONFIGURADO),
                                                                     ("correo", NO_CONFIGURADO)}
    assert any("EVOLUTION_URL" in d["motivo"] for d in body["detalle"])
    assert any("SMTP_HOST" in d["motivo"] for d in body["detalle"])


def test_recordatorio_whatsapp_enviado(client, seed, db, wa_configurado, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _respuesta(201))
    _con_deuda(db)
    h = login(client, "edificio_a", "ana@x.cl")
    body = client.post("/edificios/edificio_a/cobranza/recordatorios", headers=h,
                       json={"unidad_ids": [seed["edificio_a", "101"].id], "canales": ["whatsapp"]}).json()
    assert body["whatsapp"] == 1 and body["sin_contacto"] == []
    assert body["detalle"] == [{"unidad": "101", "residente": "Ana Pérez", "canal": "whatsapp",
                                "estado": ENVIADO, "motivo": ""}]


def test_recordatorio_correo_encolado_si_hay_smtp(client, seed, db, smtp_configurado, monkeypatch):
    monkeypatch.setattr(settings, "evolution_url", "")
    monkeypatch.setattr(settings, "evolution_instance", "")
    monkeypatch.setattr(settings, "evolution_apikey", "")
    enviados = []
    monkeypatch.setattr("app.tasks.email.enviar", lambda *a: enviados.append(a) or email.ResultadoEnvio("correo", ENVIADO))
    _con_deuda(db)
    h = login(client, "edificio_a", "ana@x.cl")
    body = client.post("/edificios/edificio_a/cobranza/recordatorios", headers=h,
                       json={"unidad_ids": [seed["edificio_a", "101"].id], "canales": ["email"]}).json()
    assert body["email"] == 1 and body["detalle"][0]["estado"] == ENCOLADO
    assert len(enviados) == 1  # en modo eager la tarea corre en la misma petición


def test_circular_avisa_si_no_hay_correo_configurado(client, seed, sin_wa_ni_smtp):
    h = login(client, "edificio_a", "ana@x.cl")
    r = client.post("/edificios/edificio_a/circulares", headers=h,
                    json={"asunto": "Corte de agua", "cuerpo_html": "<p>Mañana</p>"}).json()
    assert r["encolado"] is False and r["estado"] == NO_CONFIGURADO and "SMTP_HOST" in r["motivo"]


def test_diagnostico_solo_admin_y_sin_secretos(client, seed, wa_configurado, smtp_configurado):
    h = login(client, "edificio_a", "ana@x.cl")
    r = client.get("/edificios/edificio_a/diagnostico", headers=h)
    assert r.status_code == 200
    assert r.json()["whatsapp"]["configurado"] is True
    assert r.json()["correo"]["configurado"] is True
    assert SECRETO_EVO not in r.text and SECRETO_SMTP not in r.text and "evo.local" not in r.text

    residente = login(client, "edificio_a", "beto@x.cl")
    assert client.get("/edificios/edificio_a/diagnostico", headers=residente).status_code == 403
    assert client.get("/edificios/edificio_a/diagnostico").status_code == 401


def test_diagnostico_advierte_configuracion_insegura(client, seed, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_webhook_token", "")
    h = login(client, "edificio_a", "ana@x.cl")
    adv = client.get("/edificios/edificio_a/diagnostico", headers=h).json()["advertencias"]
    assert any("WHATSAPP_WEBHOOK_TOKEN" in a for a in adv)
