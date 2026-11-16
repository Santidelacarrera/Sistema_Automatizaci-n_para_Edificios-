"""Consultas comunitarias trazables. No certifica validez jurídica de una votación."""
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import utcnow
from ..db import get_db
from ..models import Residente, Rol, Unidad
from ..operation_schemas import ActaIn, AsambleaIn, ParticipanteIn, VotoIn
from ..operations_models import Asamblea, ParticipanteAsamblea, Voto
from ..services.notifications import notificar
from .operaciones import Admin, User, auditar, edificio, ficha, recurso

router = APIRouter(prefix="/edificios/{edificio_id}/asambleas", tags=["asambleas"])
CAMPOS = "id titulo agenda fecha estado opciones acta cerrada"


@router.post("", status_code=201)
def crear(edificio_id: str, body: AsambleaIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    a = Asamblea(edificio_id=edificio_id, creado_por=user.residente_id, **body.model_dump())
    db.add(a)
    db.flush()
    auditar(db, user, edificio_id, "asamblea.creada", a.id)
    db.commit()
    return ficha(a, CAMPOS)


@router.get("")
def listar(edificio_id: str, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    q = select(Asamblea).where(Asamblea.edificio_id == edificio_id)
    if user.rol not in (Rol.admin, Rol.superadmin):
        q = q.where(Asamblea.estado != "borrador")
    return [ficha(a, CAMPOS) for a in db.scalars(q.order_by(Asamblea.id.desc()).limit(100))]


@router.post("/{asamblea_id}/participantes", status_code=201)
def participante(edificio_id: str, asamblea_id: int, body: ParticipanteIn, user: Admin,
                 db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    a = recurso(db, Asamblea, edificio_id, asamblea_id)
    if a.estado != "borrador":
        raise HTTPException(409, "El padrón queda fijado al abrir la votación")
    r = recurso(db, Residente, edificio_id, body.residente_id)
    if not r.activo or r.rol not in (Rol.residente, Rol.admin):
        raise HTTPException(422, "Seleccione un residente activo autorizado para representar su unidad")
    if db.scalar(select(ParticipanteAsamblea.id).where(ParticipanteAsamblea.asamblea_id == a.id,
                                                      ParticipanteAsamblea.unidad_id == r.unidad_id)):
        raise HTTPException(409, "La unidad ya tiene representante")
    u = recurso(db, Unidad, edificio_id, r.unidad_id)
    p = ParticipanteAsamblea(edificio_id=edificio_id, asamblea_id=a.id, unidad_id=u.id,
                             residente_id=r.id, coeficiente=u.coeficiente)
    db.add(p)
    db.flush()
    auditar(db, user, edificio_id, "asamblea.participante", a.id, participante_id=p.id)
    db.commit()
    return {"id": p.id}


@router.post("/{asamblea_id}/abrir")
def abrir(edificio_id: str, asamblea_id: int, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    a = recurso(db, Asamblea, edificio_id, asamblea_id)
    if a.estado != "borrador":
        raise HTTPException(409, "La asamblea ya fue abierta")
    ids = db.scalars(select(ParticipanteAsamblea.residente_id).where(ParticipanteAsamblea.asamblea_id == a.id)).all()
    if not ids:
        raise HTTPException(422, "Agregue representantes antes de abrir la votación")
    a.estado = "abierta"
    notificar(db, edificio_id, db.scalars(select(Residente).where(Residente.id.in_(ids))).all(),
              "Convocatoria de asamblea", a.titulo, clave=f"asamblea:{a.id}:abierta")
    auditar(db, user, edificio_id, "asamblea.abierta", a.id)
    db.commit()
    return ficha(a, CAMPOS)


def mi_participacion(db, eid, aid, user):
    p = db.scalar(select(ParticipanteAsamblea).where(ParticipanteAsamblea.edificio_id == eid,
        ParticipanteAsamblea.asamblea_id == aid, ParticipanteAsamblea.residente_id == user.residente_id))
    if not p:
        raise HTTPException(403, "No figura en el padrón autorizado")
    return p


@router.post("/{asamblea_id}/asistencia")
def asistencia(edificio_id: str, asamblea_id: int, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    a = recurso(db, Asamblea, edificio_id, asamblea_id)
    if a.estado != "abierta":
        raise HTTPException(409, "Asamblea no abierta")
    p = mi_participacion(db, edificio_id, a.id, user)
    p.presente = True
    auditar(db, user, edificio_id, "asamblea.asistencia", a.id, participante_id=p.id)
    db.commit()
    return {"presente": True}


@router.post("/{asamblea_id}/votos", status_code=201)
def votar(edificio_id: str, asamblea_id: int, body: VotoIn, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    a = recurso(db, Asamblea, edificio_id, asamblea_id)
    if a.estado != "abierta":
        raise HTTPException(409, "La votación no está abierta")
    p = mi_participacion(db, edificio_id, a.id, user)
    if not p.presente:
        raise HTTPException(409, "Confirme asistencia antes de votar")
    if body.opcion >= len(a.opciones):
        raise HTTPException(422, "Opción no existe")
    if db.scalar(select(Voto.id).where(Voto.participante_id == p.id)):
        raise HTTPException(409, "El representante ya votó")
    recibo = hashlib.sha256(f"{a.id}:{p.id}:{body.opcion}:{secrets.token_hex(32)}".encode()).hexdigest()
    v = Voto(edificio_id=edificio_id, asamblea_id=a.id, participante_id=p.id, opcion=body.opcion, recibo=recibo)
    db.add(v)
    auditar(db, user, edificio_id, "asamblea.voto", a.id, recibo=recibo)
    db.commit()
    return {"recibo": recibo}


@router.post("/{asamblea_id}/cerrar")
def cerrar(edificio_id: str, asamblea_id: int, body: ActaIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    a = recurso(db, Asamblea, edificio_id, asamblea_id)
    if a.estado != "abierta":
        raise HTTPException(409, "Asamblea no abierta")
    a.estado, a.acta, a.cerrada = "cerrada", body.acta, utcnow()
    auditar(db, user, edificio_id, "asamblea.cerrada", a.id)
    db.commit()
    return ficha(a, CAMPOS)


@router.get("/{asamblea_id}")
def detalle(edificio_id: str, asamblea_id: int, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    a = recurso(db, Asamblea, edificio_id, asamblea_id)
    admin = user.rol in (Rol.admin, Rol.superadmin)
    if a.estado == "borrador" and not admin:
        raise HTTPException(404, "Asamblea no publicada")
    ps = db.scalars(select(ParticipanteAsamblea).where(ParticipanteAsamblea.asamblea_id == a.id)).all()
    votos = db.scalars(select(Voto).where(Voto.asamblea_id == a.id)).all()
    pesos = {p.id: p.coeficiente for p in ps}
    resultados = [{"opcion": op, "votos": sum(v.opcion == idx for v in votos),
                   "coeficiente": float(sum(pesos[v.participante_id] for v in votos if v.opcion == idx))}
                  for idx, op in enumerate(a.opciones)] if a.estado == "cerrada" else None
    propio = next((p for p in ps if p.residente_id == user.residente_id), None)
    voto = next((v for v in votos if propio and v.participante_id == propio.id), None)
    return {**ficha(a, CAMPOS), "resultados": resultados, "participantes": len(ps),
            "asistentes": sum(p.presente for p in ps), "puede_votar": bool(propio and propio.presente and not voto and a.estado == "abierta"),
            "en_padron": propio is not None, "presente": bool(propio and propio.presente),
            "mi_recibo": voto.recibo if voto else None,
            "padron": [ficha(p, "residente_id unidad_id coeficiente presente") for p in ps] if admin else [],
            "validez_juridica_verificada": False}
