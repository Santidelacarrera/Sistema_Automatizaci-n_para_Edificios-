"""Pruebas de cierre para los criterios parciales de software:
eliminación/desactivación de edificios, historial por unidad, multas,
fondo de reserva, resumen financiero PDF, comparación de medidores,
estadísticas de espacios y calendario comunitario.
"""
from datetime import datetime, timedelta

from app.config import hoy_local
from app.models import EspacioComun, LecturaMedidor, ReservaEspacio, Residente, Rol
from app.security import hash_password
from conftest import login

BASE = "/edificios/edificio_a"


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def test_edificio_eliminar_o_desactivar_e_historial_unidad(client, seed, db):
    uid_101 = seed["edificio_a", "101"].id
    uid_102 = seed["edificio_a", "102"].id
    db.add(Residente(
        edificio_id="edificio_a", unidad_id=uid_101, nombre="Root",
        rut="22.222.222-2", email="root@x.cl", telefono="56900001111",
        rol=Rol.superadmin, password_hash=hash_password("secreto123"),
    ))
    db.commit()
    superadmin = login(client, "edificio_a", "root@x.cl")
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")

    # 04.01 Crear y eliminar edificio vacío, y desactivar edificio con unidades
    ok(client.post("/edificios", headers=superadmin, json={"id": "edif_vacio", "nombre": "Torre Vacía"}), 201)
    d1 = ok(client.delete("/edificios/edif_vacio", headers=superadmin))
    assert d1["eliminado"] is True

    d2 = ok(client.delete("/edificios/edificio_b", headers=superadmin))
    assert d2["eliminado"] is False
    assert d2["activo"] is False

    # 04.13 Historial consolidado del departamento (con aislamiento para residentes)
    assert client.get(f"{BASE}/unidades/{uid_101}/historial", headers=residente).status_code == 403
    hist = ok(client.get(f"{BASE}/unidades/{uid_102}/historial", headers=admin))
    assert hist["unidad"]["numero"] == "102"
    assert all(k in hist for k in ("cargos", "pagos", "incidencias", "reservas", "visitas", "encomiendas"))


def test_multas_fondo_reserva_pdf_medidores_estadisticas_y_calendario(client, seed, db):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    uid = seed["edificio_a", "102"].id
    periodo = hoy_local().strftime("%Y-%m")

    # 05.06 Multa auditable
    multa = ok(client.post(BASE + "/finanzas/multas", headers=admin, json={
        "unidad_id": uid, "monto": 35000, "motivo": "Ruidos molestos", "periodo": periodo,
    }), 201)
    assert multa["categoria"] == "multa"
    assert multa["monto"] == 35000.0

    # 05.04 Fondo de reserva
    ok(client.post(BASE + "/finanzas/fondo-reserva", headers=admin, json={
        "tipo": "ingreso", "monto": 100000, "concepto": "Aporte mensual",
    }), 201)
    ok(client.post(BASE + "/finanzas/fondo-reserva", headers=admin, json={
        "tipo": "egreso", "monto": 25000, "concepto": "Reparación bomba",
    }), 201)
    fr = ok(client.get(BASE + "/finanzas/fondo-reserva", headers=admin))
    assert fr["saldo"] == 75000.0

    # 05.40 Resumen financiero PDF
    r_pdf = client.get(BASE + "/finanzas/resumen.pdf", headers=admin)
    assert r_pdf.status_code == 200
    assert r_pdf.content.startswith(b"%PDF-")

    # 22.17 y 22.18 Comparación de lecturas de agua y electricidad entre períodos
    db.add(LecturaMedidor(edificio_id="edificio_a", unidad_id=uid, servicio="agua", periodo="2026-09", consumo=10))
    db.add(LecturaMedidor(edificio_id="edificio_a", unidad_id=uid, servicio="agua", periodo="2026-10", consumo=14))
    db.add(LecturaMedidor(edificio_id="edificio_a", unidad_id=uid, servicio="electricidad", periodo="2026-09", consumo=100))
    db.add(LecturaMedidor(edificio_id="edificio_a", unidad_id=uid, servicio="electricidad", periodo="2026-10", consumo=90))
    esp = EspacioComun(edificio_id="edificio_a", nombre="Sala Eventos", accion="sala", tarifa=20000, garantia=30000, aforo=30)
    db.add(esp)
    db.flush()
    db.add(ReservaEspacio(
        edificio_id="edificio_a", espacio_id=esp.id, unidad_id=uid,
        desde=datetime.now() + timedelta(days=3), hasta=datetime.now() + timedelta(days=3, hours=2),
        estado="confirmada",
    ))
    db.commit()

    comp = ok(client.get(BASE + "/medidores/comparar?periodo_a=2026-09&periodo_b=2026-10", headers=admin))
    agua = next(c for c in comp["comparativa"] if c["tipo"] == "agua")
    assert agua["variacion"] == 4.0

    # 22.23 Estadísticas de espacios comunes
    stats = ok(client.get(BASE + "/espacios-comunes/estadisticas", headers=admin))
    sala = next(s for s in stats if s["nombre"] == "Sala Eventos")
    assert sala["confirmadas"] >= 1
    assert sala["recaudacion_estimada"] >= 20000.0

    # 22.24 Calendario comunitario consolidado
    cal = ok(client.get(BASE + "/calendario", headers=residente))
    assert cal["total"] >= 1
