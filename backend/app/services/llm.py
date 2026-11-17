"""Asistente administrativo inteligente y analítica determinista/LLM para comunidades.

- Analiza gastos comunes, morosidad, anomalías financieras, presupuestos y flujo de caja.
- Analiza incidencias abiertas/críticas, desempeño de proveedores y consumo de agua/electricidad.
- Genera resúmenes de actividad, propuestas de acciones de mantenimiento y borradores de circulares.
- Opera de forma determinista con los datos autorizados del edificio y, si `ANTHROPIC_API_KEY` está configurada,
  enriquece la redacción sin inventar cifras ni ejecutar acciones autónomas.
"""
import json

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import hoy_local, settings
from ..models import Cargo, Comunicado, Edificio, LecturaMedidor, Pago, Unidad
from ..operations_models import (Documento,
                                  Incidencia, MovimientoContable, OrdenTrabajo, PresupuestoRubro, Proveedor)


def analizar_edificio(db: Session, edificio_id: str) -> dict:
    """Calcula métricas reales, anomalías, patrones de morosidad y recomendaciones operativas."""
    hoy = hoy_local()
    periodo_actual = hoy.strftime("%Y-%m")
    ed = db.get(Edificio, edificio_id)
    unidades = db.scalars(select(Unidad).where(Unidad.edificio_id == edificio_id)).all()
    cargos = db.scalars(select(Cargo).where(Cargo.edificio_id == edificio_id)).all()
    pagos = db.scalars(select(Pago).where(Pago.edificio_id == edificio_id, Pago.conciliado.is_(True),
                                          Pago.revertido.is_(False), Pago.duplicado_de_id.is_(None))).all()
    incidencias = db.scalars(select(Incidencia).where(Incidencia.edificio_id == edificio_id)).all()
    ordenes = db.scalars(select(OrdenTrabajo).where(OrdenTrabajo.edificio_id == edificio_id)).all()
    proveedores = db.scalars(select(Proveedor).where(Proveedor.edificio_id == edificio_id)).all()
    movimientos = db.scalars(select(MovimientoContable).where(
        MovimientoContable.edificio_id == edificio_id, MovimientoContable.estado != "anulado")).all()
    presupuestos = db.scalars(select(PresupuestoRubro).where(PresupuestoRubro.edificio_id == edificio_id)).all()
    lecturas = db.scalars(select(LecturaMedidor).where(LecturaMedidor.edificio_id == edificio_id)).all()

    # 1. Patrones de morosidad y predicción de riesgo por unidad
    deuda_por_unidad = {}
    vencidos_por_unidad = {}
    for c in cargos:
        if float(c.saldo) > 0:
            deuda_por_unidad[c.unidad_id] = deuda_por_unidad.get(c.unidad_id, 0.0) + float(c.saldo)
            if c.vencimiento and c.vencimiento < hoy:
                vencidos_por_unidad[c.unidad_id] = vencidos_por_unidad.get(c.unidad_id, 0) + 1

    mapa_unidades = {u.id: u.numero for u in unidades}
    riesgo_morosidad = []
    for uid, monto in sorted(deuda_por_unidad.items(), key=lambda item: -item[1]):
        n_venc = vencidos_por_unidad.get(uid, 0)
        nivel = "alto" if n_venc >= 2 or monto >= 200000 else ("medio" if n_venc == 1 or monto >= 80000 else "bajo")
        riesgo_morosidad.append({
            "unidad_id": uid,
            "unidad": mapa_unidades.get(uid, str(uid)),
            "deuda": round(monto, 2),
            "periodos_vencidos": n_venc,
            "riesgo": nivel,
        })

    # 2. Anomalías financieras y desviaciones presupuestarias
    egresos_cat = {}
    for m in movimientos:
        if m.tipo == "egreso":
            egresos_cat[m.categoria] = egresos_cat.get(m.categoria, 0.0) + float(m.monto)
    desviaciones = []
    for p in presupuestos:
        ejecutado = egresos_cat.get(p.categoria, 0.0)
        pres = float(p.monto_presupuestado)
        pct = round(100 * ejecutado / pres, 1) if pres > 0 else 0.0
        desviaciones.append({
            "periodo": p.periodo,
            "categoria": p.categoria,
            "presupuestado": pres,
            "ejecutado": round(ejecutado, 2),
            "ejecucion_pct": pct,
            "alerta_desviacion": ejecutado > pres,
        })

    anomalias = [d for d in desviaciones if d["alerta_desviacion"]]
    if len(movimientos) >= 2:
        egresos_lista = [float(m.monto) for m in movimientos if m.tipo == "egreso"]
        if egresos_lista:
            promedio = sum(egresos_lista) / len(egresos_lista)
            for m in movimientos:
                if m.tipo == "egreso" and float(m.monto) > promedio * 2.0 and len(egresos_lista) >= 2:
                    anomalias.append({
                        "periodo": m.periodo,
                        "categoria": m.categoria,
                        "concepto": m.concepto,
                        "monto": float(m.monto),
                        "alerta_desviacion": True,
                        "motivo": "Gasto inusual superior al doble del promedio registrado",
                    })

    # 3. Consumos y alertas por consumos anormales
    consumos_por_servicio = {}
    alertas_consumo = []
    for lec in lecturas:
        consumos_por_servicio.setdefault(lec.servicio, []).append(float(lec.consumo))
    promedios_servicio = {s: (sum(vals) / len(vals)) for s, vals in consumos_por_servicio.items() if vals}
    for lec in lecturas:
        prom = promedios_servicio.get(lec.servicio, 0)
        if prom > 0 and float(lec.consumo) > prom * 1.8 and len(consumos_por_servicio[lec.servicio]) >= 2:
            alertas_consumo.append({
                "unidad_id": lec.unidad_id,
                "unidad": mapa_unidades.get(lec.unidad_id, str(lec.unidad_id)),
                "periodo": lec.periodo,
                "servicio": lec.servicio,
                "consumo": float(lec.consumo),
                "promedio_edificio": round(prom, 2),
            })

    # 4. Desempeño de proveedores y análisis de incidencias
    eval_prov = {}
    trabajos_prov = {}
    for o in ordenes:
        trabajos_prov[o.proveedor_id] = trabajos_prov.get(o.proveedor_id, 0) + 1
        if o.evaluacion is not None:
            eval_prov.setdefault(o.proveedor_id, []).append(o.evaluacion)
    desempeno_proveedores = [
        {
            "proveedor_id": p.id,
            "nombre": p.nombre,
            "servicio": p.servicio,
            "ordenes": trabajos_prov.get(p.id, 0),
            "promedio_evaluacion": round(sum(eval_prov[p.id]) / len(eval_prov[p.id]), 2) if p.id in eval_prov else None,
            "contrato_hasta": p.contrato_hasta.isoformat() if p.contrato_hasta else None,
        }
        for p in proveedores
    ]

    abiertas = [i for i in incidencias if i.estado not in ("resuelta", "cerrada")]
    criticas = [i for i in abiertas if i.prioridad in ("alta", "critica")]

    # 5. Proyección de caja y recomendaciones administrativas
    ingresos_totales = sum(float(p.monto) for p in pagos) + sum(
        float(m.monto) for m in movimientos if m.tipo == "ingreso" and m.pago_id is None
    )
    egresos_totales = sum(float(m.monto) for m in movimientos if m.tipo == "egreso")
    cuentas_por_cobrar = sum(deuda_por_unidad.values())
    cuentas_por_pagar = sum(float(m.monto) for m in movimientos if m.tipo == "egreso" and m.estado in ("pendiente", "aprobado"))
    saldo_caja = round(ingresos_totales - egresos_totales, 2)
    proyeccion_30d = round(saldo_caja + cuentas_por_cobrar * 0.7 - cuentas_por_pagar, 2)

    recomendaciones = []
    if any(r["riesgo"] == "alto" for r in riesgo_morosidad):
        recomendaciones.append("Ofrecer convenio de pago o activar recordatorios automáticos para unidades con 2+ períodos vencidos.")
    if criticas:
        recomendaciones.append(f"Atender prioritariamente {len(criticas)} incidencia(s) de prioridad alta/crítica pendientes.")
    if anomalias:
        recomendaciones.append("Revisar los rubros con sobreejecución presupuestaria o gastos inusuales detectados.")
    if alertas_consumo:
        recomendaciones.append("Inspeccionar posibles fugas en unidades con consumo superior al 180% del promedio.")
    if not recomendaciones:
        recomendaciones.append("Operación estable: mantener calendario de mantenimiento preventivo y conciliación mensual.")

    # 6. Predicción de mantenimientos (22.06): recurrencia por prioridad/área de incidencias
    por_categoria: dict[str, list] = {}
    for inc in incidencias:
        txt = f"{inc.titulo or ''} {inc.descripcion or ''}".lower()
        cat = "ascensor" if "ascensor" in txt else ("gasfiteria" if any(k in txt for k in ("fuga", "agua", "gotera", "gasfiter")) else (inc.prioridad or "normal"))
        por_categoria.setdefault(cat, []).append(inc)
    prediccion_mantenimientos = []
    for cat, items in sorted(por_categoria.items(), key=lambda kv: -len(kv[1])):
        abiertas_cat = sum(1 for i in items if i.estado != "cerrada")
        riesgo = "alto" if len(items) >= 3 or abiertas_cat >= 2 else ("medio" if len(items) == 2 else "bajo")
        accion = (
            f"Programar mantención preventiva en '{cat}' ({len(items)} eventos registrados, {abiertas_cat} abiertos)."
            if len(items) >= 2
            else f"Monitorear área '{cat}' en próxima inspección."
        )
        prediccion_mantenimientos.append({
            "categoria": cat,
            "eventos": len(items),
            "abiertas": abiertas_cat,
            "riesgo": riesgo,
            "accion_sugerida": accion,
        })

    # 7. Optimización de tareas (22.09): priorización de órdenes de trabajo y asignación óptima de proveedor
    prov_activos = [p for p in proveedores if p.activo]
    inc_map = {i.id: i for i in incidencias}
    peso_prio = {"critica": 4, "alta": 3, "normal": 2, "media": 2, "baja": 1}
    optimizacion_tareas = []
    for ot in sorted(
        [o for o in ordenes if o.estado in ("pendiente", "aprobada", "en_progreso")],
        key=lambda o: (-peso_prio.get((inc_map.get(o.incidencia_id).prioridad if inc_map.get(o.incidencia_id) else "normal"), 2), o.id),
    ):
        inc_rel = inc_map.get(ot.incidencia_id)
        prio = inc_rel.prioridad if inc_rel else "normal"
        candidato = next((p for p in prov_activos if p.id == ot.proveedor_id or (p.servicio or "").lower() in (ot.detalle or "").lower()), prov_activos[0] if prov_activos else None)
        optimizacion_tareas.append({
            "orden_id": ot.id,
            "detalle": ot.detalle,
            "estado": ot.estado,
            "prioridad": prio,
            "score_prioridad": peso_prio.get(prio, 2),
            "proveedor_sugerido": candidato.nombre if candidato else None,
        })

    return {
        "edificio": ed.nombre if ed else edificio_id,
        "periodo_actual": periodo_actual,
        "resumen_financiero": {
            "ingresos_acumulados": round(ingresos_totales, 2),
            "egresos_acumulados": round(egresos_totales, 2),
            "saldo_caja": saldo_caja,
            "cuentas_por_cobrar": round(cuentas_por_cobrar, 2),
            "cuentas_por_pagar": round(cuentas_por_pagar, 2),
            "proyeccion_caja_30d": proyeccion_30d,
        },
        "riesgo_morosidad": riesgo_morosidad,
        "desviaciones_presupuesto": desviaciones,
        "anomalias_financieras": anomalias,
        "alertas_consumo": alertas_consumo,
        "desempeno_proveedores": desempeno_proveedores,
        "prediccion_mantenimientos": prediccion_mantenimientos,
        "optimizacion_tareas": optimizacion_tareas,
        "incidencias": {
            "total": len(incidencias),
            "abiertas": len(abiertas),
            "criticas": len(criticas),
        },
        "recomendaciones": recomendaciones,
    }


