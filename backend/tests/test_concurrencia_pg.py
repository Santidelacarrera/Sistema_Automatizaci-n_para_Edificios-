"""Carreras reales: sólo tienen sentido en PostgreSQL (SQLite serializa todas las escrituras).

    TEST_DATABASE_URL=postgresql+psycopg://usuario@host/base pytest tests/test_concurrencia_pg.py
"""
import os
import threading
from datetime import timedelta

import pytest

from app.config import ahora_local
from app.db import SessionLocal
from app.models import Edificio, Vehiculo, Visita
from app.services import access

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
                                reason="requiere PostgreSQL (TEST_DATABASE_URL)")


def _en_paralelo(n, fn):
    barrera = threading.Barrier(n)
    resultados = []

    def correr(i):
        barrera.wait()  # todos arrancan a la vez
        resultados.append(fn(i))

    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(n)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    return resultados


def test_cupos_de_visita_no_se_sobrepasan_con_reservas_simultaneas(db, seed):
    uid = seed["edificio_a", "101"].id
    ini = ahora_local() + timedelta(hours=1)

    def reservar(i):
        with SessionLocal() as s:
            ed = s.get(Edificio, "edificio_a")
            try:
                access.reservar_visita(s, ed, uid, f"V{i}", ini, ini + timedelta(hours=2))
                s.commit()
                return True
            except access.AccesoError:
                s.rollback()
                return False

    res = _en_paralelo(14, reservar)
    assert sum(res) == 6, f"se aceptaron {sum(res)} reservas con 6 cupos"
    assert db.query(Visita).count() == 6


def test_limite_de_vehiculos_por_unidad_con_altas_simultaneas(db, seed):
    uid = seed["edificio_a", "101"].id  # la unidad 101 tiene 2 estacionamientos

    def alta(i):
        with SessionLocal() as s:
            ed = s.get(Edificio, "edificio_a")
            try:
                access.registrar_vehiculo(s, ed, uid, f"BBCD{10 + i}")
                s.commit()
                return True
            except access.AccesoError:
                s.rollback()
                return False

    assert sum(_en_paralelo(8, alta)) == 2
    assert db.query(Vehiculo).filter_by(unidad_id=uid).count() == 2
