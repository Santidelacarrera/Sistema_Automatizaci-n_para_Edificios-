"""Banco de memoria persistente de 3 niveles: corto plazo, episódica y de entidad."""
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import utcnow
from ...memory_models import MemoriaEntidad, MemoriaEpisodica, MensajeMemoria, SesionMemoria


def obtener_o_crear_sesion(
    db: Session,
    edificio_id: str,
    residente_id: int,
    unidad_id: int | None,
    sesion_uuid: str | None = None,
) -> SesionMemoria:
    if sesion_uuid:
        s = db.scalar(select(SesionMemoria).where(
            SesionMemoria.sesion_uuid == sesion_uuid,
            SesionMemoria.edificio_id == edificio_id,
            SesionMemoria.residente_id == residente_id,
        ))
        if s:
            return s
    s = SesionMemoria(
        sesion_uuid=sesion_uuid or uuid4().hex,
        edificio_id=edificio_id,
        residente_id=residente_id,
        unidad_id=unidad_id,
        entidades_activas=[],
    )
    db.add(s)
    db.flush()
    return s


def registrar_turno_sesion(
    db: Session,
    sesion: SesionMemoria,
    rol: str,
    contenido: str,
    entidades_nuevas: list[str] | None = None,
) -> None:
    db.add(MensajeMemoria(sesion_id=sesion.id, rol=rol, contenido=contenido, metadatos_json={}))
    if entidades_nuevas:
        activas = list(sesion.entidades_activas or [])
        for e in entidades_nuevas:
            if e and e not in activas:
                activas.append(e)
        sesion.entidades_activas = activas[-8:]
    sesion.actualizado = utcnow()
    db.flush()


def obtener_historial_sesion(db: Session, sesion_id: int, limite: int = 6) -> list[str]:
    rows = db.scalars(
        select(MensajeMemoria)
        .where(MensajeMemoria.sesion_id == sesion_id)
        .order_by(MensajeMemoria.id.desc())
        .limit(limite)
    ).all()
    return [f"{m.rol}: {m.contenido}" for m in reversed(rows)]


def guardar_memoria_episodica(
    db: Session,
    edificio_id: str,
    categoria: str,
    clave_tema: str,
    resumen: str,
    hechos_clave: list[str] | None = None,
    fuente_ref: str = "",
    residente_id: int | None = None,
    unidad_id: int | None = None,
) -> MemoriaEpisodica:
    """Consolida memoria episódica sin duplicar ni olvidar: marca previa como reemplazada."""
    clave_norm = clave_tema.strip().lower()[:120]
    previa = db.scalar(
        select(MemoriaEpisodica)
        .where(
            MemoriaEpisodica.edificio_id == edificio_id,
            MemoriaEpisodica.clave_tema == clave_norm,
            MemoriaEpisodica.unidad_id == unidad_id,
            MemoriaEpisodica.vigente.is_(True),
        )
        .order_by(MemoriaEpisodica.id.desc())
    )
    if previa and previa.resumen.strip() == resumen.strip():
        return previa
    nueva = MemoriaEpisodica(
        edificio_id=edificio_id,
        residente_id=residente_id,
        unidad_id=unidad_id,
        categoria=categoria[:50],
        clave_tema=clave_norm,
        resumen=resumen.strip(),
        hechos_clave_json=hechos_clave or [],
        fuente_ref=fuente_ref[:200],
        vigente=True,
        reemplaza_id=previa.id if previa else None,
    )
    if previa:
        previa.vigente = False
    db.add(nueva)
    db.flush()
    return nueva


def buscar_memorias_episodicas(
    db: Session,
    edificio_id: str,
    tokens: list[str],
    unidad_id_restringida: int | None = None,
    limite: int = 5,
) -> list[MemoriaEpisodica]:
    q = select(MemoriaEpisodica).where(
        MemoriaEpisodica.edificio_id == edificio_id,
        MemoriaEpisodica.vigente.is_(True),
    )
    if unidad_id_restringida is not None:
        q = q.where((MemoriaEpisodica.unidad_id == unidad_id_restringida) | (MemoriaEpisodica.unidad_id.is_(None)))
    candidatos = db.scalars(q.order_by(MemoriaEpisodica.id.desc()).limit(100)).all()
    if not tokens:
        return candidatos[:limite]
    set_toks = set(tokens)
    puntuados = []
    for m in candidatos:
        texto = f"{m.clave_tema} {m.resumen} {' '.join(m.hechos_clave_json or [])}".lower()
        hits = sum(1 for t in set_toks if t in texto)
        if hits > 0:
            puntuados.append((hits, m.id, m))
    puntuados.sort(key=lambda x: (-x[0], -x[1]))
    return [item[2] for item in puntuados[:limite]]


def upsert_memoria_entidad(
    db: Session,
    edificio_id: str,
    entidad_tipo: str,
    entidad_clave: str,
    atributos: dict,
    hechos: list[str],
    fuente_ref: str = "",
    unidad_id: int | None = None,
) -> MemoriaEntidad:
    """Consolida hechos verificados de una entidad sin sobrescribir atributos previos no vacíos."""
    clave = entidad_clave.strip()[:120]
    m = db.scalar(select(MemoriaEntidad).where(
        MemoriaEntidad.edificio_id == edificio_id,
        MemoriaEntidad.entidad_tipo == entidad_tipo[:40],
        MemoriaEntidad.entidad_clave == clave,
    ))
    if m:
        attrs = dict(m.atributos_json or {})
        attrs.update({k: v for k, v in atributos.items() if v is not None})
        prev_hechos = list(m.hechos_verificados or [])
        for h in hechos:
            if h not in prev_hechos:
                prev_hechos.append(h)
        m.atributos_json = attrs
        m.hechos_verificados = prev_hechos[-20:]
        if fuente_ref:
            m.fuente_ref = fuente_ref[:200]
        if unidad_id is not None:
            m.unidad_id = unidad_id
        m.actualizado = utcnow()
        db.flush()
        return m
    m = MemoriaEntidad(
        edificio_id=edificio_id,
        unidad_id=unidad_id,
        entidad_tipo=entidad_tipo[:40],
        entidad_clave=clave,
        atributos_json=atributos,
        hechos_verificados=hechos[:20],
        confianza=1.0,
        fuente_ref=fuente_ref[:200],
    )
    db.add(m)
    db.flush()
    return m


def buscar_memorias_entidad(
    db: Session,
    edificio_id: str,
    tokens: list[str],
    unidad_id_restringida: int | None = None,
    limite: int = 5,
) -> list[MemoriaEntidad]:
    q = select(MemoriaEntidad).where(MemoriaEntidad.edificio_id == edificio_id)
    if unidad_id_restringida is not None:
        q = q.where((MemoriaEntidad.unidad_id == unidad_id_restringida) | (MemoriaEntidad.unidad_id.is_(None)))
    rows = db.scalars(q.order_by(MemoriaEntidad.id.desc()).limit(120)).all()
    if not tokens:
        return rows[:limite]
    set_toks = set(tokens)
    puntuados = []
    for e in rows:
        texto = f"{e.entidad_tipo} {e.entidad_clave} {' '.join(e.hechos_verificados or [])}".lower()
        hits = sum(1 for t in set_toks if t in texto)
        if e.entidad_clave.lower() in set_toks:
            hits += 10
        if hits > 0:
            puntuados.append((hits, e.id, e))
    puntuados.sort(key=lambda x: (-x[0], -x[1]))
    return [item[2] for item in puntuados[:limite]]
