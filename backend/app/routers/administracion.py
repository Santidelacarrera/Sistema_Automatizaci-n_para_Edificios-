"""Administración del edificio desde el panel: residentes, tags RFID y reglas del motor.

Sólo admin (el superadmin también pasa). Las validaciones viven en services/administracion.py;
aquí sólo se traducen a códigos HTTP: 422 dato inválido, 409 duplicado o conflicto.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import validacion
from ..db import get_db
from ..models import Edificio, EspacioComun, Regla, Residente, Rol, Tag, Unidad
from ..schemas import ReglaIn, ReglaPatch, ResidenteIn, ResidentePatch, TagIn, TagPatch
from ..security import Principal, require_roles, tenant_of
from ..services import administracion
from ..services.administracion import AdminError

router = APIRouter(prefix="/edificios/{edificio_id}", tags=["administracion"])
Admin = Annotated[Principal, Depends(require_roles(Rol.admin))]


def _ed(db: Session, user: Principal, edificio_id: str) -> Edificio:
    tenant_of(user, edificio_id)
    ed = db.get(Edificio, edificio_id)
    if not ed:
        raise HTTPException(404, "Edificio no existe")
    return ed


def _cambios(body, nulos_ok: tuple[str, ...] = (), excluir: tuple[str, ...] = ()) -> dict:
    """Campos enviados explícitamente en un PATCH. Un null se ignora salvo en ``nulos_ok``."""
    return {k: getattr(body, k) for k in body.model_fields_set
            if k not in excluir and (getattr(body, k) is not None or k in nulos_ok)}


def _responder_error(db: Session, e: AdminError):
    db.rollback()
    raise HTTPException(e.status, str(e))


# ---------- residentes ----------
@router.get("/residentes")
def listar_residentes(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    rows = db.execute(select(Residente, Unidad.numero).join(Unidad, Unidad.id == Residente.unidad_id)
                      .where(Residente.edificio_id == ed.id).order_by(Unidad.numero, Residente.nombre)).all()
    return [{"id": r.id, "nombre": r.nombre, "rut": validacion.rut_formato(r.rut), "email": r.email,
             "telefono": r.telefono, "unidad_id": r.unidad_id, "unidad": n, "rol": r.rol.value,
             "activo": r.activo} for r, n in rows]


@router.post("/residentes", status_code=201)
def crear_residente(edificio_id: str, body: ResidenteIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    try:
        r = administracion.crear_residente(db, ed, body.model_dump(exclude={"password"}), body.password)
    except AdminError as e:
        _responder_error(db, e)
    db.commit()
    return {"id": r.id}


@router.patch("/residentes/{residente_id}")
def editar_residente(edificio_id: str, residente_id: int, body: ResidentePatch, user: Admin,
                     db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    r = db.get(Residente, residente_id)
    if not r or r.edificio_id != ed.id:
        raise HTTPException(404, "Residente no existe")
    try:
        administracion.editar_residente(db, ed, r, _cambios(body, excluir=("password",)), body.password)
    except AdminError as e:
        _responder_error(db, e)
    db.commit()
    return {"id": r.id}


# ---------- tags RFID ----------
@router.get("/tags")
def listar_tags(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    rows = db.execute(select(Tag, Unidad.numero, Residente.nombre)
                      .join(Unidad, Unidad.id == Tag.unidad_id)
                      .outerjoin(Residente, Residente.id == Tag.residente_id)
                      .where(Tag.edificio_id == ed.id).order_by(Unidad.numero, Tag.id)).all()
    return [{"id": t.id, "uid": t.uid, "tipo": t.tipo.value, "activo": t.activo, "unidad_id": t.unidad_id,
             "unidad": n, "residente_id": t.residente_id, "residente": nombre} for t, n, nombre in rows]


@router.post("/tags", status_code=201)
def asignar_tag(edificio_id: str, body: TagIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    try:
        t = administracion.alta_tag(db, ed, body.model_dump())
    except AdminError as e:
        _responder_error(db, e)
    db.commit()
    return {"id": t.id}


@router.patch("/tags/{tag_id}")
def editar_tag(edificio_id: str, tag_id: int, body: TagPatch, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    t = db.get(Tag, tag_id)
    if not t or t.edificio_id != ed.id:
        raise HTTPException(404, "Tag no existe")
    try:
        administracion.editar_tag(db, ed, t, _cambios(body, nulos_ok=("residente_id",)))
    except AdminError as e:
        _responder_error(db, e)
    db.commit()
    return {"id": t.id, "activo": t.activo}


# ---------- espacios comunes y reglas ----------
@router.get("/espacios")
def listar_espacios(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    return [{"id": e.id, "nombre": e.nombre, "accion": e.accion, "tarifa": float(e.tarifa)}
            for e in db.scalars(select(EspacioComun).where(EspacioComun.edificio_id == ed.id)
                                .order_by(EspacioComun.nombre))]


@router.get("/reglas")
def listar_reglas(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    return [{"id": r.id, "accion": r.accion, "tipo": r.tipo, "params": r.params, "activa": r.activa}
            for r in db.scalars(select(Regla).where(Regla.edificio_id == ed.id).order_by(Regla.accion, Regla.tipo))]


@router.post("/reglas", status_code=201)
def crear_regla(edificio_id: str, body: ReglaIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    try:
        r = administracion.validar_y_guardar_regla(db, ed, None, body.model_dump())
    except AdminError as e:
        _responder_error(db, e)
    db.commit()
    return {"id": r.id}


@router.patch("/reglas/{regla_id}")
def editar_regla(edificio_id: str, regla_id: int, body: ReglaPatch, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    r = db.get(Regla, regla_id)
    if not r or r.edificio_id != ed.id:
        raise HTTPException(404, "Regla no existe")
    try:
        administracion.validar_y_guardar_regla(db, ed, r, _cambios(body))
    except AdminError as e:
        _responder_error(db, e)
    db.commit()
    return {"id": r.id, "activa": r.activa}
