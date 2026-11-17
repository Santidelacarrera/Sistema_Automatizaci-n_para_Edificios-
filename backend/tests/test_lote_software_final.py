"""Pruebas del lote final de software:
aprobación/rechazo y bloqueo por mantenimiento de reservas, ingresos/salidas en portería,
torres y pisos, informe de comité, anomalías de acceso, métricas y versionamiento /api/v1.
"""
from datetime import datetime, timedelta

from app.models import AccesoLog, EspacioComun, ReservaEspacio, Tag, TipoTag, Vehiculo
from conftest import login

BASE = "/edificios/edificio_a"


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def test_reservas_bloqueo_mantenimiento_y_aprobacion(client, seed, db):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    uid = seed["edificio_a", "102"].id

    esp = EspacioComun(edificio_id="edificio_a", nombre="Piscina", accion="piscina", tarifa=5000, garantia=0, aforo=15)
    db.add(esp)
    db.commit()
    db.refresh(esp)

    ini = (datetime.now() + timedelta(days=4)).replace(hour=10, minute=0, second=0, microsecond=0)
    fin = ini + timedelta(hours=2)

    # 08.19 Bloqueo por mantenimiento impide nuevas reservas en ese horario
    bloq = ok(client.post(f"{BASE}/espacios-comunes/{esp.id}/bloqueos", headers=admin, json={
        "desde": ini.isoformat(), "hasta": fin.isoformat(), "motivo": "Limpieza de filtros",
    }), 201)
    assert len(ok(client.get(f"{BASE}/espacios-comunes/{esp.id}/bloqueos", headers=residente))) == 1

    r_choca = client.post(BASE + "/reservas-espacio", headers=residente, json={
        "espacio_id": esp.id, "unidad_id": uid, "desde": ini.isoformat(), "hasta": fin.isoformat(), "asistentes": 2,
    })
    assert r_choca.status_code == 409

    ok(client.delete(f"{BASE}/espacios-comunes/bloqueos/{bloq['id']}", headers=admin))

    # 08.14 Aprobación o rechazo por administración
    res = ReservaEspacio(
        edificio_id="edificio_a", espacio_id=esp.id, unidad_id=uid,
        desde=ini, hasta=fin, estado="pendiente",
    )
    db.add(res)
    db.commit()
    db.refresh(res)
    ap = ok(client.post(f"{BASE}/reservas-espacio/{res.id}/resolver", headers=admin, json={"decision": "aprobada"}))
    assert ap["estado"] == "confirmada"


def test_porteria_estructura_comite_anomalias_metricas_y_v1(client, seed, db):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    uid = seed["edificio_a", "102"].id

    # 07.02, 07.03, 07.04, 07.11 Ingresos y salidas en portería
    for tipo, nombre in (("proveedor", "Técnico Juan"), ("trabajador", "Pintor Luis"), ("delivery", "Pedido Express")):
        reg = ok(client.post(BASE + "/porteria/ingresos", headers=admin, json={
            "tipo": tipo, "nombre": nombre, "empresa": "Servicios SA", "unidad_id": uid, "motivo": "Mantención",
        }), 201)
        assert reg["tipo"] == tipo
        if tipo == "delivery":
            sal = ok(client.post(f"{BASE}/porteria/ingresos/{reg['id']}/salida", headers=admin))
            assert sal["salida"] is not None
    hist_port = ok(client.get(BASE + "/porteria/ingresos", headers=admin))
    assert len(hist_port) >= 3
    assert client.get(BASE + "/porteria/ingresos", headers=residente).status_code == 403

    # 04.02 Torres y pisos
    ub = ok(client.patch(f"{BASE}/unidades/{uid}/ubicacion", headers=admin, json={"torre": "A", "piso": 5}))
    assert ub["torre"] == "A" and ub["piso"] == 5
    est = ok(client.get(BASE + "/estructura", headers=residente))
    assert "A" in est["torres"] and 5 in est["pisos"]

    # 11.12 Informe ejecutivo para el comité (JSON y PDF)
    inf = ok(client.get(BASE + "/asambleas/informe-comite", headers=admin))
    assert "deuda_pendiente" in inf and "asambleas_total" in inf
    inf_pdf = client.get(BASE + "/asambleas/informe-comite.pdf", headers=admin)
    assert inf_pdf.status_code == 200 and inf_pdf.content.startswith(b"%PDF-")

    # 22.11 y 22.12 Detección de intentos anómalos y credenciales duplicadas
    for _ in range(3):
        db.add(AccesoLog(edificio_id="edificio_a", token="TOK-SOSPECHOSO", punto="porton", fuente="uhf", permitido=False, motivo="desconocido"))
    db.add(Tag(edificio_id="edificio_a", unidad_id=uid, uid="TAG-DUP-1", tipo=TipoTag.vehicular, estado="activo"))
    db.add(Tag(edificio_id="edificio_a", unidad_id=uid, uid="tag-dup-1", tipo=TipoTag.vehicular, estado="activo"))
    db.add(Vehiculo(edificio_id="edificio_a", unidad_id=uid, patente="DUP123", activo=True))
    db.commit()

    anom = ok(client.get(BASE + "/accesos/anomalias", headers=admin))
    assert any(a["token"] == "TOK-SOSPECHOSO" and a["rechazos"] >= 3 for a in anom["intentos_anomalos"])
    assert any(d["valor"] == "TAG-DUP-1" for d in anom["credenciales_duplicadas"])

    # 19.16 Métricas y 19.25 Versionamiento /api/v1
    m = ok(client.get("/metrics"))
    assert m["http_requests_total"] >= 1
    assert ok(client.get("/api/v1/health")) == {"ok": True}
    assert ok(client.get(f"/api/v1{BASE}/estructura", headers=admin))["torres"] == ["A"]
