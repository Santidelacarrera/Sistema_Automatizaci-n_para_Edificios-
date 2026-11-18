"""Pruebas de cierre operativo: historial forense de accesos, análisis de eventos,
espacios comunes por tipo con disponibilidad en tiempo real, y portería integral.
"""
from datetime import date, timedelta

from app.models import AccesoLog, EspacioComun, Residente
from app.services.cache import cache_invalidate
from app.services.notifications import notificar
from conftest import login

BASE = "/edificios/edificio_a"


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def test_forense_accesos_eventos_espacios_y_porteria_integral(client, seed, db):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    uid = seed["edificio_a", "102"].id

    # 22.15 Historial forense de accesos
    db.add(AccesoLog(edificio_id="edificio_a", token="FOR-1", punto="porton", fuente="uhf", permitido=True, motivo="ok"))
    db.add(AccesoLog(edificio_id="edificio_a", token="FOR-2", punto="porton", fuente="qr", permitido=False, motivo="expirado"))
    db.commit()
    forense = ok(client.get(BASE + "/accesos/forense?permitido=false", headers=admin))
    assert any(a["token"] == "FOR-2" and a["motivo"] == "expirado" for a in forense)

    # 22.14 Análisis de eventos
    ok(client.post(BASE + "/incidencias", headers=admin, json={"titulo": "Luz pasillo", "descripcion": "Ampolleta quemada"}), 201)
    evs = ok(client.get(BASE + "/eventos/resumen", headers=admin))
    assert evs["total"] >= 1 and len(evs["por_tipo"]) >= 1

    # 08.02-08.07, 08.09, 08.10 Espacios comunes por tipo y disponibilidad en tiempo real
    nombres = ["Salón de eventos", "Piscina", "Gimnasio", "Cancha", "Sala de reuniones", "Cowork"]
    espacios = []
    for nom in nombres:
        e = EspacioComun(edificio_id="edificio_a", nombre=nom, accion=nom.lower().replace(" ", "_"), tarifa=0, garantia=0, aforo=10)
        db.add(e)
        espacios.append(e)
    db.commit()
    cache_invalidate("espacios:edificio_a")
    lista_esp = ok(client.get(BASE + "/espacios-comunes", headers=residente))
    for nom in nombres:
        assert any(x["nombre"] == nom for x in lista_esp)
    disp = ok(client.get(f"{BASE}/espacios-comunes/{espacios[0].id}/disponibilidad?fecha={(date.today() + timedelta(days=5)).isoformat()}", headers=residente))
    assert disp["espacio"] == "Salón de eventos"

    # 07.06, 07.12, 07.14, 07.16 Correspondencia, observaciones/incidencias y notificación al residente
    enc = ok(client.post(BASE + "/encomiendas", headers=admin, json={
        "unidad_id": uid, "destinatario": "Beto Soto", "descripcion": "Sobre certificado",
    }), 201)
    assert enc["id"] > 0
    res_obj = db.query(Residente).filter(Residente.edificio_id == "edificio_a", Residente.unidad_id == uid).first()
    assert notificar(db, "edificio_a", [res_obj], "Encomienda", "Tiene un sobre en portería", f"enc:{enc['id']}", externos=False) == 1
