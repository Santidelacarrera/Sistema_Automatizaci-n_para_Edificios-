"""Seguridad de la configuración: escáner de secretos sobre lo versionado, guarda de producción,
y CORS leído desde la configuración. Los secretos de ejemplo se arman en tiempo de ejecución para que
este archivo no dispare el propio escáner."""
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import JWT_POR_DEFECTO, Settings, validar_para_arranque

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))
import escaner_secretos  # noqa: E402


def _git_disponible() -> bool:
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=RAIZ, capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


@pytest.mark.skipif(not _git_disponible(), reason="no es un repositorio Git")
def test_ningun_archivo_versionado_contiene_secretos():
    hallazgos = escaner_secretos.escanear_repo(RAIZ)
    assert hallazgos == [], f"secretos en archivos versionados: {hallazgos}"


def test_detecta_url_de_base_con_clave_real():
    url = "postgresql+psycopg://edificios:" + "Xq9vL2mP8rT4" + "@db.ejemplo.supabase.co:5432/postgres"
    assert escaner_secretos.hallazgos_en_texto(f"DATABASE_URL={url}")


def test_detecta_clave_anthropic_y_clave_privada():
    assert escaner_secretos.hallazgos_en_texto("k = '" + "sk-ant-" + "a" * 30 + "'")
    assert escaner_secretos.hallazgos_en_texto("-----BEGIN " + "RSA PRIVATE KEY-----")


def test_detecta_secreto_asignado_en_archivo_de_configuracion():
    linea = "JWT_SECRET=" + "k8Hq2Lz9Wm4Rb7Tn1Yv6Pc3Sd0Fg5Jx"
    assert escaner_secretos.hallazgos_en_texto(linea)


def test_no_marca_ejemplos_ni_marcadores():
    ejemplos = [
        "DATABASE_URL=postgresql+psycopg://usuario:clave@host:5432/edificios",
        "JWT_SECRET=cambiar-por-un-secreto-largo-de-32-caracteres",
        "DB_PASSWORD: ${DB_PASSWORD:?define DB_PASSWORD}",
        "EVOLUTION_APIKEY=",
        "DEVICE_KEY = None",
        "DEVICE_KEY = \"PEGAR-X-DEVICE-KEY-DEL-EDIFICIO\"",
    ]
    for linea in ejemplos:
        assert escaner_secretos.hallazgos_en_texto(linea) == [], linea


def test_produccion_con_jwt_por_defecto_no_arranca():
    cfg = Settings(entorno="produccion", jwt_secret=JWT_POR_DEFECTO,
                   database_url="postgresql+psycopg://u:p@h/db")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validar_para_arranque(cfg)


def test_produccion_con_sqlite_no_arranca():
    cfg = Settings(entorno="produccion", jwt_secret="x" * 40, database_url="sqlite:///./dev.db")
    with pytest.raises(RuntimeError, match="SQLite"):
        validar_para_arranque(cfg)


def test_produccion_con_secretos_propios_arranca_y_desarrollo_siempre():
    validar_para_arranque(Settings(entorno="produccion", jwt_secret="x" * 40,
                                   database_url="postgresql+psycopg://u:p@h/db"))
    validar_para_arranque(Settings(entorno="desarrollo"))
    with pytest.raises(RuntimeError, match="ENTORNO"):
        validar_para_arranque(Settings(entorno="pruebas"))


def test_cors_se_lee_de_la_configuracion(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://panel.ejemplo.cl, https://otro.ejemplo.cl")
    cfg = Settings()
    assert cfg.cors_origins == "https://panel.ejemplo.cl, https://otro.ejemplo.cl"
