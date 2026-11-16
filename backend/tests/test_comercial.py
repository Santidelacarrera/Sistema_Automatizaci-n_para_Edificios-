from datetime import timedelta
import os

import pytest
from sqlalchemy import select

from app.commercial_models import CobroSaaS, Suscripcion
from app.config import hoy_local
from app.models import Cargo, Pago, Residente, Rol, Unidad, Vehiculo
from app.security import create_token
from conftest import login

BASE = "/edificios/edificio_a"


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


@pytest.fixture
def global_user(seed, db):
    u = seed["edificio_a", "101"]
    r = Residente(edificio_id=u.edificio_id, unidad_id=u.id, nombre="Operador SaaS", rut="11111111-1", rol=Rol.superadmin)
    db.add(r)
    db.commit()
    return {"Authorization": "Bearer " + create_token(r.id, r.edificio_id, r.rol)}


def contrato(client, h, **cambios):
    c = ok(client.post("/saas/clientes", headers=h, json={"nombre": "Cliente prueba", "rut": "12345678-5", "contacto": "cliente@example.cl"}), 201)
    p = ok(client.post("/saas/planes", headers=h, json={"nombre": "Plan prueba", "precio_mensual": "10000.00",
        "max_unidades": 4, "max_residentes": 3, "max_dispositivos": 1, **cambios}), 201)
    body = {"cliente_id": c["id"], "plan_id": p["id"], "estado": "activa", "version": 0,
            "vigente_hasta": str(hoy_local() + timedelta(days=40)), "motivo": "Contrato de prueba autorizado"}
    ok(client.put("/saas/suscripciones/edificio_a", headers=h, json=body))
    return p, body


