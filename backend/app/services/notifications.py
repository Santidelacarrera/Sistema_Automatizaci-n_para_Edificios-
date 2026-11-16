"""Outbox transaccional. Nunca hace llamadas de red al crear una notificación."""
from datetime import timedelta
from html import escape
from uuid import uuid4

from sqlalchemy import select

from ..config import utcnow
from ..models import Edificio, Residente, Rol
from ..operations_models import Notificacion
from . import email, whatsapp


def notificar(db, edificio_id, residentes, titulo, texto, clave=None, externos=True):
    clave = clave or str(uuid4())
    total = 0
    for r in residentes:
        if not r.activo or r.edificio_id != edificio_id:
            continue
        canales = ["app"]
        if externos and r.email and email.configurado():
            canales.append("email")
        if externos and r.telefono and whatsapp.configurado():
            canales.append("whatsapp")
        for canal in canales:
            if db.scalar(select(Notificacion.id).where(Notificacion.residente_id == r.id,
                                                        Notificacion.clave == clave, Notificacion.canal == canal)):
                continue
            db.add(Notificacion(edificio_id=edificio_id, residente_id=r.id, clave=clave, canal=canal,
                                titulo=titulo, texto=texto, estado="disponible" if canal == "app" else "pendiente"))
            total += 1
        db.flush()
    return total


def administradores(db, edificio_id):
    return db.scalars(select(Residente).where(Residente.edificio_id == edificio_id,
                                             Residente.activo.is_(True), Residente.rol == Rol.admin)).all()


def procesar(db, limite=50):
    """Entrega al menos una vez: caída tras envío y antes de commit puede repetir el mensaje.

    SKIP LOCKED evita que dos workers envíen simultáneamente la misma fila. Los adaptadores tienen timeout.
    El fallo de un canal no deshace la operación de negocio que originó la notificación.
    """
    filas = db.scalars(select(Notificacion).where(
        Notificacion.estado.in_(["pendiente", "reintento"]), Notificacion.proximo_intento <= utcnow())
        .order_by(Notificacion.id).limit(limite).with_for_update(skip_locked=True)).all()
    resultado = {"enviados": 0, "fallidos": 0, "cancelados": 0}
    for n in filas:
        r, ed = db.get(Residente, n.residente_id), db.get(Edificio, n.edificio_id)
        if not r or not r.activo or r.edificio_id != n.edificio_id or not ed or not ed.activo:
            n.estado = "cancelado"
            resultado["cancelados"] += 1
            continue
        n.intentos += 1
        try:
            res = (email.enviar(r.email, n.titulo, f"<p>{escape(n.texto)}</p>") if n.canal == "email"
                   else whatsapp.enviar(r.telefono, n.texto))
            if res.estado == "enviado":
                n.estado, n.ultimo_error = "enviado", ""
                resultado["enviados"] += 1
                continue
            transitorio = res.transitorio
        except Exception:
            transitorio = True
        n.estado = "reintento" if transitorio and n.intentos < 5 else "fallido"
        n.ultimo_error = "El proveedor no confirmó la entrega; revise su configuración."
        n.proximo_intento = utcnow() + timedelta(seconds=min(30 * 2 ** n.intentos, 3600))
        resultado["fallidos"] += 1
    db.flush()
    return resultado
