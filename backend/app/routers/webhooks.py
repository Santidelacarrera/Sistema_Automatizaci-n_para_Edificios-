import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import MensajeWA
from ..services import finance, wa_conversacion, whatsapp

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
    payload = await request.json()
    parsed = whatsapp.parse_evolution(payload)
    if not parsed:
        return {"ignorado": True}
    telefono, texto = parsed
    msg_id = whatsapp.id_mensaje(payload)
    if msg_id:  # Evolution reintenta los webhooks: un mismo mensaje no se procesa dos veces
        db.add(MensajeWA(msg_id=msg_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"duplicado": True}
    r = whatsapp.identificar_residente(db, telefono)
    if not r:
        envio = whatsapp.enviar(telefono, "No encontramos tu número en ningún edificio. Contacta a la administración.")
        return {"residente": None, "envio": envio.estado}
    # Conversación en curso (p. ej. confirmando una visita): se sigue antes de clasificar el mensaje.
    respuestas = wa_conversacion.continuar(db, r, telefono, texto)
    intent = "conversacion" if respuestas is not None else whatsapp.clasificar(texto)
    if respuestas is None and intent == "reservar_visita":
        respuestas = wa_conversacion.iniciar_visita(db, r, telefono, texto)
    if respuestas is not None:
        db.commit()
        envios = []
        for resp in respuestas:
            res = whatsapp.enviar_imagen(telefono, resp.png, resp.texto) if resp.png else whatsapp.enviar(telefono, resp.texto)
            envios.append(res.estado)
        return {"residente": r.id, "intent": intent, "respuesta": respuestas[0].texto, "envio": envios[-1]}
    if intent == "consultar_deuda":
        resp = f"Tu deuda actual es ${finance.deuda_unidad(db, r.unidad_id):,.0f}."
    elif intent == "reservar_quincho":
        resp = "Indícanos fecha y horario para reservar el quincho; validaremos la normativa del edificio."
    else:
        resp = AYUDA.format(nombre=r.nombre.split()[0])
    envio = whatsapp.enviar(telefono, resp)
    return {"residente": r.id, "intent": intent, "respuesta": resp, "envio": envio.estado,
            "motivo_envio": envio.motivo}
