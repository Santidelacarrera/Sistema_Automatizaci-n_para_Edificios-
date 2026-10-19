"""Verifica, una por una, las conexiones configuradas en .env. No envía mensajes ni modifica datos.

    python scripts/verificar_conexiones.py            # lee la .env de la raíz
    python scripts/verificar_conexiones.py --env ruta/.env

Cada prueba responde OK, FALLÓ o NO CONFIGURADO con el motivo y qué hacer. Ningún secreto se imprime:
las cadenas de conexión y las claves se borran de los mensajes de error antes de mostrarlos.
Código de salida: 0 si nada falló, 1 si algún chequeo falló.
"""
import argparse
import smtplib
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

import httpx  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

OK, FALLO, NO_CONFIGURADO = "OK", "FALLÓ", "NO CONFIGURADO"
TIMEOUT = 8


@dataclass(frozen=True)
class Resultado:
    nombre: str
    estado: str
    mensaje: str


def limpiar(texto: str, secretos: list[str]) -> str:
    """Quita de un mensaje cualquier secreto que pudiera aparecer (claves, cadenas de conexión)."""
    for s in sorted({x for x in secretos if x}, key=len, reverse=True):
        texto = texto.replace(s, "****")
    return texto


def _secretos(cfg) -> list[str]:
    extra = [cfg.jwt_secret, cfg.evolution_apikey, cfg.smtp_password, cfg.anthropic_api_key,
             cfg.whatsapp_webhook_token]
    if cfg.database_url:
        try:
            url = make_url(cfg.database_url)
            extra += [url.password or "", cfg.database_url]
        except Exception:  # cadena mal formada: se borra completa
            extra.append(cfg.database_url)
    return extra


def chequear_jwt(cfg) -> Resultado:
    from app.config import JWT_POR_DEFECTO, validar_para_arranque
    if cfg.jwt_secret == JWT_POR_DEFECTO:
        return Resultado("Clave de sesiones (JWT_SECRET)", FALLO, "Es el valor de ejemplo. Ejecute el asistente para generar uno.")
    try:
        validar_para_arranque(cfg)
    except RuntimeError as e:
        return Resultado("Clave de sesiones (JWT_SECRET)", FALLO, str(e))
    return Resultado("Clave de sesiones (JWT_SECRET)", OK, f"largo {len(cfg.jwt_secret)} caracteres")


def chequear_webhook(cfg) -> Resultado:
    nombre = "Token del webhook de WhatsApp"
    if not cfg.whatsapp_webhook_token:
        return Resultado(nombre, NO_CONFIGURADO, "El webhook rechazará todas las llamadas. Ejecute el asistente.")
    if len(cfg.whatsapp_webhook_token) < 32:
        return Resultado(nombre, FALLO, "Muy corto (mínimo 32 caracteres). Vuelva a generarlo con el asistente.")
    return Resultado(nombre, OK, f"configurado (largo {len(cfg.whatsapp_webhook_token)})")


def chequear_base(cfg) -> Resultado:
    nombre = "Base de datos"
    if not cfg.database_url:
        return Resultado(nombre, NO_CONFIGURADO, "Se usaría SQLite local (sólo desarrollo). Ejecute el asistente si usa Supabase.")
    try:
        engine = create_engine(cfg.database_url, connect_args=_args_conexion(cfg.database_url), pool_pre_ping=True)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as e:
        return Resultado(nombre, FALLO, _explicar_error_base(limpiar(str(e), _secretos(cfg))))
    return Resultado(nombre, OK, "conexión y SELECT 1 correctos")


def _args_conexion(url: str) -> dict:
    return {"check_same_thread": False} if url.startswith("sqlite") else {"connect_timeout": 6}


def _explicar_error_base(mensaje: str) -> str:
    pistas = {
        "password authentication failed": "Contraseña incorrecta. Revise la clave en el panel de Supabase.",
        "could not translate host": "No se encuentra el servidor. Revise que la cadena se copió completa.",
        "Tenant or user not found": "Usuario del pooler incorrecto: use la cadena 'Session pooler' de Supabase.",
        "timeout": "La base no respondió a tiempo. Revise la red o el firewall.",
        "SSL": "La base exige SSL: agregue sslmode=require a la cadena (el asistente lo hace en Supabase).",
    }
    for clave, ayuda in pistas.items():
        if clave.lower() in mensaje.lower():
            return f"{ayuda} Detalle: {mensaje[:200]}"
    return mensaje[:300]


def chequear_migraciones(cfg) -> Resultado:
    nombre = "Migraciones (Alembic)"
    if not cfg.database_url:
        return Resultado(nombre, NO_CONFIGURADO, "Sin base configurada.")
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        acfg = Config(str(RAIZ / "backend" / "alembic.ini"))
        acfg.set_main_option("script_location", str(RAIZ / "backend" / "migrations"))
        head = ScriptDirectory.from_config(acfg).get_current_head()
        engine = create_engine(cfg.database_url, connect_args=_args_conexion(cfg.database_url))
        with engine.connect() as c:
            actual = MigrationContext.configure(c).get_current_revision()
        engine.dispose()
    except Exception as e:
        return Resultado(nombre, FALLO, limpiar(str(e), _secretos(cfg))[:300])
    if actual == head:
        return Resultado(nombre, OK, f"al día (revisión {head})")
    return Resultado(nombre, FALLO, "Faltan migraciones. Ejecute:  cd backend && alembic upgrade head")


