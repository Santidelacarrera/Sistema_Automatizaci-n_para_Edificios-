from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pydantic import Field
import pyotp
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings, utcnow
from ..db import get_db
from ..models import Edificio, Residente, Rol
from ..operation_schemas import Entrada
from ..operations_models import SegundoFactor
from ..security import create_token, verify_password
from ..services.mfa import cifrador, secreto, verificar

router = APIRouter(prefix="/auth/mfa", tags=["seguridad"])
bearer = HTTPBearer(auto_error=False)


def usuario_setup(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if not cred:
        raise HTTPException(401, "Falta token")
    try:
        claims = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"], options={"require": ["sub", "exp"]})
        rid = int(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, "Token inválido") from None
    r = db.scalar(select(Residente).where(Residente.id == rid).with_for_update())
    if not r or not r.activo or claims.get("sv", 0) != r.session_version:
        raise HTTPException(401, "Sesión revocada")
    ed = db.get(Edificio, r.edificio_id)
    if r.rol != Rol.superadmin and (not ed or not ed.activo):
        raise HTTPException(403, "Edificio suspendido")
    if claims.get("purpose") not in (None, "mfa_setup"):
        raise HTTPException(401, "Token no autorizado")
    return r


class ClaveIn(Entrada):
    password: str = Field(min_length=1, max_length=1024)


class CodigoIn(Entrada):
    codigo: str = Field(pattern=r"^\d{6}$")


def verificar_bloqueo(factor):
    if factor and factor.bloqueado_hasta and factor.bloqueado_hasta > utcnow():
        raise HTTPException(429, "Demasiados intentos de MFA; espere 15 minutos")


@router.post("/preparar")
def preparar(body: ClaveIn, r: Residente = Depends(usuario_setup), db: Session = Depends(get_db)):
    factor = db.get(SegundoFactor, r.id)
    verificar_bloqueo(factor)
    if factor and factor.activo:
        raise HTTPException(409, "El segundo factor ya está activo")
    if not factor:
        factor = SegundoFactor(residente_id=r.id, secreto_cifrado="", intentos=0, ultimo_paso=-1)
        db.add(factor)
    if not verify_password(body.password, r.password_hash):
        factor.intentos += 1
        if factor.intentos >= 5:
            factor.bloqueado_hasta = utcnow() + timedelta(minutes=15)
        db.commit()
        raise HTTPException(401, "Credenciales inválidas")
    if not factor.secreto_cifrado:
        factor.secreto_cifrado = cifrador().encrypt(pyotp.random_base32().encode()).decode()
    secret = secreto(factor)
    db.commit()
    return {"secreto": secret, "uri": pyotp.TOTP(secret).provisioning_uri(name=r.email, issuer_name="Fachada")}


@router.post("/confirmar")
def confirmar(body: CodigoIn, r: Residente = Depends(usuario_setup), db: Session = Depends(get_db)):
    factor = db.get(SegundoFactor, r.id)
    if not factor or not factor.secreto_cifrado or factor.activo:
        raise HTTPException(409, "No hay alta de MFA pendiente")
    verificar_bloqueo(factor)
    if not verificar(factor, body.codigo):
        factor.intentos += 1
        if factor.intentos >= 5:
            factor.bloqueado_hasta = utcnow() + timedelta(minutes=15)
        db.commit()
        raise HTTPException(401, "Código inválido o ya utilizado")
    factor.activo, factor.intentos = True, 0
    r.session_version += 1
    db.commit()
    return {"access_token": create_token(r.id, r.edificio_id, r.rol, r.session_version, mfa=True),
            "rol": r.rol.value, "nombre": r.nombre, "edificio_id": r.edificio_id, "token_type": "bearer"}
