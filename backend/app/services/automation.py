"""Automatizaciones acotadas: alertas y tareas; nunca ejecuta pagos ni abre accesos."""
from datetime import timedelta

from sqlalchemy import select

from ..config import hoy_local, utcnow
from ..models import Cargo, Evento, Residente
from ..operations_models import AutomatizacionConfig, ComandoAcceso, Dispositivo, Documento, Incidencia, PlanMantenimiento, Proveedor
from .notifications import administradores, notificar
from .transactions import bloquear_edificio


def ejecutar(db, edificio_id, hoy=None):
    hoy = hoy or hoy_local()
    ed = bloquear_edificio(db, edificio_id)
    cfg = db.get(AutomatizacionConfig, edificio_id)
    if not ed or not ed.activo or (cfg and not cfg.activa):
        return {"creadas": 0, "alertas": 0, "desactivada": True}
    admins = administradores(db, edificio_id)
    limite = cfg.max_notificaciones if cfg else 100
    creadas, alertas = 0, 0
    # Todo destinatario cuenta para el límite; sólo un aviso app por clave y día.
    def avisar(destinatarios, titulo, texto, clave):
        nonlocal alertas
        for r in destinatarios:
            if alertas >= limite:
                break
            alertas += notificar(db, edificio_id, [r], titulo, texto, clave, externos=False)

    for c in db.scalars(select(ComandoAcceso).where(ComandoAcceso.edificio_id == edificio_id,
                        ComandoAcceso.estado.in_(["pendiente", "entregado"]), ComandoAcceso.expira < utcnow())):
        c.estado = "expirado"
    for d in db.scalars(select(Dispositivo).where(Dispositivo.edificio_id == edificio_id,
                        Dispositivo.activo.is_(True)).limit(500)):
        if not admins or utcnow() - (d.ultima_comunicacion or d.creado) < timedelta(minutes=5):
            continue
        previa = db.get(Incidencia, d.incidencia_id) if d.incidencia_id else None
        if previa and previa.estado not in ("resuelta", "cerrada"):
            continue
        inc = Incidencia(edificio_id=edificio_id, autor_id=admins[0].id, responsable_id=admins[0].id,
                         titulo=f"Dispositivo desconectado: {d.nombre}", descripcion=f"Sin comunicación del controlador #{d.id} en {d.punto}.",
                         prioridad="alta", estado="asignada", vencimiento=hoy)
        db.add(inc)
        db.flush()
        d.incidencia_id = inc.id
        creadas += 1
        avisar(admins, "Controlador desconectado", d.nombre, f"dispositivo:{d.id}:inc:{inc.id}")
        db.add(Evento(edificio_id=edificio_id, tipo="incidencia.dispositivo", payload={"recurso_id": inc.id, "dispositivo_id": d.id}))

    for p in db.scalars(select(PlanMantenimiento).where(PlanMantenimiento.edificio_id == edificio_id,
                        PlanMantenimiento.activo.is_(True), PlanMantenimiento.proxima_fecha <= hoy)
                        .order_by(PlanMantenimiento.proxima_fecha).limit(100)):
        r = db.get(Residente, p.responsable_id)
        if not r or not r.activo or r.edificio_id != edificio_id:
            continue
        inc = Incidencia(edificio_id=edificio_id, autor_id=r.id, responsable_id=r.id,
                         titulo=p.titulo, descripcion="Mantenimiento preventivo programado.",
                         prioridad="alta" if p.proxima_fecha < hoy else "normal", estado="asignada",
                         vencimiento=p.proxima_fecha)
        db.add(inc)
        db.flush()
        p.ultima_incidencia_id = inc.id
        # No generar miles de atrasos: una incidencia agrupa el atraso y la próxima queda en el futuro.
        saltos = (hoy - p.proxima_fecha).days // p.intervalo_dias + 1
        p.proxima_fecha += timedelta(days=saltos * p.intervalo_dias)
        avisar([r], "Mantenimiento programado", p.titulo, f"plan:{p.id}:inc:{inc.id}")
        creadas += 1
        db.add(Evento(edificio_id=edificio_id, tipo="incidencia.programada", payload={"recurso_id": inc.id, "plan_id": p.id}))
    for inc in db.scalars(select(Incidencia).where(Incidencia.edificio_id == edificio_id,
                          Incidencia.estado.not_in(["resuelta", "cerrada"]))
                          .order_by(Incidencia.id).limit(500)):
        if inc.prioridad == "critica" or (inc.vencimiento and inc.vencimiento < hoy):
            if inc.vencimiento and inc.vencimiento < hoy and inc.prioridad == "alta":
                inc.prioridad = "critica"
            avisar(admins, "Incidencia requiere atención", inc.titulo, f"inc:{inc.id}:escalar:{hoy}")
            db.add(Evento(edificio_id=edificio_id, tipo="incidencia.escalada",
                          payload={"recurso_id": inc.id, "prioridad": inc.prioridad}))
    dias = cfg.contratos_dias if cfg else 30
    for model, campo, prefijo in ((Proveedor, Proveedor.contrato_hasta, "contrato"), (Documento, Documento.vence, "documento")):
        for obj in db.scalars(select(model).where(model.edificio_id == edificio_id, campo >= hoy,
                              campo <= hoy + timedelta(days=dias)).limit(500)):
            titulo = obj.nombre if model is Proveedor else obj.titulo
            avisar(admins, "Vencimiento próximo", titulo, f"{prefijo}:{obj.id}:vence:{hoy}")
    if cfg and cfg.recordatorios_pago:
        uids = db.scalars(select(Cargo.unidad_id).where(Cargo.edificio_id == edificio_id,
                          Cargo.saldo > 0, Cargo.vencimiento < hoy).distinct()).all()
        for r in db.scalars(select(Residente).where(Residente.edificio_id == edificio_id, Residente.unidad_id.in_(uids))):
            avisar([r], "Gastos comunes pendientes", "Tiene cargos vencidos. Consulte su estado de cuenta.",
                   f"deuda:{r.unidad_id}:{hoy}")
    db.add(Evento(edificio_id=edificio_id, tipo="automatizacion.ejecutada", payload={"creadas": creadas, "alertas": alertas}))
    db.flush()
    return {"creadas": creadas, "alertas": alertas, "desactivada": False}
