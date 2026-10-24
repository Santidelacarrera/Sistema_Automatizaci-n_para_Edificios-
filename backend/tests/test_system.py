from datetime import timedelta

from app.config import ahora_local
from app.models import Cargo, EstadoVisita, Regla, Visita
from app.services import access, finance, reconciliation

from conftest import login


def test_login_y_aislamiento_multitenant(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    ok = client.post("/edificios/edificio_a/unidades", headers=h,
                     json={"numero": "201", "coeficiente": 0.1, "codigo_cobro": "CC-A-201"})
    assert ok.status_code == 201
    cruzado = client.post("/edificios/edificio_b/unidades", headers=h,
                          json={"numero": "201", "coeficiente": 0.1, "codigo_cobro": "CC-B-201"})
    assert cruzado.status_code == 403
    assert client.post("/auth/login", json={"edificio_id": "edificio_a", "email": "ana@x.cl",
                                            "password": "mala"}).status_code == 401


def test_residente_no_puede_administrar(client, seed):
    h = login(client, "edificio_a", "beto@x.cl")
    r = client.post("/edificios/edificio_a/reglas", headers=h, json={"accion": "x", "tipo": "horario"})
    assert r.status_code == 403


def test_tags_vehiculares_maximo_por_unidad(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    uid = seed["edificio_a", "101"].id
    for i in (1, 2):
        assert client.post("/edificios/edificio_a/tags", headers=h,
                           json={"unidad_id": uid, "uid": f"E2801170{i:016X}", "tipo": "vehicular"}).status_code == 201
    r = client.post("/edificios/edificio_a/tags", headers=h,
                    json={"unidad_id": uid, "uid": "E280117000000000000000AA", "tipo": "vehicular"})
    assert r.status_code == 409
    # peatonales no cuentan contra el límite
    assert client.post("/edificios/edificio_a/tags", headers=h,
                       json={"unidad_id": uid, "uid": "BB000001", "tipo": "peatonal"}).status_code == 201


def test_dispositivo_valida_tag(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    uid = seed["edificio_a", "101"].id
    client.post("/edificios/edificio_a/tags", headers=h, json={"unidad_id": uid, "uid": "ab12cd34", "tipo": "peatonal"})
    url = "/api/v1/edificio_a/validar-acceso"
    body = {"edificio_id": "edificio_a", "token_acceso": "AB12CD34"}
    assert client.post(url, json=body).status_code == 401                              # sin API key
    assert client.post(url, json=body, headers={"X-Device-Key": "keyB"}).status_code == 401  # key de otro edificio
    assert client.post(url, json=body, headers={"X-Device-Key": "keyA"}).status_code == 200
    # tag peatonal no abre portón vehicular
    assert client.post(url, json={**body, "punto": "vehicular"}, headers={"X-Device-Key": "keyA"}).status_code == 403
    assert client.post(url, json={**body, "token_acceso": "ZZ"}, headers={"X-Device-Key": "keyA"}).status_code == 403
    # un tag de A no abre en B
    assert client.post("/api/v1/edificio_b/validar-acceso", json={**body, "edificio_id": "edificio_b"},
                       headers={"X-Device-Key": "keyB"}).status_code == 403


def test_visitas_cupos_qr_y_no_show(db, seed):
    from app.models import Edificio
    ed = db.get(Edificio, "edificio_a")
    uid = seed["edificio_a", "101"].id
    ini = ahora_local() + timedelta(minutes=1)
    vs = [access.reservar_visita(db, ed, uid, f"V{i}", ini, ini + timedelta(hours=2)) for i in range(6)]
    try:
        access.reservar_visita(db, ed, uid, "V7", ini, ini + timedelta(hours=1))
        assert False, "debió rechazar por cupos"
    except access.AccesoError:
        pass
    ok, _ = access.validar_acceso(db, ed, vs[0].codigo_qr)
    assert ok and vs[0].estado == EstadoVisita.llego
    ok, _ = access.validar_acceso(db, ed, vs[0].codigo_qr)
    ok3, motivo = access.validar_acceso(db, ed, vs[0].codigo_qr)
    assert ok and not ok3 and "usos" in motivo
    # no-show: llegada tardía > 20 min libera el cupo
    vs[1].desde = ahora_local() - timedelta(minutes=21)
    assert access.liberar_no_show(db, ed) == 1
    assert vs[1].estado == EstadoVisita.no_show
    assert access.reservar_visita(db, ed, uid, "Nuevo", ini, ini + timedelta(hours=1))


def test_motor_reglas_quincho(client, seed, db):
    h = login(client, "edificio_a", "ana@x.cl")
    from app.models import EspacioComun
    db.add(EspacioComun(edificio_id="edificio_a", nombre="quincho", accion="reservar_quincho", tarifa=10000))
    db.commit()
    esp = db.query(EspacioComun).one()
    for tipo, params in (("horario", {"desde": "10:00", "hasta": "22:00"}),
                         ("max_por_mes", {"max": 1}), ("bloquear_morosos", {"deuda_max": 0})):
        client.post("/edificios/edificio_a/reglas", headers=h,
                    json={"accion": "reservar_quincho", "tipo": tipo, "params": params})
    dia = (ahora_local() + timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
    mk = lambda d, h1, h2: {"espacio_id": esp.id, "desde": (d + timedelta(hours=h1)).isoformat(),
                            "hasta": (d + timedelta(hours=h2)).isoformat()}
    assert client.post("/edificios/edificio_a/reservas-espacio", headers=h, json=mk(dia, 6, 8)).status_code == 422
    ok = client.post("/edificios/edificio_a/reservas-espacio", headers=h, json=mk(dia, 12, 16))
    assert ok.status_code == 201
    assert client.post("/edificios/edificio_a/reservas-espacio", headers=h, json=mk(dia, 14, 15)).status_code == 409
    # 2ª reserva el mismo mes -> max_por_mes; además ahora tiene deuda por la tarifa -> moroso
    r = client.post("/edificios/edificio_a/reservas-espacio", headers=h, json=mk(dia + timedelta(days=1), 12, 14))
    assert r.status_code == 422 and len(r.json()["detail"]["motivos"]) >= 1
    # la reserva generó el cargo en la cuenta
    assert client.get(f"/edificios/edificio_a/unidades/{seed['edificio_a', '101'].id}/deuda",
                      headers=h).json()["deuda"] == 10000


def test_prorrata_suma_exacta_y_consumo(db, seed):
    from datetime import date
    from app.models import LecturaMedidor
    ua = [u for k, u in seed.items() if k[0] == "edificio_a"]
    for u, c in zip(ua, (10, 30, 60)):
        db.add(LecturaMedidor(edificio_id="edificio_a", unidad_id=u.id, periodo="2025-01", servicio="agua", consumo=c))
    db.flush()
    res = finance.generar_cargos(db, "edificio_a", "2025-01", date(2025, 2, 10), [
        {"concepto": "Administración", "monto": 1000001, "tipo": "ordinario"},
        {"concepto": "Agua", "monto": 100000, "tipo": "ordinario", "base": "consumo", "servicio": "agua"}])
    assert res["total"] == 1100001
    assert sum(float(c.monto) for c in db.query(Cargo)) == 1100001
    agua = {c.unidad_id: float(c.monto) for c in db.query(Cargo) if c.concepto.endswith("Agua")}
    assert agua[ua[0].id] == 10000 and agua[ua[2].id] == 60000
    try:
        finance.generar_cargos(db, "edificio_a", "2025-01", date(2025, 2, 10), [{"concepto": "x", "monto": 1, "tipo": "ordinario"}])
        assert False
    except ValueError:
        pass


def test_conciliacion_por_codigo_rut_e_idempotencia(db, seed):
    from datetime import date
    finance.generar_cargos(db, "edificio_a", "2025-01", date(2025, 2, 10),
                           [{"concepto": "GC", "monto": 100000, "tipo": "ordinario"}])  # 101 => 50000
    db.commit()
    csv = ("fecha,descripcion,monto,id\n"
           "05/02/2025,TRANSF CC-A-101 enero,30000,t1\n"
           "06/02/2025,Pago 12345678-5 saldo,20000,t2\n"
           "07/02/2025,Deposito desconocido,5000,t3\n"
           "08/02/2025,Cargo comision,-1000,t4\n")
    movs = reconciliation.leer_cartola(csv)
    assert len(movs) == 3
    res = reconciliation.conciliar(db, "edificio_a", movs)
    assert [c["id"] for c in res["conciliados"]] == ["t1", "t2"] and len(res["sin_match"]) == 1
    assert finance.deuda_unidad(db, seed["edificio_a", "101"].id) == 0
    res2 = reconciliation.conciliar(db, "edificio_a", movs)
    assert res2["duplicados"] == 3 and not res2["conciliados"]


def test_whatsapp_webhook(client, seed):
    payload = {"event": "messages.upsert", "data": {"key": {"remoteJid": "56911112222@s.whatsapp.net", "fromMe": False},
                                                    "message": {"conversation": "cuánto debo?"}}}
    assert client.post("/webhooks/whatsapp", json=payload).status_code == 401
    r = client.post("/webhooks/whatsapp", json=payload, headers={"X-Webhook-Token": "tok"})
    assert r.status_code == 200 and r.json()["intent"] == "consultar_deuda"
    desconocido = {**payload, "data": {**payload["data"], "key": {"remoteJid": "56900000000@s.whatsapp.net"}}}
    assert client.post("/webhooks/whatsapp", json=desconocido, headers={"X-Webhook-Token": "tok"}).json() == {"residente": None, "envio": "no_configurado"}
    propio = {**payload, "data": {**payload["data"], "key": {"remoteJid": "x@s.whatsapp.net", "fromMe": True}}}
    assert client.post("/webhooks/whatsapp", json=propio, headers={"X-Webhook-Token": "tok"}).json() == {"ignorado": True}


def test_patentes_lpr_panel_y_cobranza(client, seed, db):
    from datetime import date
    h = login(client, "edificio_a", "ana@x.cl")
    uid = seed["edificio_a", "101"].id
    r = client.post("/edificios/edificio_a/vehiculos", headers=h, json={"unidad_id": uid, "patente": "bb-cd 12", "descripcion": "Mazda 3"})
    assert r.status_code == 201 and r.json()["patente"] == "BBCD12"
    assert client.post("/edificios/edificio_a/vehiculos", headers=h, json={"unidad_id": uid, "patente": "BBCD12"}).status_code == 409
    assert client.post("/edificios/edificio_a/vehiculos", headers=h, json={"unidad_id": seed["edificio_a", "103"].id, "patente": "ZZZZ99"}).status_code == 409  # sin estacionamiento
    dev = {"X-Device-Key": "keyA"}
    url = "/api/v1/edificio_a/validar-acceso"
    ok = client.post(url, json={"edificio_id": "edificio_a", "token_acceso": "BBCD12", "punto": "vehicular"}, headers=dev)
    assert ok.status_code == 200
    assert client.post(url, json={"edificio_id": "edificio_a", "token_acceso": "BBCD12", "punto": "peatonal"}, headers=dev).status_code == 403
    p = client.get("/edificios/edificio_a/panel", headers=h).json()
    u101 = next(u for u in p["unidades"] if u["numero"] == "101")
    assert u101["vehiculos"][0]["patente"] == "BBCD12"
    assert client.get("/edificios/edificio_b/panel", headers=h).status_code == 403
    finance.generar_cargos(db, "edificio_a", "2020-01", date(2020, 2, 1), [{"concepto": "GC", "monto": 100000, "tipo": "ordinario"}])
    db.commit()
    c = client.get("/edificios/edificio_a/cobranza", headers=h).json()
    assert len(c["morosos"]) == 3 and c["morosos"][0]["dias_atraso"] > 1000
    rec = client.post("/edificios/edificio_a/cobranza/recordatorios", headers=h, json={"canales": ["whatsapp"]}).json()
    assert rec["unidades"] == 3
    pago = {"unidad_id": uid, "monto": 50000, "ref_externa": "X1"}
    assert client.post("/edificios/edificio_a/pagos", headers=h, json=pago).json()["duplicado"] is False
    assert client.post("/edificios/edificio_a/pagos", headers=h, json=pago).json()["duplicado"] is True
    assert client.get(f"/edificios/edificio_a/unidades/{uid}/deuda", headers=h).json()["deuda"] == 0
