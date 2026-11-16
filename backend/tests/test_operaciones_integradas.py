from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import ahora_local, hoy_local
from app.models import Cargo, Edificio, EspacioComun, Pago, Residente, Rol, Unidad
from app.operations_models import Incidencia, Notificacion, ParticipanteAsamblea, PlanMantenimiento
from app.security import create_token, verify_password
from app.services import notifications
from conftest import login

BASE = "/edificios/edificio_a"


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def usuarios(client, seed, db):
    a = login(client, "edificio_a", "ana@x.cl")
    r = login(client, "edificio_a", "beto@x.cl")
    b = login(client, "edificio_b", "carla@x.cl")
    return a, r, b


def test_incidencia_orden_cierre_notificaciones_y_aislamiento(client, seed, db, usuarios):
    admin, residente, otro = usuarios
    uid = seed["edificio_a", "102"].id
    inc = ok(client.post(BASE + "/incidencias", headers=residente, json={
        "titulo": "Filtración de agua", "descripcion": "Agua en el techo", "prioridad": "critica"}), 201)
    assert inc["unidad_id"] == uid
    iid = inc["id"]
    assert client.get(BASE + f"/incidencias/{iid}", headers=otro).status_code == 403
    assert client.patch(BASE + f"/incidencias/{iid}", headers=residente,
                         json={"version": 1, "estado": "resuelta"}).status_code == 403
    proveedor = ok(client.post(BASE + "/proveedores", headers=admin,
        json={"nombre": "Gasfitería", "rut": "12.345.678-5", "servicio": "Reparaciones"}), 201)
    orden = ok(client.post(BASE + f"/incidencias/{iid}/orden", headers=admin,
        json={"proveedor_id": proveedor["id"], "detalle": "Reparar cañería", "presupuesto": "30000.50"}), 201)
    assert client.patch(BASE + f"/incidencias/{iid}", headers=admin,
                         json={"version": 1, "estado": "resuelta"}).status_code == 409
    for estado in ("aprobada", "en_progreso", "terminada"):
        ok(client.post(BASE + f"/ordenes-trabajo/{orden['id']}/estado", headers=admin, json={"estado": estado}))
    ok(client.post(BASE + f"/incidencias/{iid}/comentarios", headers=residente, json={"texto": "Ya no hay fuga"}), 201)
    ok(client.patch(BASE + f"/incidencias/{iid}", headers=admin, json={"version": 1, "estado": "resuelta"}))
    assert client.patch(BASE + f"/incidencias/{iid}", headers=admin,
                        json={"version": 1, "estado": "cerrada"}).status_code == 409
    ok(client.patch(BASE + f"/incidencias/{iid}", headers=admin, json={"version": 2, "estado": "cerrada"}))
    assert client.post(BASE + f"/incidencias/{iid}/comentarios", headers=residente, json={"texto": "tarde"}).status_code == 409
    ns = ok(client.get(BASE + "/notificaciones", headers=residente))
    assert len(ns) == 2
    ok(client.post(BASE + f"/notificaciones/{ns[0]['id']}/leer", headers=residente))
    assert client.post(BASE + f"/notificaciones/{ns[0]['id']}/leer", headers=admin).status_code == 404
    detalle = ok(client.get(BASE + f"/incidencias/{iid}", headers=residente))
    assert detalle["orden"] is None and detalle["comentarios"][0]["texto"] == "Ya no hay fuga"


def test_incidencia_recurso_de_otro_edificio_y_residente(client, seed, db, usuarios):
    admin, residente, otro = usuarios
    rid = db.scalar(select(Residente.id).where(Residente.email == "carla@x.cl"))
    i = ok(client.post(BASE + "/incidencias", headers=admin,
                        json={"titulo": "Privada", "descripcion": "Revisión privada"}), 201)
    assert client.get(BASE + f"/incidencias/{i['id']}", headers=residente).status_code == 404
    assert client.patch(BASE + f"/incidencias/{i['id']}", headers=admin,
                         json={"version": 1, "responsable_id": rid}).status_code == 404
    assert client.post(BASE + "/incidencias", headers=residente, json={"titulo": "Otra unidad", "descripcion": "xxy",
                        "unidad_id": seed["edificio_b", "101"].id}).status_code == 403


