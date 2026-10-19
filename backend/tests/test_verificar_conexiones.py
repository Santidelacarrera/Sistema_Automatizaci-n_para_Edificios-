"""Verificador de conexiones: estados OK / FALLÓ / NO CONFIGURADO, mensajes sin secretos y sin llamadas
a servicios no configurados. Todas las credenciales son falsas y todas las llamadas de red se simulan."""
import smtplib
import sys
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))
import verificar_conexiones as vc  # noqa: E402

from app.config import JWT_POR_DEFECTO, Settings  # noqa: E402

CLAVE = "Fake" + "Secret" + "987"
JWT_BUENO = "j" * 20 + "k" * 20


def cfg(**extra) -> Settings:
    # Se fijan todos los valores para no depender del entorno del proceso (conftest exporta algunos).
    base = dict(_env_file=None, database_url="", jwt_secret=JWT_BUENO, entorno="desarrollo",
                whatsapp_webhook_token="", evolution_url="", evolution_instance="", evolution_apikey="",
                smtp_host="", smtp_user="", smtp_password="", anthropic_api_key="", redis_url="redis://localhost:6379/0")
    base.update(extra)
    return Settings(**base)


def _sin_red(*a, **k):
    raise AssertionError("no debió contactar la red")


# ---------- limpieza de mensajes ----------
def test_limpiar_quita_secretos_del_mensaje():
    mensaje = f"fallo con clave {CLAVE} y url postgresql://u:{CLAVE}@h/db"
    limpio = vc.limpiar(mensaje, [CLAVE, "postgresql://u:" + CLAVE + "@h/db"])
    assert CLAVE not in limpio and "****" in limpio


# ---------- sin configuración: no se contacta nada ----------
def test_servicios_no_configurados_no_se_contactan(monkeypatch):
    monkeypatch.setattr(httpx, "get", _sin_red)
    monkeypatch.setattr(smtplib, "SMTP", _sin_red)
    resultados = {r.nombre: r.estado for r in [
        vc.chequear_base(cfg()), vc.chequear_smtp(cfg()), vc.chequear_evolution(cfg()),
        vc.chequear_anthropic(cfg()), vc.chequear_webhook(cfg()), vc.chequear_migraciones(cfg())]}
    assert set(resultados.values()) == {vc.NO_CONFIGURADO}


def test_jwt_de_ejemplo_falla_aunque_sea_desarrollo():
    r = vc.chequear_jwt(cfg(jwt_secret=JWT_POR_DEFECTO))
    assert r.estado == vc.FALLO and "ejemplo" in r.mensaje


def test_webhook_corto_falla_y_largo_es_ok():
    assert vc.chequear_webhook(cfg(whatsapp_webhook_token="corto")).estado == vc.FALLO
    r = vc.chequear_webhook(cfg(whatsapp_webhook_token="w" * 40))
    assert r.estado == vc.OK and "w" * 40 not in r.mensaje


# ---------- base de datos y migraciones ----------
def test_base_sqlite_responde(tmp_path):
    r = vc.chequear_base(cfg(database_url=f"sqlite:///{(tmp_path / 'p.db').as_posix()}"))
    assert r.estado == vc.OK


def test_base_inalcanzable_no_muestra_la_clave():
    url = "postgresql+psycopg://usuario:" + CLAVE + "@127.0.0.1:1/bd"
    r = vc.chequear_base(cfg(database_url=url))
    assert r.estado == vc.FALLO and CLAVE not in r.mensaje


def test_migraciones_detecta_base_sin_migrar_y_luego_ok(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from app.config import settings
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    assert vc.chequear_migraciones(cfg(database_url=url)).estado == vc.FALLO
    monkeypatch.setattr(settings, "database_url", url)
    acfg = Config(str(RAIZ / "backend" / "alembic.ini"))
    acfg.set_main_option("script_location", str(RAIZ / "backend" / "migrations"))
    command.upgrade(acfg, "head")
    r = vc.chequear_migraciones(cfg(database_url=url))
    assert r.estado == vc.OK and "al día" in r.mensaje


def test_explica_errores_comunes_de_supabase():
    assert "Contraseña incorrecta" in vc._explicar_error_base("password authentication failed for user x")
    assert "pooler" in vc._explicar_error_base("Tenant or user not found")


# ---------- SMTP sin enviar nada ----------
class _SMTPFalso:
    comportamiento = None

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def has_extn(self, _):
        return True

    def starttls(self):
        pass

    def login(self, user, clave):
        if _SMTPFalso.comportamiento == "rechazar":
            raise smtplib.SMTPAuthenticationError(535, b"mal")

    def noop(self):
        pass

    def send_message(self, *a):
        raise AssertionError("la verificación no debe enviar correos")


def test_smtp_ok_no_envia_y_rechazo_no_muestra_la_clave(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _SMTPFalso)
    _SMTPFalso.comportamiento = None
    ok = vc.chequear_smtp(cfg(smtp_host="smtp.ejemplo.cl", smtp_user="u", smtp_password=CLAVE))
    assert ok.estado == vc.OK and "no se envió nada" in ok.mensaje
    _SMTPFalso.comportamiento = "rechazar"
    mal = vc.chequear_smtp(cfg(smtp_host="smtp.ejemplo.cl", smtp_user="u", smtp_password=CLAVE))
    assert mal.estado == vc.FALLO and CLAVE not in mal.mensaje


# ---------- Evolution y Anthropic con respuestas simuladas ----------
class _Resp:
    def __init__(self, status, datos=None):
        self.status_code = status
        self._datos = datos or {}

    def json(self):
        return self._datos


def test_evolution_estados(monkeypatch):
    c = cfg(evolution_url="https://evo.ejemplo.cl", evolution_instance="edificio-a", evolution_apikey=CLAVE)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(200, {"instance": {"state": "open"}}))
    assert vc.chequear_evolution(c).estado == vc.OK
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(200, {"instance": {"state": "close"}}))
    r = vc.chequear_evolution(c)
    assert r.estado == vc.FALLO and "QR" in r.mensaje
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(401))
    r = vc.chequear_evolution(c)
    assert r.estado == vc.FALLO and CLAVE not in r.mensaje


def test_evolution_sin_respuesta_no_muestra_la_clave(monkeypatch):
    c = cfg(evolution_url="https://evo.ejemplo.cl", evolution_instance="x", evolution_apikey=CLAVE)

    def caida(*a, **k):
        raise httpx.ConnectError("sin red para " + CLAVE)
    monkeypatch.setattr(httpx, "get", caida)
    r = vc.chequear_evolution(c)
    assert r.estado == vc.FALLO and CLAVE not in r.mensaje


def test_anthropic_estados(monkeypatch):
    c = cfg(anthropic_api_key=CLAVE)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(200))
    assert vc.chequear_anthropic(c).estado == vc.OK
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(401))
    assert vc.chequear_anthropic(c).estado == vc.FALLO


# ---------- salida ----------
def test_codigo_de_salida():
    ok = vc.Resultado("a", vc.OK, "")
    no = vc.Resultado("b", vc.NO_CONFIGURADO, "")
    malo = vc.Resultado("c", vc.FALLO, "")
    assert vc.codigo_salida([ok, no]) == 0
    assert vc.codigo_salida([ok, malo]) == 1


def test_main_sin_archivo_devuelve_2(tmp_path, capsys):
    assert vc.main(["--env", str(tmp_path / "no-existe.env")]) == 2
    assert "configurar_entorno" in capsys.readouterr().err
