from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import settings, utcnow
from ..db import get_db
from ..models import IntentoLogin, Residente
from ..schemas import LoginIn
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash de relleno: se verifica igual cuando la cuenta no existe, para que el tiempo de respuesta
# no delate qué correos están registrados.
_HASH_RELLENO = hash_password("relleno-sin-uso")


def _ip(request: Request) -> str:
    # Detrás de un proxy inverso confiable, Uvicorn ya resuelve X-Forwarded-For con --proxy-headers.
    return (request.client.host if request.client else "")[:64]


def _bloqueado(db: Session, clave: str, ip: str) -> int | None:
    """Minutos restantes de bloqueo, o None si puede intentar."""
    ventana = timedelta(minutes=settings.login_ventana_min)
    desde = utcnow() - ventana
    fallos = db.execute(select(func.count(), func.min(IntentoLogin.creado)).where(
        IntentoLogin.clave == clave, IntentoLogin.exitoso.is_(False), IntentoLogin.creado >= desde)).one()
    fallos_ip = db.scalar(select(func.count()).where(
        IntentoLogin.ip == ip, IntentoLogin.exitoso.is_(False), IntentoLogin.creado >= desde)) if ip else 0
    if fallos[0] >= settings.login_max_intentos or fallos_ip >= settings.login_max_intentos_ip:
        primero = fallos[1] or utcnow()
        restante = (primero + ventana) - utcnow()
        return max(1, int(restante.total_seconds() // 60) + 1)
    return None


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    clave = f"{body.edificio_id.strip().lower()}|{body.email.strip().lower()}"[:220]
    ip = _ip(request)
    espera = _bloqueado(db, clave, ip)
    if espera:
        raise HTTPException(429, f"Demasiados intentos fallidos. Intente de nuevo en {espera} minuto(s).",
                            headers={"Retry-After": str(espera * 60)})
    r = db.scalar(select(Residente).where(Residente.edificio_id == body.edificio_id,
                                          Residente.email == body.email, Residente.activo.is_(True)))
    ok = verify_password(body.password, r.password_hash if r else _HASH_RELLENO) and r is not None
    db.add(IntentoLogin(clave=clave, ip=ip, exitoso=ok))
    if not ok:
        db.commit()
        raise HTTPException(401, "Credenciales inválidas")
    db.execute(delete(IntentoLogin).where(IntentoLogin.clave == clave, IntentoLogin.exitoso.is_(False)))
    db.commit()
    return {"access_token": create_token(r.id, r.edificio_id, r.rol), "token_type": "bearer",
            "rol": r.rol.value, "nombre": r.nombre}
