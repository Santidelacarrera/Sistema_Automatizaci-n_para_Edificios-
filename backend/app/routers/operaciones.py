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


@router.get("/personal")
def listar_personal(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    from ..operations_models import TrabajadorEdificio
    edificio(db, user, edificio_id)
    return [ficha(t, "id nombre rut cargo turno telefono email activo creado")
            for t in db.scalars(select(TrabajadorEdificio).where(
                TrabajadorEdificio.edificio_id == edificio_id).order_by(TrabajadorEdificio.nombre))]


@router.post("/personal", status_code=201)
def crear_personal(edificio_id: str, body: dict, user: Admin, db: Session = Depends(get_db)):
    from ..operations_models import TrabajadorEdificio
    edificio(db, user, edificio_id, True)
    rut_crudo = str(body.get("rut") or "")
    if not rut_valido(rut_crudo):
        raise HTTPException(422, "RUT inválido")
    rut = rut_normalizar(rut_crudo)
    if db.scalar(select(TrabajadorEdificio.id).where(
            TrabajadorEdificio.edificio_id == edificio_id, TrabajadorEdificio.rut == rut)):
        raise HTTPException(409, "Trabajador ya registrado en este edificio")
    nombre = str(body.get("nombre") or "").strip()
    cargo = str(body.get("cargo") or "conserje").strip()
    if len(nombre) < 2 or not cargo:
        raise HTTPException(422, "Nombre y cargo son obligatorios")
    t = TrabajadorEdificio(
        edificio_id=edificio_id, nombre=nombre[:120], rut=rut, cargo=cargo[:60],
        turno=str(body.get("turno") or "diurno")[:80],
        telefono=str(body.get("telefono") or "")[:20],
        email=str(body.get("email") or "")[:160],
    )
    db.add(t)
    db.flush()
    auditar(db, user, edificio_id, "personal.creado", t.id, cargo=t.cargo)
    db.commit()
    return ficha(t, "id nombre rut cargo turno telefono email activo creado")


@router.get("/personal/asistencia")
def listar_asistencia_personal(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    from ..operations_models import AsistenciaPersonal
    edificio(db, user, edificio_id)
    return [ficha(a, "id trabajador_id fecha tipo entrada salida observacion registrado_por creado")
            for a in db.scalars(select(AsistenciaPersonal).where(
                AsistenciaPersonal.edificio_id == edificio_id).order_by(AsistenciaPersonal.id.desc()).limit(200))]


@router.post("/personal/asistencia", status_code=201)
def registrar_asistencia_personal(edificio_id: str, body: dict, user: Admin, db: Session = Depends(get_db)):
    from datetime import date as dt_date
    from ..operations_models import AsistenciaPersonal, TrabajadorEdificio
    edificio(db, user, edificio_id, True)
    tid = int(body.get("trabajador_id") or 0)
    recurso(db, TrabajadorEdificio, edificio_id, tid)
    tipo = str(body.get("tipo") or "asistencia")
    if tipo not in ("asistencia", "turno_extra", "permiso", "licencia", "inasistencia"):
        raise HTTPException(422, "Tipo de registro inválido")
    fecha = dt_date.fromisoformat(body["fecha"]) if body.get("fecha") else utcnow().date()
    a = AsistenciaPersonal(
        edificio_id=edificio_id, trabajador_id=tid, fecha=fecha, tipo=tipo,
        entrada=str(body.get("entrada") or "")[:10],
        salida=str(body.get("salida") or "")[:10],
        observacion=str(body.get("observacion") or "")[:300],
        registrado_por=user.residente_id,
    )
    db.add(a)
    db.flush()
    auditar(db, user, edificio_id, "personal.asistencia", a.id, trabajador_id=tid, clase_asistencia=tipo)
    db.commit()
    return ficha(a, "id trabajador_id fecha tipo entrada salida observacion registrado_por creado")


@router.get("/registros-comunidad")
def listar_registros_comunidad(edificio_id: str, user: User, categoria: str | None = None,
                               unidad_id: int | None = None, db: Session = Depends(get_db)):
    from ..operations_models import RegistroComunidad
    edificio(db, user, edificio_id)
    q = select(RegistroComunidad).where(RegistroComunidad.edificio_id == edificio_id)
    if user.rol == Rol.residente:
        yo = db.get(Residente, user.residente_id)
        q = q.where((RegistroComunidad.unidad_id == yo.unidad_id) | (RegistroComunidad.unidad_id.is_(None)))
    elif unidad_id is not None:
        q = q.where(RegistroComunidad.unidad_id == unidad_id)
    if categoria:
        q = q.where(RegistroComunidad.categoria == categoria)
    return [ficha(r, "id unidad_id categoria titulo rut contacto detalle desde hasta activo creado")
            for r in db.scalars(q.order_by(RegistroComunidad.id.desc()).limit(300))]


@router.post("/registros-comunidad", status_code=201)
def crear_registro_comunidad(edificio_id: str, body: dict, user: User, db: Session = Depends(get_db)):
    from datetime import date as dt_date
    from ..operations_models import RegistroComunidad
    edificio(db, user, edificio_id, True)
    cat = str(body.get("categoria") or "").strip()
    permitidas = ("copropietario", "arrendatario", "contacto_emergencia", "mascota", "bien_comun", "comite", "bodega_estac")
    if cat not in permitidas:
        raise HTTPException(422, f"Categoría inválida. Use una de: {', '.join(permitidas)}")
    uid = body.get("unidad_id")
    if user.rol == Rol.residente:
        if cat not in ("contacto_emergencia", "mascota"):
            raise HTTPException(403, "El residente sólo puede registrar mascotas o contactos de emergencia de su unidad")
        yo = db.get(Residente, user.residente_id)
        uid = yo.unidad_id
    elif uid is not None:
        recurso(db, Unidad, edificio_id, int(uid))
    titulo = str(body.get("titulo") or "").strip()
    if len(titulo) < 2:
        raise HTTPException(422, "El título o nombre es obligatorio")
    rut_str = str(body.get("rut") or "").strip()
    if rut_str:
        if not rut_valido(rut_str):
            raise HTTPException(422, "RUT inválido")
        rut_str = rut_normalizar(rut_str)
    reg = RegistroComunidad(
        edificio_id=edificio_id,
        unidad_id=int(uid) if uid is not None else None,
        categoria=cat,
        titulo=titulo[:160],
        rut=rut_str,
        contacto=str(body.get("contacto") or "")[:160],
        detalle=str(body.get("detalle") or "")[:500],
        desde=dt_date.fromisoformat(body["desde"]) if body.get("desde") else None,
        hasta=dt_date.fromisoformat(body["hasta"]) if body.get("hasta") else None,
    )
    db.add(reg)
    db.flush()
    auditar(db, user, edificio_id, "comunidad.registro_creado", reg.id, categoria=cat)
    db.commit()
    return ficha(reg, "id unidad_id categoria titulo rut contacto detalle desde hasta activo creado")


@router.get("/visitas-recurrentes")
def listar_visitas_recurrentes(edificio_id: str, user: User, db: Session = Depends(get_db)):
    from ..operations_models import VisitaRecurrente
    edificio(db, user, edificio_id)
    q = select(VisitaRecurrente).where(VisitaRecurrente.edificio_id == edificio_id, VisitaRecurrente.activa.is_(True))
    if user.rol == Rol.residente:
        yo = db.get(Residente, user.residente_id)
        q = q.where(VisitaRecurrente.unidad_id == yo.unidad_id)
    return [ficha(v, "id unidad_id nombre_visita patente dias_semana hora_desde hora_hasta vigente_hasta activa creado")
            for v in db.scalars(q.order_by(VisitaRecurrente.id.desc()))]


@router.post("/visitas-recurrentes", status_code=201)
def crear_visita_recurrente(edificio_id: str, body: dict, user: User, db: Session = Depends(get_db)):
    from datetime import date as dt_date, timedelta
    from ..config import hoy_local
    from ..operations_models import VisitaRecurrente
    edificio(db, user, edificio_id, True)
    uid = body.get("unidad_id")
    if user.rol == Rol.residente:
        yo = db.get(Residente, user.residente_id)
        uid = yo.unidad_id
    elif uid is None:
        raise HTTPException(422, "unidad_id requerido")
    recurso(db, Unidad, edificio_id, int(uid))
    nombre = str(body.get("nombre_visita") or "").strip()
    if len(nombre) < 2:
        raise HTTPException(422, "Nombre de visita inválido")
    raw_dias = body.get("dias_semana", [0, 1, 2, 3, 4])
    if isinstance(raw_dias, str):
        dias = [int(x.strip()) for x in raw_dias.split(",") if x.strip().isdigit()]
    else:
        dias = [int(x) for x in raw_dias]
    vigente = dt_date.fromisoformat(body["vigente_hasta"]) if body.get("vigente_hasta") else (hoy_local() + timedelta(days=90))
    v = VisitaRecurrente(
        edificio_id=edificio_id,
        unidad_id=int(uid),
        nombre_visita=nombre[:120],
        patente=str(body.get("patente") or "").strip()[:12],
        dias_semana=dias,
        hora_desde=str(body.get("hora_desde") or "08:00")[:5],
        hora_hasta=str(body.get("hora_hasta") or "20:00")[:5],
        vigente_hasta=vigente,
    )
    db.add(v)
    db.flush()
    auditar(db, user, edificio_id, "visita_recurrente.creada", v.id, nombre=v.nombre_visita)
    db.commit()
    return ficha(v, "id unidad_id nombre_visita patente dias_semana hora_desde hora_hasta vigente_hasta activa creado")


@router.delete("/visitas-recurrentes/{visita_id}")
def desactivar_visita_recurrente(edificio_id: str, visita_id: int, user: User, db: Session = Depends(get_db)):
    from ..operations_models import VisitaRecurrente
    edificio(db, user, edificio_id, True)
    v = recurso(db, VisitaRecurrente, edificio_id, visita_id)
    if user.rol == Rol.residente:
        yo = db.get(Residente, user.residente_id)
        if v.unidad_id != yo.unidad_id:
            raise HTTPException(403, "No autorizado")
    v.activa = False
    auditar(db, user, edificio_id, "visita_recurrente.desactivada", v.id)
    db.commit()
    return {"id": v.id, "activa": False}


@router.get("/adjuntos/{entidad}/{entidad_id}")
def listar_adjuntos(edificio_id: str, entidad: str, entidad_id: int, user: User, db: Session = Depends(get_db)):
    from ..operations_models import AdjuntoOperacion
    edificio(db, user, edificio_id)
    if entidad not in ("incidencia", "porteria_visita", "porteria_encomienda"):
        raise HTTPException(422, "Entidad inválida")
    rows = db.scalars(select(AdjuntoOperacion).where(
        AdjuntoOperacion.edificio_id == edificio_id,
        AdjuntoOperacion.entidad == entidad,
        AdjuntoOperacion.entidad_id == entidad_id,
    ).order_by(AdjuntoOperacion.id.desc())).all()
    return [{"id": a.id, "entidad": a.entidad, "entidad_id": a.entidad_id, "nombre_archivo": a.nombre_archivo,
             "mime_type": a.mime_type, "tamano_bytes": len(a.contenido_b64 or ""), "autorizado_por": a.autorizado_por,
             "creado": a.creado.isoformat() if a.creado else None} for a in rows]


@router.post("/adjuntos/{entidad}/{entidad_id}", status_code=201)
def subir_adjunto(edificio_id: str, entidad: str, entidad_id: int, body: dict, user: User, db: Session = Depends(get_db)):
    import base64
    from ..operations_models import AdjuntoOperacion
    edificio(db, user, edificio_id, True)
    if entidad not in ("incidencia", "porteria_visita", "porteria_encomienda"):
        raise HTTPException(422, "Entidad inválida")
    if entidad in ("porteria_visita", "porteria_encomienda"):
        if user.rol == Rol.residente:
            raise HTTPException(403, "Solo conserjería o administración puede adjuntar fotografías de portería")
        if not body.get("autorizacion_residente", False):
            raise HTTPException(422, "Se requiere autorización explícita para almacenar fotografías en portería")
    mime = str(body.get("mime_type") or "").strip().lower()
    if mime not in ("image/png", "image/jpeg", "application/pdf"):
        raise HTTPException(422, "Tipo de archivo no permitido (use image/png, image/jpeg o application/pdf)")
    contenido_b64 = str(body.get("contenido_base64") or "").strip()
    try:
        raw = base64.b64decode(contenido_b64, validate=True)
    except Exception:
        raise HTTPException(422, "Contenido base64 inválido")
    if len(raw) == 0 or len(raw) > 2 * 1024 * 1024:
        raise HTTPException(422, "El adjunto debe medir entre 1 byte y 2 MiB")
    nombre = str(body.get("nombre_archivo") or "adjunto")[:140]
    adj = AdjuntoOperacion(
        edificio_id=edificio_id,
        entidad=entidad,
        entidad_id=entidad_id,
        nombre_archivo=nombre,
        mime_type=mime,
        contenido_b64=contenido_b64,
        autorizado_por=user.residente_id,
    )
    db.add(adj)
    db.flush()
    auditar(db, user, edificio_id, "adjunto.subido", adj.id, entidad=entidad, entidad_id=entidad_id)
    db.commit()
    return {"id": adj.id, "entidad": adj.entidad, "entidad_id": adj.entidad_id,
            "nombre_archivo": adj.nombre_archivo, "mime_type": adj.mime_type, "tamano_bytes": len(raw)}


@router.post("/push/suscribir", status_code=201)
def suscribir_push(edificio_id: str, body: dict, user: User, db: Session = Depends(get_db)):
    from ..operations_models import SuscripcionPush
    edificio(db, user, edificio_id, True)
    endpoint = str(body.get("endpoint") or body.get("token") or "").strip()
    if len(endpoint) < 10:
        raise HTTPException(422, "Endpoint o token de suscripción inválido")
    p256dh = str(body.get("p256dh") or "").strip()[:200]
    auth = str(body.get("auth") or "").strip()[:100]
    existente = db.scalar(select(SuscripcionPush).where(
        SuscripcionPush.residente_id == user.residente_id,
        SuscripcionPush.endpoint == endpoint,
    ))
    if existente:
        existente.p256dh = p256dh
        existente.auth = auth
        db.commit()
        return {"id": existente.id, "endpoint": existente.endpoint, "activo": True}
    s = SuscripcionPush(edificio_id=edificio_id, residente_id=user.residente_id, endpoint=endpoint, p256dh=p256dh, auth=auth)
    db.add(s)
    db.commit()
    return {"id": s.id, "endpoint": s.endpoint, "activo": True}


@router.post("/notificaciones/enviar-externo")
def enviar_notificacion_externa(edificio_id: str, body: dict, user: Admin, db: Session = Depends(get_db)):
    from ..operations_models import SuscripcionPush
    from ..services.push_sms import enviar_push, enviar_sms
    edificio(db, user, edificio_id, True)
    canal = str(body.get("canal") or "push").strip().lower()
    titulo = str(body.get("titulo") or "").strip()
    mensaje = str(body.get("mensaje") or "").strip()
    residente_id = body.get("residente_id")
    if canal not in ("push", "sms"):
        raise HTTPException(422, "Canal debe ser 'push' o 'sms'")
    if not mensaje:
        raise HTTPException(422, "Mensaje requerido")
    if canal == "push":
        q = select(SuscripcionPush).where(SuscripcionPush.edificio_id == edificio_id)
        if residente_id is not None:
            q = q.where(SuscripcionPush.residente_id == int(residente_id))
        tokens = [s.endpoint for s in db.scalars(q).all()]
        resultados = [
            r.a_dict()
            for r in (enviar_push(t, titulo or "Notificación de edificio", mensaje) for t in tokens)
        ]
        return {"canal": "push", "destinatarios": len(tokens), "resultados": resultados}
    telefono = str(body.get("telefono") or "").strip()
    if not telefono and residente_id is not None:
        res = db.get(Residente, int(residente_id))
        telefono = res.telefono if res else ""
    if not telefono:
        raise HTTPException(422, "Teléfono o residente_id con teléfono requerido para SMS")
    return enviar_sms(telefono, mensaje).a_dict()


@router.get("/padron-copropietarios")
def padron_copropietarios(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    """Padrón formal de copropietarios vinculados a unidades y alicuotas (17.06)."""
    from ..operations_models import RegistroComunidad
    edificio(db, user, edificio_id)
    unidades = {u.id: u for u in db.scalars(select(Unidad).where(Unidad.edificio_id == edificio_id)).all()}
    registros = db.scalars(select(RegistroComunidad).where(
        RegistroComunidad.edificio_id == edificio_id,
        RegistroComunidad.categoria == "copropietario",
        RegistroComunidad.activo.is_(True),
    ).order_by(RegistroComunidad.id.asc())).all()
    padron = []
    for r in registros:
        u = unidades.get(r.unidad_id) if r.unidad_id else None
        padron.append({
            "registro_id": r.id,
            "unidad_id": r.unidad_id,
            "unidad": u.numero if u else None,
            "torre": u.torre if u else None,
            "alicuota": float(u.coeficiente) if u else 0.0,
            "nombre": r.titulo,
            "rut": r.rut,
            "contacto": r.contacto,
            "desde": r.desde.isoformat() if r.desde else None,
        })
    return {"total_copropietarios": len(padron), "alicuota_cubierta": round(sum(p["alicuota"] for p in padron), 4), "padron": padron}


@router.post("/contabilidad/presupuestos/{presupuesto_id}/aprobar")
def aprobar_presupuesto_asamblea(edificio_id: str, presupuesto_id: int, body: dict, user: Admin, db: Session = Depends(get_db)):
    """Vincula formalmente un rubro presupuestario con la asamblea que lo aprobó (17.07)."""
    from ..operations_models import Asamblea, PresupuestoRubro
    edificio(db, user, edificio_id, True)
    p = recurso(db, PresupuestoRubro, edificio_id, presupuesto_id)
    asamblea_id = body.get("asamblea_id")
    if not asamblea_id:
        raise HTTPException(422, "asamblea_id requerido")
    recurso(db, Asamblea, edificio_id, int(asamblea_id))
    p.aprobado_asamblea_id = int(asamblea_id)
    auditar(db, user, edificio_id, "presupuesto.aprobado_asamblea", p.id, asamblea_id=int(asamblea_id))
    db.commit()
    return {"id": p.id, "categoria": p.categoria, "periodo": p.periodo, "aprobado_asamblea_id": p.aprobado_asamblea_id}


@router.get("/encuestas")
def listar_encuestas(edificio_id: str, user: User, db: Session = Depends(get_db)):
    from ..operations_models import EncuestaComunidad, RespuestaEncuesta
    edificio(db, user, edificio_id)
    encuestas = db.scalars(select(EncuestaComunidad).where(EncuestaComunidad.edificio_id == edificio_id).order_by(EncuestaComunidad.id.desc())).all()
    salida = []
    for e in encuestas:
        resps = db.scalars(select(RespuestaEncuesta).where(RespuestaEncuesta.encuesta_id == e.id)).all()
        promedio = round(sum(r.puntaje for r in resps) / len(resps), 2) if resps else 0.0
        salida.append({
            "id": e.id, "titulo": e.titulo, "pregunta": e.pregunta, "activa": e.activa,
            "total_respuestas": len(resps), "indice_satisfaccion": promedio,
            "creado": e.creado.isoformat() if e.creado else None,
        })
    return salida


@router.post("/encuestas", status_code=201)
def crear_encuesta(edificio_id: str, body: dict, user: Admin, db: Session = Depends(get_db)):
    from ..operations_models import EncuestaComunidad
    edificio(db, user, edificio_id, True)
    titulo = str(body.get("titulo") or "").strip()
    pregunta = str(body.get("pregunta") or "").strip()
    if len(titulo) < 3 or len(pregunta) < 5:
        raise HTTPException(422, "Título y pregunta requeridos")
    e = EncuestaComunidad(edificio_id=edificio_id, titulo=titulo[:160], pregunta=pregunta[:500])
    db.add(e)
    db.commit()
    return {"id": e.id, "titulo": e.titulo, "pregunta": e.pregunta, "activa": e.activa}


@router.post("/encuestas/{encuesta_id}/responder", status_code=201)
def responder_encuesta(edificio_id: str, encuesta_id: int, body: dict, user: User, db: Session = Depends(get_db)):
    from ..operations_models import EncuestaComunidad, RespuestaEncuesta
    edificio(db, user, edificio_id, True)
    e = recurso(db, EncuestaComunidad, edificio_id, encuesta_id)
    if not e.activa:
        raise HTTPException(409, "Encuesta cerrada")
    try:
        puntaje = int(body.get("puntaje"))
    except (TypeError, ValueError):
        raise HTTPException(422, "Puntaje entero requerido (1 a 5)")
    if puntaje < 1 or puntaje > 5:
        raise HTTPException(422, "El puntaje debe estar entre 1 y 5")
    previa = db.scalar(select(RespuestaEncuesta).where(
        RespuestaEncuesta.encuesta_id == e.id, RespuestaEncuesta.residente_id == user.residente_id))
    if previa:
        raise HTTPException(409, "Ya respondiste esta encuesta")
    r = RespuestaEncuesta(
        edificio_id=edificio_id, encuesta_id=e.id, residente_id=user.residente_id,
        puntaje=puntaje, comentario=str(body.get("comentario") or "")[:400],
    )
    db.add(r)
    db.commit()
    return {"id": r.id, "encuesta_id": e.id, "puntaje": r.puntaje}
