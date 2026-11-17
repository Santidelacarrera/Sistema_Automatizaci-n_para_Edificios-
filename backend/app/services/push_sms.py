"""Adaptadores para notificaciones Push (FCM / Web Push) y SMS (Twilio REST API)."""
import httpx

from ..config import settings
from .resultado import ENVIADO, ERROR, NO_CONFIGURADO, ResultadoEnvio


def push_configurado() -> bool:
    return bool(settings.fcm_server_key)


def sms_configurado() -> bool:
    return bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number)


def enviar_push(token_o_endpoint: str, titulo: str, cuerpo: str) -> ResultadoEnvio:
    if not token_o_endpoint:
        return ResultadoEnvio("push", NO_CONFIGURADO, "El dispositivo no tiene token o endpoint Push")
    if not push_configurado():
        return ResultadoEnvio("push", NO_CONFIGURADO, "Falta FCM_SERVER_KEY en .env")
    try:
        r = httpx.post(
            "https://fcm.googleapis.com/fcm/send",
            headers={"Authorization": f"key={settings.fcm_server_key}", "Content-Type": "application/json"},
            timeout=10,
            json={"to": token_o_endpoint, "notification": {"title": titulo, "body": cuerpo}},
        )
    except httpx.TimeoutException:
        return ResultadoEnvio("push", ERROR, "FCM no respondió a tiempo", transitorio=True)
    except httpx.HTTPError as e:
        return ResultadoEnvio("push", ERROR, f"Error de red con FCM ({e.__class__.__name__})", transitorio=True)
    if r.is_success:
        return ResultadoEnvio("push", ENVIADO)
    return ResultadoEnvio("push", ERROR, f"FCM respondió HTTP {r.status_code}", transitorio=r.status_code >= 500)


def enviar_sms(telefono: str, mensaje: str) -> ResultadoEnvio:
    if not telefono:
        return ResultadoEnvio("sms", NO_CONFIGURADO, "El residente no tiene teléfono registrado")
    if not sms_configurado():
        return ResultadoEnvio("sms", NO_CONFIGURADO, "Faltan TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER en .env")
    destino = telefono if telefono.startswith("+") else f"+{telefono}"
    try:
        r = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=10,
            data={"From": settings.twilio_from_number, "To": destino, "Body": mensaje[:1600]},
        )
    except httpx.TimeoutException:
        return ResultadoEnvio("sms", ERROR, "Twilio no respondió a tiempo", transitorio=True)
    except httpx.HTTPError as e:
        return ResultadoEnvio("sms", ERROR, f"Error de red con Twilio ({e.__class__.__name__})", transitorio=True)
    if r.is_success:
        return ResultadoEnvio("sms", ENVIADO)
    return ResultadoEnvio("sms", ERROR, f"Twilio respondió HTTP {r.status_code}", transitorio=r.status_code >= 500)
