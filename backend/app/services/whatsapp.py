"""WhatsApp vía Evolution API: envío, parseo de webhook y clasificación de intención."""
import json
import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Residente
from .resultado import ENVIADO, ERROR, NO_CONFIGURADO, ResultadoEnvio

INTENCIONES = ("reservar_visita", "reservar_quincho", "consultar_deuda", "otro")
CANAL = "whatsapp"

_KEYWORDS = {
    "consultar_deuda": ("deuda", "saldo", "gasto común", "gasto comun", "cuánto debo", "cuanto debo", "pagar"),
    "reservar_quincho": ("quincho", "parrilla", "asado"),
    "reservar_visita": ("visita", "estacionamiento", "invitado", "qr"),
}


def normalizar_telefono(jid: str) -> str:
    return re.sub(r"\D", "", jid.split("@")[0])


def parse_evolution(payload: dict) -> tuple[str, str] | None:
    """Devuelve (telefono, texto) de un evento messages.upsert; None si no aplica."""
    if str(payload.get("event", "")).lower().replace("_", ".") != "messages.upsert":
        return None
    data = payload.get("data") or {}
    if isinstance(data, list):
        data = data[0] if data else {}
    key = data.get("key") or {}
    if key.get("fromMe"):
        return None
    msg = data.get("message") or {}
    texto = msg.get("conversation") or (msg.get("extendedTextMessage") or {}).get("text") or ""
    jid = key.get("remoteJid", "")
    if not texto or "@g.us" in jid:  # ignora grupos y mensajes sin texto
        return None
    return normalizar_telefono(jid), texto.strip()


def id_mensaje(payload: dict) -> str:
    """Id único del mensaje de Evolution (para no procesarlo dos veces); vacío si no viene."""
    data = payload.get("data") or {}
    if isinstance(data, list):
        data = data[0] if data else {}
    return str((data.get("key") or {}).get("id") or "")[:120]


def clasificar_keywords(texto: str) -> str:
    t = texto.lower()
    for intent, kws in _KEYWORDS.items():
        if any(k in t for k in kws):
            return intent
    return "otro"


def clasificar(texto: str) -> str:
    """LLM si hay API key; ante cualquier fallo, reglas por palabras clave."""
    if settings.anthropic_api_key:
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages", timeout=10,
                headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"},
                json={"model": settings.llm_model, "max_tokens": 20,
                      "system": f"Clasifica el mensaje de un residente en UNA de: {', '.join(INTENCIONES)}. "
                                "Responde sólo la etiqueta.",
                      "messages": [{"role": "user", "content": texto[:1000]}]})
            r.raise_for_status()
            etiqueta = r.json()["content"][0]["text"].strip().lower()
            if etiqueta in INTENCIONES:
                return etiqueta
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError):
            pass
    return clasificar_keywords(texto)


def identificar_residente(db: Session, telefono: str) -> Residente | None:
    """Match por teléfono; tolera con/sin código de país comparando los últimos 9 dígitos."""
    cola = telefono[-9:]
    if len(cola) != 9 or not cola.isdigit():
        return None
    candidatos = db.scalars(select(Residente).where(Residente.telefono.like(f"%{cola}"),
                                                   Residente.activo.is_(True)).limit(2)).all()
    return candidatos[0] if len(candidatos) == 1 else None


def faltantes() -> list[str]:
    if settings.whatsapp_cloud_token and settings.whatsapp_phone_number_id:
        return []
    """Nombres de las variables de entorno que faltan para enviar. Nunca incluye sus valores."""
    requeridas = {"EVOLUTION_URL": settings.evolution_url, "EVOLUTION_INSTANCE": settings.evolution_instance,
                  "EVOLUTION_APIKEY": settings.evolution_apikey}
    return [nombre for nombre, valor in requeridas.items() if not valor]


def configurado() -> bool:
    return not faltantes()


def motivo_no_configurado() -> str:
    faltan = faltantes()
    return f"Falta {', '.join(faltan)} en .env (Evolution API no configurada)" if faltan else ""


def parse_cloud_webhook(payload: dict) -> tuple[str, str, str] | None:
    """Devuelve (telefono, texto, msg_id) de un webhook de WhatsApp Business Cloud API (Meta)."""
    try:
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                for m in (change.get("value") or {}).get("messages") or []:
                    if m.get("type") == "text":
                        tel = normalizar_telefono(str(m.get("from", "")))
                        txt = str((m.get("text") or {}).get("body") or "").strip()
                        mid = str(m.get("id") or "")[:120]
                        if tel and txt:
                            return tel, txt, mid
    except (AttributeError, TypeError):
        return None
    return None


