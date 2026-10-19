"""Formato genérico (JSON): el puente de la cámara ya entrega patente y confianza.

    {"patente": "BB-CD-12", "confianza": 0.97, "camara": "entrada-1", "fecha": "2026-10-19T12:00:00Z"}

``confianza`` es un decimal entre 0 y 1. Si la cámara entrega porcentajes (0-100), el puente debe
convertirlos antes de llamar aquí: no se adivina la escala.
"""
from datetime import datetime

from ..lectura import Lectura, LecturaInvalida, normalizar_patente


def parsear(payload: dict) -> Lectura:
    if not isinstance(payload, dict):
        raise LecturaInvalida("El cuerpo debe ser un objeto JSON")
    try:
        confianza = float(payload["confianza"])
    except (KeyError, TypeError, ValueError):
        raise LecturaInvalida("Falta 'confianza' numérica")
    fecha = None
    if payload.get("fecha"):
        try:
            fecha = datetime.fromisoformat(str(payload["fecha"]).replace("Z", "+00:00"))
        except ValueError:
            raise LecturaInvalida("'fecha' no es ISO 8601")
    return Lectura(patente=normalizar_patente(str(payload.get("patente", ""))), confianza=confianza,
                   camara=str(payload.get("camara", ""))[:40], fecha=fecha)