def test_contrato_limites_y_aislamiento(client, seed, db, global_user):
    p, body = contrato(client, global_user)
    admin = login(client, "edificio_a", "ana@x.cl")
    otro = login(client, "edificio_b", "carla@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    for h in (admin, otro, residente):
        for ruta in ("clientes", "planes", "suscripciones", "metricas", "cobros", "soporte"):
            assert client.get("/saas/" + ruta, headers=h).status_code == 403
    assert client.get(BASE + "/suscripcion", headers=otro).status_code == 403
    assert client.get(BASE + "/suscripcion", headers=residente).status_code == 403
    ok(client.post(BASE + "/unidades", headers=admin, json={"numero": "104", "coeficiente": .1, "codigo_cobro": "NUEVA104"}), 201)
    assert client.post(BASE + "/unidades", headers=admin, json={"numero": "105", "coeficiente": .1, "codigo_cobro": "NUEVA105"}).status_code == 409
    assert client.post(BASE + "/residentes", headers=admin, json={"nombre": "Otro", "rut": "11111111-1", "unidad_id": seed["edificio_a", "101"].id, "rol": "residente"}).status_code == 409
    ok(client.post(BASE + "/dispositivos", headers=admin, json={"nombre": "Simulador", "punto": "laboratorio"}), 201)
    assert client.post(BASE + "/dispositivos", headers=admin, json={"nombre": "Segundo", "punto": "laboratorio"}).status_code == 409
    assert client.put("/saas/suscripciones/edificio_a", headers=global_user, json=body).status_code == 409
    small = ok(client.post("/saas/planes", headers=global_user, json={"nombre": "Insuficiente", "precio_mensual": 0,
        "max_unidades": 1, "max_residentes": 1, "max_dispositivos": 0}), 201)
    assert client.put("/saas/suscripciones/edificio_a", headers=global_user, json={**body, "plan_id": small["id"], "version": 1}).status_code == 409
    assert ok(client.get(BASE + "/suscripcion", headers=admin))["uso"] == {"unidades": 4, "residentes": 3, "dispositivos": 1}


def test_cobro_idempotente_y_separado_de_finanzas(client, seed, db, global_user):
    p, body = contrato(client, global_user)
    data = {"periodo": hoy_local().strftime("%Y-%m"), "vencimiento": str(hoy_local() + timedelta(days=20))}
    url = "/saas/suscripciones/edificio_a/cobros"
    c = ok(client.post(url, headers=global_user, json=data), 201)
    assert ok(client.post(url, headers=global_user, json=data), 201)["id"] == c["id"]
    assert db.query(CobroSaaS).count() == 1 and db.query(Pago).count() == 0 and db.query(Cargo).count() == 0
    assert client.post(url, headers=global_user, json={**data, "vencimiento": str(hoy_local())}).status_code == 409
    assert client.post(url, headers=global_user, json={**data, "periodo": "2000-01"}).status_code == 422
    resolved = {"estado": "pagado", "referencia": "comprobante-verificado", "motivo": "Verificación manual del abono"}
    url = f"/saas/cobros/{c['id']}/resolver"
    ok(client.post(url, headers=global_user, json=resolved))
    ok(client.post(url, headers=global_user, json=resolved))
    assert client.post(url, headers=global_user, json={**resolved, "estado": "anulado"}).status_code == 409
    assert float(ok(client.get("/saas/metricas", headers=global_user))["ingreso_mensual_contratado"]) == 10000


def test_vencimiento_suspension_y_plan_retirado(client, seed, db, global_user):
    p, body = contrato(client, global_user)
    admin = login(client, "edificio_a", "ana@x.cl")
    s = db.get(Suscripcion, "edificio_a")
    s.vigente_hasta = hoy_local() - timedelta(days=1)
    db.commit()
    nueva = {"numero": "104", "coeficiente": .1, "codigo_cobro": "NUEVA104"}
    assert client.post(BASE + "/unidades", headers=admin, json=nueva).status_code == 409
    assert client.get(BASE + "/panel", headers=admin).status_code == 200
    assert client.get(BASE + "/suscripcion", headers=admin).json()["vigente"] is False
    ok(client.patch(f"/saas/planes/{p['id']}", headers=global_user, json={"activo": False}))
    ok(client.put("/saas/suscripciones/edificio_a", headers=global_user, json={**body, "version": 1, "estado": "suspendida"}))
    assert client.post(BASE + "/unidades", headers=admin, json=nueva).status_code == 409
    # La clave del controlador sigue autenticando: la suscripción no controla seguridad física.
    db.add(Vehiculo(edificio_id="edificio_a", unidad_id=seed["edificio_a", "101"].id, patente="BBCD12"))
    db.commit()
    response = client.post("/api/v1/edificio_a/validar-acceso", headers={"X-Device-Key": "keyA"},
        json={"edificio_id": "edificio_a", "token_acceso": "BBCD12", "punto": "vehicular", "tipo": "patente", "confianza": .99})
    assert response.status_code == 200
    assert response.json()["abrir"]


def test_soporte_conversacion_y_privacidad(client, seed, db, global_user):
    admin = login(client, "edificio_a", "ana@x.cl")
    otro = login(client, "edificio_b", "carla@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    t = ok(client.post(BASE + "/soporte", headers=admin, json={"titulo": "Necesito ampliar el plan", "texto": "Agregaremos otra torre"}), 201)
    path = BASE + f"/soporte/{t['id']}"
    assert client.get(path, headers=otro).status_code == 403
    assert client.get(f"/edificios/edificio_b/soporte/{t['id']}", headers=otro).status_code == 404
    assert client.get(path, headers=residente).status_code == 403
    ok(client.post(path + "/mensajes", headers=global_user, json={"texto": "Recibimos la solicitud", "estado": "en_progreso"}), 201)
    detalle = ok(client.get(path, headers=admin))
    assert detalle["estado"] == "en_progreso" and len(detalle["mensajes"]) == 2
    assert client.post(path + "/mensajes", headers=admin, json={"texto": "Cambio de estado", "estado": "en_progreso"}).status_code == 403
    assert any(n["titulo"] == "Respuesta de soporte" for n in ok(client.get(BASE + "/notificaciones", headers=admin)))
    ok(client.post(path + "/mensajes", headers=admin, json={"texto": "Gracias, resuelto", "estado": "resuelto"}), 201)
    assert ok(client.get("/saas/metricas", headers=global_user))["tickets_abiertos"] == 0


def test_validacion_plan_y_cliente(client, seed, db, global_user):
    assert client.post("/saas/clientes", headers=global_user, json={"nombre": "Inválido", "rut": "12345678-0", "contacto": "mal"}).status_code == 422
    assert client.post("/saas/planes", headers=global_user, json={"nombre": "Inválido", "precio_mensual": "NaN", "max_unidades": 0, "max_residentes": 0, "max_dispositivos": 0}).status_code == 422
    contrato(client, global_user)
    assert client.post("/saas/clientes", headers=global_user, json={"nombre": "Duplicado", "rut": "12.345.678-5", "contacto": "cliente@example.cl"}).status_code == 409
    assert db.scalar(select(CobroSaaS.id)) is None


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"), reason="requiere PostgreSQL real")
def test_cupo_unidades_no_se_excede_con_altas_concurrentes(client, seed, db, global_user):
    from test_concurrencia_financiera_pg import paralelo
    from app.routers.edificio import crear_unidad
    from app.schemas import UnidadIn
    from app.security import Principal
    contrato(client, global_user)
    rid = db.scalar(select(Residente.id).where(Residente.email == "ana@x.cl"))
    principal = Principal(rid, "edificio_a", Rol.admin)
    results = paralelo(lambda session, i: crear_unidad("edificio_a", UnidadIn(
        numero=f"NEW{i}", coeficiente=.01, codigo_cobro=f"NEW{i}"), principal, session))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert results.count(409) == 5
    assert db.query(Unidad).filter_by(edificio_id="edificio_a").count() == 4
