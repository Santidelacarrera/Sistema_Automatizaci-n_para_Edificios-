import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Edificio
from ..services import access, finance, whatsapp

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

AYUDA = ("Hola {nombre} 👋 Puedo ayudarte con:\n• Reservar visita (ej: «visita Juan mañana 18:00»)\n"
         "• Reservar quincho\n• Consultar tu deuda")


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, x_webhook_token: str | None = Header(None),
                           db: Session = Depends(get_db)):
    # Token compartido configurado en Evolution API; sin él, cualquiera podría suplantar residentes.
    if not settings.whatsapp_webhook_token or not x_webhook_token or \
            not hmac.compare_digest(settings.whatsapp_webhook_token, x_webhook_token):
        raise HTTPException(401, "Webhook no autorizado")
    parsed = whatsapp.parse_evolution(await request.json())
    if not parsed:
        return {"ignorado": True}
    telefono, texto = parsed
    r = whatsapp.identificar_residente(db, telefono)
    if not r:
        envio = whatsapp.enviar(telefono, "No encontramos tu número en ningún edificio. Contacta a la administración.")
        return {"residente": None, "envio": envio.estado}
    intent = whatsapp.clasificar(texto)
    if intent == "consultar_deuda":
        resp = f"Tu deuda actual es ${finance.deuda_unidad(db, r.unidad_id):,.0f}."
    elif intent == "reservar_visita":
        ed = db.get(Edificio, r.edificio_id)
        libres = ed.cupos_visitas - access.cupos_ocupados(db, ed.id, *_ahora_rango())
        resp = (f"Hay {libres} cupo(s) de visita disponibles ahora. Para reservar usa la app o indícanos "
                "nombre, fecha y hora de tu visita.")
    elif intent == "reservar_quincho":
        resp = "Indícanos fecha y horario para reservar el quincho; validaremos la normativa del edificio."
    else:
        resp = AYUDA.format(nombre=r.nombre.split()[0])
    envio = whatsapp.enviar(telefono, resp)
    return {"residente": r.id, "intent": intent, "respuesta": resp, "envio": envio.estado,
            "motivo_envio": envio.motivo}


def _ahora_rango():
    from datetime import timedelta
    from ..config import utcnow
    return utcnow(), utcnow() + timedelta(minutes=1)
