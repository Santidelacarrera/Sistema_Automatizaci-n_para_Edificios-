from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class EdificioIn(Entrada):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,39}$")
    nombre: str = Field(min_length=2, max_length=120)
    cupos_visitas: int = Field(6, ge=0, le=10000)


class EdificioPatch(Entrada):
    nombre: str | None = Field(None, min_length=2, max_length=120)
    activo: bool | None = None


class ProveedorIn(Entrada):
    nombre: str = Field(min_length=2, max_length=120)
    rut: str = Field(min_length=3, max_length=15)
    contacto: str = Field("", max_length=160)
    servicio: str = Field("", max_length=160)
    contrato_hasta: date | None = None


class IncidenciaIn(Entrada):
    unidad_id: int | None = None
    titulo: str = Field(min_length=3, max_length=160)
    descripcion: str = Field(min_length=3, max_length=6000)
    prioridad: Literal["baja", "normal", "alta", "critica"] = "normal"


class IncidenciaPatch(Entrada):
    version: int = Field(ge=1)
    estado: Literal["abierta", "asignada", "en_progreso", "resuelta", "cerrada"] | None = None
    prioridad: Literal["baja", "normal", "alta", "critica"] | None = None
    responsable_id: int | None = None
    vencimiento: date | None = None


class ComentarioIn(Entrada):
    texto: str = Field(min_length=1, max_length=4000)


class OrdenIn(Entrada):
    proveedor_id: int
    detalle: str = Field(min_length=3, max_length=4000)
    presupuesto: Decimal = Field(ge=0, le=999999999999, decimal_places=2)


class OrdenEstado(Entrada):
    estado: Literal["aprobada", "en_progreso", "terminada", "rechazada"]
    evaluacion: int | None = Field(None, ge=1, le=5)


class PlanIn(Entrada):
    titulo: str = Field(min_length=3, max_length=160)
    responsable_id: int
    intervalo_dias: int = Field(ge=1, le=3650)
    proxima_fecha: date


class ActivoIn(Entrada):
    activo: bool


class AsambleaIn(Entrada):
    titulo: str = Field(min_length=3, max_length=160)
    agenda: str = Field(min_length=3, max_length=10000)
    fecha: datetime
    opciones: list[str] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def validar(self):
        if self.fecha.tzinfo:
            raise ValueError("Use la fecha y hora local del edificio")
        self.opciones = [s.strip() for s in self.opciones]
        if any(not s or len(s) > 160 for s in self.opciones) or len(set(self.opciones)) != len(self.opciones):
            raise ValueError("Las opciones deben ser distintas, no vacías y de hasta 160 caracteres")
        return self


class ParticipanteIn(Entrada):
    residente_id: int


class VotoIn(Entrada):
    opcion: int = Field(ge=0, le=9)


class ActaIn(Entrada):
    acta: str = Field(min_length=3, max_length=20000)


class ReversaIn(Entrada):
    motivo: str = Field(min_length=10, max_length=500)


class AutomatizacionIn(Entrada):
    activa: bool = True
    recordatorios_pago: bool = False
    contratos_dias: int = Field(30, ge=0, le=365)
    max_notificaciones: int = Field(100, ge=1, le=1000)
