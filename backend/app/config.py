from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


JWT_POR_DEFECTO = "cambiar-en-produccion"


_RAIZ = Path(__file__).resolve().parents[2]  # raíz del repositorio (en Docker no existe ese archivo: no pasa nada)


class Settings(BaseSettings):
    # Primero el .env de la raíz (el que usa Docker Compose y el asistente), luego el del directorio actual.
    model_config = SettingsConfigDict(env_file=(_RAIZ / ".env", ".env"), extra="ignore")

    entorno: str = "desarrollo"  # desarrollo | produccion
    cors_origins: str = "http://localhost:3000"  # separados por coma
    database_url: str = "sqlite:///./dev.db"
    db_pool_size: int = 5      # conexiones por proceso (API, worker y beat abren las suyas)
    db_max_overflow: int = 5   # conexiones extra en picos; el pooler de Supabase limita el total
    login_max_intentos: int = 5  # fallos por cuenta antes de bloquear
    login_max_intentos_ip: int = 30  # fallos por IP antes de bloquear
    login_ventana_min: int = 15  # ventana y duración del bloqueo
    zona_horaria: str = "America/Santiago"  # hora de pared de los 4 edificios
    jwt_secret: str = JWT_POR_DEFECTO
    jwt_expire_minutes: int = 60 * 8
    redis_url: str = "redis://localhost:6379/0"
    celery_eager: bool = True  # sin broker: ejecuta tareas en el mismo proceso

    # WhatsApp (Evolution API)
    evolution_url: str = ""
    evolution_instance: str = ""
    evolution_apikey: str = ""
    whatsapp_webhook_token: str = ""

    # LLM opcional para clasificar mensajes (Anthropic)
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-5-5"

    # SMTP / SES
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "administracion@example.com"


settings = Settings()


def validar_para_arranque(cfg: Settings = settings) -> None:
    """Se niega a arrancar con una configuración insegura para producción."""
    if cfg.entorno not in ("desarrollo", "produccion"):
        raise RuntimeError("ENTORNO debe ser 'desarrollo' o 'produccion'")
    if cfg.entorno == "produccion":
        if cfg.jwt_secret == JWT_POR_DEFECTO or len(cfg.jwt_secret) < 32:
            raise RuntimeError("En producción JWT_SECRET debe ser propio y tener al menos 32 caracteres")
        if cfg.database_url.startswith("sqlite"):
            raise RuntimeError("En producción no se usa SQLite: configure DATABASE_URL (PostgreSQL)")


def ahora_local() -> datetime:
    """Hora de pared en la zona del negocio, sin tzinfo.

    Las fechas que escribe una persona (reservas, ventanas de visita, horarios de reglas) se
    guardan y comparan en esta hora local. Los instantes técnicos (bitácora, lecturas, JWT)
    siguen en UTC con ``utcnow()``.
    """
    return datetime.now(ZoneInfo(settings.zona_horaria)).replace(tzinfo=None)


def hoy_local():
    return ahora_local().date()


def utcnow() -> datetime:
    """Datetime UTC sin tzinfo (consistente entre SQLite y PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