def verificar_firma_meta(cuerpo: bytes, header_sig: str | None) -> bool:
    """Verifica firma `X-Hub-Signature-256: sha256=...` de Meta con `WHATSAPP_APP_SECRET`."""
    import hashlib
    import hmac
    if not settings.whatsapp_app_secret or not header_sig or not header_sig.startswith("sha256="):
        return False
    esperada = hmac.new(settings.whatsapp_app_secret.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, header_sig.removeprefix("sha256="))


def enviar(telefono: str, texto: str) -> ResultadoEnvio:
    if telefono and settings.whatsapp_cloud_token and settings.whatsapp_phone_number_id:
        try:
            r = httpx.post(
                f"https://graph.facebook.com/v20.0/{settings.whatsapp_phone_number_id}/messages",
                headers={"Authorization": f"Bearer {settings.whatsapp_cloud_token}"},
                timeout=10,
                json={"messaging_product": "whatsapp", "to": normalizar_telefono(telefono),
                      "type": "text", "text": {"body": texto}},
            )
        except httpx.TimeoutException:
            return ResultadoEnvio(CANAL, ERROR, "WhatsApp Cloud API no respondió a tiempo", transitorio=True)
        except httpx.HTTPError as e:
            return ResultadoEnvio(CANAL, ERROR, f"No se pudo conectar con WhatsApp Cloud API ({e.__class__.__name__})",
                                  transitorio=True)
        if r.is_success:
            return ResultadoEnvio(CANAL, ENVIADO)
        return ResultadoEnvio(CANAL, ERROR, f"WhatsApp Cloud API respondió HTTP {r.status_code}",
                              transitorio=r.status_code >= 500)
    """Envía un mensaje y devuelve el resultado explícito. No lanza excepciones por fallos de red."""
    if not telefono:
        return ResultadoEnvio(CANAL, NO_CONFIGURADO, "El residente no tiene teléfono registrado")
    if not configurado():
        return ResultadoEnvio(CANAL, NO_CONFIGURADO, motivo_no_configurado())
    try:
        r = httpx.post(f"{settings.evolution_url}/message/sendText/{settings.evolution_instance}",
                       headers={"apikey": settings.evolution_apikey}, timeout=10,
                       json={"number": telefono, "text": texto})
    except httpx.TimeoutException:
        return ResultadoEnvio(CANAL, ERROR, "Evolution API no respondió a tiempo", transitorio=True)
    except httpx.HTTPError as e:
        return ResultadoEnvio(CANAL, ERROR, f"No se pudo conectar con Evolution API ({e.__class__.__name__})",
                              transitorio=True)
    if r.is_success:
        return ResultadoEnvio(CANAL, ENVIADO)
    return ResultadoEnvio(CANAL, ERROR, f"Evolution API respondió HTTP {r.status_code}", transitorio=r.status_code >= 500)


def enviar_imagen(telefono: str, png: bytes, leyenda: str = "") -> ResultadoEnvio:
    """Envía una imagen PNG (p. ej. el QR de una visita) por Evolution API."""
    import base64
    if not telefono:
        return ResultadoEnvio(CANAL, NO_CONFIGURADO, "El residente no tiene teléfono registrado")
    if not configurado():
        return ResultadoEnvio(CANAL, NO_CONFIGURADO, motivo_no_configurado())
    try:
        r = httpx.post(f"{settings.evolution_url}/message/sendMedia/{settings.evolution_instance}",
                       headers={"apikey": settings.evolution_apikey}, timeout=20,
                       json={"number": telefono, "mediatype": "image", "mimetype": "image/png",
                             "media": base64.b64encode(png).decode(), "fileName": "qr-visita.png",
                             "caption": leyenda})
    except httpx.TimeoutException:
        return ResultadoEnvio(CANAL, ERROR, "Evolution API no respondió a tiempo", transitorio=True)
    except httpx.HTTPError as e:
        return ResultadoEnvio(CANAL, ERROR, f"No se pudo conectar con Evolution API ({e.__class__.__name__})",
                              transitorio=True)
    if r.is_success:
        return ResultadoEnvio(CANAL, ENVIADO)
    return ResultadoEnvio(CANAL, ERROR, f"Evolution API respondió HTTP {r.status_code}", transitorio=r.status_code >= 500)
