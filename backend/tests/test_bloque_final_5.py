"""Pruebas de los 5 bloques finales de software local:
observabilidad JSON + ErrorLog + paginación, organizaciones SaaS + onboarding,
escalamiento de alertas + KPIs de proveedores, cotizaciones + reglamentos internos,
y pruebas dedicadas de webhooks, outbox/correo, caché y worker.
"""
from datetime import timedelta
import json

from app.config import hoy_local, settings
from app.models import Evento, Residente, Rol
from app.operations_models import ErrorLog, Incidencia
from app.security import hash_password
from app.services import automation
from app.services.cache import cache_get, cache_invalidate, cache_set
from app.services.logging_json import emitir_log_json
from app.services.notifications import notificar
from conftest import login

BASE = "/edificios/edificio_a"


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def test_observabilidad_errores_y_paginacion(client, seed, db):
    uid_101 = seed["edificio_a", "101"].id
    db.add(Residente(
        edificio_id="edificio_a", unidad_id=uid_101, nombre="Root",
        rut="22.222.222-2", email="root@x.cl", telefono="56900001111",
        rol=Rol.superadmin, password_hash=hash_password("secreto123"),
    ))
    db.add(ErrorLog(ruta="/falla-demo", metodo="GET", edificio_id="edificio_a", mensaje="RuntimeError: demo", detalle=""))
    db.commit()

    superadmin = login(client, "edificio_a", "root@x.cl")
    admin = login(client, "edificio_a", "ana@x.cl")

    # 19.15 Log estructurado JSON
    linea = emitir_log_json("info", "test.evento", edificio_id="edificio_a")
    parsed = json.loads(linea)
    assert parsed["evento"] == "test.evento"

    # 24.10 Registro centralizado de errores (superadmin)
    errs = ok(client.get("/saas/errores?limit=10&offset=0", headers=superadmin))
    assert any(e["ruta"] == "/falla-demo" for e in errs)
    assert client.get("/saas/errores", headers=admin).status_code == 403

    # 19.21 Paginación limit/offset
    for i in range(3):
        ok(client.post(BASE + "/porteria/ingresos", headers=admin, json={"tipo": "delivery", "nombre": f"Reparto {i}"}), 201)
    p1 = ok(client.get(BASE + "/porteria/ingresos?limit=2&offset=0", headers=admin))
    p2 = ok(client.get(BASE + "/porteria/ingresos?limit=2&offset=2", headers=admin))
    assert len(p1) == 2 and len(p2) >= 1 and p1[0]["id"] != p2[0]["id"]


def test_organizaciones_saas_y_onboarding(client, seed, db):
    uid_101 = seed["edificio_a", "101"].id
    db.add(Residente(
        edificio_id="edificio_a", unidad_id=uid_101, nombre="Root",
        rut="22.222.222-2", email="root@x.cl", telefono="56900001111",
        rol=Rol.superadmin, password_hash=hash_password("secreto123"),
    ))
    db.commit()
    superadmin = login(client, "edificio_a", "root@x.cl")

    # 24.03 Organizaciones y membresías
    org = ok(client.post("/saas/organizaciones", headers=superadmin, json={"nombre": "Inmobiliaria Sur", "slug": "inmo-sur"}), 201)
    m = ok(client.post(f"/saas/organizaciones/{org['id']}/miembros", headers=superadmin, json={"email": "gestor@sur.cl", "rol": "gestor"}), 201)
    assert m["rol"] == "gestor"
    orgs = ok(client.get("/saas/organizaciones", headers=superadmin))
    assert any(o["slug"] == "inmo-sur" and o["miembros"] == 1 for o in orgs)

    # 24.05 Onboarding atómico
    onb = ok(client.post("/saas/onboarding", headers=superadmin, json={
        "edificio_id": "torre_onb",
        "nombre": "Torre Onboarding",
        "admin_email": "admin@onb.cl",
        "admin_nombre": "Admin Onb",
        "unidades": ["201", "202", "203"],
    }), 201)
    assert onb["unidades_creadas"] == 3


