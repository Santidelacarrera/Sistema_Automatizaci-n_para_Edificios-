from datetime import datetime, timezone

from pydantic_settings import BaseSettings, SettingsConfigDict


JWT_POR_DEFECTO = "cambiar-en-produccion"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    entorno: str = "desarrollo"  # desarrollo | produccion
    cors_origins: str = "http://localhost:3000"  # separados por coma
    database_url: str = "sqlite:///./dev.db"
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


def utcnow() -> datetime:
    """Datetime UTC sin tzinfo (consistente entre SQLite y PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
