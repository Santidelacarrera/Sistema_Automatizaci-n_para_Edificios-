import hashlib
import hmac
import os
from datetime import timedelta
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings, utcnow
from .db import get_db
from .models import Edificio, Rol

_bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + h.hex()


def verify_password(pw: str, stored: str) -> bool:
    try:
        salt_hex, h_hex = stored.split("$")
    except ValueError:
        return False
    h = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(h.hex(), h_hex)


def create_token(residente_id: int, edificio_id: str, rol: Rol) -> str:
    exp = utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(residente_id), "edificio_id": edificio_id,
                       "rol": rol.value, "exp": exp}, settings.jwt_secret, algorithm="HS256")


class Principal:
    def __init__(self, residente_id: int, edificio_id: str, rol: Rol):
        self.residente_id, self.edificio_id, self.rol = residente_id, edificio_id, rol


def current_user(cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> Principal:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta token")
    try:
        p = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"])
        return Principal(int(p["sub"]), p["edificio_id"], Rol(p["rol"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido")


def require_roles(*roles: Rol):
    def dep(user: Annotated[Principal, Depends(current_user)]) -> Principal:
        if user.rol not in roles and user.rol != Rol.superadmin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permisos insuficientes")
        return user
    return dep


def tenant_of(user: Principal, edificio_id: str) -> str:
    """El tenant de la ruta debe coincidir con el del token (salvo superadmin)."""
    if user.rol != Rol.superadmin and user.edificio_id != edificio_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Edificio no autorizado")
    return edificio_id


def device_building(
    edificio_id: str,
    x_device_key: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Edificio:
    """Autenticación de lectores ESP32: API key por edificio."""
    ed = db.get(Edificio, edificio_id)
    if not ed or not x_device_key or not hmac.compare_digest(ed.device_api_key, x_device_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Dispositivo no autorizado")
    return ed
