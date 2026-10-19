"""Formato canónico de las credenciales de acceso (stickers UHF, llaveros RC522, patentes).

Un solo formato por tipo, siempre en mayúsculas, para que la búsqueda y la unicidad sean exactas:

  epc      sticker UHF EPC Gen2: hex de 12 a 24 caracteres, longitud par. Ej. ``E2801170A1B2C3D4``.
  wiegand  código Wiegand 26 o 34 (lo que emite un lector que decodifica el sticker):
           ``W26:<facility>:<card>`` o ``W34:<facility>:<card>``, con valores decimales.
           Ej. ``W26:42:12345``. Rangos: W26 facility 0-255, card 0-65535;
           W34 facility 0-65535, card 0-4294967295.
  rc522    UID de llavero MIFARE (13,56 MHz): hex de 8 a 20 caracteres (sólo puerta peatonal).

El conciliador de cartolas y los nombres de patente no cambian: esto es sólo para credenciales.
"""
import re

_RE_HEX = re.compile(r"[0-9A-F]+")
_RE_WIEGAND = re.compile(r"W(26|34):(\d{1,10}):(\d{1,10})")
RANGOS = {"26": (255, 65535), "34": (65535, 4294967295)}


class CredencialInvalida(ValueError):
    """Formato de credencial no reconocido o fuera de rango. El mensaje es para la bitácora y el panel."""


def normalizar_epc(texto: str) -> str:
    limpio = re.sub(r"[\s:-]", "", texto or "").upper()
    if not _RE_HEX.fullmatch(limpio) or not 12 <= len(limpio) <= 24 or len(limpio) % 2:
        raise CredencialInvalida("EPC inválido: 12 a 24 caracteres hexadecimales (longitud par)")
    return limpio


def normalizar_wiegand(texto: str) -> str:
    m = _RE_WIEGAND.fullmatch((texto or "").strip().upper())
    if not m:
        raise CredencialInvalida("Wiegand inválido: use W26:<facility>:<card> o W34:<facility>:<card>")
    bits, fac, card = m.group(1), int(m.group(2)), int(m.group(3))
    max_fac, max_card = RANGOS[bits]
    if fac > max_fac or card > max_card:
        raise CredencialInvalida(f"Wiegand {bits} fuera de rango (facility ≤ {max_fac}, card ≤ {max_card})")
    return f"W{bits}:{fac}:{card}"


def normalizar_rc522(texto: str) -> str:
    limpio = re.sub(r"\s", "", texto or "").upper()
    if not _RE_HEX.fullmatch(limpio) or not 8 <= len(limpio) <= 20:
        raise CredencialInvalida("UID de llavero inválido: 8 a 20 caracteres hexadecimales")
    return limpio


def normalizar(texto: str, formato: str) -> str:
    """Canoniza ``texto`` para el formato indicado ('epc', 'wiegand', 'rc522')."""
    if formato == "epc":
        return normalizar_epc(texto)
    if formato == "wiegand":
        return normalizar_wiegand(texto)
    if formato == "rc522":
        return normalizar_rc522(texto)
    raise CredencialInvalida(f"Formato desconocido: {formato}")


def detectar_formato(texto: str) -> str:
    """Adivina el formato de un código suelto (lo usa el endpoint de validación cuando no llega el tipo)."""
    t = (texto or "").strip().upper()
    if t.startswith("W26:") or t.startswith("W34:"):
        return "wiegand"
    if _RE_HEX.fullmatch(re.sub(r"[\s:-]", "", t)) and 12 <= len(re.sub(r"[\s:-]", "", t)) <= 24:
        return "epc"
    return "rc522"
