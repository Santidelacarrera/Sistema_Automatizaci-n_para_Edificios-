from app.config import settings

from conftest import login


def _mal(client, email="ana@x.cl", pw="mala"):
    return client.post("/auth/login", json={"edificio_id": "edificio_a", "email": email, "password": pw})


def test_bloquea_tras_fallos_y_avisa_cuanto_esperar(client, seed):
    for _ in range(settings.login_max_intentos):
        assert _mal(client).status_code == 401
    r = _mal(client)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    # incluso con la clave correcta sigue bloqueado durante la ventana
    assert _mal(client, pw="secreto123").status_code == 429


def test_login_correcto_borra_los_fallos(client, seed):
    for _ in range(settings.login_max_intentos - 1):
        _mal(client)
    login(client, "edificio_a", "ana@x.cl")  # acierta antes del tope
    for _ in range(settings.login_max_intentos - 1):
        assert _mal(client).status_code == 401  # contador reiniciado


def test_bloqueo_es_por_cuenta_y_no_afecta_a_otra(client, seed):
    for _ in range(settings.login_max_intentos):
        _mal(client)
    assert _mal(client).status_code == 429
    login(client, "edificio_a", "beto@x.cl")


def test_cuenta_inexistente_tambien_se_limita(client, seed):
    for _ in range(settings.login_max_intentos):
        assert _mal(client, email="nadie@x.cl").status_code == 401
    assert _mal(client, email="nadie@x.cl").status_code == 429