def responder_consulta(db: Session, edificio_id: str, pregunta: str, unidad_id_restringida: int | None = None) -> dict:
    """Responde preguntas operativas, financieras, normativas o genera borradores basados en los datos autorizados."""
    q = pregunta.strip().lower()
    analisis = analizar_edificio(db, edificio_id)
    if unidad_id_restringida is not None:
        # Residente: sólo ve los datos de su propia unidad
        mi_mora = [r for r in analisis["riesgo_morosidad"] if r["unidad_id"] == unidad_id_restringida]
        deuda = mi_mora[0]["deuda"] if mi_mora else 0.0
        u = db.get(Unidad, unidad_id_restringida)
        docs = db.scalars(select(Documento).where(
            Documento.edificio_id == edificio_id, Documento.publico_comunidad.is_(True))).all()
        comunicados = db.scalars(select(Comunicado).where(Comunicado.edificio_id == edificio_id).limit(5)).all()
        respuesta = (
            f"Estado de su unidad {u.numero if u else unidad_id_restringida}: "
            f"deuda pendiente CLP {deuda:,.0f}, saldo a favor CLP {float(u.saldo_favor if u else 0):,.0f}. "
            f"Documentos comunitarios publicados: {len(docs)}. "
            f"Comunicados vigentes: {len(comunicados)}."
        )
        return {
            "respuesta": respuesta,
            "modo": "determinista_residente",
            "datos_respaldo": {"unidad_id": unidad_id_restringida, "deuda": deuda, "documentos_publicos": len(docs)},
            "borrador_circular": None,
        }

    borrador = None
    if "circular" in q or "comunicado" in q or "borrador" in q:
        borrador = {
            "asunto": f"Informativo operativo y financiero — {analisis['edificio']}",
            "cuerpo": (
                f"Estimada comunidad de {analisis['edificio']}:\n\n"
                f"Informamos el estado operativo del período {analisis['periodo_actual']}. "
                f"Actualmente registramos {analisis['incidencias']['abiertas']} incidencia(s) en seguimiento "
                f"y {len(analisis['riesgo_morosidad'])} unidad(es) con saldo por regularizar.\n\n"
                f"Agradecemos mantener sus pagos al día indicando el código de su unidad.\n"
                f"Atentamente,\nAdministración"
            ),
        }

    rf = analisis["resumen_financiero"]
    base_txt = (
        f"Resumen de {analisis['edificio']} ({analisis['periodo_actual']}): "
        f"Saldo en caja CLP {rf['saldo_caja']:,.0f}, cuentas por cobrar CLP {rf['cuentas_por_cobrar']:,.0f}, "
        f"cuentas por pagar CLP {rf['cuentas_por_pagar']:,.0f}, proyección a 30 días CLP {rf['proyeccion_caja_30d']:,.0f}. "
        f"Incidencias abiertas: {analisis['incidencias']['abiertas']} ({analisis['incidencias']['criticas']} críticas). "
        f"Recomendación principal: {analisis['recomendaciones'][0]}"
    )

    modo = "determinista"
    if settings.anthropic_api_key:
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                timeout=12,
                headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"},
                json={
                    "model": settings.llm_model,
                    "max_tokens": 350,
                    "system": (
                        "Eres el asistente de administración del edificio. Responde únicamente usando los datos "
                        "JSON proporcionados, en español claro y conciso, sin inventar cifras."
                    ),
                    "messages": [{
                        "role": "user",
                        "content": f"Datos del edificio: {json.dumps(analisis, ensure_ascii=False)}\nPregunta: {pregunta[:500]}",
                    }],
                },
            )
            r.raise_for_status()
            texto_llm = r.json()["content"][0]["text"].strip()
            if texto_llm:
                base_txt = texto_llm
                modo = "llm_autorizado"
        except Exception:
            modo = "determinista"

    return {
        "respuesta": base_txt,
        "modo": modo,
        "datos_respaldo": analisis,
        "borrador_circular": borrador,
    }
