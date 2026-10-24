from sqlalchemy import select

from app.models import Edificio
from app.security import hash_clave_dispositivo

from conftest import login


def test_la_base_guarda_hash_no_la_clave(db, seed):
    ed = db.get(Edificio, "edificio_a")
    assert ed.device_api_key != "keyA" and ed.device_api_key == hash_clave_dispositivo("keyA")


def test_rotar_clave_invalida_la_anterior_y_la_nueva_funciona(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    url = "/api/v1/edificio_a/validar-acceso"
    cuerpo = {"edificio_id": "edificio_a", "token_acceso": "NOEXISTE"}
    assert client.post(url, json=cuerpo, headers={"X-Device-Key": "keyA"}).status_code == 403  # autenticado, credencial desconocida
    r = client.post("/edificios/edificio_a/dispositivos/rotar-clave", headers=h)
    assert r.status_code == 200
    nueva = r.json()["device_key"]
    assert len(nueva) >= 32
    assert client.post(url, json=cuerpo, headers={"X-Device-Key": "keyA"}).status_code == 401
    assert client.post(url, json={**cuerpo, "token_acceso": "OTRO"}, headers={"X-Device-Key": nueva}).status_code == 403


def test_residente_no_puede_rotar_ni_otro_edificio(client, seed):
    hb = login(client, "edificio_a", "beto@x.cl")
    assert client.post("/edificios/edificio_a/dispositivos/rotar-clave", headers=hb).status_code == 403
    ha = login(client, "edificio_a", "ana@x.cl")
    assert client.post("/edificios/edificio_b/dispositivos/rotar-clave", headers=ha).status_code == 403
