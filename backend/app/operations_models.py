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


class MovimientoContable(Base):
    """Libro de ingresos y egresos con cuentas por pagar/cobrar y doble partida."""
    __tablename__ = "movimientos_contables"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    periodo: Mapped[str] = mapped_column(String(7), index=True)
    tipo: Mapped[str] = mapped_column(String(20), index=True)  # ingreso | egreso | ajuste
    categoria: Mapped[str] = mapped_column(String(40), default="general")
    cuenta_debe: Mapped[str] = mapped_column(String(60), default="caja_banco")
    cuenta_haber: Mapped[str] = mapped_column(String(60), default="ingresos_comunes")
    concepto: Mapped[str] = mapped_column(String(200))
    monto: Mapped[float] = mapped_column(Numeric(14, 2))
    estado: Mapped[str] = mapped_column(String(20), default="confirmado")  # pendiente | aprobado | pagado | confirmado | anulado
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"))
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("documentos.id"))
    unidad_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"))
    pago_id: Mapped[int | None] = mapped_column(ForeignKey("pagos.id"))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("residentes.id"))
    aprobado_por: Mapped[int | None] = mapped_column(ForeignKey("residentes.id"))
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PresupuestoRubro(Base):
    """Presupuesto mensual o anual por categoría para control de desviaciones."""
    __tablename__ = "presupuestos_rubro"
    __table_args__ = (UniqueConstraint("edificio_id", "periodo", "categoria"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    periodo: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM o YYYY
    categoria: Mapped[str] = mapped_column(String(40))
    monto_presupuestado: Mapped[float] = mapped_column(Numeric(14, 2))
    aprobado_asamblea_id: Mapped[int | None] = mapped_column(ForeignKey("asambleas.id"))
    notas: Mapped[str] = mapped_column(String(300), default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ConvenioPago(Base):
    """Convenio de pago de deuda morosa en cuotas acordadas con la unidad."""
    __tablename__ = "convenios_pago"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    monto_total: Mapped[float] = mapped_column(Numeric(14, 2))
    pie_inicial: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    cuotas: Mapped[int] = mapped_column(Integer)
    cuotas_pagadas: Mapped[int] = mapped_column(Integer, default=0)
    tasa_interes_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    primer_vencimiento: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="activo")  # activo | cumplido | incumplido | anulado
    observaciones: Mapped[str] = mapped_column(String(400), default="")
    creado_por: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TransaccionPasarela(Base):
    """Intento de pago en pasarela (Sandbox, Transbank Webpay, Mercado Pago, Khipu)."""
    __tablename__ = "transacciones_pasarela"
    __table_args__ = (UniqueConstraint("edificio_id", "idempotencia"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    residente_id: Mapped[int | None] = mapped_column(ForeignKey("residentes.id"))
    proveedor: Mapped[str] = mapped_column(String(20))  # sandbox | transbank | mercadopago | khipu
    idempotencia: Mapped[str] = mapped_column(String(64))
    orden_compra: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_pasarela: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    monto: Mapped[float] = mapped_column(Numeric(14, 2))
    moneda: Mapped[str] = mapped_column(String(8), default="CLP")
    estado: Mapped[str] = mapped_column(String(20), default="iniciada")  # iniciada | autorizada | rechazada | reembolsada | expirada
    url_pago: Mapped[str] = mapped_column(String(300), default="")
    codigo_autorizacion: Mapped[str] = mapped_column(String(40), default="")
    pago_id: Mapped[int | None] = mapped_column(ForeignKey("pagos.id"))
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    confirmado_at: Mapped[datetime | None] = mapped_column(DateTime)


class TrabajadorEdificio(Base):
    """Personal de planta del edificio (conserjes, aseo, mantención) y sus turnos."""
    __tablename__ = "trabajadores_edificio"
    __table_args__ = (UniqueConstraint("edificio_id", "rut"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    rut: Mapped[str] = mapped_column(String(15))
    cargo: Mapped[str] = mapped_column(String(60))  # conserje | mayordomo | aseo | mantencion
    turno: Mapped[str] = mapped_column(String(80), default="diurno")
    telefono: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AsistenciaPersonal(Base):
    """Registro de asistencia, turnos o permisos del personal del edificio."""
    __tablename__ = "asistencia_personal"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    trabajador_id: Mapped[int] = mapped_column(ForeignKey("trabajadores_edificio.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    tipo: Mapped[str] = mapped_column(String(20), default="asistencia")  # asistencia | turno_extra | permiso | licencia | inasistencia
    entrada: Mapped[str] = mapped_column(String(10), default="")
    salida: Mapped[str] = mapped_column(String(10), default="")
    observacion: Mapped[str] = mapped_column(String(300), default="")
    registrado_por: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CompromisoAsamblea(Base):
    """Acuerdos y compromisos derivados de una asamblea o comité con seguimiento."""
    __tablename__ = "compromisos_asamblea"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    asamblea_id: Mapped[int | None] = mapped_column(ForeignKey("asambleas.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(160))
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("residentes.id"))
    vencimiento: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | en_progreso | cumplido
    notas: Mapped[str] = mapped_column(String(500), default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RegistroComunidad(Base):
    """Ficha complementaria de comunidad: copropietarios, historial, contactos de emergencia, mascotas y bienes comunes."""
    __tablename__ = "registros_comunidad"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"), index=True)
    categoria: Mapped[str] = mapped_column(String(30), index=True)  # copropietario | arrendatario | contacto_emergencia | mascota | bien_comun | comite | bodega_estac
    titulo: Mapped[str] = mapped_column(String(160))
    rut: Mapped[str] = mapped_column(String(15), default="")
    contacto: Mapped[str] = mapped_column(String(160), default="")
    detalle: Mapped[str] = mapped_column(String(500), default="")
    desde: Mapped[date | None] = mapped_column(Date)
    hasta: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TokenRecuperacion(Base):
    """Token de un solo uso y corta duración para recuperación segura de contraseña."""
    __tablename__ = "tokens_recuperacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    residente_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    usado: Mapped[bool] = mapped_column(Boolean, default=False)
    expira: Mapped[datetime] = mapped_column(DateTime)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VisitaRecurrente(Base):
    """Pases recurrentes para familiares, cuidadores o personal autorizado por días de semana."""
    __tablename__ = "visitas_recurrentes"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    nombre_visita: Mapped[str] = mapped_column(String(120))
    patente: Mapped[str] = mapped_column(String(12), default="")
    dias_semana: Mapped[list] = mapped_column(JSON, default=list)  # 0=lunes .. 6=domingo
    hora_desde: Mapped[str] = mapped_column(String(5), default="08:00")
    hora_hasta: Mapped[str] = mapped_column(String(5), default="20:00")
    vigente_hasta: Mapped[date] = mapped_column(Date)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdjuntoOperacion(Base):
    """Fotografías o documentos adjuntos autorizados para incidencias, portería y encomiendas."""
    __tablename__ = "adjuntos_operacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    entidad: Mapped[str] = mapped_column(String(20), index=True)  # incidencia | visita | encomienda
    entidad_id: Mapped[int] = mapped_column(Integer, index=True)
    nombre_archivo: Mapped[str] = mapped_column(String(160))
    mime_type: Mapped[str] = mapped_column(String(80))
    contenido_b64: Mapped[str] = mapped_column(Text)
    autorizado_por: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SuscripcionPush(Base):
    """Suscripción Web Push / FCM de un residente para alertas en tiempo real."""
    __tablename__ = "suscripciones_push"
    __table_args__ = (UniqueConstraint("residente_id", "endpoint"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    residente_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"), index=True)
    endpoint: Mapped[str] = mapped_column(String(500))
    p256dh: Mapped[str] = mapped_column(String(200), default="")
    auth: Mapped[str] = mapped_column(String(100), default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EncuestaComunidad(Base):
    """Encuesta de satisfacción de residentes y percepción de servicios del edificio."""
    __tablename__ = "encuestas_comunidad"
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(160))
    pregunta: Mapped[str] = mapped_column(String(400))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RespuestaEncuesta(Base):
    """Respuesta única por residente en una encuesta de satisfacción."""
    __tablename__ = "respuestas_encuesta"
    __table_args__ = (UniqueConstraint("encuesta_id", "residente_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    edificio_id: Mapped[str] = mapped_column(ForeignKey("edificios.id"), index=True)
    encuesta_id: Mapped[int] = mapped_column(ForeignKey("encuestas_comunidad.id"), index=True)
    residente_id: Mapped[int] = mapped_column(ForeignKey("residentes.id"))
    puntaje: Mapped[int] = mapped_column(Integer)  # 1..5
    comentario: Mapped[str] = mapped_column(String(400), default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
