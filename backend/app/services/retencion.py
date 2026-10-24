"""Retención de datos personales: borra o anonimiza lo que ya cumplió su plazo.

Plazos en config (``retencion_*_dias``). Qué se conserva y por qué: docs/PRIVACIDAD.md.
No toca residentes, vehículos, tags, cargos ni pagos: esos tienen otras reglas (contrato y contabilidad).
"""
from datetime import timedelta

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from ..config import ahora_local, settings, utcnow
from ..models import AccesoLog, Evento, IntentoLogin, LecturaPendiente, Visita


def purgar(db: Session) -> dict:
    ahora = utcnow()
    res = {"accesos": 0, "eventos": 0, "intentos_login": 0, "lecturas_pendientes": 0, "visitas_anonimizadas": 0}
    if settings.retencion_accesos_dias > 0:
        res["accesos"] = db.execute(delete(AccesoLog).where(
            AccesoLog.creado < ahora - timedelta(days=settings.retencion_accesos_dias))).rowcount
    if settings.retencion_eventos_dias > 0:
        res["eventos"] = db.execute(delete(Evento).where(
            Evento.creado < ahora - timedelta(days=settings.retencion_eventos_dias))).rowcount
    if settings.retencion_intentos_login_dias > 0:
        res["intentos_login"] = db.execute(delete(IntentoLogin).where(
            IntentoLogin.creado < ahora - timedelta(days=settings.retencion_intentos_login_dias))).rowcount
    res["lecturas_pendientes"] = db.execute(delete(LecturaPendiente).where(
        LecturaPendiente.creado < ahora - timedelta(days=1))).rowcount  # nunca sirven pasada la ventana
    if settings.retencion_visitas_dias > 0:
        # La visita se conserva sin datos personales: sirve para estadísticas de uso de cupos.
        res["visitas_anonimizadas"] = db.execute(update(Visita).where(
            Visita.hasta < ahora_local() - timedelta(days=settings.retencion_visitas_dias),
            Visita.nombre_visita != "[eliminado]").values(nombre_visita="[eliminado]", patente="")).rowcount
    db.flush()
    return res
