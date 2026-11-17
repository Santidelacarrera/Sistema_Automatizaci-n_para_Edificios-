"""Contratos SaaS y soporte; separados del dinero de las comunidades."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .config import utcnow
from .db import Base


class ClienteSaaS(Base):
    __tablename__ = "clientes_saas"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(160))
    rut: Mapped[str] = mapped_column(String(15), unique=True)
    contacto: Mapped[str] = mapped_column(String(160))
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PlanComercial(Base):
    __tablename__ = "planes_comerciales"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    precio_mensual: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    max_unidades: Mapped[int] = mapped_column(Integer)
    max_residentes: Mapped[int] = mapped_column(Integer)
    max_dispositivos: Mapped[int] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Suscripcion(Base):
    __tablename__ = "suscripciones"
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes_saas.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("planes_comerciales.id"))
    estado: Mapped[str] = mapped_column(String(20))
    vigente_hasta: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CobroSaaS(Base):
    __tablename__ = "cobros_saas"
    __table_args__ = (UniqueConstraint("edificio_id", "periodo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes_saas.id"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("planes_comerciales.id"))
    periodo: Mapped[str] = mapped_column(String(7))
    monto: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    vencimiento: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    referencia: Mapped[str] = mapped_column(String(120), default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TicketSoporte(Base):
    __tablename__ = "tickets_soporte"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    autor_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    titulo: Mapped[str] = mapped_column(String(160))
    estado: Mapped[str] = mapped_column(String(20), default="abierto")
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MensajeSoporte(Base):
    __tablename__ = "mensajes_soporte"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets_soporte.id"), index=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    autor_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    texto: Mapped[str] = mapped_column(Text)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
