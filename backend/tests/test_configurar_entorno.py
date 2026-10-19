"""Asistente de configuración: validación, enmascarado, escritura de .env, .gitignore e idempotencia.

TODOS los valores de este archivo son falsos. Nunca se usan credenciales reales en pruebas.
La consola se simula con respuestas predefinidas; se comprueba además que ningún secreto llega a la pantalla.
"""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))
import configurar_entorno as ce  # noqa: E402

# Valores de ejemplo falsos: se arman con concatenación para no parecer literales de credenciales.
CLAVE_BD = "Fake" + "Pass" + "123"
URL_BD = "postgresql://postgres.abcdefgh:" + CLAVE_BD + "@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
JWT = "j" * 20 + "k" * 20   # 40 caracteres de ejemplo


class Consola:
    """Entrada simulada. Cada respuesta se busca por un fragmento de la pregunta; las listas se consumen en orden."""

    def __init__(self, respuestas: dict):
        self.respuestas = {k: (list(v) if isinstance(v, list) else v) for k, v in respuestas.items()}
        self.salida: list[str] = []
        self.preguntas: list[str] = []

    def _buscar(self, pregunta: str, defecto):
        self.preguntas.append(pregunta)
        for clave, valor in self.respuestas.items():
            if clave in pregunta:
                if isinstance(valor, list):
                    if not valor:
                        raise AssertionError(f"sin respuestas preparadas para: {pregunta}")
                    return valor.pop(0)
                return valor
        return defecto

    def texto(self, pregunta, por_defecto=""):
        return self._buscar(pregunta, por_defecto)

    def secreto(self, pregunta):
        return self._buscar(pregunta, "")

    def si_no(self, pregunta, por_defecto=True):
        return self._buscar(pregunta, por_defecto)

    def info(self, mensaje):
        self.salida.append(mensaje)

    def error(self, mensaje):
        self.salida.append("ERROR " + mensaje)

    def texto_completo(self) -> str:
        return "\n".join(self.salida)


RESPUESTAS_BASE = {
    "ENTORNO": "desarrollo",
    "DATABASE_URL": URL_BD,
    "¿Generar JWT_SECRET": False,
    "Ingrese JWT_SECRET": JWT,
    "¿Configurar WhatsApp": False,
    "¿Guardar la X-Device-Key": False,
    "EVOLUTION_URL": "",
    "SMTP_HOST": "",
    "ANTHROPIC_API_KEY": "",
    "CORS_ORIGINS": "http://localhost:3000",
    "¿Escribir el archivo": True,
}


# ---------- enmascarado ----------
def test_mascara_muestra_solo_los_ultimos_cuatro():
    assert ce.mascara("abcdefgh") == "****efgh"
    assert ce.mascara("abc") == "****"
    assert ce.mascara("") == "(vacío)"


def test_enmascarar_url_no_deja_la_clave_visible():
    mostrada = ce.enmascarar_url(ce.normalizar_database_url(URL_BD)[0])
    assert CLAVE_BD not in mostrada
    assert mostrada.startswith("postgresql+psycopg://postgres.abcdefgh:****")


# ---------- validación ----------
def test_jwt_por_defecto_y_corto_se_rechazan():
    assert ce.validar_jwt(ce.JWT_POR_DEFECTO)
    assert ce.validar_jwt("x" * 10)
    assert ce.validar_jwt("x" * 40) is None


def test_generar_secreto_cumple_el_minimo():
    s = ce.generar_secreto()
    assert len(s) >= 32 and ce.validar_jwt(s) is None


def test_normaliza_cadena_de_supabase_y_agrega_ssl():
    url, avisos = ce.normalizar_database_url(URL_BD)
    assert url.startswith("postgresql+psycopg://postgres.abcdefgh:")
    assert "sslmode=require" in url
    assert any("SSL" in a for a in avisos)


def test_conserva_prefijo_psycopg_y_ssl_existente():
    url, _ = ce.normalizar_database_url("postgresql+psycopg://u:" + CLAVE_BD + "@db.x.supabase.co:5432/postgres?sslmode=verify-full")
    assert url.startswith("postgresql+psycopg://") and "sslmode=verify-full" in url


def test_rechaza_puerto_del_pooler_transaction_sin_mostrar_la_clave():
    url = "postgresql://u:" + CLAVE_BD + "@aws-0.pooler.supabase.com:6543/postgres"
    with pytest.raises(ValueError) as e:
        ce.normalizar_database_url(url)
    assert "6543" in str(e.value) and CLAVE_BD not in str(e.value)


@pytest.mark.parametrize("url,motivo", [
    ("mysql://usuario:clave@host/db", "postgresql://"),
    ("postgresql://u@h:5432/db", "contraseña"),
    ("postgresql://u:[YOUR-PASSWORD]@h:5432/db", "marcador"),
    ("postgresql://:p@h:5432/db", "usuario"),
])
def test_rechaza_cadenas_incompletas(url, motivo):
    with pytest.raises(ValueError) as e:
        ce.normalizar_database_url(url)
    assert motivo in str(e.value)


def test_sqlite_se_acepta_con_aviso():
    url, avisos = ce.normalizar_database_url("sqlite:///./dev.db")
    assert url == "sqlite:///./dev.db" and avisos


def test_valida_url_correo_y_puerto():
    assert ce.validar_url_http("EVOLUTION_URL", "https://evo.ejemplo.cl") is None
    assert ce.validar_url_http("EVOLUTION_URL", "evo.ejemplo.cl")
    assert ce.validar_correo("panel@ejemplo.cl") is None and ce.validar_correo("nada")
    assert ce.validar_puerto("587") is None and ce.validar_puerto("99999")


