"""Esquema multi-tenant: toda tabla de negocio lleva ``edificio_id``."""
import enum
from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer,
                        Numeric, String, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import utcnow
from .db import Base


class Rol(str, enum.Enum):
    superadmin = "superadmin"
    admin = "admin"
    residente = "residente"
    conserje = "conserje"


class TipoTag(str, enum.Enum):
    vehicular = "vehicular"  # RFID UHF 10-15 m
    peatonal = "peatonal"    # RFID 13.56 MHz / llavero


class EstadoVisita(str, enum.Enum):
    reservada = "reservada"
    llego = "llego"
    no_show = "no_show"
    cancelada = "cancelada"


class Edificio(Base):
    __tablename__ = "edificios"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # p.ej. "edificio_a"
    nombre: Mapped[str] = mapped_column(String(120))
    cupos_visitas: Mapped[int] = mapped_column(Integer, default=6)
    max_estac_por_unidad: Mapped[int] = mapped_column(Integer, default=2)
    tolerancia_visita_min: Mapped[int] = mapped_column(Integer, default=20)
    device_api_key: Mapped[str] = mapped_column(String(80), unique=True)


class Unidad(Base):
    __tablename__ = "unidades"
    __table_args__ = (UniqueConstraint("edificio_id", "numero"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    numero: Mapped[str] = mapped_column(String(20))
    coeficiente: Mapped[float] = mapped_column(Numeric(9, 6))  # copropiedad, suma ~1 por edificio
    codigo_cobro: Mapped[str] = mapped_column(String(30), unique=True)
    estacionamientos: Mapped[int] = mapped_column(Integer, default=0)
    residentes: Mapped[list["Residente"]] = relationship(back_populates="unidad")


class Residente(Base):
    __tablename__ = "residentes"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"))
    nombre: Mapped[str] = mapped_column(String(120))
    rut: Mapped[str] = mapped_column(String(15), index=True)
    email: Mapped[str] = mapped_column(String(160), default="")
    telefono: Mapped[str] = mapped_column(String(20), default="", index=True)  # solo dígitos, con país
    password_hash: Mapped[str] = mapped_column(String(200), default="")
    rol: Mapped[Rol] = mapped_column(Enum(Rol), default=Rol.residente)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    unidad: Mapped[Unidad] = relationship(back_populates="residentes")


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("edificio_id", "uid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"))
    residente_id: Mapped[int | None] = mapped_column(ForeignKey("residentes.id"))
    uid: Mapped[str] = mapped_column(String(40))
    tipo: Mapped[TipoTag] = mapped_column(Enum(TipoTag))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Visita(Base):
    __tablename__ = "visitas"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"))
    nombre_visita: Mapped[str] = mapped_column(String(120))
    patente: Mapped[str] = mapped_column(String(12), default="")
    usa_estacionamiento: Mapped[bool] = mapped_column(Boolean, default=True)
    desde: Mapped[datetime] = mapped_column(DateTime)
    hasta: Mapped[datetime] = mapped_column(DateTime)
    codigo_qr: Mapped[str] = mapped_column(String(64), unique=True)
    usos_max: Mapped[int] = mapped_column(Integer, default=2)  # entrada + salida
    usos: Mapped[int] = mapped_column(Integer, default=0)
    estado: Mapped[EstadoVisita] = mapped_column(Enum(EstadoVisita), default=EstadoVisita.reservada)
    llegada_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (Index("ix_visitas_ventana", "edificio_id", "desde", "hasta"),)


class Regla(Base):
    __tablename__ = "reglas"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    accion: Mapped[str] = mapped_column(String(60))  # p.ej. "reservar_quincho"
    tipo: Mapped[str] = mapped_column(String(40))    # horario | max_por_mes | bloquear_morosos | multa_cancelacion | anticipacion
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class EspacioComun(Base):
    __tablename__ = "espacios_comunes"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(60))  # "quincho"
    accion: Mapped[str] = mapped_column(String(60))  # clave de reglas
    tarifa: Mapped[float] = mapped_column(Numeric(12, 2), default=0)


class ReservaEspacio(Base):
    __tablename__ = "reservas_espacio"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    espacio_id: Mapped[int] = mapped_column(ForeignKey("espacios_comunes.id"))
    unidad_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"))
    desde: Mapped[datetime] = mapped_column(DateTime)
    hasta: Mapped[datetime] = mapped_column(DateTime)
    estado: Mapped[str] = mapped_column(String(20), default="confirmada")


class Cargo(Base):
    """Cargo de gasto común (o multa/reserva) por unidad y periodo."""
    __tablename__ = "cargos"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    periodo: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    concepto: Mapped[str] = mapped_column(String(80))
    monto: Mapped[float] = mapped_column(Numeric(14, 2))
    saldo: Mapped[float] = mapped_column(Numeric(14, 2))
    vencimiento: Mapped[date | None] = mapped_column(Date)


class LecturaMedidor(Base):
    __tablename__ = "lecturas_medidor"
    __table_args__ = (UniqueConstraint("unidad_id", "periodo", "servicio"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"))
    periodo: Mapped[str] = mapped_column(String(7))
    servicio: Mapped[str] = mapped_column(String(20))  # agua | gas | calefaccion
    consumo: Mapped[float] = mapped_column(Numeric(14, 3))


class Pago(Base):
    __tablename__ = "pagos"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"))
    monto: Mapped[float] = mapped_column(Numeric(14, 2))
    fecha: Mapped[date] = mapped_column(Date)
    referencia: Mapped[str] = mapped_column(String(200), default="")
    ref_banco: Mapped[str] = mapped_column(String(80), default="")  # id de transacción -> idempotencia
    conciliado: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("edificio_id", "ref_banco"),)


class Evento(Base):
    """Bitácora de eventos (auditoría + bus)."""
    __tablename__ = "eventos"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(String(40), index=True)
    tipo: Mapped[str] = mapped_column(String(60), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AccesoLog(Base):
    __tablename__ = "accesos_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(String(40), index=True)
    token: Mapped[str] = mapped_column(String(80))
    punto: Mapped[str] = mapped_column(String(40))
    permitido: Mapped[bool] = mapped_column(Boolean)
    motivo: Mapped[str] = mapped_column(String(120), default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
