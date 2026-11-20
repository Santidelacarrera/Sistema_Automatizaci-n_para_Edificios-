"""Modelos relacionales y vectoriales del Banco de Memoria Persistente y Motor Q&A."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .config import utcnow
from .db import Base


class FuenteConocimiento(Base):
    """Documento o fuente estructurada indexada por edificio."""
    __tablename__ = "fuentes_conocimiento"
    __table_args__ = (UniqueConstraint("edificio_id", "tipo_fuente", "referencia_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    tipo_fuente: Mapped[str] = mapped_column(String(40), index=True)  # reglamento | documento | comunicado | asamblea | espacio | incidencia
    referencia_id: Mapped[int] = mapped_column(Integer)
    titulo: Mapped[str] = mapped_column(String(200))
    publico_comunidad: Mapped[bool] = mapped_column(Boolean, default=True)
    unidad_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"), nullable=True, index=True)
    hash_contenido: Mapped[str] = mapped_column(String(64))
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FragmentoConocimiento(Base):
    """Fragmento estructural con metadatos, tokens BM25 y vector semántico."""
    __tablename__ = "fragmentos_conocimiento"
    id: Mapped[int] = mapped_column(primary_key=True)
    fuente_id: Mapped[int] = mapped_column(ForeignKey("fuentes_conocimiento.id", ondelete="CASCADE"), index=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"), nullable=True, index=True)
    publico_comunidad: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    seccion: Mapped[str] = mapped_column(String(200), default="General")
    tipo_bloque: Mapped[str] = mapped_column(String(20), default="texto")  # texto | tabla | lista
    contenido: Mapped[str] = mapped_column(Text)
    tokens_bm25: Mapped[list] = mapped_column(JSON, default=list)
    embedding_json: Mapped[list] = mapped_column(JSON, default=list)
    metadatos_json: Mapped[dict] = mapped_column(JSON, default=dict)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SesionMemoria(Base):
    """Memoria de corto plazo por usuario/edificio para mantener el hilo y correferencias."""
    __tablename__ = "sesiones_memoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    sesion_uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    residente_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"), index=True)
    unidad_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"), nullable=True)
    entidades_activas: Mapped[list] = mapped_column(JSON, default=list)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MensajeMemoria(Base):
    """Turnos de conversación almacenados en la memoria de corto plazo."""
    __tablename__ = "mensajes_memoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    sesion_id: Mapped[int] = mapped_column(ForeignKey("sesiones_memoria.id", ondelete="CASCADE"), index=True)
    rol: Mapped[str] = mapped_column(String(20))  # usuario | asistente
    contenido: Mapped[str] = mapped_column(Text)
    metadatos_json: Mapped[dict] = mapped_column(JSON, default=dict)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MemoriaEpisodica(Base):
    """Memoria episódica de largo plazo entre sesiones con consolidación y versionado."""
    __tablename__ = "memorias_episodicas"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    residente_id: Mapped[int | None] = mapped_column(ForeignKey("residentes.id"), nullable=True, index=True)
    unidad_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"), nullable=True, index=True)
    categoria: Mapped[str] = mapped_column(String(50), index=True)  # decision | hallazgo | consulta | regla
    clave_tema: Mapped[str] = mapped_column(String(120), index=True)
    resumen: Mapped[str] = mapped_column(Text)
    hechos_clave_json: Mapped[list] = mapped_column(JSON, default=list)
    fuente_ref: Mapped[str] = mapped_column(String(200), default="")
    vigente: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    reemplaza_id: Mapped[int | None] = mapped_column(ForeignKey("memorias_episodicas.id"), nullable=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MemoriaEntidad(Base):
    """Memoria estructurada consolidada por entidad dentro de un edificio."""
    __tablename__ = "memorias_entidad"
    __table_args__ = (UniqueConstraint("edificio_id", "entidad_tipo", "entidad_clave"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"), nullable=True, index=True)
    entidad_tipo: Mapped[str] = mapped_column(String(40), index=True)  # edificio | unidad | espacio | proveedor | reglamento
    entidad_clave: Mapped[str] = mapped_column(String(120))
    atributos_json: Mapped[dict] = mapped_column(JSON, default=dict)
    hechos_verificados: Mapped[list] = mapped_column(JSON, default=list)
    confianza: Mapped[float] = mapped_column(Float, default=1.0)
    fuente_ref: Mapped[str] = mapped_column(String(200), default="")
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditoriaConsultaIA(Base):
    """Trazabilidad completa de consultas al motor Q&A, filtros y controles anti-alucinación."""
    __tablename__ = "auditoria_consultas_ia"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    residente_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"), index=True)
    rol: Mapped[str] = mapped_column(String(20))
    pregunta_sanitizada: Mapped[str] = mapped_column(Text)
    variantes_consulta: Mapped[list] = mapped_column(JSON, default=list)
    filtros_alcance: Mapped[dict] = mapped_column(JSON, default=dict)
    fuentes_citadas: Mapped[list] = mapped_column(JSON, default=list)
    bloqueo_seguridad: Mapped[bool] = mapped_column(Boolean, default=False)
    modo_respuesta: Mapped[str] = mapped_column(String(40))
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
