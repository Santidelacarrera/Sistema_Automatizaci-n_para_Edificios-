from app.models import Evento, Residente

from conftest import login


def _id(db, email):
    return db.query(Residente).filter_by(email=email).one().id


def test_exportar_datos_personales_y_queda_registrado(client, seed, db):
    h = login(client, "edificio_a", "ana@x.cl")
    rid = _id(db, "beto@x.cl")
    r = client.get(f"/edificios/edificio_a/residentes/{rid}/datos-personales", headers=h)
    assert r.status_code == 200 and r.json()["residente"]["nombre"] == "Beto Soto"
    assert db.query(Evento).filter_by(tipo="privacidad.exportacion").count() == 1


def test_anonimizar_borra_datos_y_quita_acceso(client, seed, db):
    h = login(client, "edificio_a", "ana@x.cl")
    rid = _id(db, "beto@x.cl")
    assert client.post(f"/edificios/edificio_a/residentes/{rid}/anonimizar", headers=h).status_code == 200
    db.expire_all()
    r = db.get(Residente, rid)
    assert (r.nombre, r.rut, r.email, r.telefono, r.password_hash, r.activo) == ("[eliminado]", "", "", "", "", False)
    mal = client.post("/auth/login", json={"edificio_id": "edificio_a", "email": "beto@x.cl", "password": "secreto123"})
    assert mal.status_code == 401


def test_no_se_anonimiza_a_uno_mismo_ni_a_otro_edificio_ni_siendo_residente(client, seed, db):
    ha = login(client, "edificio_a", "ana@x.cl")
    assert client.post(f"/edificios/edificio_a/residentes/{_id(db, 'ana@x.cl')}/anonimizar", headers=ha).status_code == 409
    rid_b = _id(db, "carla@x.cl")
    assert client.post(f"/edificios/edificio_a/residentes/{rid_b}/anonimizar", headers=ha).status_code == 404
    hb = login(client, "edificio_a", "beto@x.cl")
    assert client.post(f"/edificios/edificio_a/residentes/{_id(db, 'ana@x.cl')}/anonimizar", headers=hb).status_code == 403
    assert client.get(f"/edificios/edificio_a/residentes/{_id(db, 'ana@x.cl')}/datos-personales", headers=hb).status_code == 403
