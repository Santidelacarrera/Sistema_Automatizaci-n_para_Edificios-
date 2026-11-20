"""Router del Motor de Preguntas, Respuestas Híbrido y Banco de Memoria Persistente."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..memory_models import AuditoriaConsultaIA, MemoriaEntidad, MemoriaEpisodica
from ..models import Residente, Rol
from ..services.qa_engine.memory_bank import guardar_memoria_episodica, upsert_memoria_entidad
from ..services.qa_engine.orchestrator import indexar_edificio, responder_pregunta
from .operaciones import Admin, User, auditar, edificio, recurso

router = APIRouter(prefix="/edificios/{edificio_id}/ia", tags=["memoria_qa"])


@router.post("/indexar")
def indexar(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    """Indexa reglamentos, documentos, comunicados, asambleas, espacios e incidencias del edificio."""
    edificio(db, user, edificio_id, True)
    res = indexar_edificio(db, edificio_id)
    auditar(db, user, edificio_id, "ia.indexado", edificio_id, **res)
    db.commit()
    return res


@router.post("/preguntar")
def preguntar(edificio_id: str, body: dict, user: User, db: Session = Depends(get_db)):
    """Responde preguntas no literales usando expansión semántica, búsqueda híbrida, reranking y memoria persistente."""
    edificio(db, user, edificio_id)
    pregunta = str(body.get("pregunta") or "").strip()
    if len(pregunta) < 3 or len(pregunta) > 2000:
        raise HTTPException(422, "La pregunta debe tener entre 3 y 2000 caracteres")
    sesion_uuid = str(body.get("sesion_uuid") or "").strip()[:64] or None
    guardar = bool(body.get("guardar_memoria", True))
    uid_restringida = None
    if user.rol == Rol.residente:
        yo = db.get(Residente, user.residente_id)
        uid_restringida = yo.unidad_id if yo else -1
    return responder_pregunta(
        db, edificio_id, user, pregunta,
        unidad_id_restringida=uid_restringida,
        sesion_uuid=sesion_uuid,
        guardar_memoria=guardar,
    )


@router.get("/memoria")
def listar_memoria(edificio_id: str, user: User, tipo: str | None = None, db: Session = Depends(get_db)):
    """Lista memorias episódicas vigentes y memorias de entidad respetando el aislamiento del rol."""
    edificio(db, user, edificio_id)
    uid_restringida = None
    if user.rol == Rol.residente:
        yo = db.get(Residente, user.residente_id)
        uid_restringida = yo.unidad_id if yo else -1

    episodicas = []
    if tipo in (None, "episodica"):
        q_ep = select(MemoriaEpisodica).where(MemoriaEpisodica.edificio_id == edificio_id, MemoriaEpisodica.vigente.is_(True))
        if uid_restringida is not None:
            q_ep = q_ep.where((MemoriaEpisodica.unidad_id == uid_restringida) | (MemoriaEpisodica.unidad_id.is_(None)))
        episodicas = [
            {"id": m.id, "categoria": m.categoria, "clave_tema": m.clave_tema, "resumen": m.resumen,
             "hechos_clave": m.hechos_clave_json, "reemplaza_id": m.reemplaza_id, "creado": m.creado.isoformat()}
            for m in db.scalars(q_ep.order_by(MemoriaEpisodica.id.desc()).limit(100)).all()
        ]

    entidades = []
    if tipo in (None, "entidad"):
        q_ent = select(MemoriaEntidad).where(MemoriaEntidad.edificio_id == edificio_id)
        if uid_restringida is not None:
            q_ent = q_ent.where((MemoriaEntidad.unidad_id == uid_restringida) | (MemoriaEntidad.unidad_id.is_(None)))
        entidades = [
            {"id": e.id, "entidad_tipo": e.entidad_tipo, "entidad_clave": e.entidad_clave,
             "atributos": e.atributos_json, "hechos_verificados": e.hechos_verificados}
            for e in db.scalars(q_ent.order_by(MemoriaEntidad.id.desc()).limit(100)).all()
        ]
    return {"episodicas": episodicas, "entidades": entidades}


@router.post("/memoria", status_code=201)
def guardar_memoria_manual(edificio_id: str, body: dict, user: Admin, db: Session = Depends(get_db)):
    """Registra o consolida una memoria episódica o de entidad verificada."""
    edificio(db, user, edificio_id, True)
    clase = str(body.get("tipo") or "episodica").strip().lower()
    if clase == "entidad":
        etipo = str(body.get("entidad_tipo") or "").strip()
        eclave = str(body.get("entidad_clave") or "").strip()
        hechos = body.get("hechos") or []
        if not etipo or not eclave or not hechos:
            raise HTTPException(422, "entidad_tipo, entidad_clave y hechos requeridos")
        m = upsert_memoria_entidad(
            db, edificio_id, etipo, eclave,
            dict(body.get("atributos") or {}), [str(h) for h in hechos],
            fuente_ref=str(body.get("fuente_ref") or "manual"),
            unidad_id=body.get("unidad_id"),
        )
        db.commit()
        return {"id": m.id, "tipo": "entidad", "entidad_clave": m.entidad_clave}

    tema = str(body.get("clave_tema") or "").strip()
    resumen = str(body.get("resumen") or "").strip()
    if len(tema) < 2 or len(resumen) < 5:
        raise HTTPException(422, "clave_tema y resumen requeridos")
    m = guardar_memoria_episodica(
        db, edificio_id, str(body.get("categoria") or "decision"), tema, resumen,
        hechos_clave=[str(h) for h in (body.get("hechos_clave") or [])],
        fuente_ref=str(body.get("fuente_ref") or "manual"),
        residente_id=user.residente_id,
        unidad_id=body.get("unidad_id"),
    )
    db.commit()
    return {"id": m.id, "tipo": "episodica", "clave_tema": m.clave_tema, "reemplaza_id": m.reemplaza_id}


@router.delete("/memoria/{memoria_id}")
def desactivar_memoria(edificio_id: str, memoria_id: int, user: Admin, db: Session = Depends(get_db)):
    """Marca una memoria episódica como no vigente preservando su historial."""
    edificio(db, user, edificio_id, True)
    m = recurso(db, MemoriaEpisodica, edificio_id, memoria_id)
    m.vigente = False
    auditar(db, user, edificio_id, "ia.memoria_desactivada", m.id)
    db.commit()
    return {"id": m.id, "vigente": False}


@router.get("/auditoria")
def auditoria_ia(edificio_id: str, user: Admin, limit: int = 50, db: Session = Depends(get_db)):
    """Consulta la bitácora de auditoría del motor Q&A."""
    edificio(db, user, edificio_id)
    rows = db.scalars(
        select(AuditoriaConsultaIA)
        .where(AuditoriaConsultaIA.edificio_id == edificio_id)
        .order_by(AuditoriaConsultaIA.id.desc())
        .limit(min(200, max(1, limit)))
    ).all()
    return [
        {"id": r.id, "rol": r.rol, "pregunta": r.pregunta_sanitizada, "variantes": r.variantes_consulta,
         "fuentes": r.fuentes_citadas, "bloqueo_seguridad": r.bloqueo_seguridad,
         "modo": r.modo_respuesta, "creado": r.creado.isoformat()}
        for r in rows
    ]
