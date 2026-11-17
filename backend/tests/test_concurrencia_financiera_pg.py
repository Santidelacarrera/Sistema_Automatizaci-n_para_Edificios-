"""Casos reales de carreras; se omiten en SQLite, que no implementa FOR UPDATE."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
import threading

from fastapi import HTTPException
import pytest
from sqlalchemy import select

from app.config import ahora_local
from app.db import SessionLocal
from app.models import Cargo, EspacioComun, Pago, Residente, ReservaEspacio, Rol
from app.routers.edificio import reservar_espacio
from app.routers.panel import registrar_pago
from app.schemas import PagoIn, ReservaEspacioIn
from app.security import Principal

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"), reason="requiere PostgreSQL real")


def paralelo(fn, cantidad=6):
    barrier = threading.Barrier(cantidad)
    def worker(i):
        barrier.wait(timeout=30)
        with SessionLocal() as session:
            try:
                return fn(session, i)
            except HTTPException as exc:
                session.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=cantidad) as pool:
        return list(pool.map(worker, range(cantidad)))


def test_reservas_simultaneas_no_duplican_espacio(db, seed):
    r = db.scalar(select(Residente).where(Residente.email == "ana@x.cl"))
    principal = Principal(r.id, "edificio_a", Rol.admin)
    esp = EspacioComun(edificio_id="edificio_a", nombre="Sala", accion="reservar_sala", tarifa=1000)
    db.add(esp)
    db.commit()
    inicio = ahora_local() + timedelta(days=1)
    body = ReservaEspacioIn(espacio_id=esp.id, unidad_id=r.unidad_id, desde=inicio, hasta=inicio + timedelta(hours=1))
    results = paralelo(lambda session, i: reservar_espacio("edificio_a", body, principal, session))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count(409) == 5
    assert db.query(ReservaEspacio).count() == 1
    assert db.query(Cargo).count() == 1


def test_pago_repetido_simultaneo_abona_una_vez(db, seed):
    r = db.scalar(select(Residente).where(Residente.email == "ana@x.cl"))
    principal = Principal(r.id, "edificio_a", Rol.admin)
    cargo = Cargo(edificio_id="edificio_a", unidad_id=r.unidad_id, periodo="2026-11", concepto="Cuota", monto=1000, saldo=1000)
    db.add(cargo)
    db.commit()
    body = PagoIn(unidad_id=r.unidad_id, monto=100, ref_externa="misma-referencia")
    results = paralelo(lambda session, i: registrar_pago("edificio_a", body, principal, session))
    assert sum(not result["duplicado"] for result in results) == 1
    db.expire_all()
    assert db.get(Cargo, cargo.id).saldo == 900
    assert db.query(Pago).count() == 1


def test_pagos_distintos_concurrentes_no_pierden_abonos(db, seed):
    r = db.scalar(select(Residente).where(Residente.email == "ana@x.cl"))
    principal = Principal(r.id, "edificio_a", Rol.admin)
    cargo = Cargo(edificio_id="edificio_a", unidad_id=r.unidad_id, periodo="2026-11", concepto="Cuota", monto=1000, saldo=1000)
    db.add(cargo)
    db.commit()
    paralelo(lambda session, i: registrar_pago("edificio_a", PagoIn(unidad_id=r.unidad_id, monto=100,
                                                                   ref_externa=f"referencia-{i}"), principal, session))
    db.expire_all()
    assert db.get(Cargo, cargo.id).saldo == 400
    assert db.query(Pago).count() == 6