# ---------- archivo .env ----------
def test_construir_env_es_determinista_y_ordenado():
    valores = {"DATABASE_URL": URL_BD, "ENTORNO": "desarrollo", "DEVICE_KEY_EDIFICIO_A": "k" * 32, "JWT_SECRET": JWT,
               "SMTP_FROM": "panel@ejemplo.cl"}
    a = ce.construir_env(valores)
    assert a == ce.construir_env(dict(reversed(list(valores.items()))))
    lineas = [l for l in a.splitlines() if "=" in l]
    assert lineas[0].startswith("ENTORNO=") and lineas[-1].startswith("DEVICE_KEY_EDIFICIO_A=")


def test_construir_env_entrecomilla_valores_con_espacios():
    assert 'CORS_ORIGINS="https://a.cl, https://b.cl"' in ce.construir_env({"CORS_ORIGINS": "https://a.cl, https://b.cl"})


def test_escribir_env_nuevo_no_crea_respaldo(tmp_path):
    ruta = tmp_path / ".env"
    assert ce.escribir_env(ruta, "A=1\n") is None
    assert ruta.read_text(encoding="utf-8") == "A=1\n"
    if os.name == "posix":
        assert oct(ruta.stat().st_mode & 0o777) == "0o600"


def test_escribir_env_con_respaldo_conserva_la_copia_anterior(tmp_path):
    ruta = tmp_path / ".env"
    ruta.write_text("VIEJO=1\n", encoding="utf-8")
    respaldo = ce.escribir_env(ruta, "NUEVO=2\n")
    assert respaldo == tmp_path / ".env.bak"
    assert respaldo.read_text(encoding="utf-8") == "VIEJO=1\n"
    assert ruta.read_text(encoding="utf-8") == "NUEVO=2\n"


def test_asegurar_ignorados_agrega_una_sola_vez(tmp_path):
    (tmp_path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    primera = ce.asegurar_ignorados(tmp_path)
    assert ".env" in primera and "config_local.py" in primera
    assert ce.asegurar_ignorados(tmp_path) == []
    lineas = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lineas.count(".env") == 1


def test_fuera_de_git_no_se_puede_verificar(tmp_path):
    assert ce.verificar_ignorados(tmp_path, [".env"]) is None


def test_los_ignorados_del_repositorio_real_cubren_los_secretos():
    gi = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    for entrada in (".env", ".env.bak", "config_local.py"):
        assert any(l.strip() in (entrada, "*" + entrada, "**/" + entrada) or l.strip().endswith(entrada) for l in gi), entrada
    assert "!.env.example" in gi


# ---------- flujo completo con consola simulada ----------
def test_flujo_completo_escribe_env_y_no_muestra_secretos(tmp_path, capsys):
    consola = Consola(RESPUESTAS_BASE)
    assert ce.ejecutar(consola, ruta_env=tmp_path / ".env", raiz=tmp_path) == 0
    contenido = (tmp_path / ".env").read_text(encoding="utf-8")
    assert f"JWT_SECRET={JWT}" in contenido
    assert "DATABASE_URL=postgresql+psycopg://" in contenido
    visible = consola.texto_completo() + capsys.readouterr().out
    assert CLAVE_BD not in visible and JWT not in visible
    assert "****" in visible
    assert any("Desactivado" in l for l in consola.salida)


def test_existente_y_respuesta_no_no_toca_nada(tmp_path):
    ruta = tmp_path / ".env"
    ruta.write_text("ORIGINAL=1\n", encoding="utf-8")
    consola = Consola({"Ya existe": False})
    assert ce.ejecutar(consola, ruta_env=ruta, raiz=tmp_path) == 0
    assert ruta.read_text(encoding="utf-8") == "ORIGINAL=1\n"
    assert not (tmp_path / ".env.bak").exists()


def test_es_idempotente_con_mismas_respuestas(tmp_path):
    ruta = tmp_path / ".env"
    respuestas = dict(RESPUESTAS_BASE, **{"Ya existe": True})
    ce.ejecutar(Consola(dict(RESPUESTAS_BASE)), ruta_env=ruta, raiz=tmp_path)
    primera = ruta.read_text(encoding="utf-8")
    ce.ejecutar(Consola(respuestas), ruta_env=ruta, raiz=tmp_path)
    assert ruta.read_text(encoding="utf-8") == primera
    assert (tmp_path / ".env.bak").read_text(encoding="utf-8") == primera


def test_vuelve_a_preguntar_si_la_url_es_invalida(tmp_path):
    consola = Consola(dict(RESPUESTAS_BASE, **{"DATABASE_URL": ["mysql://x", URL_BD]}))
    assert ce.ejecutar(consola, ruta_env=tmp_path / ".env", raiz=tmp_path) == 0
    assert any(l.startswith("ERROR") and "postgresql://" in l for l in consola.salida)
    assert "DATABASE_URL=postgresql+psycopg://" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_produccion_exige_base_y_jwt_propio(tmp_path):
    respuestas = dict(RESPUESTAS_BASE, ENTORNO="produccion", DATABASE_URL=["", URL_BD])
    consola = Consola(respuestas)
    assert ce.ejecutar(consola, ruta_env=tmp_path / ".env", raiz=tmp_path, produccion_por_defecto=True) == 0
    assert any("obligatoria" in l for l in consola.salida)


def test_cancelar_en_el_resumen_no_escribe(tmp_path):
    consola = Consola(dict(RESPUESTAS_BASE, **{"¿Escribir el archivo": False}))
    assert ce.ejecutar(consola, ruta_env=tmp_path / ".env", raiz=tmp_path) == 1
    assert not (tmp_path / ".env").exists()


def test_resumen_indica_lo_desactivado():
    lineas = ce.resumen({"ENTORNO": "desarrollo"})
    texto = "\n".join(lineas)
    assert "WhatsApp" in texto and "correos" in texto