def test_asamblea_voto_unico_padron_congelado_y_resultados(client, seed, db, usuarios):
    admin, residente, otro = usuarios
    rid = db.scalar(select(Residente.id).where(Residente.email == "beto@x.cl"))
    a = ok(client.post(BASE + "/asambleas", headers=admin, json={"titulo": "Presupuesto",
        "agenda": "Aprobación propuesta", "fecha": ahora_local().isoformat(), "opciones": ["Sí", "No"]}), 201)
    path = BASE + f"/asambleas/{a['id']}"
    assert ok(client.get(BASE + "/asambleas", headers=residente)) == []
    ok(client.post(path + "/participantes", headers=admin, json={"residente_id": rid}), 201)
    assert client.post(path + "/participantes", headers=admin, json={"residente_id": rid}).status_code == 409
    ok(client.post(path + "/abrir", headers=admin))
    assert client.post(path + "/participantes", headers=admin, json={"residente_id": rid}).status_code == 409
    assert client.post(path + "/votos", headers=residente, json={"opcion": 0}).status_code == 409
    ok(client.post(path + "/asistencia", headers=residente))
    voto = ok(client.post(path + "/votos", headers=residente, json={"opcion": 0}), 201)
    assert len(voto["recibo"]) == 64
    assert client.post(path + "/votos", headers=residente, json={"opcion": 1}).status_code == 409
    assert client.post(path + "/votos", headers=otro, json={"opcion": 1}).status_code == 403
    assert ok(client.get(path, headers=admin))["resultados"] is None
    ok(client.post(path + "/cerrar", headers=admin, json={"acta": "Se aprueba la propuesta presentada."}))
    detalle = ok(client.get(path, headers=residente))
    assert detalle["resultados"][0] == {"opcion": "Sí", "votos": 1, "coeficiente": 0.3}
    assert detalle["mi_recibo"] == voto["recibo"]
    assert not detalle["validez_juridica_verificada"] and detalle["padron"] == []
    assert db.query(ParticipanteAsamblea).count() == 1


def test_automatizacion_idempotente_y_desactivable(client, seed, db, usuarios):
    admin, _, _ = usuarios
    rid = db.scalar(select(Residente.id).where(Residente.email == "ana@x.cl"))
    p = ok(client.post(BASE + "/mantenimientos", headers=admin, json={"titulo": "Revisar ascensor",
        "responsable_id": rid, "intervalo_dias": 30, "proxima_fecha": str(hoy_local() - timedelta(days=3))}), 201)
    result = ok(client.post(BASE + "/automatizaciones/ejecutar", headers=admin))
    assert result["creadas"] == 1
    assert ok(client.post(BASE + "/automatizaciones/ejecutar", headers=admin))["creadas"] == 0
    assert db.query(Incidencia).count() == 1
    db.expire_all()
    assert db.get(PlanMantenimiento, p["id"]).proxima_fecha > hoy_local()
    ok(client.put(BASE + "/automatizaciones", headers=admin, json={"activa": False}))
    assert ok(client.post(BASE + "/automatizaciones/ejecutar", headers=admin))["desactivada"]


def test_notificacion_rollback_no_envia_y_reintentos(db, seed, monkeypatch):
    r = db.scalar(select(Residente).where(Residente.email == "ana@x.cl"))
    calls = []
    monkeypatch.setattr(notifications.email, "configurado", lambda: True)
    monkeypatch.setattr(notifications.email, "enviar", lambda *a: calls.append(a))
    notifications.notificar(db, r.edificio_id, [r], "Aviso", "Prueba")
    assert not calls
    db.rollback()
    assert db.query(Notificacion).count() == 0
    notifications.notificar(db, r.edificio_id, [r], "Aviso", "Prueba", "unico")
    db.commit()
    assert notifications.procesar(db)["fallidos"] == 1
    db.commit()
    n = db.scalar(select(Notificacion).where(Notificacion.canal == "email"))
    assert n.estado == "reintento" and n.intentos == 1
    assert notifications.procesar(db)["fallidos"] == 0


def test_pago_anticipado_aplicacion_exacta_y_reversa(client, seed, db, usuarios):
    admin, _, _ = usuarios
    uid = seed["edificio_a", "101"].id
    pago = {"unidad_id": uid, "monto": 150.50, "ref_externa": "anticipo-1"}
    assert ok(client.post(BASE + "/pagos", headers=admin, json=pago))["excedente"] == 150.5
    ok(client.post(BASE + "/gastos-comunes/generar", headers=admin, json={"periodo": "2027-01",
        "vencimiento": "2027-01-15", "gastos": [{"concepto": "Luz", "monto": 200}]}))
    db.expire_all()
    assert db.get(Unidad, uid).saldo_favor == Decimal("50.50")
    assert db.scalar(select(Cargo.saldo).where(Cargo.unidad_id == uid)) == 0
    ps = ok(client.get(BASE + "/pagos", headers=admin))
    pid = ps[0]["id"]
    ok(client.post(BASE + f"/pagos/{pid}/revertir", headers=admin, json={"motivo": "Transferencia reversada por banco"}))
    assert client.post(BASE + f"/pagos/{pid}/revertir", headers=admin,
                        json={"motivo": "Transferencia reversada por banco"}).status_code == 409
    db.expire_all()
    assert db.get(Unidad, uid).saldo_favor == 0
    assert db.scalar(select(Cargo.saldo).where(Cargo.unidad_id == uid)) == 100
    assert ok(client.get(BASE + "/dashboard", headers=admin))["ingresos_mes"] == 0


