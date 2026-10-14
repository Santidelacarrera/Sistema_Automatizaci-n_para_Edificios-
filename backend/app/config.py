from datetime import datetime, timezone

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    jwt_secret: str = "cambiar-en-produccion"
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


def utcnow() -> datetime:
    """Datetime UTC sin tzinfo (consistente entre SQLite y PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
