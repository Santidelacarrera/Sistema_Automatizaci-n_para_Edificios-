"""Gestión comercial interna: no procesa pagos ni emite documentos tributarios."""
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..commercial_models import ClienteSaaS, CobroSaaS, MensajeSoporte, PlanComercial, Suscripcion, TicketSoporte
from ..config import hoy_local, utcnow
from ..db import get_db
from ..models import Edificio, Rol
from ..operation_schemas import ActivoIn, Entrada
from ..services.commercial import uso
from ..services.notifications import administradores, notificar
from ..validacion import email_valido, rut_normalizar, rut_valido
from .gestion import Global
from .operaciones import Admin, auditar, edificio, ficha, recurso

router = APIRouter(tags=["comercial-y-soporte"])
PLAN = "id nombre precio_mensual max_unidades max_residentes max_dispositivos activo"
SUB = "edificio_id cliente_id plan_id estado vigente_hasta version"
COBRO = "id edificio_id cliente_id plan_id periodo monto vencimiento estado referencia creado"
TICKET = "id edificio_id autor_id titulo estado creado actualizado"


class ClienteIn(Entrada):
    nombre: str = Field(min_length=2, max_length=160)
    rut: str = Field(min_length=3, max_length=15)
    contacto: str = Field(min_length=3, max_length=160)


class PlanIn(Entrada):
    nombre: str = Field(min_length=3, max_length=100)
    precio_mensual: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    max_unidades: int = Field(ge=1, le=100000)
    max_residentes: int = Field(ge=1, le=1000000)
    max_dispositivos: int = Field(ge=0, le=10000)


class SuscripcionIn(Entrada):
    cliente_id: int
    plan_id: int
    estado: Literal["prueba", "activa", "suspendida", "cancelada"]
    vigente_hasta: date
    version: int = Field(ge=0)
    motivo: str = Field(min_length=10, max_length=500)


class CobroIn(Entrada):
    periodo: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    vencimiento: date


class ResolverCobro(Entrada):
    estado: Literal["pagado", "anulado"]
    referencia: str = Field(min_length=3, max_length=120)
    motivo: str = Field(min_length=10, max_length=500)


class TicketIn(Entrada):
    titulo: str = Field(min_length=3, max_length=160)
    texto: str = Field(min_length=3, max_length=6000)


class RespuestaIn(Entrada):
    texto: str = Field(min_length=3, max_length=6000)
    estado: Literal["abierto", "en_progreso", "resuelto"]


@router.get("/saas/clientes")
def clientes(user: Global, db: Session = Depends(get_db)):
    return [ficha(c, "id nombre rut contacto creado") for c in db.scalars(select(ClienteSaaS).order_by(ClienteSaaS.id).limit(1000))]


@router.post("/saas/clientes", status_code=201)
def crear_cliente(body: ClienteIn, user: Global, db: Session = Depends(get_db)):
    if not rut_valido(body.rut) or not email_valido(body.contacto):
        raise HTTPException(422, "RUT o correo de contacto inválido")
    c = ClienteSaaS(**{**body.model_dump(), "rut": rut_normalizar(body.rut)})
    db.add(c)
    db.flush()
    auditar(db, user, user.edificio_id, "saas.cliente_creado", c.id)
    db.commit()
    return ficha(c, "id nombre rut contacto creado")


@router.get("/saas/planes")
def planes(user: Global, db: Session = Depends(get_db)):
    return [ficha(p, PLAN) for p in db.scalars(select(PlanComercial).order_by(PlanComercial.id).limit(200))]


@router.post("/saas/planes", status_code=201)
def crear_plan(body: PlanIn, user: Global, db: Session = Depends(get_db)):
    p = PlanComercial(**body.model_dump())
    db.add(p)
    db.flush()
    auditar(db, user, user.edificio_id, "saas.plan_creado", p.id)
    db.commit()
    return ficha(p, PLAN)


@router.patch("/saas/planes/{plan_id}")
def disponibilidad_plan(plan_id: int, body: ActivoIn, user: Global, db: Session = Depends(get_db)):
    p = db.scalar(select(PlanComercial).where(PlanComercial.id == plan_id).with_for_update())
    if not p:
        raise HTTPException(404, "Plan no existe")
    # Los precios y límites son inmutables: nuevas condiciones requieren otro plan y cambio auditado de contrato.
    p.activo = body.activo
    auditar(db, user, user.edificio_id, "saas.plan_disponibilidad", p.id, activo=p.activo)
    db.commit()
    return ficha(p, PLAN)


