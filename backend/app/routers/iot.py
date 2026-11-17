"""Inventario y protocolo de laboratorio. No habilita actuadores reales."""
from datetime import timedelta
import hmac
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import utcnow
from ..db import get_db
from ..models import Edificio, IntentoLogin, Residente
from ..operation_schemas import ActivoIn, Entrada
from ..operations_models import ComandoAcceso, Dispositivo
from ..security import hash_clave_dispositivo, verify_password
from ..services.transactions import bloquear_edificio
from .operaciones import Admin, auditar, edificio, ficha, recurso
from .auth import _bloqueado

router = APIRouter(tags=["iot-laboratorio"])
BASE = "/edificios/{edificio_id}/dispositivos"
DEVICE = "/api/v1/{edificio_id}/dispositivos/{dispositivo_id}"


class DispositivoIn(Entrada):
    nombre: str = Field(min_length=2, max_length=80)
    punto: str = Field(min_length=2, max_length=40)
    laboratorio: bool = True


class HeartbeatIn(Entrada):
    firmware: str = Field("", max_length=80)
    bateria: int | None = Field(None, ge=0, le=100)


class AperturaIn(Entrada):
    password: str = Field(min_length=1, max_length=1024)
    motivo: str = Field(min_length=10, max_length=200)
    idempotencia: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class ConfirmacionIn(Entrada):
    nonce: str = Field(min_length=32, max_length=64)
    estado: Literal["ejecutado", "fallido"]


def autenticar(edificio_id: str, dispositivo_id: int, x_device_key: str | None = Header(None), db: Session = Depends(get_db)):
    bloquear_edificio(db, edificio_id)
    ed = db.get(Edificio, edificio_id)
    d = db.scalar(select(Dispositivo).where(Dispositivo.id == dispositivo_id, Dispositivo.edificio_id == edificio_id))
    if not ed or not ed.activo or not d or not d.activo or not x_device_key or not hmac.compare_digest(
            hash_clave_dispositivo(x_device_key), d.clave_hash):
        raise HTTPException(401, "Dispositivo no autorizado")
    return d


