import time

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
import pyotp

from ..config import settings
from ..models import Rol


def requerido(rol):
    return rol in (Rol.admin, Rol.superadmin) and (settings.entorno == "produccion" or settings.mfa_required_privileged)


def cifrador():
    try:
        return Fernet(settings.mfa_encryption_key.encode())
    except (ValueError, TypeError):
        raise HTTPException(503, "Configure MFA_ENCRYPTION_KEY antes de activar el segundo factor") from None


def secreto(factor):
    try:
        return cifrador().decrypt(factor.secreto_cifrado.encode()).decode()
    except InvalidToken:
        raise HTTPException(503, "No se pudo leer el segundo factor; revise la clave de cifrado") from None


def verificar(factor, codigo, instante=None):
    if not codigo or not codigo.isdigit() or len(codigo) != 6:
        return False
    instante = time.time() if instante is None else instante
    totp = pyotp.TOTP(secreto(factor))
    paso = int(instante // 30)
    for candidato in (paso - 1, paso, paso + 1):
        if candidato > factor.ultimo_paso and totp.verify(codigo, for_time=candidato * 30):
            factor.ultimo_paso = candidato
            return True
    return False
