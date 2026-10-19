"""Superadmin: lista de edificios y acceso a varios edificios; sólo él puede hacerlo."""
from scripts import crear_superadmin

from conftest import login

RUT_SA = "33333333-3"  # DV verificado


def _crear(password="clave-muy-segura-1", **extra):
    args = ["--edificio", "edificio_a", "--unidad", "101", "--nombre", "Soporte", "--rut", RUT_SA,
            "--email", "soporte@empresa.cl", "--password", password]
    return crear_superadmin.main(args + list(extra.get("mas", [])))


def test_superadmin_lista_edificios_y_ve_otro_edificio(client, seed):
    assert _crear() == 0
    r0 = client.post("/auth/login", json={"edificio_id": "edificio_a", "email": "soporte@empresa.cl",
                                          "password": "clave-muy-segura-1"})
    h = {"Authorization": f"Bearer {r0.json()['access_token']}"}
    r = client.get("/edificios", headers=h)
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert {"edificio_a", "edificio_b"} <= ids
    assert client.get("/edificios/edificio_b/panel", headers=h).status_code == 200


def test_solo_superadmin_lista_edificios(client, seed):
    h_admin = login(client, "edificio_a", "ana@x.cl")
    h_res = login(client, "edificio_a", "beto@x.cl")
    assert client.get("/edificios", headers=h_admin).status_code == 403
    assert client.get("/edificios", headers=h_res).status_code == 403
    assert client.get("/edificios").status_code == 401


def test_admin_no_entra_a_otro_edificio_aunque_sea_admin(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    assert client.get("/edificios/edificio_b/panel", headers=h).status_code == 403


def test_crear_superadmin_valida(client, seed):
    assert _crear(password="corta") == 1
    assert _crear() == 0
    assert _crear() == 1  # mismo RUT en el edificio
