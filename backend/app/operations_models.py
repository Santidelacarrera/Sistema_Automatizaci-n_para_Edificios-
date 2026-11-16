"""Operaciones comunitarias: datos de tenant y trazabilidad persistente."""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .config import utcnow
from .db import Base


class Notificacion(Base):
    __tablename__ = "notificaciones"
    __table_args__ = (UniqueConstraint("residente_id", "clave", "canal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    residente_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"), index=True)
    clave: Mapped[str] = mapped_column(String(120))
    canal: Mapped[str] = mapped_column(String(12), default="app")
    titulo: Mapped[str] = mapped_column(String(160))
    texto: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", index=True)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    proximo_intento: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ultimo_error: Mapped[str] = mapped_column(String(200), default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    leido: Mapped[datetime | None] = mapped_column(DateTime)


class Proveedor(Base):
    __tablename__ = "proveedores"
    __table_args__ = (UniqueConstraint("edificio_id", "rut"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    rut: Mapped[str] = mapped_column(String(15))
    contacto: Mapped[str] = mapped_column(String(160), default="")
    servicio: Mapped[str] = mapped_column(String(160), default="")
    contrato_hasta: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Incidencia(Base):
    __tablename__ = "incidencias"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"))
    autor_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    titulo: Mapped[str] = mapped_column(String(160))
    descripcion: Mapped[str] = mapped_column(Text)
    prioridad: Mapped[str] = mapped_column(String(12), default="normal")
    estado: Mapped[str] = mapped_column(String(20), default="abierta", index=True)
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("residentes.id"))
    vencimiento: Mapped[date | None] = mapped_column(Date)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ComentarioIncidencia(Base):
    __tablename__ = "comentarios_incidencia"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    incidencia_id: Mapped[int] = mapped_column(ForeignKey("incidencias.id"), index=True)
    autor_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    texto: Mapped[str] = mapped_column(Text)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OrdenTrabajo(Base):
    __tablename__ = "ordenes_trabajo"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    incidencia_id: Mapped[int] = mapped_column(ForeignKey("incidencias.id"), unique=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"))
    detalle: Mapped[str] = mapped_column(Text)
    presupuesto: Mapped[float] = mapped_column(Numeric(14, 2))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    aprobada_por: Mapped[int | None] = mapped_column(ForeignKey("residentes.id"))
    evaluacion: Mapped[int | None] = mapped_column(Integer)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PlanMantenimiento(Base):
    __tablename__ = "planes_mantenimiento"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(160))
    responsable_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    intervalo_dias: Mapped[int] = mapped_column(Integer)
    proxima_fecha: Mapped[date] = mapped_column(Date, index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultima_incidencia_id: Mapped[int | None] = mapped_column(ForeignKey("incidencias.id"))


class Asamblea(Base):
    __tablename__ = "asambleas"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(160))
    agenda: Mapped[str] = mapped_column(Text)
    fecha: Mapped[datetime] = mapped_column(DateTime)
    estado: Mapped[str] = mapped_column(String(20), default="borrador")
    opciones: Mapped[list] = mapped_column(JSON)
    acta: Mapped[str] = mapped_column(Text, default="")
    creado_por: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    cerrada: Mapped[datetime | None] = mapped_column(DateTime)


class ParticipanteAsamblea(Base):
    __tablename__ = "participantes_asamblea"
    __table_args__ = (UniqueConstraint("asamblea_id", "unidad_id"), UniqueConstraint("asamblea_id", "residente_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    asamblea_id: Mapped[int] = mapped_column(ForeignKey("asambleas.id"), index=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"))
    residente_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    coeficiente: Mapped[float] = mapped_column(Numeric(9, 6))
    presente: Mapped[bool] = mapped_column(Boolean, default=False)


class Voto(Base):
    __tablename__ = "votos"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    asamblea_id: Mapped[int] = mapped_column(ForeignKey("asambleas.id"), index=True)
    participante_id: Mapped[int] = mapped_column(ForeignKey("participantes_asamblea.id"), unique=True)
    opcion: Mapped[int] = mapped_column(Integer)
    recibo: Mapped[str] = mapped_column(String(64), unique=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AutomatizacionConfig(Base):
    __tablename__ = "automatizaciones_config"
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), primary_key=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    recordatorios_pago: Mapped[bool] = mapped_column(Boolean, default=False)
    contratos_dias: Mapped[int] = mapped_column(Integer, default=30)
    max_notificaciones: Mapped[int] = mapped_column(Integer, default=100)


class Documento(Base):
    """Mapa autorizado al documento de DOCMIND; no duplica OCR ni RAG."""
    __tablename__ = "documentos"
    __table_args__ = (UniqueConstraint("edificio_id", "externo_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    externo_id: Mapped[str] = mapped_column(String(36))
    titulo: Mapped[str] = mapped_column(String(160))
    categoria: Mapped[str] = mapped_column(String(30), default="general")
    publico_comunidad: Mapped[bool] = mapped_column(Boolean, default=False)
    vence: Mapped[date | None] = mapped_column(Date)
    creado_por: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SegundoFactor(Base):
    __tablename__ = "segundos_factores"
    residente_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"), primary_key=True)
    secreto_cifrado: Mapped[str] = mapped_column(String(500))
    activo: Mapped[bool] = mapped_column(Boolean, default=False)
    ultimo_paso: Mapped[int] = mapped_column(Integer, default=-1)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)


class Dispositivo(Base):
    __tablename__ = "dispositivos"
    __table_args__ = (UniqueConstraint("edificio_id", "nombre"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    punto: Mapped[str] = mapped_column(String(40))
    clave_hash: Mapped[str] = mapped_column(String(64), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    laboratorio: Mapped[bool] = mapped_column(Boolean, default=True)
    firmware: Mapped[str] = mapped_column(String(80), default="")
    ultima_comunicacion: Mapped[datetime | None] = mapped_column(DateTime)
    bateria: Mapped[int | None] = mapped_column(Integer)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    incidencia_id: Mapped[int | None] = mapped_column(ForeignKey("incidencias.id"))


class ComandoAcceso(Base):
    __tablename__ = "comandos_acceso"
    __table_args__ = (UniqueConstraint("dispositivo_id", "idempotencia"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    dispositivo_id: Mapped[int] = mapped_column(ForeignKey("dispositivos.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    idempotencia: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(String(64))
    motivo: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expira: Mapped[datetime] = mapped_column(DateTime)
    confirmado: Mapped[datetime | None] = mapped_column(DateTime)
