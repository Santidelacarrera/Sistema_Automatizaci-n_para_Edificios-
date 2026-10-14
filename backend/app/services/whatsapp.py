"""WhatsApp vía Evolution API: envío, parseo de webhook y clasificación de intención."""
import json
import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Residente

INTENCIONES = ("reservar_visita", "reservar_quincho", "consultar_deuda", "otro")

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
    for r in db.scalars(select(Residente).where(Residente.telefono.like(f"%{cola}"), Residente.activo.is_(True))):
        return r
    return None


def enviar(telefono: str, texto: str) -> bool:
    if not (settings.evolution_url and settings.evolution_instance):
        return False  # modo desarrollo: no hay gateway configurado
    try:
        r = httpx.post(f"{settings.evolution_url}/message/sendText/{settings.evolution_instance}",
                       headers={"apikey": settings.evolution_apikey}, timeout=10,
                       json={"number": telefono, "text": texto})
        return r.is_success
    except httpx.HTTPError:
        return False
