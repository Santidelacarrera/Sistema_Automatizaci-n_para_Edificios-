from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.config import utcnow
from app.models import Cargo, Pago, Residente
from app.operations_models import ComandoAcceso, Dispositivo, Incidencia
from app.services.automation import ejecutar
from app.services.whatsapp import identificar_residente
from conftest import login

BASE = "/edificios/edificio_a"


def test_protocolo_iot_nonce_replay_expiracion_y_revocacion(client, seed, db):
    admin = login(client, "edificio_a", "ana@x.cl")
    response = client.post(BASE + "/dispositivos", headers=admin, json={"nombre": "Simulador", "punto": "Portón"})
    assert response.status_code == 201, response.text
    d = response.json()
    device_headers = {"X-Device-Key": d["clave"]}
    path = f"/api/v1/edificio_a/dispositivos/{d['id']}"
    abrir = BASE + f"/dispositivos/{d['id']}/abrir"
    body = {"password": "secreto123", "motivo": "Prueba de laboratorio autorizada", "idempotencia": "prueba-12345678901"}
    assert client.post(abrir, headers=admin, json=body).status_code == 409  # desconectado
    assert client.post(path + "/heartbeat", headers=device_headers, json={"firmware": "sim-1", "bateria": 90}).status_code == 200
    c = client.post(abrir, headers=admin, json=body)
    assert c.status_code == 201
    assert client.post(abrir, headers=admin, json=body).json()["id"] == c.json()["id"]
    entrega = client.post(path + "/comandos/obtener", headers=device_headers).json()["comando"]
    assert entrega["accion"] == "simular_apertura"
    assert client.post(path + "/comandos/obtener", headers=device_headers).json()["comando"] is None
    ack = path + f"/comandos/{entrega['id']}/confirmar"
    assert client.post(ack, headers=device_headers, json={"nonce": "x" * 32, "estado": "ejecutado"}).status_code == 404
    payload = {"nonce": entrega["nonce"], "estado": "ejecutado"}
    assert client.post(ack, headers=device_headers, json=payload).status_code == 200
    assert client.post(ack, headers=device_headers, json=payload).status_code == 409
    body["idempotencia"] = "prueba-12345678902"
    cid = client.post(abrir, headers=admin, json=body).json()["id"]
    comando = db.get(ComandoAcceso, cid)
    comando.expira = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post(path + "/comandos/obtener", headers=device_headers).json()["comando"] is None
    nueva = client.post(BASE + f"/dispositivos/{d['id']}/rotar", headers=admin).json()
    assert nueva["clave"] != d["clave"]
    assert client.post(path + "/heartbeat", headers=device_headers, json={}).status_code == 401
    assert "clave_hash" not in client.get(BASE + "/dispositivos", headers=admin).text


def test_iot_no_habilita_apertura_real_ni_otro_edificio(client, seed, db):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    r = client.post(BASE + "/dispositivos", headers=admin,
                    json={"nombre": "Sólo telemetría", "punto": "Puerta", "laboratorio": False})
    did = r.json()["id"]
    path = BASE + f"/dispositivos/{did}/abrir"
    b = {"password": "secreto123", "motivo": "No debe accionar nada real", "idempotencia": "intento-1234567890"}
    assert client.post(path, headers=admin, json=b).status_code == 409
    assert client.post(path, headers=residente, json=b).status_code == 403
    assert client.post(f"/api/v1/edificio_b/dispositivos/{did}/heartbeat", json={},
                       headers={"X-Device-Key": r.json()["clave"]}).status_code == 401
    d = db.get(Dispositivo, did)
    d.creado = utcnow() - timedelta(minutes=10)
    db.commit()
    assert ejecutar(db, "edificio_a")["creadas"] == 1
    db.commit()
    assert ejecutar(db, "edificio_a")["creadas"] == 0
    assert db.query(Incidencia).count() == 1


def test_documentos_pdf_reales_y_permiso_unidad(client, seed, db):
    h = login(client, "edificio_a", "beto@x.cl")
    uid = seed["edificio_a", "102"].id
    db.add(Cargo(edificio_id="edificio_a", unidad_id=uid, periodo="2026-11", concepto="<Gasto>", monto=500, saldo=400))
    p = Pago(edificio_id="edificio_a", unidad_id=uid, monto=Decimal("100"), fecha=utcnow().date(), ref_banco="pdf-1", conciliado=True)
    db.add(p)
    db.commit()
    for path in (f"/unidades/{uid}/estado-cuenta.pdf", f"/pagos/{p.id}/comprobante.pdf"):
        r = client.get(BASE + path, headers=h)
        assert r.status_code == 200, r.text
        assert r.content.startswith(b"%PDF-") and r.content.rstrip().endswith(b"%%EOF")
        assert r.headers["cache-control"] == "no-store"
    otro_uid = seed["edificio_a", "101"].id
    assert client.get(BASE + f"/unidades/{otro_uid}/estado-cuenta.pdf", headers=h).status_code == 403


def test_whatsapp_telefono_compartido_no_selecciona_un_tenant(db, seed):
    ana = db.scalar(select(Residente).where(Residente.email == "ana@x.cl"))
    carla = db.scalar(select(Residente).where(Residente.email == "carla@x.cl"))
    assert identificar_residente(db, ana.telefono).id == ana.id
    carla.telefono = ana.telefono
    db.commit()
    assert identificar_residente(db, ana.telefono) is None
