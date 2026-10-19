"""Esqueleto para cámaras Hikvision con ANPR. NO PROBADO contra hardware.

Pendiente: confirmar con el modelo exacto qué evento envía la cámara (ISAPI, JSON o XML, campos de
matrícula y de confianza, y si la confianza viene en 0-100). Hasta entonces el adaptador falla
explícitamente en vez de inventar un formato.
"""
from ..lectura import Lectura


def parsear(payload: dict) -> Lectura:
    raise NotImplementedError("Adaptador Hikvision pendiente: falta confirmar el formato del modelo de cámara")
