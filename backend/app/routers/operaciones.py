"""Mantenimiento, proveedores y notificaciones. Autorización por tenant y recurso."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import utcnow
from ..db import get_db
from ..models import Edificio, Evento, Residente, Rol, Unidad
from ..operations_models import (ComentarioIncidencia, Incidencia, Notificacion, OrdenTrabajo,
                                  PlanMantenimiento, Proveedor)
from ..operation_schemas import (ActivoIn, ComentarioIn, IncidenciaIn, IncidenciaPatch, OrdenEstado,
                                 OrdenIn, PlanIn, ProveedorIn)
from ..security import Principal, current_user, require_roles, tenant_of
from ..services.notifications import administradores, notificar
from ..services.transactions import bloquear_edificio
from ..validacion import rut_normalizar, rut_valido

router = APIRouter(prefix="/edificios/{edificio_id}", tags=["operaciones"])
User = Annotated[Principal, Depends(current_user)]
Admin = Annotated[Principal, Depends(require_roles(Rol.admin))]


def edificio(db, user, eid, escribir=False):
    tenant_of(user, eid)
    ed = bloquear_edificio(db, eid) if escribir else db.get(Edificio, eid)
    if not ed:
        raise HTTPException(404, "Edificio no existe")
    if not ed.activo and user.rol != Rol.superadmin:
        raise HTTPException(403, "Edificio suspendido")
    return ed


def recurso(db, model, eid, rid):
    obj = db.scalar(select(model).where(model.id == rid, model.edificio_id == eid))
    if obj is None:
        raise HTTPException(404, "Recurso no existe en este edificio")
    return obj


def auditar(db, user, eid, tipo, recurso_id, **datos):
    db.add(Evento(edificio_id=eid, tipo=tipo,
                  payload={"actor_id": user.residente_id, "recurso_id": recurso_id, **datos}))


def ficha(obj, campos):
    # Instantes técnicos se almacenan UTC naive; las fechas de agenda siguen hora local.
    tecnicos = {"creado", "actualizado", "leido", "cerrada", "expira", "confirmado", "ultima_comunicacion"}
    return {k: (getattr(obj, k).isoformat() + "Z" if k in tecnicos and getattr(obj, k) is not None else getattr(obj, k))
            for k in campos.split()}


INC_CAMPOS = "id unidad_id autor_id titulo descripcion prioridad estado responsable_id vencimiento creado actualizado version"
PROV_CAMPOS = "id nombre rut contacto servicio contrato_hasta activo"
ORD_CAMPOS = "id incidencia_id proveedor_id detalle presupuesto estado aprobada_por evaluacion creado"
PLAN_CAMPOS = "id titulo responsable_id intervalo_dias proxima_fecha activo ultima_incidencia_id"


def ver_incidencia(db, user, eid, rid):
    inc = recurso(db, Incidencia, eid, rid)
    if user.rol == Rol.residente and inc.autor_id != user.residente_id:
        raise HTTPException(404, "Incidencia no existe")
    return inc


def responsable(db, eid, rid):
    r = recurso(db, Residente, eid, rid)
    if not r.activo or r.rol not in (Rol.admin, Rol.conserje):
        raise HTTPException(422, "El responsable debe ser personal activo del edificio")
    return r


@router.get("/notificaciones")
def notificaciones(edificio_id: str, user: User, antes: int | None = None,
                   limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    q = select(Notificacion).where(Notificacion.edificio_id == edificio_id,
                                  Notificacion.residente_id == user.residente_id, Notificacion.canal == "app")
    if antes:
        q = q.where(Notificacion.id < antes)
    return [ficha(n, "id titulo texto creado leido") for n in db.scalars(q.order_by(Notificacion.id.desc()).limit(limit))]


@router.post("/notificaciones/{notificacion_id}/leer")
def leer(edificio_id: str, notificacion_id: int, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    n = recurso(db, Notificacion, edificio_id, notificacion_id)
    if n.residente_id != user.residente_id or n.canal != "app":
        raise HTTPException(404, "Notificación no existe")
    n.leido = n.leido or utcnow()
    db.commit()
    return {"leido": n.leido}


@router.get("/notificaciones/entregas")
def entregas(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    return [ficha(n, "id residente_id canal estado intentos ultimo_error creado") for n in db.scalars(
        select(Notificacion).where(Notificacion.edificio_id == edificio_id, Notificacion.canal != "app")
        .order_by(Notificacion.id.desc()).limit(100))]


@router.get("/proveedores")
def proveedores(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    return [ficha(p, PROV_CAMPOS) for p in db.scalars(select(Proveedor).where(
        Proveedor.edificio_id == edificio_id).order_by(Proveedor.nombre).limit(500))]


@router.post("/proveedores", status_code=201)
def crear_proveedor(edificio_id: str, body: ProveedorIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    if not rut_valido(body.rut):
        raise HTTPException(422, "RUT inválido")
    rut = rut_normalizar(body.rut)
    if db.scalar(select(Proveedor.id).where(Proveedor.edificio_id == edificio_id, Proveedor.rut == rut)):
        raise HTTPException(409, "Proveedor ya registrado")
    p = Proveedor(edificio_id=edificio_id, **(body.model_dump() | {"rut": rut}))
    db.add(p)
    db.flush()
    auditar(db, user, edificio_id, "proveedor.creado", p.id)
    db.commit()
    return ficha(p, PROV_CAMPOS)


@router.put("/proveedores/{proveedor_id}")
def editar_proveedor(edificio_id: str, proveedor_id: int, body: ProveedorIn, user: Admin,
                     db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    p = recurso(db, Proveedor, edificio_id, proveedor_id)
    if not rut_valido(body.rut):
        raise HTTPException(422, "RUT inválido")
    rut = rut_normalizar(body.rut)
    if db.scalar(select(Proveedor.id).where(Proveedor.edificio_id == edificio_id, Proveedor.rut == rut,
                                           Proveedor.id != p.id)):
        raise HTTPException(409, "Proveedor ya registrado")
    for k, v in (body.model_dump() | {"rut": rut}).items():
        setattr(p, k, v)
    auditar(db, user, edificio_id, "proveedor.editado", p.id)
    db.commit()
    return ficha(p, PROV_CAMPOS)


@router.post("/incidencias", status_code=201)
def crear_incidencia(edificio_id: str, body: IncidenciaIn, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    datos = body.model_dump()
    if user.rol == Rol.residente:
        yo = db.get(Residente, user.residente_id)
        if body.unidad_id not in (None, yo.unidad_id):
            raise HTTPException(403, "Sólo puede reportar para su unidad")
        datos["unidad_id"] = yo.unidad_id
    elif body.unidad_id:
        recurso(db, Unidad, edificio_id, body.unidad_id)
    inc = Incidencia(edificio_id=edificio_id, autor_id=user.residente_id, **datos)
    db.add(inc)
    db.flush()
    auditar(db, user, edificio_id, "incidencia.creada", inc.id)
    notificar(db, edificio_id, administradores(db, edificio_id), f"Incidencia {inc.prioridad}",
              inc.titulo, clave=f"incidencia:{inc.id}:creada")
    db.commit()
    return ficha(inc, INC_CAMPOS)


@router.get("/incidencias")
def incidencias(edificio_id: str, user: User, estado: str | None = None, antes: int | None = None,
                limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    q = select(Incidencia).where(Incidencia.edificio_id == edificio_id)
    if user.rol == Rol.residente:
        q = q.where(Incidencia.autor_id == user.residente_id)
    if estado:
        q = q.where(Incidencia.estado == estado)
    if antes:
        q = q.where(Incidencia.id < antes)
    return [ficha(i, INC_CAMPOS) for i in db.scalars(q.order_by(Incidencia.id.desc()).limit(limit))]


@router.get("/incidencias/{incidencia_id}")
def detalle_incidencia(edificio_id: str, incidencia_id: int, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    inc = ver_incidencia(db, user, edificio_id, incidencia_id)
    comentarios = db.scalars(select(ComentarioIncidencia).where(
        ComentarioIncidencia.edificio_id == edificio_id, ComentarioIncidencia.incidencia_id == inc.id)
        .order_by(ComentarioIncidencia.id).limit(300)).all()
    historial = db.scalars(select(Evento).where(Evento.edificio_id == edificio_id,
                                               Evento.tipo.like("incidencia.%"))
                          .order_by(Evento.id.desc()).limit(1000)).all()
    orden = db.scalar(select(OrdenTrabajo).where(OrdenTrabajo.incidencia_id == inc.id,
                                                OrdenTrabajo.edificio_id == edificio_id))
    return {**ficha(inc, INC_CAMPOS), "comentarios": [ficha(c, "id autor_id texto creado") for c in comentarios],
            "historial": [{"tipo": e.tipo, "creado": e.creado, **e.payload} for e in historial
                          if e.payload.get("recurso_id") == inc.id],
            "orden": ficha(orden, ORD_CAMPOS) if orden and user.rol != Rol.residente else None}


@router.patch("/incidencias/{incidencia_id}")
def actualizar_incidencia(edificio_id: str, incidencia_id: int, body: IncidenciaPatch, user: Admin,
                          db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    inc = recurso(db, Incidencia, edificio_id, incidencia_id)
    if body.version != inc.version:
        raise HTTPException(409, "La incidencia cambió; recargue antes de guardar")
    transiciones = {"abierta": {"asignada", "en_progreso", "resuelta"}, "asignada": {"en_progreso", "resuelta"},
                    "en_progreso": {"resuelta"}, "resuelta": {"cerrada", "en_progreso"}, "cerrada": set()}
    if body.estado and body.estado != inc.estado and body.estado not in transiciones[inc.estado]:
        raise HTTPException(409, "Transición de estado no permitida")
    if inc.estado == "cerrada":
        raise HTTPException(409, "La incidencia está cerrada")
    if body.responsable_id is not None:
        responsable(db, edificio_id, body.responsable_id)
    if body.estado in ("resuelta", "cerrada"):
        pendiente = db.scalar(select(OrdenTrabajo.id).where(OrdenTrabajo.incidencia_id == inc.id,
                               OrdenTrabajo.estado.not_in(["terminada", "rechazada"])))
        if pendiente:
            raise HTTPException(409, "Termine o rechace la orden de trabajo antes de cerrar la incidencia")
    cambios = body.model_dump(exclude_unset=True, exclude={"version"})
    for k, v in cambios.items():
        if v is not None or k in ("responsable_id", "vencimiento"):
            setattr(inc, k, v)
    if inc.estado == "asignada" and not inc.responsable_id:
        raise HTTPException(422, "Indique un responsable")
    inc.version += 1
    inc.actualizado = utcnow()
    auditar(db, user, edificio_id, "incidencia.actualizada", inc.id,
            cambios=body.model_dump(mode="json", exclude_unset=True))
    destinatarios = [db.get(Residente, inc.autor_id)]
    if inc.responsable_id and inc.responsable_id != inc.autor_id:
        destinatarios.append(db.get(Residente, inc.responsable_id))
    notificar(db, edificio_id, destinatarios, "Incidencia actualizada", f"{inc.titulo}: {inc.estado}",
              clave=f"incidencia:{inc.id}:v{inc.version}")
    db.commit()
    return ficha(inc, INC_CAMPOS)


@router.post("/incidencias/{incidencia_id}/comentarios", status_code=201)
def comentar(edificio_id: str, incidencia_id: int, body: ComentarioIn, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    inc = ver_incidencia(db, user, edificio_id, incidencia_id)
    if inc.estado == "cerrada":
        raise HTTPException(409, "Incidencia cerrada")
    c = ComentarioIncidencia(edificio_id=edificio_id, incidencia_id=inc.id,
                            autor_id=user.residente_id, texto=body.texto)
    db.add(c)
    db.flush()
    auditar(db, user, edificio_id, "incidencia.comentario", inc.id, comentario_id=c.id)
    db.commit()
    return ficha(c, "id autor_id texto creado")


@router.post("/incidencias/{incidencia_id}/orden", status_code=201)
def crear_orden(edificio_id: str, incidencia_id: int, body: OrdenIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    inc = recurso(db, Incidencia, edificio_id, incidencia_id)
    p = recurso(db, Proveedor, edificio_id, body.proveedor_id)
    if inc.estado in ("resuelta", "cerrada") or not p.activo:
        raise HTTPException(409, "La incidencia o el proveedor no admiten trabajos")
    if db.scalar(select(OrdenTrabajo.id).where(OrdenTrabajo.incidencia_id == inc.id)):
        raise HTTPException(409, "La incidencia ya tiene una orden de trabajo")
    o = OrdenTrabajo(edificio_id=edificio_id, incidencia_id=inc.id, **body.model_dump())
    db.add(o)
    db.flush()
    auditar(db, user, edificio_id, "incidencia.orden_creada", inc.id, orden_id=o.id)
    db.commit()
    return ficha(o, ORD_CAMPOS)


@router.post("/ordenes-trabajo/{orden_id}/estado")
def estado_orden(edificio_id: str, orden_id: int, body: OrdenEstado, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    o = recurso(db, OrdenTrabajo, edificio_id, orden_id)
    permitidas = {"pendiente": {"aprobada", "rechazada"}, "aprobada": {"en_progreso", "rechazada"},
                  "en_progreso": {"terminada"}, "terminada": set(), "rechazada": set()}
    if body.estado not in permitidas[o.estado]:
        raise HTTPException(409, "Transición de orden no permitida")
    if body.evaluacion is not None and body.estado != "terminada":
        raise HTTPException(422, "Evalúe sólo trabajos terminados")
    o.estado = body.estado
    if o.estado == "aprobada":
        o.aprobada_por = user.residente_id
    o.evaluacion = body.evaluacion
    auditar(db, user, edificio_id, "incidencia.orden_actualizada", o.incidencia_id,
            orden_id=o.id, estado=o.estado)
    db.commit()
    return ficha(o, ORD_CAMPOS)


@router.get("/mantenimientos")
def planes(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    return [ficha(p, PLAN_CAMPOS) for p in db.scalars(select(PlanMantenimiento).where(
        PlanMantenimiento.edificio_id == edificio_id).order_by(PlanMantenimiento.proxima_fecha).limit(500))]


@router.post("/mantenimientos", status_code=201)
def crear_plan(edificio_id: str, body: PlanIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    responsable(db, edificio_id, body.responsable_id)
    p = PlanMantenimiento(edificio_id=edificio_id, **body.model_dump())
    db.add(p)
    db.flush()
    auditar(db, user, edificio_id, "mantenimiento.creado", p.id)
    db.commit()
    return ficha(p, PLAN_CAMPOS)


@router.patch("/mantenimientos/{plan_id}")
def activar_plan(edificio_id: str, plan_id: int, body: ActivoIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    p = recurso(db, PlanMantenimiento, edificio_id, plan_id)
    p.activo = body.activo
    auditar(db, user, edificio_id, "mantenimiento.configurado", p.id, activo=p.activo)
    db.commit()
    return ficha(p, PLAN_CAMPOS)
