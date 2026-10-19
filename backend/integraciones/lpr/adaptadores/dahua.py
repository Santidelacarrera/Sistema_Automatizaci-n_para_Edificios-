"""Esqueleto para cámaras Dahua con ANPR. NO PROBADO contra hardware.

Pendiente: confirmar el evento (ITC / ANPR), campos de placa y de confianza y su escala con el
modelo exacto. Hasta entonces el adaptador falla explícitamente.
"""
from ..lectura import Lectura


def parsear(payload: dict) -> Lectura:
    raise NotImplementedError("Adaptador Dahua pendiente: falta confirmar el formato del modelo de cámara")