@router.get(BASE)
def listar(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    return [{**ficha(d, "id nombre punto activo laboratorio firmware ultima_comunicacion bateria"),
             "conectado": bool(d.ultima_comunicacion and utcnow() - d.ultima_comunicacion < timedelta(minutes=5))}
            for d in db.scalars(select(Dispositivo).where(Dispositivo.edificio_id == edificio_id).order_by(Dispositivo.id).limit(500))]


@router.post(BASE, status_code=201)
def registrar(edificio_id: str, body: DispositivoIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    from ..services.commercial import comprobar_cupo
    comprobar_cupo(db, edificio_id, "dispositivos")
    if db.scalar(select(Dispositivo.id).where(Dispositivo.edificio_id == edificio_id, Dispositivo.nombre == body.nombre)):
        raise HTTPException(409, "Nombre de dispositivo ya registrado")
    clave = secrets.token_urlsafe(32)
    d = Dispositivo(edificio_id=edificio_id, clave_hash=hash_clave_dispositivo(clave), **body.model_dump())
    db.add(d)
    db.flush()
    auditar(db, user, edificio_id, "dispositivo.registrado", d.id)
    db.commit()
    return {"id": d.id, "clave": clave, "laboratorio": d.laboratorio}


@router.patch(BASE + "/{dispositivo_id}")
def activar(edificio_id: str, dispositivo_id: int, body: ActivoIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    d = recurso(db, Dispositivo, edificio_id, dispositivo_id)
    d.activo = body.activo
    if not d.activo:
        for c in db.scalars(select(ComandoAcceso).where(ComandoAcceso.dispositivo_id == d.id,
                                                       ComandoAcceso.estado.in_(["pendiente", "entregado"]))):
            c.estado = "cancelado"
    auditar(db, user, edificio_id, "dispositivo.configurado", d.id, activo=d.activo)
    db.commit()
    return {"id": d.id, "activo": d.activo}


@router.post(BASE + "/{dispositivo_id}/rotar")
def rotar(edificio_id: str, dispositivo_id: int, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    d = recurso(db, Dispositivo, edificio_id, dispositivo_id)
    clave = secrets.token_urlsafe(32)
    d.clave_hash = hash_clave_dispositivo(clave)
    for c in db.scalars(select(ComandoAcceso).where(ComandoAcceso.dispositivo_id == d.id,
                                                   ComandoAcceso.estado.in_(["pendiente", "entregado"]))):
        c.estado = "cancelado"
    auditar(db, user, edificio_id, "dispositivo.clave_rotada", d.id)
    db.commit()
    return {"id": d.id, "clave": clave}


@router.post(BASE + "/{dispositivo_id}/abrir", status_code=201)
def abrir(edificio_id: str, dispositivo_id: int, body: AperturaIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    d = recurso(db, Dispositivo, edificio_id, dispositivo_id)
    if not d.activo or not d.laboratorio:
        raise HTTPException(409, "Sólo se permiten comandos para dispositivos de laboratorio activos")
    r = db.get(Residente, user.residente_id)
    clave_intento = f"abrir:{r.id}"
    if _bloqueado(db, clave_intento, ""):
        raise HTTPException(429, "Demasiados intentos; espere antes de autorizar otra apertura")
    if not verify_password(body.password, r.password_hash):
        db.add(IntentoLogin(clave=clave_intento, ip="", exitoso=False))
        db.commit()
        raise HTTPException(401, "Confirme su contraseña para autorizar el comando")
    anterior = db.scalar(select(ComandoAcceso).where(ComandoAcceso.dispositivo_id == d.id,
                                                    ComandoAcceso.idempotencia == body.idempotencia))
    if anterior:
        return ficha(anterior, "id estado expira")
    if not d.ultima_comunicacion or utcnow() - d.ultima_comunicacion > timedelta(minutes=5):
        raise HTTPException(409, "Dispositivo desconectado")
    c = ComandoAcceso(edificio_id=edificio_id, dispositivo_id=d.id, actor_id=user.residente_id,
                      idempotencia=body.idempotencia, nonce=secrets.token_urlsafe(32), motivo=body.motivo,
                      expira=utcnow() + timedelta(seconds=30))
    db.add(c)
    db.flush()
    auditar(db, user, edificio_id, "dispositivo.comando_solicitado", d.id, comando_id=c.id, laboratorio=True)
    db.commit()
    return ficha(c, "id estado expira")


@router.get(BASE + "/{dispositivo_id}/comandos")
def historial(edificio_id: str, dispositivo_id: int, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    d = recurso(db, Dispositivo, edificio_id, dispositivo_id)
    return [ficha(c, "id actor_id motivo estado creado expira confirmado") for c in db.scalars(
        select(ComandoAcceso).where(ComandoAcceso.dispositivo_id == d.id).order_by(ComandoAcceso.id.desc()).limit(100))]


@router.post(DEVICE + "/heartbeat")
def heartbeat(body: HeartbeatIn, d: Dispositivo = Depends(autenticar), db: Session = Depends(get_db)):
    d.ultima_comunicacion, d.firmware, d.bateria = utcnow(), body.firmware, body.bateria
    db.commit()
    return {"ok": True, "laboratorio": d.laboratorio}


@router.post(DEVICE + "/comandos/obtener")
def obtener(d: Dispositivo = Depends(autenticar), db: Session = Depends(get_db)):
    if not d.laboratorio:
        raise HTTPException(409, "Protocolo remoto habilitado sólo para laboratorio")
    for c in db.scalars(select(ComandoAcceso).where(ComandoAcceso.dispositivo_id == d.id,
                                                  ComandoAcceso.estado.in_(["pendiente", "entregado"])).order_by(ComandoAcceso.id)):
        if c.expira <= utcnow():
            c.estado = "expirado"
        elif c.estado == "pendiente":
            c.estado = "entregado"
            db.commit()
            return {"comando": {"id": c.id, "accion": "simular_apertura", "nonce": c.nonce,
                                 "expira": c.expira.isoformat() + "Z"}}
    db.commit()
    return {"comando": None}


@router.post(DEVICE + "/comandos/{comando_id}/confirmar")
def confirmar(comando_id: int, body: ConfirmacionIn, d: Dispositivo = Depends(autenticar), db: Session = Depends(get_db)):
    c = db.scalar(select(ComandoAcceso).where(ComandoAcceso.id == comando_id, ComandoAcceso.dispositivo_id == d.id))
    if not c or not hmac.compare_digest(body.nonce, c.nonce):
        raise HTTPException(404, "Comando no autorizado")
    if c.estado != "entregado" or c.expira <= utcnow():
        raise HTTPException(409, "Comando expirado o ya confirmado")
    c.estado, c.confirmado = body.estado, utcnow()
    db.commit()
    return {"id": c.id, "estado": c.estado, "laboratorio": True}
