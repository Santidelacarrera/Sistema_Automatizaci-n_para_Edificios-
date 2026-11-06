"""Propiedades de docker-compose.yml para base externa (Supabase) y base local opcional."""
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]


def _compose():
    return yaml.safe_load((RAIZ / "docker-compose.yml").read_text(encoding="utf-8"))


def test_la_base_local_es_opcional_con_perfil():
    db = _compose()["services"]["db"]
    assert db["profiles"] == ["db-local"]


def test_api_worker_y_beat_no_dependen_de_la_base_local():
    servicios = _compose()["services"]
    for nombre in ("api", "worker", "beat"):
        dependencias = servicios[nombre].get("depends_on", [])
        assert "db" not in dependencias, nombre


def test_api_y_worker_usan_database_url_del_env():
    servicios = _compose()["services"]
    for nombre in ("api", "worker"):
        url = servicios[nombre]["environment"]["DATABASE_URL"]
        assert url.startswith("${DATABASE_URL:-"), nombre
        assert servicios[nombre]["env_file"] == ".env"


def test_ningun_servicio_tiene_secretos_escritos_a_mano():
    import re
    texto = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    # tras "edificios:" sólo puede venir una variable de .env, nunca una clave escrita a mano
    assert not re.search(r"edificios:(?!\$\{)[^\s@}]+@", texto)


def test_produccion_por_defecto_en_servicios_de_python():
    servicios = _compose()["services"]
    for nombre in ("api", "worker", "beat"):
        assert servicios[nombre]["environment"]["ENTORNO"] == "${ENTORNO:-produccion}", nombre


def test_los_servicios_rotan_sus_logs():
    servicios = _compose()["services"]
    for nombre in ("redis", "api", "panel", "proxy", "worker", "beat"):
        assert servicios[nombre]["logging"]["options"]["max-size"], nombre


def test_docs_interactivas_solo_fuera_de_produccion():
    texto = (RAIZ / "Caddyfile").read_text(encoding="utf-8")
    assert "/docs" not in texto and "/openapi.json" not in texto
