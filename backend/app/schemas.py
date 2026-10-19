from datetime import date, datetime
from typing import Literal

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
    tipo: Literal["sticker", "patente"] | None = None  # None = comportamiento anterior
    confianza: float | None = Field(None, ge=0, le=1)  # sólo patentes (LPR)
    direccion: Literal["entrada", "salida"] | None = None  # sólo con anti-passback


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


class ResidentePatch(BaseModel):
    """Edición parcial: sólo se aplica lo que llega con valor (null = no cambiar)."""
    unidad_id: int | None = None
    nombre: str | None = None
    rut: str | None = None
    email: str | None = None
    telefono: str | None = None
    rol: Rol | None = None
    activo: bool | None = None
    password: str | None = Field(None, min_length=8)


class TagPatch(BaseModel):
    residente_id: int | None = None  # null = desvincular el tag de su residente
    activo: bool | None = None


class ReglaPatch(BaseModel):
    tipo: str | None = None
    params: dict | None = None
    activa: bool | None = None


class TagReasignar(BaseModel):
    unidad_id: int
    residente_id: int | None = None
    vehiculo_id: int | None = None  # patente que queda asociada a este sticker (opcional)


class TagMotivo(BaseModel):
    motivo: str = Field("", max_length=200)


class AjustesAccesoIn(BaseModel):
    """Cómo se decide la entrada vehicular y los tiempos de la lectura."""
    modo_acceso: Literal["sticker_o_patente", "sticker_y_patente", "solo_sticker", "solo_patente"] | None = None
    ventana_coincidencia_s: int | None = Field(None, ge=1, le=120)
    antirrebote_s: int | None = Field(None, ge=0, le=60)
    anti_passback: bool | None = None
    umbral_confianza_patente: float | None = Field(None, ge=0, le=1)


class CircularIn(BaseModel):
    asunto: str
    cuerpo_html: str


class LecturaIn(BaseModel):
    unidad_id: int
    periodo: str
    servicio: str = "agua"
    consumo: float = Field(ge=0)


class VehiculoIn(BaseModel):
    unidad_id: int
    patente: str
    descripcion: str = ""
    tag_id: int | None = None


class PagoIn(BaseModel):
    """Pago confirmado por la pasarela/banco ya resuelto: sólo se registra y se comunica."""
    unidad_id: int
    monto: float = Field(gt=0)
    referencia: str = ""
    ref_externa: str = Field(min_length=1, max_length=80)


class RecordatorioIn(BaseModel):
    unidad_ids: list[int] | None = None  # None = todas las unidades con deuda
    canales: list[str] = ["whatsapp", "email"]
    mensaje_extra: str = ""
