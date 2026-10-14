from datetime import date, datetime

from pydantic import BaseModel, Field

from .models import Rol, TipoTag


class LoginIn(BaseModel):
    edificio_id: str
    email: str
    password: str


class ValidarAccesoIn(BaseModel):
    edificio_id: str
    token_acceso: str = Field(min_length=1, max_length=80)
    punto: str = "peatonal"


class UnidadIn(BaseModel):
    numero: str
    coeficiente: float = Field(gt=0)
    codigo_cobro: str
    estacionamientos: int = Field(0, ge=0)


class ResidenteIn(BaseModel):
    unidad_id: int
    nombre: str
    rut: str
    email: str = ""
    telefono: str = ""
    password: str | None = Field(None, min_length=8)
    rol: Rol = Rol.residente


class TagIn(BaseModel):
    unidad_id: int
    uid: str
    tipo: TipoTag
    residente_id: int | None = None


class ReglaIn(BaseModel):
    accion: str
    tipo: str
    params: dict = {}


class VisitaIn(BaseModel):
    unidad_id: int | None = None
    nombre_visita: str
    desde: datetime
    hasta: datetime
    patente: str = ""
    usa_estacionamiento: bool = True
    usos_max: int = Field(2, ge=1, le=20)


class ReservaEspacioIn(BaseModel):
    espacio_id: int
    unidad_id: int | None = None
    desde: datetime
    hasta: datetime


class GastoIn(BaseModel):
    concepto: str
    monto: float = Field(gt=0)
    tipo: str = "ordinario"
    base: str = "coeficiente"
    servicio: str = "agua"


class GenerarGastosIn(BaseModel):
    periodo: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    vencimiento: date
    gastos: list[GastoIn]


class CircularIn(BaseModel):
    asunto: str
    cuerpo_html: str


class LecturaIn(BaseModel):
    unidad_id: int
    periodo: str
    servicio: str = "agua"
    consumo: float = Field(ge=0)
