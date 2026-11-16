from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import settings, utcnow
from ..db import get_db
from ..models import Edificio, IntentoLogin, Residente, Rol
from ..operations_models import SegundoFactor
from ..services import mfa
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
    r = db.scalar(select(Residente).where(Residente.edificio_id == body.edificio_id.strip(),
                                          func.lower(Residente.email) == body.email.strip().lower(), Residente.activo.is_(True)))
    ok = verify_password(body.password, r.password_hash if r else _HASH_RELLENO) and r is not None
    if ok and r.rol != Rol.superadmin:
        ed = db.get(Edificio, r.edificio_id)
        ok = bool(ed and ed.activo)
    factor = None
    if ok:
        factor = db.scalar(select(SegundoFactor).where(SegundoFactor.residente_id == r.id).with_for_update())
        if factor and factor.activo:
            ok = mfa.verificar(factor, body.codigo_mfa)
    db.add(IntentoLogin(clave=clave, ip=ip, exitoso=ok))
    if not ok:
        db.commit()
        raise HTTPException(401, "Credenciales inválidas")
    db.execute(delete(IntentoLogin).where(IntentoLogin.clave == clave, IntentoLogin.exitoso.is_(False)))
    db.commit()
    if mfa.requerido(r.rol) and not (factor and factor.activo):
        import jwt
        mfa.cifrador()  # fail closed si falta la clave; no emite una sesión privilegiada
        token = jwt.encode({"sub": str(r.id), "sv": r.session_version, "purpose": "mfa_setup",
                            "exp": utcnow() + timedelta(minutes=10)}, settings.jwt_secret, algorithm="HS256")
        return {"mfa_setup_required": True, "setup_token": token}
    return {"access_token": create_token(r.id, r.edificio_id, r.rol, r.session_version, bool(factor and factor.activo)), "token_type": "bearer",
            "rol": r.rol.value, "nombre": r.nombre}


@router.post("/recuperar/solicitar")
def solicitar_recuperacion(body: dict, request: Request, db: Session = Depends(get_db)):
    """Emite un token de recuperación de 15 minutos y lo encola al correo registrado sin revelar si la cuenta existe."""
    import hashlib
    import secrets
    from ..operations_models import Notificacion, TokenRecuperacion
    edificio_id = str(body.get("edificio_id") or "").strip()
    correo = str(body.get("email") or "").strip().lower()
    if not edificio_id or not correo:
        raise HTTPException(422, "Indique edificio y correo")
    r = db.scalar(select(Residente).where(
        Residente.edificio_id == edificio_id,
        func.lower(Residente.email) == correo,
        Residente.activo.is_(True),
    ))
    token_claro = None
    if r:
        token_claro = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(token_claro.encode()).hexdigest()
        db.add(TokenRecuperacion(
            edificio_id=edificio_id, residente_id=r.id,
            token_hash=token_hash, expira=utcnow() + timedelta(minutes=15),
        ))
        db.add(Notificacion(
            edificio_id=edificio_id, residente_id=r.id,
            clave=f"recuperacion:{token_hash[:16]}", canal="email",
            titulo="Recuperación de acceso",
            texto=f"Código temporal de recuperación (expira en 15 min): {token_claro}",
            estado="pendiente",
        ))
        db.commit()
    resp = {"mensaje": "Si la cuenta existe y está activa, se envió una instrucción de recuperación."}
    if settings.entorno != "produccion" and token_claro:
        resp["token_desarrollo"] = token_claro
    return resp


@router.post("/recuperar/confirmar")
def confirmar_recuperacion(body: dict, db: Session = Depends(get_db)):
    """Valida el token de recuperación de un solo uso, actualiza la contraseña y revoca sesiones previas."""
    import hashlib
    from ..operations_models import TokenRecuperacion
    token = str(body.get("token") or "").strip()
    nueva_password = str(body.get("nueva_password") or "")
    if not token or len(nueva_password) < 8:
        raise HTTPException(422, "Token válido y contraseña de al menos 8 caracteres son obligatorios")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    reg = db.scalar(select(TokenRecuperacion).where(
        TokenRecuperacion.token_hash == token_hash).with_for_update())
    if not reg or reg.usado or reg.expira < utcnow():
        raise HTTPException(401, "Token de recuperación inválido o expirado")
    r = db.get(Residente, reg.residente_id)
    if not r or not r.activo:
        raise HTTPException(401, "Cuenta inactiva")
    reg.usado = True
    r.password_hash = hash_password(nueva_password)
    r.session_version += 1
    db.execute(delete(IntentoLogin).where(
        IntentoLogin.clave == f"{r.edificio_id.lower()}|{r.email.lower()}"))
    db.commit()
    return {"actualizada": True, "sesiones_revocadas": True}
