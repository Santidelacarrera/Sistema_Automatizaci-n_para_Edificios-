"""Límites de altas. Un vencimiento comercial nunca acciona ni bloquea un portón."""
from fastapi import HTTPException
from sqlalchemy import func, select

from ..commercial_models import PlanComercial, Suscripcion
from ..config import hoy_local
from ..models import Residente, Unidad
from ..operations_models import Dispositivo
from .transactions import bloquear_edificio

RECURSOS = {"unidades": Unidad, "residentes": Residente, "dispositivos": Dispositivo}


def uso(db, eid):
    # Cuentan también los registros desactivados: no eludir cuotas conservando un historial sin límite.
    return {nombre: db.scalar(select(func.count(model.id)).where(model.edificio_id == eid))
            for nombre, model in RECURSOS.items()}


def comprobar_cupo(db, eid, recurso, cantidad=1):
    bloquear_edificio(db, eid)
    sub = db.get(Suscripcion, eid)
    if not sub:
        return  # Instalaciones existentes: régimen sin contrato, visible explícitamente en el panel global.
    if sub.estado not in ("prueba", "activa") or sub.vigente_hasta < hoy_local():
        raise HTTPException(409, "Suscripción sin vigencia para nuevas altas; contacte con soporte")
    plan = db.get(PlanComercial, sub.plan_id)
    model = RECURSOS[recurso]
    total = db.scalar(select(func.count(model.id)).where(model.edificio_id == eid))
    if total + cantidad > getattr(plan, "max_" + recurso):
        raise HTTPException(409, "Se alcanzó el límite de " + recurso + " del plan contratado")
