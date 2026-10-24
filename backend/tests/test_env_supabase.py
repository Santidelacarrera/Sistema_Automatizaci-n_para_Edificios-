"""El .env de plantilla (variables vacías comentadas) lo lee la aplicación con valores por defecto, y la
conexión a Supabase usa el pool configurado. Valores falsos."""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))
import configurar_entorno as ce  # noqa: E402

from app.config import Settings  # noqa: E402


def test_plantilla_vacia_no_rompe_la_configuracion(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)  # conftest la exporta; el entorno gana al archivo
    ruta = tmp_path / ".env"
    ruta.write_text(ce.construir_env({"ENTORNO": "desarrollo", "CORS_ORIGINS": "http://localhost:3000"}), encoding="utf-8")
    cfg = Settings(_env_file=ruta)
    assert cfg.entorno == "desarrollo"
    assert cfg.database_url == "sqlite:///./dev.db"  # DATABASE_URL comentada: sin base remota aun
    assert cfg.db_pool_size == 5 and cfg.db_max_overflow == 5


def test_variables_vacias_quedan_comentadas_y_con_explicacion():
    texto = ce.construir_env({"ENTORNO": "desarrollo"})
    assert "# DATABASE_URL=" in texto and "\nDATABASE_URL=" not in texto
    assert "Supabase" in texto  # la explicación de DATABASE_URL va encima


def test_cadena_de_supabase_queda_activa_y_con_pool(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = "postgresql+psycopg://postgres.abcdefgh:" + "Fake" + "Pass" + "123" + \
          "@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
    ruta = tmp_path / ".env"
    ruta.write_text(ce.construir_env({"ENTORNO": "produccion", "DATABASE_URL": url, "DB_POOL_SIZE": "3",
                                      "DB_MAX_OVERFLOW": "2", "JWT_SECRET": "j" * 40}), encoding="utf-8")
    cfg = Settings(_env_file=ruta)
    assert cfg.database_url == url
    assert cfg.db_pool_size == 3 and cfg.db_max_overflow == 2


@pytest.mark.skipif(bool(os.environ.get("TEST_DATABASE_URL")), reason="la suite corre contra PostgreSQL")
def test_el_pool_solo_se_aplica_a_bases_que_no_son_sqlite():
    from app import db
    # En pruebas la base es SQLite: el motor no recibe argumentos de pool (SQLite no los admite).
    assert db._sqlite is True
    assert db._pool == {}
