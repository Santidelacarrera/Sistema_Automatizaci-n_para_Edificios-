"""Conversación por WhatsApp para reservar una visita: entender, preguntar lo que falta, confirmar y enviar el QR.

Nunca reserva sin un «sí» explícito del residente. El estado se guarda en la base (expira a los 15 minutos),
así funciona aunque haya varios procesos y sobrevive a reinicios.
"""
import io
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import ahora_local, utcnow
from ..models import ConversacionWA, Edificio, Residente
from . import access, wa_parser

EXPIRA_MIN = 15
MAX_DIAS_ADELANTE = 30


@dataclass
class Respuesta:
    texto: str
    png: bytes | None = None  # si viene, se envía como imagen con `texto` de leyenda


_SI = {"si", "sí", "s", "ok", "okey", "confirmo", "confirmar", "dale", "listo", "correcto", "claro", "yes"}
_NO = {"no", "n", "cancelar", "cancela", "cancelo", "anular", "olvidalo", "olvídalo", "nada"}


def _limpio(t: str) -> str:
    return re.sub(r"[¡!.,;¿?]", "", t.strip().lower())


def _qr_png(codigo: str) -> bytes:
    import qrcode
    buf = io.BytesIO()
    qrcode.make(codigo).save(buf, format="PNG")
    return buf.getvalue()


def _estado(db: Session, telefono: str) -> ConversacionWA | None:
    c = db.scalar(select(ConversacionWA).where(ConversacionWA.telefono == telefono))
    if c and utcnow() - c.actualizado > timedelta(minutes=EXPIRA_MIN):
        db.delete(c)
        db.flush()
        return None
    return c


def _guardar(db: Session, telefono: str, estado: str, datos: dict) -> None:
    c = db.scalar(select(ConversacionWA).where(ConversacionWA.telefono == telefono))
    if c is None:
        c = ConversacionWA(telefono=telefono, estado=estado, datos=datos)
        db.add(c)
    c.estado, c.datos, c.actualizado = estado, dict(datos), utcnow()  # dict nuevo: SQLAlchemy detecta el cambio
    db.flush()


def _olvidar(db: Session, telefono: str) -> None:
    db.execute(delete(ConversacionWA).where(ConversacionWA.telefono == telefono))


def _pregunta(datos: dict) -> str | None:
    if not datos.get("nombre"):
        return "¿Cómo se llama tu visita?"
    if not datos.get("fecha"):
        return "¿Para qué día? Puedes escribir «hoy», «mañana», un día de la semana o una fecha como 15/11."
    if not datos.get("hora"):
        return "¿A qué hora llega? Por ejemplo 18:00."
    return None


def _validar_horario(datos: dict) -> str | None:
    h = wa_parser.a_horario(datos)
    ahora = ahora_local()
    if h is None:
        return None
    desde, _ = h
    if desde < ahora - timedelta(minutes=5):
        return "Esa hora ya pasó. ¿Para qué día y hora la reservamos?"
    if desde > ahora + timedelta(days=MAX_DIAS_ADELANTE):
        return f"Sólo se pueden reservar visitas con hasta {MAX_DIAS_ADELANTE} días de anticipación."
    return None


def _resumen(db: Session, ed: Edificio, datos: dict) -> str:
    desde, hasta = wa_parser.a_horario(datos)
    est = datos.get("usa_estacionamiento", False)
    if est:
        libres = ed.cupos_visitas - access.cupos_ocupados(db, ed.id, desde, hasta)
        auto = f"viene en auto (patente {datos['patente']})" if datos.get("patente") else "viene en auto, sin patente"
        auto += f", hay {max(libres, 0)} cupo(s) libre(s) en ese horario"
    else:
        auto = "viene a pie (si viene en auto, responde NO y escribe «con auto»)"
    return (f"Reservo la visita de *{datos['nombre']}* el {wa_parser.describir_dia(desde)} "
            f"hasta las {hasta.strftime('%H:%M')}; {auto}.\nResponde *SÍ* para confirmar o *NO* para cancelar.")


def _fusionar(datos: dict, nuevo: dict) -> dict:
    out = dict(datos)
    out.update({k: v for k, v in nuevo.items() if v not in (None, "")})
    return out


def iniciar_visita(db: Session, r: Residente, telefono: str, texto: str) -> list[Respuesta]:
    return _avanzar(db, r, telefono, {}, texto)


def _avanzar(db: Session, r: Residente, telefono: str, previos: dict, texto: str) -> list[Respuesta]:
    datos = _fusionar(previos, wa_parser.extraer_visita(texto, ahora_local()))
    # Al preguntar sólo por el nombre, una respuesta como «mañana» no debe volverse nombre (ya lo filtra el parser).
    pregunta = _pregunta(datos)
    if pregunta:
        _guardar(db, telefono, "pidiendo", datos)
        return [Respuesta(pregunta)]
    problema = _validar_horario(datos)
    if problema:
        datos.pop("fecha", None); datos.pop("hora", None)
        _guardar(db, telefono, "pidiendo", datos)
        return [Respuesta(problema)]
    ed = db.get(Edificio, r.edificio_id)
    _guardar(db, telefono, "confirmando", datos)
    return [Respuesta(_resumen(db, ed, datos))]


def _confirmar(db: Session, r: Residente, telefono: str, datos: dict) -> list[Respuesta]:
    ed = db.get(Edificio, r.edificio_id)
    desde, hasta = wa_parser.a_horario(datos)
    try:
        v = access.reservar_visita(db, ed, r.unidad_id, datos["nombre"], desde, hasta, datos.get("patente", ""),
                                   bool(datos.get("usa_estacionamiento")))
    except access.AccesoError as e:
        _olvidar(db, telefono)
        return [Respuesta(f"No pude reservar: {e}. Escríbeme de nuevo si quieres probar otro horario.")]
    _olvidar(db, telefono)
    leyenda = (f"Listo ✅ Visita de {datos['nombre']}: {wa_parser.describir_dia(desde)}. "
               "Reenvíale este QR; sirve sólo en ese horario." +
               (" Si viene en auto, la cámara también reconoce su patente." if datos.get("patente") else ""))
    return [Respuesta(leyenda, _qr_png(v.codigo_qr))]


def continuar(db: Session, r: Residente, telefono: str, texto: str) -> list[Respuesta] | None:
    """Si hay una conversación en curso, la sigue y devuelve las respuestas; si no, devuelve None."""
    c = _estado(db, telefono)
    if c is None:
        return None
    limpio = _limpio(texto)
    if limpio in _NO:
        _olvidar(db, telefono)
        return [Respuesta("Listo, no reservé nada. Escríbeme cuando quieras.")]
    if c.estado == "confirmando":
        if limpio in _SI:
            return _confirmar(db, r, telefono, c.datos)
        # Cualquier otra cosa corrige los datos (p. ej. «con auto», «a las 19:00»); se vuelve a pedir confirmación.
        return _avanzar(db, r, telefono, c.datos, texto)
    return _avanzar(db, r, telefono, c.datos, texto)
