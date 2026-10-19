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


# Formatos de patente chilena de 6 caracteres: antiguo AA1234 (2 letras + 4 dígitos) y nuevo BCDF12
# (4 letras + 2 dígitos). Motos y otros formatos se aceptan como 'otro' si tienen entre 5 y 7 caracteres.
_RE_CHILE_ANTIGUO = re.compile(r"[A-Z]{2}\d{4}")
_RE_CHILE_NUEVO = re.compile(r"[A-Z]{4}\d{2}")


def formato_patente(patente: str) -> str:
    if _RE_CHILE_NUEVO.fullmatch(patente):
        return "chileno_nuevo"
    if _RE_CHILE_ANTIGUO.fullmatch(patente):
        return "chileno_antiguo"
    return "otro"


def validar(lectura: Lectura) -> Lectura:
    if not 5 <= len(lectura.patente) <= 7 or not re.fullmatch(r"[A-Z0-9]+", lectura.patente):
        raise LecturaInvalida(f"Patente inválida: '{lectura.patente}'")
    if not 0.0 <= lectura.confianza <= 1.0:
        raise LecturaInvalida("La confianza debe estar entre 0 y 1")
    return lectura