def test_cancelacion_anula_solo_su_cargo(client, seed, db, usuarios):
    admin, _, _ = usuarios
    esp = EspacioComun(edificio_id="edificio_a", nombre="Sala", accion="reservar_sala", tarifa=100)
    db.add(esp)
    db.commit()
    ids = []
    for horas in (24, 48):
        desde = ahora_local() + timedelta(hours=horas)
        r = ok(client.post(BASE + "/reservas-espacio", headers=admin, json={"unidad_id": seed["edificio_a", "101"].id,
            "espacio_id": esp.id, "desde": desde.isoformat(), "hasta": (desde + timedelta(hours=1)).isoformat()}), 201)
        ids.append(r["id"])
    ok(client.post(BASE + f"/reservas-espacio/{ids[1]}/cancelar", headers=admin))
    cargos = db.scalars(select(Cargo).order_by(Cargo.id)).all()
    assert [float(c.saldo) for c in cargos] == [100, 0]


def test_hash_malformado_no_falla_y_logout_revoca(client, seed, usuarios):
    assert not verify_password("clave", "zz$" + "a" * 128)
    admin, _, _ = usuarios
    ok(client.post("/auth/logout", headers=admin))
    assert client.get(BASE + "/panel", headers=admin).status_code == 401


def test_conserje_no_consulta_finanzas(client, seed, db):
    r = db.scalar(select(Residente).where(Residente.email == "beto@x.cl"))
    r.rol = Rol.conserje
    db.commit()
    headers = login(client, "edificio_a", r.email)
    for ruta in ("/mi-depto", "/cobranza", "/pagos", "/dashboard", "/unidades/1/deuda"):
        assert client.get(BASE + ruta, headers=headers).status_code == 403
    panel = ok(client.get(BASE + "/panel", headers=headers))
    assert all(u["deuda"] is None and u["vencida"] is None for u in panel["unidades"])


@pytest.mark.parametrize("ruta", ["/incidencias", "/proveedores", "/mantenimientos", "/asambleas", "/notificaciones",
                                  "/documentos", "/automatizaciones", "/pagos", "/dashboard", "/auditoria"])
def test_nuevas_rutas_rechazan_otro_tenant(client, seed, usuarios, ruta):
    _, _, otro = usuarios
    assert client.get(BASE + ruta, headers=otro).status_code == 403


def test_alta_y_suspension_edificio(client, seed, db, usuarios):
    admin, _, _ = usuarios
    r = db.scalar(select(Residente).where(Residente.email == "ana@x.cl"))
    assert client.post("/edificios", headers=admin, json={"id": "nuevo", "nombre": "Nuevo"}).status_code == 403
    r.rol = Rol.superadmin
    db.commit()
    h = {"Authorization": "Bearer " + create_token(r.id, r.edificio_id, r.rol)}
    ok(client.post("/edificios", headers=h, json={"id": "nuevo", "nombre": "Nuevo"}), 201)
    ok(client.patch("/edificios/edificio_b", headers=h, json={"activo": False}))
    assert client.get("/edificios/edificio_b/panel", headers=usuarios[2]).status_code == 403
    assert db.get(Edificio, "nuevo")


def test_cartola_repetida_en_un_archivo_y_exportacion_segura(client, seed, db, usuarios):
    admin, _, _ = usuarios
    csv = "fecha,descripcion,monto,id\n2026-11-01,CC-A-101,100,x1\n2026-11-01,CC-A-101,100,x1\n"
    r = ok(client.post(BASE + "/conciliacion", headers=admin, files={"cartola": ("c.csv", csv)}))
    assert r["duplicados"] == 1 and db.query(Pago).count() == 1
    p = db.query(Pago).first()
    p.referencia = "=HYPERLINK(1)"
    db.commit()
    export = client.get(BASE + "/finanzas/exportar.csv", headers=admin)
    assert export.status_code == 200 and "'=HYPERLINK(1)" in export.text
