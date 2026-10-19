"""Tareas asíncronas Celery (broker Redis). Con CELERY_EAGER=true corren en proceso (dev/tests)."""
import logging

from celery import Celery

from .config import settings
from .db import SessionLocal
from .models import Cargo, Edificio, Residente, Unidad
from .services import access, email
from .services.resultado import ERROR

log = logging.getLogger(__name__)

celery = Celery("edificios", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.task_always_eager = settings.celery_eager
celery.conf.beat_schedule = {
    "liberar-no-show": {"task": "app.tasks.liberar_no_show", "schedule": 60.0},
}


@celery.task(name="app.tasks.liberar_no_show")
def liberar_no_show() -> int:
    with SessionLocal() as db:
        n = access.liberar_no_show(db)
        db.commit()
        return n


@celery.task(name="app.tasks.enviar_email", bind=True, max_retries=5)
def enviar_email(self, destino: str, asunto: str, html: str) -> dict:
    """Reintenta sólo fallos transitorios (red, 4xx SMTP); los permanentes quedan registrados en el log."""
    res = email.enviar(destino, asunto, html)
    if res.estado == ERROR and res.transitorio:
        raise self.retry(exc=OSError(res.motivo), countdown=min(30 * 2 ** self.request.retries, 900))
    if res.estado == ERROR:
        log.error("Correo a %s no enviado: %s", destino, res.motivo)
    return res.a_dict()


@celery.task(name="app.tasks.enviar_gastos_comunes")
def enviar_gastos_comunes(edificio_id: str, periodo: str) -> int:
    """Encola un correo por residente con su cargo del periodo."""
    from sqlalchemy import func, select
    n = 0
    with SessionLocal() as db:
        ed = db.get(Edificio, edificio_id)
        for u in db.scalars(select(Unidad).where(Unidad.edificio_id == edificio_id)):
            cargos = db.execute(select(func.sum(Cargo.monto), func.max(Cargo.vencimiento)).where(
                Cargo.unidad_id == u.id, Cargo.periodo == periodo)).one()
            if not cargos[0]:
                continue
            for r in db.scalars(select(Residente).where(Residente.unidad_id == u.id, Residente.email != "")):
                html = email.render(email.PLANTILLA_GASTO_COMUN, edificio=ed.nombre, periodo=periodo,
                                    nombre=r.nombre, unidad=u.numero, monto=f"${float(cargos[0]):,.0f}",
                                    vencimiento=cargos[1], codigo_cobro=u.codigo_cobro)
                enviar_email.delay(r.email, f"Gastos comunes {periodo} — {ed.nombre}", html)
                n += 1
    return n


@celery.task(name="app.tasks.enviar_circular")
def enviar_circular(edificio_id: str, asunto: str, cuerpo_html: str) -> int:
    from sqlalchemy import select
    n = 0
    with SessionLocal() as db:
        ed = db.get(Edificio, edificio_id)
        for r in db.scalars(select(Residente).where(Residente.edificio_id == edificio_id,
                                                    Residente.email != "", Residente.activo.is_(True))):
            html = email.render(email.PLANTILLA_CIRCULAR, edificio=ed.nombre, asunto=asunto,
                                nombre=r.nombre, cuerpo=cuerpo_html)
            enviar_email.delay(r.email, asunto, html)
            n += 1
    return n
