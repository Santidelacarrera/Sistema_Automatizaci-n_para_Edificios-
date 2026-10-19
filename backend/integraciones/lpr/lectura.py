"""Formato interno de una lectura de patente, independiente de la marca de la cámara."""
import re
from dataclasses import dataclass
from datetime import datetime


class LecturaInvalida(ValueError):
    """La cámara envió algo que no es una lectura utilizable (se responde 422, no se abre)."""


@dataclass(frozen=True)
class Lectura:
    patente: str          # normalizada: mayúsculas, sin guiones ni espacios
    confianza: float      # 0.0 a 1.0
    camara: str = ""
    fecha: datetime | None = None


def normalizar_patente(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (texto or "").upper())


def validar(lectura: Lectura) -> Lectura:
    if not 5 <= len(lectura.patente) <= 7 or not re.fullmatch(r"[A-Z0-9]+", lectura.patente):
        raise LecturaInvalida(f"Patente inválida: '{lectura.patente}'")
    if not 0.0 <= lectura.confianza <= 1.0:
        raise LecturaInvalida("La confianza debe estar entre 0 y 1")
    return lectura
