from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import rules, tasks
from ..config import utcnow
from ..db import get_db
from ..models import (Cargo, Edificio, EspacioComun, LecturaMedidor, Residente, ReservaEspacio,
                      Rol, Unidad, Visita)
from ..schemas import (CircularIn, GenerarGastosIn, LecturaIn, ReservaEspacioIn, UnidadIn, VisitaIn)
from ..security import Principal, current_user, require_roles, tenant_of
from ..services import access, email, finance, reconciliation
from ..services.resultado import ENCOLADO, NO_CONFIGURADO

router = APIRouter(prefix="/edificios/{edificio_id}", tags=["edificio"])
Admin = Annotated[Principal, Depends(require_roles(Rol.admin))]
User = Annotated[Principal, Depends(current_user)]


def _ed(db: Session, user: Principal, edificio_id: str) -> Edificio:
    tenant_of(user, edificio_id)
    ed = db.get(Edificio, edificio_id)
    if not ed:
        raise HTTPException(404, "Edificio no existe")
    return ed


def _unidad_propia(db, user, ed, unidad_id):
    """Residentes sólo operan sobre su propia unidad; admin sobre cualquiera del edificio."""
    me = db.get(Residente, user.residente_id)
    if user.rol == Rol.residente and unidad_id not in (None, me.unidad_id):
        raise HTTPException(403, "Sólo puede operar sobre su unidad")
    if unidad_id is None and me:
        unidad_id = me.unidad_id  # por defecto, la unidad propia
    if unidad_id is None:
        raise HTTPException(422, "unidad_id requerido")
    u = db.get(Unidad, unidad_id)
    if not u or u.edificio_id != ed.id:
        raise HTTPException(404, "Unidad no existe en este edificio")
    return u


# ---- administración ----
@router.post("/unidades", status_code=201)
def crear_unidad(edificio_id: str, body: UnidadIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    u = Unidad(edificio_id=ed.id, **body.model_dump())
    db.add(u)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Unidad o código de cobro duplicado")
    return {"id": u.id}


@router.post("/lecturas", status_code=201)
def cargar_lectura(edificio_id: str, body: LecturaIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    _unidad_propia(db, user, ed, body.unidad_id)
    db.add(LecturaMedidor(edificio_id=ed.id, **body.model_dump()))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Lectura ya existe para unidad/periodo/servicio")
    return {"ok": True}


# ---- finanzas ----
@router.post("/gastos-comunes/generar")
def generar_gastos(edificio_id: str, body: GenerarGastosIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    try:
        res = finance.generar_cargos(db, ed.id, body.periodo, body.vencimiento,
                                     [g.model_dump() for g in body.gastos])
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e))
    db.commit()
    return res


@router.post("/gastos-comunes/enviar/{periodo}")
def enviar_gastos(edificio_id: str, periodo: str, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    if not email.configurado():
        return {"encolado": False, "estado": NO_CONFIGURADO, "motivo": email.motivo_no_configurado()}
    tasks.enviar_gastos_comunes.delay(ed.id, periodo)
    return {"encolado": True, "estado": ENCOLADO, "motivo": ""}


@router.post("/circulares")
def enviar_circular(edificio_id: str, body: CircularIn, user: Admin, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    if not email.configurado():
        return {"encolado": False, "estado": NO_CONFIGURADO, "motivo": email.motivo_no_configurado()}
    tasks.enviar_circular.delay(ed.id, body.asunto, body.cuerpo_html)
    return {"encolado": True, "estado": ENCOLADO, "motivo": ""}


@router.post("/conciliacion")
async def conciliar(edificio_id: str, user: Admin, cartola: UploadFile = File(...), db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    try:
        movs = reconciliation.leer_cartola(await cartola.read())
    except (ValueError, KeyError) as e:
        raise HTTPException(422, f"Cartola inválida: {e}")
    res = reconciliation.conciliar(db, ed.id, movs)
    db.commit()
    return res


@router.get("/unidades/{unidad_id}/deuda")
def deuda(edificio_id: str, unidad_id: int, user: User, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    u = _unidad_propia(db, user, ed, unidad_id)
    return {"unidad": u.numero, "deuda": finance.deuda_unidad(db, u.id)}


# ---- visitas y espacios comunes ----
@router.post("/visitas", status_code=201)
def reservar_visita(edificio_id: str, body: VisitaIn, user: User, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    u = _unidad_propia(db, user, ed, body.unidad_id)
    try:
        v = access.reservar_visita(db, ed, u.id, body.nombre_visita, body.desde, body.hasta,
                                   body.patente, body.usa_estacionamiento, body.usos_max)
    except access.AccesoError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return {"id": v.id, "codigo_qr": v.codigo_qr}


@router.post("/reservas-espacio", status_code=201)
def reservar_espacio(edificio_id: str, body: ReservaEspacioIn, user: User, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    u = _unidad_propia(db, user, ed, body.unidad_id)
    esp = db.get(EspacioComun, body.espacio_id)
    if not esp or esp.edificio_id != ed.id:
        raise HTTPException(404, "Espacio no existe")
    if body.hasta <= body.desde:
        raise HTTPException(422, "Rango horario inválido")
    choque = db.scalar(select(func.count(ReservaEspacio.id)).where(
        ReservaEspacio.espacio_id == esp.id, ReservaEspacio.estado == "confirmada",
        ReservaEspacio.desde < body.hasta, ReservaEspacio.hasta > body.desde))
    if choque:
        raise HTTPException(409, "Espacio ya reservado en ese horario")
    mes_ini = body.desde.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    usos_mes = db.scalar(select(func.count(ReservaEspacio.id)).where(
        ReservaEspacio.unidad_id == u.id, ReservaEspacio.espacio_id == esp.id,
        ReservaEspacio.estado == "confirmada", ReservaEspacio.desde >= mes_ini,
        ReservaEspacio.desde < (mes_ini + timedelta(days=32)).replace(day=1)))
    d = rules.evaluar(db, ed.id, esp.accion, {"inicio": body.desde, "fin": body.hasta,
                                              "usos_mes": usos_mes, "deuda": finance.deuda_unidad(db, u.id)})
    if not d.permitido:
        raise HTTPException(422, {"motivos": d.motivos})
    r = ReservaEspacio(edificio_id=ed.id, espacio_id=esp.id, unidad_id=u.id, desde=body.desde, hasta=body.hasta)
    db.add(r)
    if float(esp.tarifa) > 0:  # la reserva actualiza automáticamente la cuenta
        db.add(Cargo(edificio_id=ed.id, unidad_id=u.id, periodo=body.desde.strftime("%Y-%m"),
                     concepto=f"Reserva {esp.nombre}", monto=esp.tarifa, saldo=esp.tarifa,
                     vencimiento=body.desde.date()))
    db.commit()
    return {"id": r.id, "tarifa": float(esp.tarifa)}


@router.get("/visitas/cupos")
def cupos(edificio_id: str, user: User, db: Session = Depends(get_db)):
    ed = _ed(db, user, edificio_id)
    ocupados = access.cupos_ocupados(db, ed.id, utcnow(), utcnow() + timedelta(minutes=1))
    return {"total": ed.cupos_visitas, "ocupados": ocupados, "libres": ed.cupos_visitas - ocupados}
