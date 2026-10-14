import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["WHATSAPP_WEBHOOK_TOKEN"] = "tok"
os.environ["CELERY_EAGER"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Edificio, Residente, Rol, Unidad
from app.security import hash_password


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        yield s


@pytest.fixture()
def client(db):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seed(db):
    """2 edificios para probar aislamiento multi-tenant."""
    for eid, key in (("edificio_a", "keyA"), ("edificio_b", "keyB")):
        db.add(Edificio(id=eid, nombre=eid.upper(), device_api_key=key, cupos_visitas=6))
        for n, coef, est in (("101", 0.5, 2), ("102", 0.3, 1), ("103", 0.2, 0)):
            db.add(Unidad(edificio_id=eid, numero=n, coeficiente=coef, estacionamientos=est,
                          codigo_cobro=f"CC-{eid[-1].upper()}-{n}"))
    db.flush()
    u = {(x.edificio_id, x.numero): x for x in db.query(Unidad)}
    db.add(Residente(edificio_id="edificio_a", unidad_id=u["edificio_a", "101"].id, nombre="Ana Pérez",
                     rut="12.345.678-5", email="ana@x.cl", telefono="56911112222", rol=Rol.admin,
                     password_hash=hash_password("secreto123")))
    db.add(Residente(edificio_id="edificio_a", unidad_id=u["edificio_a", "102"].id, nombre="Beto Soto",
                     rut="9.876.543-2", email="beto@x.cl", telefono="56933334444",
                     password_hash=hash_password("secreto123")))
    db.add(Residente(edificio_id="edificio_b", unidad_id=u["edificio_b", "101"].id, nombre="Carla Admin",
                     rut="11.111.111-1", email="carla@x.cl", rol=Rol.admin,
                     password_hash=hash_password("secreto123")))
    db.commit()
    return u


def login(client, edificio, email):
    r = client.post("/auth/login", json={"edificio_id": edificio, "email": email, "password": "secreto123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