def resumen_sub(db, eid):
    s = db.get(Suscripcion, eid)
    return {"edificio_id": eid, "uso": uso(db, eid), "contrato": ficha(s, SUB) if s else None,
            "plan": ficha(db.get(PlanComercial, s.plan_id), PLAN) if s else None,
            "vigente": bool(s and s.estado in ("prueba", "activa") and s.vigente_hasta >= hoy_local())}


@router.get("/saas/suscripciones")
def suscripciones(user: Global, db: Session = Depends(get_db)):
    return [resumen_sub(db, eid) for eid in db.scalars(select(Edificio.id).order_by(Edificio.id).limit(1000))]


@router.get("/edificios/{edificio_id}/suscripcion")
def mi_suscripcion(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    return resumen_sub(db, edificio_id)


@router.put("/saas/suscripciones/{edificio_id}")
def contratar(edificio_id: str, body: SuscripcionIn, user: Global, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    p = db.scalar(select(PlanComercial).where(PlanComercial.id == body.plan_id).with_for_update())
    s = db.get(Suscripcion, edificio_id)
    if not p or (not p.activo and (not s or s.plan_id != p.id)) or not db.get(ClienteSaaS, body.cliente_id):
        raise HTTPException(422, "Cliente o plan activo no existe")
    if body.version != (s.version if s else 0):
        raise HTTPException(409, "El contrato cambió; recargue antes de guardar")
    if body.estado in ("activa", "prueba") and body.vigente_hasta < hoy_local():
        raise HTTPException(422, "La vigencia no puede finalizar en el pasado")
    if any(valor > getattr(p, "max_" + nombre) for nombre, valor in uso(db, edificio_id).items()):
        raise HTTPException(409, "El uso actual supera los límites del plan elegido")
    if not s:
        s = Suscripcion(edificio_id=edificio_id, version=0)
        db.add(s)
    for k in ("cliente_id", "plan_id", "estado", "vigente_hasta"):
        setattr(s, k, getattr(body, k))
    s.version += 1
    auditar(db, user, edificio_id, "saas.suscripcion_configurada", edificio_id,
            motivo=body.motivo, estado=s.estado, plan_id=s.plan_id, version=s.version)
    db.commit()
    return resumen_sub(db, edificio_id)


@router.get("/saas/cobros")
def cobros(user: Global, antes: int | None = None, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    q = select(CobroSaaS)
    if antes is not None:
        q = q.where(CobroSaaS.id < antes)
    return [ficha(c, COBRO) for c in db.scalars(q.order_by(CobroSaaS.id.desc()).limit(limit))]


@router.post("/saas/suscripciones/{edificio_id}/cobros", status_code=201)
def emitir_cobro(edificio_id: str, body: CobroIn, user: Global, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    s = db.get(Suscripcion, edificio_id)
    if not s or s.estado != "activa" or s.vigente_hasta < hoy_local():
        raise HTTPException(409, "Se requiere una suscripción activa y vigente")
    if not s.creado.strftime("%Y-%m") <= body.periodo <= s.vigente_hasta.strftime("%Y-%m"):
        raise HTTPException(422, "Período fuera de la vigencia contratada")
    anterior = db.scalar(select(CobroSaaS).where(CobroSaaS.edificio_id == edificio_id, CobroSaaS.periodo == body.periodo))
    if anterior:
        if anterior.vencimiento != body.vencimiento:
            raise HTTPException(409, "El período ya tiene un cobro con otro vencimiento")
        return ficha(anterior, COBRO)
    p = db.get(PlanComercial, s.plan_id)
    c = CobroSaaS(edificio_id=edificio_id, cliente_id=s.cliente_id, plan_id=s.plan_id,
                 monto=p.precio_mensual, **body.model_dump())
    db.add(c)
    db.flush()
    auditar(db, user, edificio_id, "saas.cobro_emitido", c.id)
    db.commit()
    return ficha(c, COBRO)


@router.post("/saas/cobros/{cobro_id}/resolver")
def resolver_cobro(cobro_id: int, body: ResolverCobro, user: Global, db: Session = Depends(get_db)):
    c = db.scalar(select(CobroSaaS).where(CobroSaaS.id == cobro_id).with_for_update())
    if not c:
        raise HTTPException(404, "Cobro no existe")
    if c.estado != "pendiente":
        if (c.estado, c.referencia) == (body.estado, body.referencia):
            return ficha(c, COBRO)
        raise HTTPException(409, "Cobro ya resuelto; no se puede reescribir")
    c.estado, c.referencia = body.estado, body.referencia
    auditar(db, user, c.edificio_id, "saas.cobro_" + c.estado, c.id, motivo=body.motivo, referencia=body.referencia)
    db.commit()
    return ficha(c, COBRO)


@router.get("/saas/metricas")
def metricas(user: Global, db: Session = Depends(get_db)):
    estados = dict(db.execute(select(Suscripcion.estado, func.count()).group_by(Suscripcion.estado)).all())
    mrr = db.scalar(select(func.coalesce(func.sum(PlanComercial.precio_mensual), 0)).join(
        Suscripcion, Suscripcion.plan_id == PlanComercial.id).where(Suscripcion.estado == "activa", Suscripcion.vigente_hasta >= hoy_local()))
    return {"clientes": db.scalar(select(func.count(ClienteSaaS.id))),
            "edificios": db.scalar(select(func.count(Edificio.id))), "suscripciones": estados,
            "ingreso_mensual_contratado": mrr, "tickets_abiertos": db.scalar(select(func.count(TicketSoporte.id)).where(
                TicketSoporte.estado != "resuelto"))}


@router.get("/saas/soporte")
def soporte_global(user: Global, antes: int | None = None, db: Session = Depends(get_db)):
    q = select(TicketSoporte)
    if antes is not None:
        q = q.where(TicketSoporte.id < antes)
    return [ficha(t, TICKET) for t in db.scalars(q.order_by(TicketSoporte.id.desc()).limit(200))]


@router.get("/edificios/{edificio_id}/soporte")
def soporte(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    return [ficha(t, TICKET) for t in db.scalars(select(TicketSoporte).where(
        TicketSoporte.edificio_id == edificio_id).order_by(TicketSoporte.id.desc()).limit(200))]


@router.get("/saas/organizaciones")
def listar_organizaciones(user: Global, db: Session = Depends(get_db)):
    """Lista organizaciones SaaS y cantidad de miembros (24.03)."""
    from ..operations_models import MiembroOrganizacion, Organizacion
    orgs = db.scalars(select(Organizacion).order_by(Organizacion.id.desc())).all()
    miembros = db.scalars(select(MiembroOrganizacion)).all()
    conteo = {}
    for m in miembros:
        conteo[m.organizacion_id] = conteo.get(m.organizacion_id, 0) + 1
    return [{"id": o.id, "nombre": o.nombre, "slug": o.slug, "activo": o.activo, "miembros": conteo.get(o.id, 0)} for o in orgs]


@router.post("/saas/organizaciones", status_code=201)
def crear_organizacion(body: dict, user: Global, db: Session = Depends(get_db)):
    """Crea una organización SaaS con slug único (24.03)."""
    from ..operations_models import Organizacion
    nombre = str(body.get("nombre") or "").strip()
    slug = str(body.get("slug") or "").strip().lower()
    if len(nombre) < 2 or len(slug) < 2:
        raise HTTPException(422, "nombre y slug son obligatorios")
    if db.scalar(select(Organizacion).where(Organizacion.slug == slug)):
        raise HTTPException(409, "Slug de organización ya existe")
    org = Organizacion(nombre=nombre[:160], slug=slug[:60])
    db.add(org)
    db.commit()
    return {"id": org.id, "nombre": org.nombre, "slug": org.slug, "activo": org.activo}


@router.post("/saas/organizaciones/{org_id}/miembros", status_code=201)
def agregar_miembro_organizacion(org_id: int, body: dict, user: Global, db: Session = Depends(get_db)):
    """Agrega un miembro con rol interno a una organización SaaS (24.03)."""
    from ..operations_models import MiembroOrganizacion, Organizacion
    org = db.get(Organizacion, org_id)
    if not org:
        raise HTTPException(404, "Organización no existe")
    email = str(body.get("email") or "").strip().lower()
    rol = str(body.get("rol") or "gestor").strip().lower()
    if "@" not in email or rol not in ("propietario", "gestor", "lectura"):
        raise HTTPException(422, "Email o rol de organización inválido")
    if db.scalar(select(MiembroOrganizacion).where(MiembroOrganizacion.organizacion_id == org.id, MiembroOrganizacion.email == email)):
        raise HTTPException(409, "Miembro ya registrado en la organización")
    m = MiembroOrganizacion(organizacion_id=org.id, email=email[:160], rol=rol)
    db.add(m)
    db.commit()
    return {"id": m.id, "organizacion_id": m.organizacion_id, "email": m.email, "rol": m.rol}


@router.post("/saas/onboarding", status_code=201)
def onboarding_edificio(body: dict, user: Global, db: Session = Depends(get_db)):
    """Onboarding atómico de nuevo edificio, unidades iniciales y administrador (24.05)."""
    import secrets
    from ..models import Residente, Rol, Unidad
    from ..security import hash_clave_dispositivo, hash_password
    ed_id = str(body.get("edificio_id") or "").strip().lower()
    nombre_ed = str(body.get("nombre") or "").strip()
    admin_email = str(body.get("admin_email") or "").strip().lower()
    admin_nombre = str(body.get("admin_nombre") or "Administrador").strip()
    admin_pw = str(body.get("admin_password") or "TempPass123!")
    unidades_in = body.get("unidades") or ["101", "102"]
    if len(ed_id) < 2 or len(nombre_ed) < 2 or "@" not in admin_email or not unidades_in:
        raise HTTPException(422, "Datos de onboarding incompletos")
    if db.get(Edificio, ed_id):
        raise HTTPException(409, "Edificio ya existe")
    ed = Edificio(id=ed_id[:40], nombre=nombre_ed[:120], device_api_key=hash_clave_dispositivo(secrets.token_urlsafe(24)))
    db.add(ed)
    db.flush()
    coef = round(1.0 / len(unidades_in), 6)
    primera_u = None
    for num in unidades_in:
        u = Unidad(edificio_id=ed.id, numero=str(num)[:20], coeficiente=coef, codigo_cobro=f"ONB-{ed.id[:8]}-{num}"[:30])
        db.add(u)
        db.flush()
        if primera_u is None:
            primera_u = u
    adm = Residente(
        edificio_id=ed.id, unidad_id=primera_u.id, nombre=admin_nombre[:120],
        rut=str(body.get("admin_rut") or "11.111.111-1")[:20],
        email=admin_email[:160], rol=Rol.admin, password_hash=hash_password(admin_pw),
    )
    db.add(adm)
    db.commit()
    return {"edificio_id": ed.id, "unidades_creadas": len(unidades_in), "admin_email": adm.email}


@router.get("/saas/errores")
def listar_errores_ops(user: Global, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    """Consulta paginada del registro centralizado de errores (24.10, 19.21)."""
    from ..operations_models import ErrorLog
    rows = db.scalars(
        select(ErrorLog).order_by(ErrorLog.id.desc()).offset(max(0, offset)).limit(min(200, max(1, limit)))
    ).all()
    return [
        {"id": e.id, "metodo": e.metodo, "ruta": e.ruta, "mensaje": e.mensaje,
         "creado": e.creado.isoformat() if e.creado else None}
        for e in rows
    ]


@router.post("/edificios/{edificio_id}/soporte", status_code=201)
def nuevo_ticket(edificio_id: str, body: TicketIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    t = TicketSoporte(edificio_id=edificio_id, autor_id=user.residente_id, titulo=body.titulo)
    db.add(t)
    db.flush()
    db.add(MensajeSoporte(ticket_id=t.id, edificio_id=edificio_id, autor_id=user.residente_id, texto=body.texto))
    auditar(db, user, edificio_id, "soporte.creado", t.id)
    db.commit()
    return ficha(t, TICKET)


@router.get("/edificios/{edificio_id}/soporte/{ticket_id}")
def detalle_ticket(edificio_id: str, ticket_id: int, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    t = recurso(db, TicketSoporte, edificio_id, ticket_id)
    return {**ficha(t, TICKET), "mensajes": [ficha(m, "id autor_id texto creado") for m in db.scalars(select(
        MensajeSoporte).where(MensajeSoporte.ticket_id == ticket_id).order_by(MensajeSoporte.id))]}


@router.post("/edificios/{edificio_id}/soporte/{ticket_id}/mensajes", status_code=201)
def responder_ticket(edificio_id: str, ticket_id: int, body: RespuestaIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    t = recurso(db, TicketSoporte, edificio_id, ticket_id)
    if user.rol != Rol.superadmin and body.estado == "en_progreso":
        raise HTTPException(403, "Sólo soporte puede marcar la atención en progreso")
    t.estado, t.actualizado = body.estado, utcnow()
    m = MensajeSoporte(ticket_id=t.id, edificio_id=edificio_id, autor_id=user.residente_id, texto=body.texto)
    db.add(m)
    db.flush()
    auditar(db, user, edificio_id, "soporte.respondido", t.id, estado=t.estado)
    if user.rol == Rol.superadmin:
        notificar(db, edificio_id, administradores(db, edificio_id), "Respuesta de soporte", t.titulo, clave=f"soporte:{m.id}")
    db.commit()
    return {"id": m.id, "estado": t.estado}
