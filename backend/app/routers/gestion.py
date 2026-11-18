"""Gestión de edificios, reversas, exportaciones y configuración de automatizaciones."""
import csv
import io
import secrets
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import hoy_local
from ..db import get_db
from ..models import AplicacionPago, Cargo, Edificio, Encomienda, Evento, Pago, Residente, Rol, Unidad
from ..operation_schemas import AutomatizacionIn, EdificioIn, EdificioPatch, ReversaIn
from ..operations_models import AutomatizacionConfig, Incidencia, OrdenTrabajo
from ..security import Principal, hash_clave_dispositivo, require_roles
from ..services.automation import ejecutar
from ..services.cache import cache_get, cache_set
from .operaciones import Admin, User, auditar, edificio, ficha, recurso

router = APIRouter(tags=["gestion"])
Global = Annotated[Principal, Depends(require_roles(Rol.superadmin))]


@router.post("/edificios", status_code=201)
def crear(ed: EdificioIn, user: Global, db: Session = Depends(get_db)):
    if db.get(Edificio, ed.id):
        raise HTTPException(409, "Identificador de edificio ya existe")
    e = Edificio(**ed.model_dump(), device_api_key=hash_clave_dispositivo(secrets.token_urlsafe(32)))
    db.add(e)
    db.flush()
    auditar(db, user, e.id, "edificio.creado", e.id)
    db.commit()
    return {"id": e.id, "nombre": e.nombre, "activo": e.activo}


@router.patch("/edificios/{edificio_id}")
def editar(edificio_id: str, body: EdificioPatch, user: Global, db: Session = Depends(get_db)):
    e = edificio(db, user, edificio_id, True)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(e, k, v)
    auditar(db, user, edificio_id, "edificio.configurado", e.id, cambios=body.model_dump(exclude_none=True))
    db.commit()
    return {"id": e.id, "nombre": e.nombre, "activo": e.activo}


@router.post("/auth/logout")
def logout(user: User, db: Session = Depends(get_db)):
    # Revoca todas las sesiones de este usuario, incluidas las anteriores al cambio de contraseña.
    r = db.scalar(select(Residente).where(Residente.id == user.residente_id).with_for_update())
    r.session_version += 1
    db.commit()
    return {"revocadas": True}


