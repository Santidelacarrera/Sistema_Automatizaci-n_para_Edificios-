"""Panel de stickers: vincular sticker y patente, prueba de alcance en la bitácora y fuente de cada lectura."""
from app.models import Edificio, Evento, TipoTag
from app.services import access

from conftest import login


def epc(i):
    return f"E2801170{i:016X}"


def _tag(db, seed, unidad, codigo):
    ed = db.get(Edificio, "edificio_a")
    t = access.asignar_tag(db, ed, seed["edificio_a", unidad].id, codigo, TipoTag.vehicular)
    db.commit()
    return t


def test_vincular_sticker_a_patente_valida_y_reglas(client, seed, db):
    h = login(client, "edificio_a", "ana@x.cl")
    t1 = _tag(db, seed, "101", epc(200))
    t2 = _tag(db, seed, "101", epc(201))
    v1 = access.registrar_vehiculo(db, db.get(Edificio, "edificio_a"), seed["edificio_a", "101"].id, "VVVV11", "A")
    v2 = access.registrar_vehiculo(db, db.get(Edificio, "edificio_a"), seed["edificio_a", "101"].id, "VVVV22", "B")
    db.commit()
    url = f"/edificios/edificio_a/tags/{t1.id}/vincular"
    assert client.post(url, headers=h, json={"vehiculo_id": v1.id}).status_code == 200
    # el auto ya tiene otro sticker: no se le puede poner un segundo
    r = client.post(f"/edificios/edificio_a/tags/{t2.id}/vincular", headers=h, json={"vehiculo_id": v1.id})
    assert r.status_code == 409 and "ya tiene otro sticker" in r.json()["detail"]
    # el sticker ya tiene otra patente
    r = client.post(url, headers=h, json={"vehiculo_id": v2.id})
    assert r.status_code == 409 and "VVVV11" in r.json()["detail"]
    assert client.post(url, headers=h, json={"vehiculo_id": 9999}).status_code == 404
    # desvincular libera el auto
    assert client.post(f"/edificios/edificio_a/tags/{t1.id}/desvincular", headers=h).status_code == 200
    assert client.post(f"/edificios/edificio_a/tags/{t2.id}/vincular", headers=h, json={"vehiculo_id": v1.id}).status_code == 200


def test_vincular_otro_departamento_falla(client, seed, db):
    h = login(client, "edificio_a", "ana@x.cl")
    t = _tag(db, seed, "101", epc(202))
    ed = db.get(Edificio, "edificio_a")
    v = access.registrar_vehiculo(db, ed, seed["edificio_a", "102"].id, "WWWW11", "C")
    db.commit()
    r = client.post(f"/edificios/edificio_a/tags/{t.id}/vincular", headers=h, json={"vehiculo_id": v.id})
    assert r.status_code == 422 and "otro departamento" in r.json()["detail"]


def test_prueba_de_alcance_queda_en_bitacora(client, seed, db):
    h = login(client, "edificio_a", "ana@x.cl")
    r = client.post("/edificios/edificio_a/pruebas-alcance", headers=h,
                    json={"distancia_m": 4.5, "resultado": "leyo", "tag_uid": epc(203), "nota": "parabrisas"})
    assert r.status_code == 201
    lista = client.get("/edificios/edificio_a/pruebas-alcance", headers=h).json()
    assert lista[0]["distancia_m"] == 4.5 and lista[0]["resultado"] == "leyo" and lista[0]["nota"] == "parabrisas"
    assert db.query(Evento).filter_by(tipo="prueba.alcance").count() == 1
    assert client.post("/edificios/edificio_a/pruebas-alcance", headers=h,
                       json={"distancia_m": 99, "resultado": "leyo"}).status_code == 422
    residente = login(client, "edificio_a", "beto@x.cl")
    assert client.get("/edificios/edificio_a/pruebas-alcance", headers=residente).status_code == 403


def test_portón_muestra_la_fuente_de_cada_lectura(client, seed, db):
    _tag(db, seed, "101", epc(204))
    client.post("/api/v1/edificio_a/validar-acceso", headers={"X-Device-Key": "keyA"},
                json={"edificio_id": "edificio_a", "token_acceso": epc(204), "punto": "vehicular", "tipo": "sticker"})
    h = login(client, "edificio_a", "ana@x.cl")
    lectura = client.get("/edificios/edificio_a/accesos", headers=h).json()[0]
    assert lectura["fuente"] == "sticker" and lectura["permitido"] is True  # modo o: el sticker basta
    assert "fuente" in lectura and "motivo" in lectura