def test_escalamiento_kpis_cotizaciones_reglamentos_y_componentes_internos(client, seed, db, monkeypatch):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")

    # 16.05 Cotizaciones y comparación
    p1 = ok(client.post(BASE + "/proveedores", headers=admin, json={"nombre": "Prov Uno", "rut": "76123456-0", "servicio": "gasfiteria"}), 201)
    p2 = ok(client.post(BASE + "/proveedores", headers=admin, json={"nombre": "Prov Dos", "rut": "11111111-1", "servicio": "gasfiteria"}), 201)
    inc = ok(client.post(BASE + "/incidencias", headers=admin, json={"titulo": "Bomba agua", "descripcion": "Fuga en bomba", "prioridad": "alta"}), 201)

    c1 = ok(client.post(BASE + "/cotizaciones", headers=admin, json={"incidencia_id": inc["id"], "proveedor_id": p1["id"], "monto": 90000, "plazo_dias": 2}), 201)
    c2 = ok(client.post(BASE + "/cotizaciones", headers=admin, json={"incidencia_id": inc["id"], "proveedor_id": p2["id"], "monto": 120000, "plazo_dias": 3}), 201)
    lista_c = ok(client.get(f"{BASE}/cotizaciones?incidencia_id={inc['id']}", headers=admin))
    assert lista_c[0]["monto"] <= lista_c[1]["monto"]
    sel = ok(client.post(f"{BASE}/cotizaciones/{c1['id']}/seleccionar", headers=admin))
    assert sel["estado"] == "seleccionada"
    lista_c2 = ok(client.get(f"{BASE}/cotizaciones?incidencia_id={inc['id']}", headers=admin))
    assert any(x["id"] == c2["id"] and x["estado"] == "descartada" for x in lista_c2)

    # 22.08 KPIs de proveedores
    ot = ok(client.post(f"{BASE}/incidencias/{inc['id']}/orden", headers=admin, json={
        "proveedor_id": p1["id"], "detalle": "Cambio sello bomba", "presupuesto": 90000,
    }), 201)
    ok(client.post(f"{BASE}/ordenes-trabajo/{ot['id']}/estado", headers=admin, json={"estado": "aprobada"}))
    ok(client.post(f"{BASE}/ordenes-trabajo/{ot['id']}/estado", headers=admin, json={"estado": "en_progreso"}))
    ok(client.post(f"{BASE}/ordenes-trabajo/{ot['id']}/estado", headers=admin, json={"estado": "terminada", "evaluacion": 5}))
    kpis = ok(client.get(BASE + "/proveedores/kpis", headers=admin))
    k_p1 = next(k for k in kpis if k["proveedor_id"] == p1["id"])
    assert k_p1["ordenes_terminadas"] == 1 and k_p1["evaluacion_promedio"] == 5.0

    # 22.29 Escalamiento de alertas en automation.py
    inc_obj = db.get(Incidencia, inc["id"])
    inc_obj.vencimiento = hoy_local() - timedelta(days=2)
    inc_obj.estado = "asignada"
    db.commit()
    automation.ejecutar(db, "edificio_a")
    db.commit()
    db.refresh(inc_obj)
    assert inc_obj.prioridad == "critica"
    assert db.query(Evento).filter(Evento.edificio_id == "edificio_a", Evento.tipo == "incidencia.escalada").count() >= 1

    # 04.14 Reglamentos internos
    reg = ok(client.post(BASE + "/reglamentos", headers=admin, json={
        "titulo": "Reglamento de Copropiedad", "version": "2.0", "contenido": "Horario de mudanzas de 09:00 a 18:00.",
    }), 201)
    ok(client.patch(f"{BASE}/reglamentos/{reg['id']}", headers=admin, json={"version": "2.1"}))
    assert any(r["version"] == "2.1" for r in ok(client.get(BASE + "/reglamentos", headers=residente)))

    # 20.13 - 20.17 Pruebas dedicadas de caché, notificaciones/outbox y webhook verificación
    cache_set("k:test", {"v": 1}, ttl_s=10)
    assert cache_get("k:test") == {"v": 1}
    cache_invalidate("k:")
    assert cache_get("k:test") is None

    res_obj = db.query(Residente).filter(Residente.edificio_id == "edificio_a").first()
    env = notificar(db, "edificio_a", [res_obj], "Prueba", "Cuerpo", "clave-test-notif", externos=False)
    assert env == 1

    monkeypatch.setattr(settings, "whatsapp_verify_token", "tok-verif-123")
    wh = client.get("/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=tok-verif-123&hub.challenge=998877")
    assert wh.status_code == 200 and wh.text == "998877"