@router.get("/edificios/{edificio_id}/pagos")
def pagos(edificio_id: str, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    if user.rol == Rol.conserje:
        raise HTTPException(403, "Permisos insuficientes")
    q = select(Pago).where(Pago.edificio_id == edificio_id, Pago.duplicado_de_id.is_(None))
    if user.rol == Rol.residente:
        q = q.where(Pago.unidad_id == db.get(Residente, user.residente_id).unidad_id)
    return [ficha(p, "id unidad_id monto fecha referencia ref_banco conciliado excedente revertido")
            for p in db.scalars(q.order_by(Pago.id.desc()).limit(200))]


@router.post("/edificios/{edificio_id}/pagos/{pago_id}/revertir")
def revertir(edificio_id: str, pago_id: int, body: ReversaIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    p = recurso(db, Pago, edificio_id, pago_id)
    if p.revertido or p.duplicado_de_id or not p.conciliado or not p.unidad_id:
        raise HTTPException(409, "El pago no admite reversa")
    aplicaciones = db.scalars(select(AplicacionPago).where(AplicacionPago.pago_id == p.id)).all()
    suma = sum((Decimal(str(a.monto)) for a in aplicaciones), Decimal("0")) + Decimal(str(p.excedente))
    if suma != p.monto:
        raise HTTPException(409, "Pago histórico sin desglose completo; requiere conciliación manual")
    u = recurso(db, Unidad, edificio_id, p.unidad_id)
    if u.saldo_favor < p.excedente:
        raise HTTPException(409, "El saldo a favor fue utilizado; requiere conciliación manual")
    for a in aplicaciones:
        c = recurso(db, Cargo, edificio_id, a.cargo_id)
        if c.saldo + a.monto > c.monto:
            raise HTTPException(409, "El cargo tiene ajustes posteriores; requiere conciliación manual")
        c.saldo += a.monto
    u.saldo_favor -= p.excedente
    p.revertido = True
    auditar(db, user, edificio_id, "pago.revertido", p.id, motivo=body.motivo)
    db.commit()
    return {"id": p.id, "revertido": True}


@router.get("/edificios/{edificio_id}/dashboard")
def dashboard(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    cached = cache_get(f"dash:{edificio_id}")
    if cached is not None:
        return cached
    inicio = hoy_local().replace(day=1)
    def count(model, *where):
        return db.scalar(select(func.count(model.id)).where(model.edificio_id == edificio_id, *where))
    def suma(col, *where):
        return float(db.scalar(select(func.coalesce(func.sum(col), 0)).where(col.class_.edificio_id == edificio_id, *where)))
    unidades = count(Unidad)
    ocupadas = db.scalar(select(func.count(func.distinct(Residente.unidad_id))).where(
        Residente.edificio_id == edificio_id, Residente.activo.is_(True)))
    res = {"unidades": unidades, "residentes": count(Residente, Residente.activo.is_(True)),
           "ocupacion_pct": round(100 * ocupadas / unidades, 1) if unidades else 0,
           "ingresos_mes": suma(Pago.monto, Pago.fecha >= inicio, Pago.conciliado.is_(True),
                                 Pago.revertido.is_(False), Pago.duplicado_de_id.is_(None)),
           "deuda": suma(Cargo.saldo), "saldo_favor": suma(Unidad.saldo_favor),
           "deuda_vencida": suma(Cargo.saldo, Cargo.vencimiento < hoy_local()),
           "incidencias_abiertas": count(Incidencia, Incidencia.estado.not_in(["resuelta", "cerrada"])),
           "incidencias_criticas": count(Incidencia, Incidencia.prioridad == "critica", Incidencia.estado.not_in(["resuelta", "cerrada"])),
           "ordenes_pendientes": count(OrdenTrabajo, OrdenTrabajo.estado == "pendiente"),
           "encomiendas_pendientes": count(Encomienda, Encomienda.estado == "pendiente")}
    cache_set(f"dash:{edificio_id}", res, ttl_s=15)
    return res


@router.get("/edificios/{edificio_id}/auditoria")
def auditoria(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    return [ficha(e, "id tipo payload creado") for e in db.scalars(select(Evento).where(
        Evento.edificio_id == edificio_id).order_by(Evento.id.desc()).limit(200))]


@router.get("/edificios/{edificio_id}/finanzas/exportar.csv")
def exportar(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["tipo", "id", "unidad_id", "fecha_periodo", "concepto", "monto", "saldo", "estado"])
    def seguro(valor):
        valor = str(valor)
        return "'" + valor if valor.lstrip().startswith(("=", "+", "-", "@")) else valor
    for c in db.scalars(select(Cargo).where(Cargo.edificio_id == edificio_id).order_by(Cargo.id)):
        writer.writerow(["cargo", c.id, c.unidad_id, c.periodo, seguro(c.concepto), c.monto, c.saldo, ""])
    for p in db.scalars(select(Pago).where(Pago.edificio_id == edificio_id, Pago.duplicado_de_id.is_(None)).order_by(Pago.id)):
        writer.writerow(["pago", p.id, p.unidad_id, p.fecha, seguro(p.referencia), p.monto, p.excedente,
                         "revertido" if p.revertido else "conciliado" if p.conciliado else "pendiente"])
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="movimientos.csv"'})


@router.get("/edificios/{edificio_id}/automatizaciones")
def config_automatizaciones(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    cfg = db.get(AutomatizacionConfig, edificio_id)
    return ficha(cfg, "activa recordatorios_pago contratos_dias max_notificaciones") if cfg else AutomatizacionIn().model_dump()


@router.put("/edificios/{edificio_id}/automatizaciones")
def guardar_automatizaciones(edificio_id: str, body: AutomatizacionIn, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    cfg = db.get(AutomatizacionConfig, edificio_id)
    if not cfg:
        cfg = AutomatizacionConfig(edificio_id=edificio_id)
        db.add(cfg)
    for k, v in body.model_dump().items():
        setattr(cfg, k, v)
    auditar(db, user, edificio_id, "automatizacion.configurada", edificio_id, **body.model_dump())
    db.commit()
    return body.model_dump()


@router.post("/edificios/{edificio_id}/automatizaciones/ejecutar")
def ejecutar_automatizaciones(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    result = ejecutar(db, edificio_id)
    auditar(db, user, edificio_id, "automatizacion.manual", edificio_id)
    db.commit()
    return result


# ---- Contabilidad, presupuestos, convenios, pasarela de pago e IA ----
@router.get("/edificios/{edificio_id}/contabilidad/movimientos")
def listar_movimientos_contables(edificio_id: str, user: Admin, periodo: str | None = None,
                                 tipo: str | None = None, db: Session = Depends(get_db)):
    from ..operations_models import MovimientoContable
    edificio(db, user, edificio_id)
    q = select(MovimientoContable).where(MovimientoContable.edificio_id == edificio_id)
    if periodo:
        q = q.where(MovimientoContable.periodo == periodo)
    if tipo in ("ingreso", "egreso", "ajuste"):
        q = q.where(MovimientoContable.tipo == tipo)
    return [ficha(m, "id fecha periodo tipo categoria cuenta_debe cuenta_haber concepto monto estado proveedor_id documento_id unidad_id pago_id creado")
            for m in db.scalars(q.order_by(MovimientoContable.id.desc()).limit(300))]


@router.post("/edificios/{edificio_id}/contabilidad/movimientos", status_code=201)
def registrar_movimiento_contable(edificio_id: str, body: dict, user: Admin, db: Session = Depends(get_db)):
    from datetime import date as dt_date
    from ..operations_models import Documento, MovimientoContable, Proveedor
    edificio(db, user, edificio_id, True)
    tipo = str(body.get("tipo") or "egreso")
    if tipo not in ("ingreso", "egreso", "ajuste"):
        raise HTTPException(422, "El tipo debe ser ingreso, egreso o ajuste")
    monto = float(body.get("monto") or 0)
    if monto <= 0 or monto > 999999999999:
        raise HTTPException(422, "El monto debe ser mayor que cero")
    concepto = str(body.get("concepto") or "").strip()
    if len(concepto) < 3:
        raise HTTPException(422, "Indique el concepto del movimiento contable")
    fecha = dt_date.fromisoformat(body["fecha"]) if body.get("fecha") else hoy_local()
    periodo = str(body.get("periodo") or fecha.strftime("%Y-%m"))
    prov_id = int(body["proveedor_id"]) if body.get("proveedor_id") else None
    doc_id = int(body["documento_id"]) if body.get("documento_id") else None
    uni_id = int(body["unidad_id"]) if body.get("unidad_id") else None
    if prov_id:
        recurso(db, Proveedor, edificio_id, prov_id)
    if doc_id:
        recurso(db, Documento, edificio_id, doc_id)
    if uni_id:
        recurso(db, Unidad, edificio_id, uni_id)
    estado = str(body.get("estado") or ("pendiente" if tipo == "egreso" and prov_id else "confirmado"))
    if estado not in ("pendiente", "aprobado", "pagado", "confirmado", "anulado"):
        raise HTTPException(422, "Estado contable inválido")
    m = MovimientoContable(
        edificio_id=edificio_id,
        fecha=fecha,
        periodo=periodo[:7],
        tipo=tipo,
        categoria=str(body.get("categoria") or "general")[:40],
        cuenta_debe=str(body.get("cuenta_debe") or ("gastos_operacionales" if tipo == "egreso" else "caja_banco"))[:60],
        cuenta_haber=str(body.get("cuenta_haber") or ("cuentas_por_pagar" if estado == "pendiente" else "caja_banco"))[:60],
        concepto=concepto[:200],
        monto=Decimal(str(monto)).quantize(Decimal("0.01")),
        estado=estado,
        proveedor_id=prov_id,
        documento_id=doc_id,
        unidad_id=uni_id,
        creado_por=user.residente_id,
    )
    db.add(m)
    db.flush()
    auditar(db, user, edificio_id, "contabilidad.movimiento", m.id, clase_movimiento=tipo, monto=float(m.monto))
    db.commit()
    return ficha(m, "id fecha periodo tipo categoria cuenta_debe cuenta_haber concepto monto estado proveedor_id documento_id unidad_id creado")


@router.patch("/edificios/{edificio_id}/contabilidad/movimientos/{movimiento_id}")
def actualizar_movimiento_contable(edificio_id: str, movimiento_id: int, body: dict,
                                   user: Admin, db: Session = Depends(get_db)):
    from ..operations_models import MovimientoContable
    edificio(db, user, edificio_id, True)
    m = recurso(db, MovimientoContable, edificio_id, movimiento_id)
    nuevo_estado = str(body.get("estado") or "")
    if nuevo_estado not in ("aprobado", "pagado", "confirmado", "anulado"):
        raise HTTPException(422, "Estado inválido")
    m.estado = nuevo_estado
    if nuevo_estado in ("aprobado", "pagado"):
        m.aprobado_por = user.residente_id
    auditar(db, user, edificio_id, "contabilidad.estado", m.id, estado=nuevo_estado)
    db.commit()
    return ficha(m, "id fecha periodo tipo categoria concepto monto estado aprobado_por")


@router.get("/edificios/{edificio_id}/contabilidad/presupuestos")
def listar_presupuestos(edificio_id: str, user: Admin, periodo: str | None = None, db: Session = Depends(get_db)):
    from ..operations_models import PresupuestoRubro
    edificio(db, user, edificio_id)
    q = select(PresupuestoRubro).where(PresupuestoRubro.edificio_id == edificio_id)
    if periodo:
        q = q.where(PresupuestoRubro.periodo == periodo)
    return [ficha(p, "id periodo categoria monto_presupuestado notas creado")
            for p in db.scalars(q.order_by(PresupuestoRubro.periodo.desc(), PresupuestoRubro.categoria))]


@router.post("/edificios/{edificio_id}/contabilidad/presupuestos", status_code=201)
def guardar_presupuesto(edificio_id: str, body: dict, user: Admin, db: Session = Depends(get_db)):
    from ..operations_models import PresupuestoRubro
    edificio(db, user, edificio_id, True)
    periodo = str(body.get("periodo") or hoy_local().strftime("%Y-%m")).strip()
    categoria = str(body.get("categoria") or "").strip().lower()
    monto = float(body.get("monto_presupuestado") or 0)
    if not categoria or monto < 0:
        raise HTTPException(422, "Categoría y monto presupuestado válido son obligatorios")
    previo = db.scalar(select(PresupuestoRubro).where(
        PresupuestoRubro.edificio_id == edificio_id,
        PresupuestoRubro.periodo == periodo,
        PresupuestoRubro.categoria == categoria))
    if previo:
        previo.monto_presupuestado = Decimal(str(monto)).quantize(Decimal("0.01"))
        previo.notas = str(body.get("notas") or "")[:300]
        p = previo
    else:
        p = PresupuestoRubro(edificio_id=edificio_id, periodo=periodo[:7], categoria=categoria[:40],
                             monto_presupuestado=Decimal(str(monto)).quantize(Decimal("0.01")),
                             notas=str(body.get("notas") or "")[:300])
        db.add(p)
    db.flush()
    auditar(db, user, edificio_id, "contabilidad.presupuesto", p.id, periodo=p.periodo, categoria=p.categoria)
    db.commit()
    return ficha(p, "id periodo categoria monto_presupuestado notas creado")


@router.get("/edificios/{edificio_id}/contabilidad/balance")
def balance_y_estado_financiero(edificio_id: str, user: Admin, anio: int | None = None, db: Session = Depends(get_db)):
    """Balance general, estado de resultados, flujo de caja, cuentas por cobrar/pagar y fondo de reserva."""
    from ..operations_models import MovimientoContable, PresupuestoRubro
    edificio(db, user, edificio_id)
    anio_str = str(anio or hoy_local().year)
    movs = db.scalars(select(MovimientoContable).where(
        MovimientoContable.edificio_id == edificio_id, MovimientoContable.estado != "anulado")).all()
    pagos_ok = db.scalars(select(Pago).where(
        Pago.edificio_id == edificio_id, Pago.conciliado.is_(True),
        Pago.revertido.is_(False), Pago.duplicado_de_id.is_(None))).all()
    cargos_all = db.scalars(select(Cargo).where(Cargo.edificio_id == edificio_id)).all()
    unidades_all = db.scalars(select(Unidad).where(Unidad.edificio_id == edificio_id)).all()

    ingresos_cobranza = sum(float(p.monto) for p in pagos_ok)
    ingresos_extra = sum(float(m.monto) for m in movs if m.tipo == "ingreso" and m.pago_id is None)
    egresos_pagados = sum(float(m.monto) for m in movs if m.tipo == "egreso" and m.estado in ("pagado", "confirmado"))
    cuentas_por_pagar = sum(float(m.monto) for m in movs if m.tipo == "egreso" and m.estado in ("pendiente", "aprobado"))
    cuentas_por_cobrar = sum(float(c.saldo) for c in cargos_all if float(c.saldo) > 0)
    fondo_reserva_emitido = sum(float(c.monto) for c in cargos_all if c.categoria == "fondo_reserva")
    fondo_reserva_recaudado = sum(float(c.monto) - float(c.saldo) for c in cargos_all if c.categoria == "fondo_reserva")
    anticipos_residentes = sum(float(u.saldo_favor) for u in unidades_all)

    caja_disponible = round(ingresos_cobranza + ingresos_extra - egresos_pagados, 2)
    activos = round(caja_disponible + cuentas_por_cobrar, 2)
    pasivos = round(cuentas_por_pagar + anticipos_residentes, 2)
    patrimonio = round(activos - pasivos, 2)

    # Flujo mensual del año solicitado
    flujo_mensual = {}
    for p in pagos_ok:
        per = p.fecha.strftime("%Y-%m")
        if per.startswith(anio_str):
            flujo_mensual.setdefault(per, {"ingresos": 0.0, "egresos": 0.0})["ingresos"] += float(p.monto)
    for m in movs:
        if m.periodo.startswith(anio_str):
            slot = flujo_mensual.setdefault(m.periodo, {"ingresos": 0.0, "egresos": 0.0})
            if m.tipo == "ingreso" and m.pago_id is None:
                slot["ingresos"] += float(m.monto)
            elif m.tipo == "egreso" and m.estado != "anulado":
                slot["egresos"] += float(m.monto)

    presupuestos = db.scalars(select(PresupuestoRubro).where(PresupuestoRubro.edificio_id == edificio_id)).all()
    return {
        "anio": int(anio_str),
        "caja_disponible": caja_disponible,
        "ingresos_totales": round(ingresos_cobranza + ingresos_extra, 2),
        "egresos_totales": round(egresos_pagados, 2),
        "cuentas_por_cobrar": round(cuentas_por_cobrar, 2),
        "cuentas_por_pagar": round(cuentas_por_pagar, 2),
        "anticipos_residentes": round(anticipos_residentes, 2),
        "fondo_reserva": {
            "emitido": round(fondo_reserva_emitido, 2),
            "recaudado": round(fondo_reserva_recaudado, 2),
        },
        "balance": {
            "activos": activos,
            "pasivos": pasivos,
            "patrimonio_comunidad": patrimonio,
        },
        "flujo_mensual": [
            {"periodo": k, "ingresos": round(v["ingresos"], 2), "egresos": round(v["egresos"], 2),
             "neto": round(v["ingresos"] - v["egresos"], 2)}
            for k, v in sorted(flujo_mensual.items())
        ],
        "presupuestos_registrados": len(presupuestos),
    }


@router.get("/edificios/{edificio_id}/convenios-pago")
def listar_convenios(edificio_id: str, user: User, db: Session = Depends(get_db)):
    from ..operations_models import ConvenioPago
    edificio(db, user, edificio_id)
    q = select(ConvenioPago).where(ConvenioPago.edificio_id == edificio_id)
    if user.rol == Rol.residente:
        yo = db.get(Residente, user.residente_id)
        q = q.where(ConvenioPago.unidad_id == yo.unidad_id)
    return [ficha(c, "id unidad_id monto_total pie_inicial cuotas cuotas_pagadas tasa_interes_pct primer_vencimiento estado observaciones creado")
            for c in db.scalars(q.order_by(ConvenioPago.id.desc()).limit(100))]


@router.post("/edificios/{edificio_id}/convenios-pago", status_code=201)
def crear_convenio(edificio_id: str, body: dict, user: Admin, db: Session = Depends(get_db)):
    from datetime import date as dt_date
    from ..operations_models import ConvenioPago
    edificio(db, user, edificio_id, True)
    uid = int(body.get("unidad_id") or 0)
    recurso(db, Unidad, edificio_id, uid)
    monto = float(body.get("monto_total") or 0)
    cuotas = int(body.get("cuotas") or 0)
    if monto <= 0 or not (1 <= cuotas <= 60):
        raise HTTPException(422, "Indique un monto mayor que cero y entre 1 y 60 cuotas")
    venc = dt_date.fromisoformat(body["primer_vencimiento"]) if body.get("primer_vencimiento") else hoy_local()
    c = ConvenioPago(
        edificio_id=edificio_id,
        unidad_id=uid,
        monto_total=Decimal(str(monto)).quantize(Decimal("0.01")),
        pie_inicial=Decimal(str(float(body.get("pie_inicial") or 0))).quantize(Decimal("0.01")),
        cuotas=cuotas,
        tasa_interes_pct=Decimal(str(float(body.get("tasa_interes_pct") or 0))).quantize(Decimal("0.01")),
        primer_vencimiento=venc,
        observaciones=str(body.get("observaciones") or "")[:400],
        creado_por=user.residente_id,
    )
    db.add(c)
    db.flush()
    auditar(db, user, edificio_id, "convenio.creado", c.id, unidad_id=uid, cuotas=cuotas)
    db.commit()
    return ficha(c, "id unidad_id monto_total pie_inicial cuotas cuotas_pagadas tasa_interes_pct primer_vencimiento estado observaciones creado")


@router.post("/edificios/{edificio_id}/cargos/{cargo_id}/ajustar")
def ajustar_cargo(edificio_id: str, cargo_id: int, body: dict, user: Admin, db: Session = Depends(get_db)):
    """Aplica un descuento o ajuste autorizado sobre el saldo de un cargo y deja registro contable."""
    from ..operations_models import MovimientoContable
    edificio(db, user, edificio_id, True)
    c = recurso(db, Cargo, edificio_id, cargo_id)
    descuento = Decimal(str(float(body.get("descuento") or 0))).quantize(Decimal("0.01"))
    motivo = str(body.get("motivo") or "").strip()
    if descuento <= 0 or descuento > Decimal(str(c.saldo)):
        raise HTTPException(422, "El descuento debe ser mayor que cero y no superar el saldo pendiente del cargo")
    if len(motivo) < 5:
        raise HTTPException(422, "Indique el motivo del descuento o ajuste (mínimo 5 caracteres)")
    c.saldo = Decimal(str(c.saldo)) - descuento
    m = MovimientoContable(
        edificio_id=edificio_id, fecha=hoy_local(), periodo=c.periodo, tipo="ajuste",
        categoria="descuento_autorizado", cuenta_debe="descuentos_gastos_comunes",
        cuenta_haber="cuentas_por_cobrar", concepto=f"Descuento cargo #{c.id}: {motivo}"[:200],
        monto=descuento, estado="confirmado", unidad_id=c.unidad_id, creado_por=user.residente_id,
    )
    db.add(m)
    auditar(db, user, edificio_id, "cargo.ajustado", c.id, descuento=float(descuento), motivo=motivo)
    db.commit()
    return {"id": c.id, "saldo": float(c.saldo), "descuento_aplicado": float(descuento)}


@router.post("/edificios/{edificio_id}/pagos/pasarela/iniciar", status_code=201)
def iniciar_pago_pasarela(edificio_id: str, body: dict, user: User, db: Session = Depends(get_db)):
    from ..config import settings
    from ..operations_models import TransaccionPasarela
    from ..services import payment_gateways
    edificio(db, user, edificio_id, True)
    if user.rol == Rol.conserje:
        raise HTTPException(403, "Permisos insuficientes")
    yo = db.get(Residente, user.residente_id)
    uid = yo.unidad_id if user.rol == Rol.residente else int(body.get("unidad_id") or yo.unidad_id)
    u = recurso(db, Unidad, edificio_id, uid)
    idemp = str(body.get("idempotencia") or secrets.token_urlsafe(16))[:64]
    previa = db.scalar(select(TransaccionPasarela).where(
        TransaccionPasarela.edificio_id == edificio_id, TransaccionPasarela.idempotencia == idemp))
    if previa:
        return ficha(previa, "id proveedor orden_compra token_pasarela monto estado url_pago pago_id")
    monto = float(body.get("monto") or 0)
    if monto <= 0:
        from ..services.finance import deuda_unidad
        monto = deuda_unidad(db, u.id)
    if monto <= 0:
        raise HTTPException(422, "Indique un monto mayor que cero o tenga cargos pendientes")
    proveedor = str(body.get("proveedor") or settings.payment_gateway_default).lower()
    orden = f"ED-{edificio_id[:8].upper()}-{u.numero}-{secrets.token_hex(4).upper()}"[:26]
    tx_info = payment_gateways.crear_transaccion(
        proveedor, orden, f"sess-{user.residente_id}", monto, "CLP", str(body.get("url_retorno") or "")
    )
    tx = TransaccionPasarela(
        edificio_id=edificio_id, unidad_id=u.id, residente_id=user.residente_id,
        proveedor=proveedor, idempotencia=idemp, orden_compra=orden,
        token_pasarela=tx_info["token"], monto=Decimal(str(monto)).quantize(Decimal("0.01")),
        url_pago=tx_info["url_pago"], estado="iniciada",
    )
    db.add(tx)
    db.flush()
    auditar(db, user, edificio_id, "pasarela.iniciada", tx.id, proveedor=proveedor, monto=monto)
    db.commit()
    return ficha(tx, "id proveedor orden_compra token_pasarela monto estado url_pago pago_id")


@router.post("/edificios/{edificio_id}/pagos/pasarela/{tx_id}/confirmar")
def confirmar_pago_pasarela(edificio_id: str, tx_id: int, body: dict, user: User, db: Session = Depends(get_db)):
    from ..config import utcnow
    from ..operations_models import MovimientoContable, TransaccionPasarela
    from ..services import payment_gateways
    from ..services.reconciliation import _aplicar
    edificio(db, user, edificio_id, True)
    tx = recurso(db, TransaccionPasarela, edificio_id, tx_id)
    if user.rol == Rol.residente:
        yo = db.get(Residente, user.residente_id)
        if tx.unidad_id != yo.unidad_id:
            raise HTTPException(404, "Transacción no existe")
    if tx.estado == "autorizada":
        return ficha(tx, "id proveedor orden_compra token_pasarela monto estado codigo_autorizacion pago_id")
    if tx.estado != "iniciada":
        raise HTTPException(409, f"La transacción ya fue {tx.estado}")
    res = payment_gateways.confirmar_transaccion(
        tx.proveedor, tx.token_pasarela, float(tx.monto), str(body.get("resultado_sandbox") or "autorizada")
    )
    tx.estado = res["estado"]
    tx.codigo_autorizacion = res.get("codigo_autorizacion", "")
    tx.confirmado_at = utcnow()
    if tx.estado == "autorizada":
        ref = f"pasarela:{tx.proveedor}:{tx.orden_compra}"[:80]
        previo = db.scalar(select(Pago).where(Pago.edificio_id == edificio_id, Pago.ref_banco == ref))
        if not previo:
            pago = Pago(
                edificio_id=edificio_id, unidad_id=tx.unidad_id, monto=tx.monto,
                fecha=hoy_local(), referencia=f"Pago {tx.proveedor} {tx.orden_compra} ({tx.codigo_autorizacion})",
                ref_banco=ref, conciliado=True,
            )
            db.add(pago)
            db.flush()
            _aplicar(db, tx.unidad_id, float(tx.monto), pago)
            tx.pago_id = pago.id
            db.add(MovimientoContable(
                edificio_id=edificio_id, fecha=hoy_local(), periodo=hoy_local().strftime("%Y-%m"),
                tipo="ingreso", categoria="cobranza_pasarela", cuenta_debe="caja_banco",
                cuenta_haber="cuentas_por_cobrar", concepto=f"Cobro pasarela {tx.orden_compra}",
                monto=tx.monto, estado="confirmado", unidad_id=tx.unidad_id, pago_id=pago.id,
                creado_por=user.residente_id,
            ))
    auditar(db, user, edificio_id, f"pasarela.{tx.estado}", tx.id, pago_id=tx.pago_id)
    db.commit()
    return ficha(tx, "id proveedor orden_compra token_pasarela monto estado codigo_autorizacion pago_id")


@router.get("/edificios/{edificio_id}/ia/analisis")
def analisis_ia(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    from ..services import llm
    edificio(db, user, edificio_id)
    return llm.analizar_edificio(db, edificio_id)


@router.post("/edificios/{edificio_id}/ia/asistente")
def asistente_ia(edificio_id: str, body: dict, user: User, db: Session = Depends(get_db)):
    from ..services import llm
    edificio(db, user, edificio_id)
    if user.rol == Rol.conserje:
        raise HTTPException(403, "Permisos insuficientes")
    pregunta = str(body.get("pregunta") or "").strip()
    if len(pregunta) < 3:
        raise HTTPException(422, "Escriba una consulta de al menos 3 caracteres")
    uid_restringida = None
    if user.rol == Rol.residente:
        yo = db.get(Residente, user.residente_id)
        uid_restringida = yo.unidad_id
    return llm.responder_consulta(db, edificio_id, pregunta, uid_restringida)


@router.get("/edificios/{edificio_id}/mi-perfil")
def ver_mi_perfil(edificio_id: str, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    r = db.get(Residente, user.residente_id)
    return {"id": r.id, "nombre": r.nombre, "email": r.email, "telefono": r.telefono, "unidad_id": r.unidad_id}


@router.patch("/edificios/{edificio_id}/mi-perfil")
def actualizar_mi_perfil(edificio_id: str, body: dict, user: User, db: Session = Depends(get_db)):
    from .. import validacion
    from ..security import hash_password
    edificio(db, user, edificio_id, True)
    r = db.get(Residente, user.residente_id)
    if "nombre" in body and body["nombre"]:
        nom = str(body["nombre"]).strip()
        if len(nom) < 2 or len(nom) > 120:
            raise HTTPException(422, "Nombre inválido")
        r.nombre = nom
    if "email" in body and body["email"] is not None:
        em = str(body["email"]).strip()
        if em and not validacion.email_valido(em):
            raise HTTPException(422, "Correo inválido")
        r.email = em
    if "telefono" in body and body["telefono"] is not None:
        tel = str(body["telefono"]).strip()
        if tel and not validacion.telefono_valido(tel):
            raise HTTPException(422, "Teléfono inválido")
        r.telefono = validacion.telefono_normalizar(tel) if tel else ""
    if body.get("password"):
        pw = str(body["password"])
        if len(pw) < 8:
            raise HTTPException(422, "La contraseña debe tener al menos 8 caracteres")
        r.password_hash = hash_password(pw)
        r.session_version += 1
    auditar(db, user, edificio_id, "perfil.actualizado", r.id)
    db.commit()
    return {"id": r.id, "nombre": r.nombre, "email": r.email, "telefono": r.telefono}


@router.get("/edificios/{edificio_id}/buscar")
def buscar_global(edificio_id: str, q: str = "", user: User = ..., db: Session = Depends(get_db)):
    """Búsqueda global transversal (21.07) sobre unidades, residentes, incidencias, documentos y proveedores."""
    from ..operations_models import Documento, Proveedor
    edificio(db, user, edificio_id)
    termino = q.strip().lower()
    if len(termino) < 2:
        return {"unidades": [], "residentes": [], "incidencias": [], "documentos": [], "proveedores": []}

    es_residente = user.rol == Rol.residente
    yo = db.get(Residente, user.residente_id) if es_residente else None
    mi_unidad_id = yo.unidad_id if yo else None

    q_unidades = select(Unidad).where(Unidad.edificio_id == edificio_id)
    if es_residente:
        q_unidades = q_unidades.where(Unidad.id == mi_unidad_id)
    unidades = [
        {"id": u.id, "numero": u.numero, "torre": u.torre or ""}
        for u in db.scalars(q_unidades).all()
        if termino in (u.numero or "").lower() or termino in (u.torre or "").lower()
    ][:10]

    q_res = select(Residente).where(Residente.edificio_id == edificio_id, Residente.activo.is_(True))
    if es_residente:
        q_res = q_res.where(Residente.unidad_id == mi_unidad_id)
    residentes = [
        {"id": r.id, "nombre": r.nombre, "unidad_id": r.unidad_id, "rol": r.rol.value}
        for r in db.scalars(q_res).all()
        if termino in (r.nombre or "").lower() or termino in (r.email or "").lower()
    ][:10]

    q_inc = select(Incidencia).where(Incidencia.edificio_id == edificio_id)
    if es_residente:
        q_inc = q_inc.where(Incidencia.unidad_id == mi_unidad_id)
    incidencias = [
        {"id": i.id, "titulo": i.titulo, "estado": i.estado, "prioridad": i.prioridad}
        for i in db.scalars(q_inc).all()
        if termino in (i.titulo or "").lower() or termino in (i.descripcion or "").lower()
    ][:10]

    documentos = [
        {"id": d.id, "titulo": d.titulo, "categoria": d.categoria}
        for d in db.scalars(select(Documento).where(Documento.edificio_id == edificio_id)).all()
        if termino in (d.titulo or "").lower() or termino in (d.categoria or "").lower()
    ][:10]

    proveedores = []
    if not es_residente:
        proveedores = [
            {"id": p.id, "nombre": p.nombre, "servicio": p.servicio}
            for p in db.scalars(select(Proveedor).where(Proveedor.edificio_id == edificio_id)).all()
            if termino in (p.nombre or "").lower() or termino in (p.servicio or "").lower()
        ][:10]

    return {
        "unidades": unidades,
        "residentes": residentes,
        "incidencias": incidencias,
        "documentos": documentos,
        "proveedores": proveedores,
    }


@router.delete("/edificios/{edificio_id}")
def eliminar_o_desactivar_edificio(edificio_id: str, user: Global, db: Session = Depends(get_db)):
    """Elimina un edificio vacío o lo desactiva de forma segura si posee historial (04.01)."""
    e = edificio(db, user, edificio_id, True)
    tiene_unidades = db.scalar(select(func.count(Unidad.id)).where(Unidad.edificio_id == edificio_id)) or 0
    tiene_cargos = db.scalar(select(func.count(Cargo.id)).where(Cargo.edificio_id == edificio_id)) or 0
    if tiene_unidades == 0 and tiene_cargos == 0:
        db.delete(e)
        db.commit()
        return {"id": edificio_id, "eliminado": True, "activo": False}
    e.activo = False
    auditar(db, user, edificio_id, "edificio.desactivado", edificio_id)
    db.commit()
    return {"id": edificio_id, "eliminado": False, "activo": False}


@router.get("/edificios/{edificio_id}/unidades/{unidad_id}/historial")
def historial_unidad(edificio_id: str, unidad_id: int, user: User, db: Session = Depends(get_db)):
    """Historial consolidado de un departamento (04.13): cargos, pagos, incidencias, reservas, visitas y encomiendas."""
    from ..models import ReservaEspacio, Visita
    edificio(db, user, edificio_id)
    u = recurso(db, Unidad, edificio_id, unidad_id)
    if user.rol == Rol.residente:
        yo = db.get(Residente, user.residente_id)
        if not yo or yo.unidad_id != u.id:
            raise HTTPException(403, "Solo puede consultar el historial de su propio departamento")
    cargos = db.scalars(select(Cargo).where(Cargo.edificio_id == edificio_id, Cargo.unidad_id == u.id).order_by(Cargo.id.desc()).limit(50)).all()
    pagos = db.scalars(select(Pago).where(Pago.edificio_id == edificio_id, Pago.unidad_id == u.id).order_by(Pago.id.desc()).limit(50)).all()
    incidencias = db.scalars(select(Incidencia).where(Incidencia.edificio_id == edificio_id, Incidencia.unidad_id == u.id).order_by(Incidencia.id.desc()).limit(50)).all()
    reservas = db.scalars(select(ReservaEspacio).where(ReservaEspacio.edificio_id == edificio_id, ReservaEspacio.unidad_id == u.id).order_by(ReservaEspacio.id.desc()).limit(50)).all()
    visitas = db.scalars(select(Visita).where(Visita.edificio_id == edificio_id, Visita.unidad_id == u.id).order_by(Visita.id.desc()).limit(50)).all()
    encomiendas = db.scalars(select(Encomienda).where(Encomienda.edificio_id == edificio_id, Encomienda.unidad_id == u.id).order_by(Encomienda.id.desc()).limit(50)).all()
    return {
        "unidad": {"id": u.id, "numero": u.numero, "torre": u.torre, "coeficiente": float(u.coeficiente), "saldo_favor": float(u.saldo_favor)},
        "cargos": [{"id": c.id, "periodo": c.periodo, "concepto": c.concepto, "monto": float(c.monto), "saldo": float(c.saldo)} for c in cargos],
        "pagos": [{"id": p.id, "fecha": p.fecha.isoformat(), "monto": float(p.monto), "conciliado": p.conciliado, "revertido": p.revertido} for p in pagos],
        "incidencias": [{"id": i.id, "titulo": i.titulo, "estado": i.estado, "prioridad": i.prioridad} for i in incidencias],
        "reservas": [{"id": r.id, "espacio_id": r.espacio_id, "desde": r.desde.isoformat(), "estado": r.estado} for r in reservas],
        "visitas": [{"id": v.id, "nombre_visita": v.nombre_visita, "estado": v.estado.value} for v in visitas],
        "encomiendas": [{"id": e.id, "destinatario": e.destinatario, "estado": e.estado} for e in encomiendas],
    }


@router.post("/edificios/{edificio_id}/finanzas/multas", status_code=201)
def aplicar_multa(edificio_id: str, body: dict, user: Admin, db: Session = Depends(get_db)):
    """Aplica una multa auditable a una unidad (05.06)."""
    from datetime import timedelta
    from ..operations_models import Notificacion
    edificio(db, user, edificio_id, True)
    uid = body.get("unidad_id")
    if not uid:
        raise HTTPException(422, "unidad_id requerido")
    u = recurso(db, Unidad, edificio_id, int(uid))
    try:
        monto = Decimal(str(body.get("monto", 0)))
    except Exception:
        raise HTTPException(422, "Monto inválido")
    if monto <= 0:
        raise HTTPException(422, "El monto de la multa debe ser mayor a 0")
    motivo = str(body.get("motivo") or "Infracción al reglamento interno").strip()[:180]
    periodo = str(body.get("periodo") or hoy_local().strftime("%Y-%m")).strip()[:7]
    cargo = Cargo(
        edificio_id=edificio_id,
        unidad_id=u.id,
        periodo=periodo,
        categoria="multa",
        concepto=f"Multa: {motivo}",
        monto=monto,
        saldo=monto,
        vencimiento=hoy_local() + timedelta(days=15),
    )
    db.add(cargo)
    db.flush()
    for res in db.scalars(select(Residente).where(Residente.edificio_id == edificio_id, Residente.unidad_id == u.id, Residente.activo.is_(True))).all():
        db.add(Notificacion(edificio_id=edificio_id, residente_id=res.id, clave=f"multa:{cargo.id}", titulo="Multa aplicada", texto=cargo.concepto, canal="app"))
    auditar(db, user, edificio_id, "finanzas.multa", cargo.id, unidad_id=u.id, monto=float(monto))
    db.commit()
    return {"id": cargo.id, "unidad_id": u.id, "categoria": cargo.categoria, "monto": float(cargo.monto), "concepto": cargo.concepto}


@router.get("/edificios/{edificio_id}/finanzas/fondo-reserva")
def ver_fondo_reserva(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    """Saldo y movimientos del fondo de reserva del edificio (05.04)."""
    from ..operations_models import MovimientoContable
    edificio(db, user, edificio_id)
    movs = db.scalars(select(MovimientoContable).where(
        MovimientoContable.edificio_id == edificio_id,
        MovimientoContable.categoria == "fondo_reserva",
        MovimientoContable.estado != "anulado",
    ).order_by(MovimientoContable.id.desc())).all()
    aportes = sum(float(m.monto) for m in movs if m.tipo == "ingreso")
    egresos = sum(float(m.monto) for m in movs if m.tipo == "egreso")
    return {
        "saldo": round(aportes - egresos, 2),
        "aportes": round(aportes, 2),
        "egresos": round(egresos, 2),
        "movimientos": [{"id": m.id, "fecha": m.fecha.isoformat(), "tipo": m.tipo, "monto": float(m.monto), "concepto": m.concepto} for m in movs],
    }


@router.post("/edificios/{edificio_id}/finanzas/fondo-reserva", status_code=201)
def registrar_fondo_reserva(edificio_id: str, body: dict, user: Admin, db: Session = Depends(get_db)):
    """Registra aporte o uso del fondo de reserva (05.04)."""
    from ..operations_models import MovimientoContable
    edificio(db, user, edificio_id, True)
    tipo = str(body.get("tipo") or "ingreso").strip().lower()
    if tipo not in ("ingreso", "egreso"):
        raise HTTPException(422, "tipo debe ser 'ingreso' o 'egreso'")
    try:
        monto = Decimal(str(body.get("monto", 0)))
    except Exception:
        raise HTTPException(422, "Monto inválido")
    if monto <= 0:
        raise HTTPException(422, "Monto debe ser mayor a 0")
    concepto = str(body.get("concepto") or "Movimiento fondo de reserva").strip()[:180]
    hoy = hoy_local()
    m = MovimientoContable(
        edificio_id=edificio_id,
        fecha=hoy,
        periodo=hoy.strftime("%Y-%m"),
        tipo=tipo,
        categoria="fondo_reserva",
        cuenta_debe="fondo_reserva" if tipo == "ingreso" else "gastos_reserva",
        cuenta_haber="caja_banco" if tipo == "egreso" else "ingresos_reserva",
        concepto=concepto,
        monto=monto,
        estado="pagado",
        creado_por=user.residente_id,
    )
    db.add(m)
    db.flush()
    auditar(db, user, edificio_id, "fondo_reserva.movimiento", m.id, clase_mov=tipo, monto=float(monto))
    db.commit()
    return {"id": m.id, "tipo": m.tipo, "monto": float(m.monto), "concepto": m.concepto}


@router.get("/edificios/{edificio_id}/medidores/comparar")
def comparar_medidores(edificio_id: str, periodo_a: str, periodo_b: str, user: Admin, db: Session = Depends(get_db)):
    """Seguimiento y comparación de consumos de agua y electricidad entre dos períodos (22.17, 22.18)."""
    from ..models import LecturaMedidor
    edificio(db, user, edificio_id)
    lecturas = db.scalars(select(LecturaMedidor).where(
        LecturaMedidor.edificio_id == edificio_id,
        LecturaMedidor.periodo.in_([periodo_a, periodo_b]),
    )).all()
    resumen = {periodo_a: {}, periodo_b: {}}
    for lec in lecturas:
        bucket = resumen.setdefault(lec.periodo, {})
        bucket[lec.servicio] = round(bucket.get(lec.servicio, 0.0) + float(lec.consumo or 0), 3)
    tipos = sorted(set(resumen[periodo_a].keys()) | set(resumen[periodo_b].keys()))
    comparativa = []
    for t in tipos:
        va = resumen[periodo_a].get(t, 0.0)
        vb = resumen[periodo_b].get(t, 0.0)
        comparativa.append({"tipo": t, "periodo_a": va, "periodo_b": vb, "variacion": round(vb - va, 3)})
    return {"periodo_a": periodo_a, "periodo_b": periodo_b, "comparativa": comparativa}


@router.get("/edificios/{edificio_id}/calendario")
def calendario_comunitario(edificio_id: str, user: User, db: Session = Depends(get_db)):
    """Calendario comunitario consolidado: asambleas, mantenimientos y reservas confirmadas (22.24)."""
    from ..models import ReservaEspacio
    from ..operations_models import Asamblea, PlanMantenimiento
    edificio(db, user, edificio_id)
    eventos = []
    for a in db.scalars(select(Asamblea).where(Asamblea.edificio_id == edificio_id)).all():
        eventos.append({"tipo": "asamblea", "id": a.id, "titulo": a.titulo, "fecha": a.fecha.isoformat(), "estado": a.estado})
    for pm in db.scalars(select(PlanMantenimiento).where(PlanMantenimiento.edificio_id == edificio_id, PlanMantenimiento.activo.is_(True))).all():
        eventos.append({"tipo": "mantenimiento", "id": pm.id, "titulo": pm.titulo, "fecha": pm.proxima_fecha.isoformat(), "estado": "programado"})
    for r in db.scalars(select(ReservaEspacio).where(ReservaEspacio.edificio_id == edificio_id, ReservaEspacio.estado == "confirmada")).all():
        eventos.append({"tipo": "reserva", "id": r.id, "titulo": f"Reserva espacio #{r.espacio_id}", "fecha": r.desde.isoformat(), "estado": r.estado})
    eventos.sort(key=lambda x: x["fecha"])
    return {"total": len(eventos), "eventos": eventos}


@router.get("/edificios/{edificio_id}/estructura")
def estructura_edificio(edificio_id: str, user: User, db: Session = Depends(get_db)):
    """Devuelve torres, pisos y unidades agrupadas del edificio (04.02)."""
    edificio(db, user, edificio_id)
    unidades = db.scalars(select(Unidad).where(Unidad.edificio_id == edificio_id).order_by(Unidad.numero)).all()
    torres = sorted({u.torre for u in unidades if u.torre})
    pisos = sorted({u.piso for u in unidades if u.piso is not None})
    return {
        "torres": torres,
        "pisos": pisos,
        "unidades": [{"id": u.id, "numero": u.numero, "torre": u.torre or "", "piso": u.piso} for u in unidades],
    }


@router.patch("/edificios/{edificio_id}/unidades/{unidad_id}/ubicacion")
def actualizar_ubicacion_unidad(edificio_id: str, unidad_id: int, body: dict, user: Admin, db: Session = Depends(get_db)):
    """Asigna torre y piso explícitos a una unidad (04.02)."""
    edificio(db, user, edificio_id, True)
    u = recurso(db, Unidad, edificio_id, unidad_id)
    if "torre" in body:
        u.torre = str(body["torre"] or "").strip()[:40]
    if "piso" in body:
        u.piso = int(body["piso"]) if body["piso"] is not None else None
    auditar(db, user, edificio_id, "unidad.ubicacion", u.id, torre=u.torre, piso=u.piso)
    db.commit()
    return {"id": u.id, "numero": u.numero, "torre": u.torre, "piso": u.piso}


@router.get("/edificios/{edificio_id}/accesos/anomalias")
def detectar_anomalias_acceso(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    """Detecta intentos repetidos de acceso rechazado (22.11) y credenciales/tags duplicados (22.12)."""
    from collections import Counter
    from ..models import AccesoLog, Tag, Vehiculo
    edificio(db, user, edificio_id)
    rechazos = db.scalars(select(AccesoLog).where(
        AccesoLog.edificio_id == edificio_id, AccesoLog.permitido.is_(False),
    ).order_by(AccesoLog.id.desc()).limit(500)).all()
    conteo_rechazos = Counter((a.token, a.punto) for a in rechazos)
    intentos_anomalos = [
        {"token": tok, "punto": pto, "rechazos": n}
        for (tok, pto), n in conteo_rechazos.items()
        if n >= 3
    ]

    tags = db.scalars(select(Tag).where(Tag.edificio_id == edificio_id, Tag.estado == "activo")).all()
    conteo_tags = Counter((t.uid or "").upper() for t in tags if t.uid)
    vehiculos = db.scalars(select(Vehiculo).where(Vehiculo.edificio_id == edificio_id, Vehiculo.activo.is_(True))).all()
    conteo_patentes = Counter((v.patente or "").upper() for v in vehiculos if v.patente)
    credenciales_duplicadas = [
        {"tipo": "tag", "valor": k, "cantidad": v} for k, v in conteo_tags.items() if v > 1
    ] + [
        {"tipo": "patente", "valor": k, "cantidad": v} for k, v in conteo_patentes.items() if v > 1
    ]
    return {
        "intentos_anomalos": intentos_anomalos,
        "credenciales_duplicadas": credenciales_duplicadas,
    }



@router.get("/edificios/{edificio_id}/accesos/forense")
def historial_forense_accesos(edificio_id: str, user: Admin, token: str | None = None,
                              permitido: bool | None = None, limit: int = 100, offset: int = 0,
                              db: Session = Depends(get_db)):
    """Historial forense filtrable y paginado de accesos (22.15)."""
    from ..models import AccesoLog
    edificio(db, user, edificio_id)
    q = select(AccesoLog).where(AccesoLog.edificio_id == edificio_id)
    if token:
        q = q.where(AccesoLog.token == token.strip())
    if permitido is not None:
        q = q.where(AccesoLog.permitido.is_(permitido))
    rows = db.scalars(q.order_by(AccesoLog.id.desc()).offset(max(0, offset)).limit(min(500, max(1, limit)))).all()
    return [{"id": a.id, "token": a.token, "punto": a.punto, "fuente": a.fuente,
             "permitido": a.permitido, "motivo": a.motivo, "creado": a.creado.isoformat()} for a in rows]


@router.get("/edificios/{edificio_id}/eventos/resumen")
def resumen_eventos(edificio_id: str, user: Admin, db: Session = Depends(get_db)):
    """Análisis agrupado de eventos del edificio por tipo (22.14)."""
    from collections import Counter
    edificio(db, user, edificio_id)
    evs = db.scalars(select(Evento).where(Evento.edificio_id == edificio_id).order_by(Evento.id.desc()).limit(1000)).all()
    conteo = Counter(e.tipo for e in evs)
    return {"total": len(evs), "por_tipo": [{"tipo": k, "cantidad": v} for k, v in conteo.most_common()]}
