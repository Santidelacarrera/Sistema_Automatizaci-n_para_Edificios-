"""Validación y normalización de datos de contacto e identificación (Chile: RUT, teléfono con +56)."""
import re

_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def rut_normalizar(rut: str) -> str:
    """'12.345.678-5' / '12345678-5' / '123456785' -> '12345678-5' (sin puntos, DV en mayúscula)."""
    limpio = re.sub(r"[.\-\s]", "", rut).upper()
    return f"{limpio[:-1]}-{limpio[-1:]}" if len(limpio) > 1 else limpio


def rut_valido(rut: str) -> bool:
    """Valida el dígito verificador (módulo 11)."""
    limpio = re.sub(r"[.\-\s]", "", rut).upper()
    if not re.fullmatch(r"\d{7,8}[\dK]", limpio):
        return False
    cuerpo, dv = limpio[:-1], limpio[-1]
    suma, factor = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    esperado = {11: "0", 10: "K"}.get(resto, str(resto))
    return dv == esperado


def rut_formato(rut: str) -> str:
    """'12345678-5' -> '12.345.678-5' (formato visible para el residente)."""
    canon = rut_normalizar(rut)
    cuerpo, dv = canon.split("-")
    return f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"


def telefono_normalizar(tel: str) -> str:
    """Sólo dígitos, con código de país. Un celular chileno de 9 dígitos (9XXXXXXXX) recibe 56."""
    digitos = re.sub(r"\D", "", tel or "")
    if len(digitos) == 9 and digitos.startswith("9"):
        digitos = "56" + digitos
    return digitos


def telefono_valido(tel: str) -> bool:
    return bool(tel) and 8 <= len(telefono_normalizar(tel)) <= 15


def email_valido(email: str) -> bool:
    return bool(_RE_EMAIL.match(email or "")) and len(email) <= 160