def chequear_redis(cfg) -> Resultado:
    nombre = "Redis (cola de tareas)"
    try:
        import redis
        redis.Redis.from_url(cfg.redis_url, socket_timeout=3, socket_connect_timeout=3).ping()
    except Exception as e:
        nota = "Sólo es necesario con el worker de Celery (producción)." if cfg.entorno == "produccion" else \
            "Opcional en desarrollo: CELERY_EAGER=true no lo necesita."
        return Resultado(nombre, FALLO if cfg.entorno == "produccion" else NO_CONFIGURADO,
                         f"No responde ({e.__class__.__name__}). {nota}")
    return Resultado(nombre, OK, "responde PING")


def chequear_smtp(cfg) -> Resultado:
    nombre = "Correo (SMTP)"
    if not cfg.smtp_host:
        return Resultado(nombre, NO_CONFIGURADO, "Sin SMTP_HOST: los correos quedan 'no configurados'.")
    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=TIMEOUT) as s:
            s.ehlo()
            if s.has_extn("starttls"):
                s.starttls()
                s.ehlo()
            if cfg.smtp_user:
                s.login(cfg.smtp_user, cfg.smtp_password)
            s.noop()
    except smtplib.SMTPAuthenticationError:
        return Resultado(nombre, FALLO, "El servidor rechazó el usuario o la clave SMTP (no se muestran por seguridad). "
                                        "En SES use las credenciales SMTP de la consola, no las de AWS.")
    except (smtplib.SMTPException, OSError) as e:
        return Resultado(nombre, FALLO, limpiar(f"No se pudo conectar ({e.__class__.__name__}).", _secretos(cfg)))
    return Resultado(nombre, OK, f"conexión y login correctos en {cfg.smtp_host}:{cfg.smtp_port} (no se envió nada)")


def chequear_evolution(cfg) -> Resultado:
    nombre = "WhatsApp (Evolution API)"
    if not (cfg.evolution_url and cfg.evolution_instance and cfg.evolution_apikey):
        return Resultado(nombre, NO_CONFIGURADO, "Faltan EVOLUTION_URL, EVOLUTION_INSTANCE o EVOLUTION_APIKEY.")
    url = f"{cfg.evolution_url.rstrip('/')}/instance/connectionState/{cfg.evolution_instance}"
    try:
        r = httpx.get(url, headers={"apikey": cfg.evolution_apikey}, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        return Resultado(nombre, FALLO, limpiar(f"Sin respuesta del servidor ({e.__class__.__name__}).", _secretos(cfg)))
    if r.status_code in (401, 403):
        return Resultado(nombre, FALLO, "La API key de Evolution fue rechazada.")
    if r.status_code == 404:
        return Resultado(nombre, FALLO, "La instancia no existe con ese nombre. Revise EVOLUTION_INSTANCE.")
    if r.status_code != 200:
        return Resultado(nombre, FALLO, f"Evolution respondió HTTP {r.status_code}.")
    try:
        estado = (r.json().get("instance") or {}).get("state", "desconocido")
    except ValueError:
        estado = "desconocido"
    if estado == "open":
        return Resultado(nombre, OK, "instancia conectada (estado 'open')")
    return Resultado(nombre, FALLO, f"La instancia está en estado '{estado}'. Escanee el código QR de la instancia.")


def chequear_anthropic(cfg) -> Resultado:
    nombre = "Clasificación con IA (Anthropic)"
    if not cfg.anthropic_api_key:
        return Resultado(nombre, NO_CONFIGURADO, "Sin clave: los mensajes se clasifican por palabras clave.")
    try:
        r = httpx.get("https://api.anthropic.com/v1/models", timeout=TIMEOUT,
                      headers={"x-api-key": cfg.anthropic_api_key, "anthropic-version": "2023-06-01"})
    except httpx.HTTPError as e:
        return Resultado(nombre, FALLO, f"Sin respuesta ({e.__class__.__name__}).")
    if r.status_code == 200:
        return Resultado(nombre, OK, "clave válida")
    if r.status_code in (401, 403):
        return Resultado(nombre, FALLO, "La clave fue rechazada.")
    return Resultado(nombre, FALLO, f"Anthropic respondió HTTP {r.status_code}.")


def verificar_todo(cfg) -> list[Resultado]:
    return [chequear_jwt(cfg), chequear_webhook(cfg), chequear_base(cfg), chequear_migraciones(cfg),
            chequear_redis(cfg), chequear_smtp(cfg), chequear_evolution(cfg), chequear_anthropic(cfg)]


def codigo_salida(resultados: list[Resultado]) -> int:
    return 1 if any(r.estado == FALLO for r in resultados) else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Verifica las conexiones configuradas en .env (sin enviar mensajes).")
    p.add_argument("--env", default=str(RAIZ / ".env"))
    a = p.parse_args(argv)
    ruta = Path(a.env)
    if not ruta.exists():
        print(f"No existe {ruta}. Ejecute primero: python scripts/configurar_entorno.py", file=sys.stderr)
        return 2
    from app.config import Settings
    cfg = Settings(_env_file=ruta)
    resultados = verificar_todo(cfg)
    marcas = {OK: "[OK]", FALLO: "[FALLÓ]", NO_CONFIGURADO: "[NO CONFIGURADO]"}
    for r in resultados:
        print(f"{marcas[r.estado]:<18} {r.nombre}: {r.mensaje}")
    print("\nTodo lo marcado OK funciona. FALLÓ requiere corregir la configuración antes de usar esa parte.")
    return codigo_salida(resultados)


if __name__ == "__main__":
    sys.exit(main())
