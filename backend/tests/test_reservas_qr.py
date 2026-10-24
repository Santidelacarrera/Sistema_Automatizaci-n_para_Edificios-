"""QR de visitas (PNG) y cancelación de reservas de espacios comunes con multa."""
from datetime import timedelta

from app.config import ahora_local
from app.models import Cargo, EspacioComun, Regla, Visita
from app.services import access

from conftest import login


def _visita(db, seed):
    from app.models import Edificio
    ed = db.get(Edificio, "edificio_a")
    ini = ahora_local() + timedelta(hours=5)
    return access.reservar_visita(db, ed, seed["edificio_a", "101"].id, "Visita QR", ini, ini + timedelta(hours=2))


def test_qr_visita_devuelve_png_solo_a_su_unidad(client, seed, db):
    v = _visita(db, seed)
    db.commit()
    h_ana = login(client, "edificio_a", "ana@x.cl")      # unidad 101
    h_beto = login(client, "edificio_a", "beto@x.cl")    # unidad 102
    r = client.get(f"/edificios/edificio_a/visitas/{v.id}/qr.png", headers=h_ana)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert r.headers["cache-control"] == "no-store"
    assert client.get(f"/edificios/edificio_a/visitas/{v.id}/qr.png", headers=h_beto).status_code == 403
    assert client.get(f"/edificios/edificio_a/visitas/999/qr.png", headers=h_ana).status_code == 404
    assert client.get(f"/edificios/edificio_a/visitas/{v.id}/qr.png").status_code == 401


def _reservar(client, h, espacio_id, desde_h, dur_h=2, unidad=None):
    d = ahora_local() + timedelta(hours=desde_h)
    body = {"espacio_id": espacio_id, "desde": d.isoformat(), "hasta": (d + timedelta(hours=dur_h)).isoformat()}
    if unidad:
        body["unidad_id"] = unidad
    return client.post("/edificios/edificio_a/reservas-espacio", headers=h, json=body)


def _setup(db):
    db.add(EspacioComun(edificio_id="edificio_a", nombre="quincho", accion="reservar_quincho", tarifa=10000))
    db.add(Regla(edificio_id="edificio_a", accion="reservar_quincho", tipo="multa_cancelacion",
                 params={"horas": 24, "monto": 15000}))
    db.commit()
    return db.query(EspacioComun).one()


def test_cancelar_con_aviso_suficiente_no_cobra_multa_y_anula_tarifa(client, seed, db):
    esp = _setup(db)
    h = login(client, "edificio_a", "ana@x.cl")
    rid = _reservar(client, h, esp.id, desde_h=72).json()["id"]
    r = client.post(f"/edificios/edificio_a/reservas-espacio/{rid}/cancelar", headers=h)
    assert r.status_code == 200 and r.json() == {"estado": "cancelada", "multa": 0, "tarifa_anulada": True}
    deuda = client.get(f"/edificios/edificio_a/unidades/{seed['edificio_a', '101'].id}/deuda", headers=h).json()
    assert deuda["deuda"] == 0
    assert client.post(f"/edificios/edificio_a/reservas-espacio/{rid}/cancelar", headers=h).status_code == 409


def test_cancelar_con_poco_aviso_carga_multa(client, seed, db):
    esp = _setup(db)
    h = login(client, "edificio_a", "ana@x.cl")
    rid = _reservar(client, h, esp.id, desde_h=10).json()["id"]
    r = client.post(f"/edificios/edificio_a/reservas-espacio/{rid}/cancelar", headers=h).json()
    assert r["multa"] == 15000 and r["tarifa_anulada"] is True
    cargos = {c.concepto: float(c.saldo) for c in db.query(Cargo).filter_by(edificio_id="edificio_a")}
    assert cargos["Multa cancelación quincho"] == 15000
    assert cargos["Reserva quincho"] == 0
    deuda = client.get(f"/edificios/edificio_a/unidades/{seed['edificio_a', '101'].id}/deuda", headers=h).json()
    assert deuda["deuda"] == 15000


def test_residente_no_cancela_reserva_ajena(client, seed, db):
    esp = _setup(db)
    h_ana = login(client, "edificio_a", "ana@x.cl")
    h_beto = login(client, "edificio_a", "beto@x.cl")
    rid = _reservar(client, h_ana, esp.id, desde_h=72).json()["id"]
    assert client.post(f"/edificios/edificio_a/reservas-espacio/{rid}/cancelar", headers=h_beto).status_code == 403
    assert client.post(f"/edificios/edificio_a/reservas-espacio/999/cancelar", headers=h_ana).status_code == 404
