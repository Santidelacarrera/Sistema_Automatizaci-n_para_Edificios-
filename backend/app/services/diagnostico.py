"""Diagnóstico de configuración para el administrador: qué canales están listos y por qué no.

Sólo expone booleanos y datos no secretos (host SMTP, nombre de instancia, remitente).
Nunca devuelve claves, contraseñas, tokens ni la URL completa de Evolution API.
"""
from ..config import settings
from ..db import engine
from . import email, whatsapp

_JWT_EJEMPLO = "cambiar-en-produccion"


def reporte() -> dict:
    advertencias = []
    if settings.jwt_secret == _JWT_EJEMPLO or len(settings.jwt_secret) < 32:
        advertencias.append("JWT_SECRET usa el valor de ejemplo o tiene menos de 32 caracteres")
    if not settings.whatsapp_webhook_token:
        advertencias.append("WHATSAPP_WEBHOOK_TOKEN vacío: el webhook de WhatsApp rechaza todas las llamadas")
    if settings.celery_eager:
        advertencias.append("CELERY_EAGER=true: correos y tareas se ejecutan en la misma petición (sólo desarrollo)")
    if engine.dialect.name == "sqlite":
        advertencias.append("Base SQLite: sólo para desarrollo")
    return {
        "whatsapp": {
            "configurado": whatsapp.configurado(),
            "motivo": whatsapp.motivo_no_configurado(),
            "url_configurada": bool(settings.evolution_url),
            "instancia": settings.evolution_instance or None,
            "apikey_configurada": bool(settings.evolution_apikey),
            "webhook_token_configurado": bool(settings.whatsapp_webhook_token),
        },
        "correo": {
            "configurado": email.configurado(),
            "motivo": email.motivo_no_configurado(),
            "servidor": settings.smtp_host or None,
            "puerto": settings.smtp_port,
            "remitente": settings.smtp_from,
            "autenticacion": bool(settings.smtp_user and settings.smtp_password),
        },
        "clasificacion_mensajes": {"modo": "LLM" if settings.anthropic_api_key else "palabras clave",
                                   "modelo": settings.llm_model if settings.anthropic_api_key else None},
        "cola": {"modo": "en proceso (CELERY_EAGER)" if settings.celery_eager else "worker Celery",
                 "broker_configurado": bool(settings.redis_url)},
        "base_de_datos": engine.dialect.name,
        "advertencias": advertencias,
    }
