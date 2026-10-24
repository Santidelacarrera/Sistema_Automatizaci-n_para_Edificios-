"""Administración del edificio desde el panel: residentes, tags RFID y reglas del motor.

Sólo admin (el superadmin también pasa). Las validaciones viven en services/administracion.py;
aquí sólo se traducen a códigos HTTP: 422 dato inválido, 409 duplicado o conflicto.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

import secrets

from .. import validacion
from ..db import get_db
from ..models import Edificio, EspacioComun, Regla, Residente, Rol, Tag, Unidad
from ..models import EstadoTag, Evento, Vehiculo
from ..schemas import (AjustesAccesoIn, PruebaAlcanceIn, ReglaIn, ReglaPatch, ResidenteIn, ResidentePatch, TagIn,
                       TagMotivo, TagPatch, TagReasignar, TagVincular)
from ..security import Principal, hash_clave_dispositivo, require_roles, tenant_of
from ..services import administracion, privacidad
from ..services.administracion import AdminError

router = APIRouter(prefix="/edificios/{edificio_id}", tags=["administracion"])
Admin = Annotated[Principal, Depends(require_roles(Rol.admin))]

# Listado de todos los edificios: sólo superadmin (no pasa por el filtro de tenant).
edificios_router = APIRouter(prefix="/edificios", tags=["administracion"])


@edificios_router.get("")
def listar_edificios(user: Annotated[Principal, Depends(require_roles(Rol.superadmin))],
                     db: Session = Depends(get_db)):
    """Resumen de cada edificio: departamentos, residentes activos y deuda total."""
    from sqlalchemy import func
    from ..models import Cargo
    deuda = dict(db.execute(select(Cargo.edificio_id, func.sum(Cargo.saldo)).where(Cargo.saldo > 0)
                            .group_by(Cargo.edificio_id)).all())
    filas = []
    for ed in db.scalars(select(Edificio).order_by(Edificio.nombre)):
        unidades = db.scalar(select(func.count(Unidad.id)).where(Unidad.edificio_id == ed.id))
        residentes = db.scalar(select(func.count(Residente.id)).where(
            Residente.edificio_id == ed.id, Residente.activo.is_(True)))
        filas.append({"id": ed.id, "nombre": ed.nombre, "unidades": unidades, "residentes": residentes,
                      "deuda_total": float(deuda.get(ed.id, 0) or 0)})
    return filas


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
    patentes = dict(db.execute(select(Vehiculo.tag_id, Vehiculo.patente).where(
        Vehiculo.edificio_id == ed.id, Vehiculo.tag_id.is_not(None), Vehiculo.activo.is_(True))).all())
    return [{"id": t.id, "uid": t.uid, "formato": t.formato, "tipo": t.tipo.value, "estado": t.estado,
             "activo": t.activo, "unidad_id": t.unidad_id, "unidad": n, "residente_id": t.residente_id,
             "residente": nombre, "patente": patentes.get(t.id, ""),
             "fecha_alta": t.fecha_alta.isoformat() + "Z",
             "ultima_lectura": t.ultima_lectura.isoformat() + "Z" if t.ultima_lectura else None}
            for t, n, nombre in rows]


def _tag_del_edificio(db: Session, ed: Edificio, tag_id: int) -> Tag:
    t = db.get(Tag, tag_id)
    if not t or t.edificio_id != ed.id:
        raise HTTPException(404, "Tag no existe")
    return t


@router.post("/tags/{tag_id}/activar")
def activar_tag(edificio_id: str, tag_id: int, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    t = administracion.cambiar_estado_tag(db, ed, _tag_del_edificio(db, ed, tag_id), EstadoTag.activo.value)
    db.commit()
    return {"id": t.id, "estado": t.estado}


@router.post("/tags/{tag_id}/perder")
def perder_tag(edificio_id: str, tag_id: int, body: TagMotivo, user: Admin, db: Session = Depends(get_db)):
    """Marca el sticker como perdido: deja de abrir desde la siguiente lectura."""
    ed = _ed(db, user, edificio_id)
    t = administracion.cambiar_estado_tag(db, ed, _tag_del_edificio(db, ed, tag_id),
                                          EstadoTag.perdido.value, body.motivo)
    db.commit()
    return {"id": t.id, "estado": t.estado}


@router.post("/tags/{tag_id}/bloquear")
def bloquear_tag(edificio_id: str, tag_id: int, body: TagMotivo, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    t = administracion.cambiar_estado_tag(db, ed, _tag_del_edificio(db, ed, tag_id),
                                          EstadoTag.bloqueado.value, body.motivo)
    db.commit()
    return {"id": t.id, "estado": t.estado}


@router.post("/tags/{tag_id}/reasignar")
def reasignar_tag(edificio_id: str, tag_id: int, body: TagReasignar, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    t = _tag_del_edificio(db, ed, tag_id)
    try:
        administracion.reasignar_tag(db, ed, t, body.unidad_id, body.residente_id, body.vehiculo_id)
    except AdminError as e:
        _responder_error(db, e)
    db.commit()
    return {"id": t.id, "unidad_id": t.unidad_id}


@router.post("/tags/{tag_id}/vincular")
def vincular_tag(edificio_id: str, tag_id: int, body: TagVincular, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    t = _tag_del_edificio(db, ed, tag_id)
    try:
        administracion.vincular_sticker(db, ed, t, body.vehiculo_id)
    except AdminError as e:
        _responder_error(db, e)
    db.commit()
    return {"id": t.id}


@router.post("/tags/{tag_id}/desvincular")
def desvincular_tag(edificio_id: str, tag_id: int, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    t = administracion.desvincular_sticker(db, ed, _tag_del_edificio(db, ed, tag_id))
    db.commit()
    return {"id": t.id}


@router.get("/pruebas-alcance")
def listar_pruebas_alcance(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    """Bitácora de la prueba de alcance del lector: distancia y resultado anotados por el técnico."""
    ed = _ed(db, user, edificio_id)
    rows = db.scalars(select(Evento).where(Evento.edificio_id == ed.id, Evento.tipo == "prueba.alcance")
                      .order_by(Evento.id.desc()).limit(100)).all()
    return [{"id": e.id, "creado": e.creado.isoformat() + "Z", **e.payload} for e in rows]


@router.post("/pruebas-alcance", status_code=201)
def anotar_prueba_alcance(edificio_id: str, body: PruebaAlcanceIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    e = Evento(edificio_id=ed.id, tipo="prueba.alcance",
               payload={"distancia_m": body.distancia_m, "resultado": body.resultado, "tag": body.tag_uid,
                        "nota": body.nota, "anotado_por": user.residente_id})
    db.add(e)
    db.commit()
    return {"id": e.id}


@router.get("/ajustes-acceso")
def ver_ajustes(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    return {"modo_acceso": ed.modo_acceso, "ventana_coincidencia_s": ed.ventana_coincidencia_s,
            "antirrebote_s": ed.antirrebote_s, "anti_passback": ed.anti_passback,
            "umbral_confianza_patente": ed.umbral_confianza_patente}


@router.patch("/ajustes-acceso")
def cambiar_ajustes(edificio_id: str, body: AjustesAccesoIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    cambios = _cambios(body)
    for campo, valor in cambios.items():
        setattr(ed, campo, valor)
    db.add(Evento(edificio_id=ed.id, tipo="ajustes.acceso", payload={"cambios": cambios}))
    db.commit()
    return ver_ajustes(edificio_id, user, db)


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


@router.post("/dispositivos/rotar-clave")
def rotar_clave_dispositivo(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    """Genera una nueva X-Device-Key. Se muestra una sola vez; los lectores con la anterior quedan sin acceso."""
    ed = _ed(db, user, edificio_id)
    clave = secrets.token_urlsafe(32)
    ed.device_api_key = hash_clave_dispositivo(clave)
    db.add(Evento(edificio_id=ed.id, tipo="dispositivos.clave_rotada", payload={"por": user.residente_id}))
    db.commit()
    return {"device_key": clave, "aviso": "Guárdela ahora: no se vuelve a mostrar. Reconfigure los lectores."}


@router.get("/residentes/{residente_id}/datos-personales")
def datos_personales(edificio_id: str, residente_id: int, user: Admin, db: Session = Depends(get_db)):
    """Derecho de acceso: todo lo que el sistema guarda de la persona. Queda registrado."""
    ed = _ed(db, user, edificio_id)
    r = db.get(Residente, residente_id)
    if not r or r.edificio_id != ed.id:
        raise HTTPException(404, "Residente no existe")
    db.add(Evento(edificio_id=ed.id, tipo="privacidad.exportacion", payload={"residente_id": r.id, "por": user.residente_id}))
    db.commit()
    return privacidad.exportar(db, r)


@router.post("/residentes/{residente_id}/anonimizar")
def anonimizar_residente(edificio_id: str, residente_id: int, user: Admin, db: Session = Depends(get_db)):
    """Derecho de supresión: borra los datos identificables. No se puede deshacer."""
    ed = _ed(db, user, edificio_id)
    r = db.get(Residente, residente_id)
    if not r or r.edificio_id != ed.id:
        raise HTTPException(404, "Residente no existe")
    if r.id == user.residente_id:
        raise HTTPException(409, "No puede anonimizar su propia cuenta")
    privacidad.anonimizar(db, r)
    db.add(Evento(edificio_id=ed.id, tipo="privacidad.anonimizacion", payload={"residente_id": r.id, "por": user.residente_id}))
    db.commit()
    return {"ok": True}
