"""Adaptadores por marca. Cada módulo expone ``parsear(payload) -> Lectura``."""
from importlib import import_module

_ADAPTADORES = {"generico": "generico", "hikvision": "hikvision", "dahua": "dahua"}


def cargar(nombre: str):
    if nombre not in _ADAPTADORES:
        raise RuntimeError(f"Adaptador desconocido: {nombre}. Opciones: {', '.join(_ADAPTADORES)}")
    return import_module(f".{_ADAPTADORES[nombre]}", __package__).parsear
