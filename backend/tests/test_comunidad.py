"""Comunicados, encomiendas, avisos de pago, Mi Depto, intereses, fondo de reserva, aforo y WhatsApp de visitas."""
from datetime import date, timedelta

from app.config import utcnow
from app.models import Cargo, EspacioComun, Regla, Residente, Rol, Unidad
from app.security import hash_password
from app.services import access, finance

from conftest import login

A = "/edificios/edificio_a"


def _conserje(db, seed):
    db.add(Residente(edificio_id="edificio_a", unidad_id=seed["edificio_a", "103"].id, nombre="Carlos Conserje",
                     rut="5.555.555-5", email="conserje@x.cl", rol=Rol.conserje,
                     password_hash=hash_password("secreto123")))
    db.commit()
    return login_c


def login_c(client):
    return login(client, "edificio_a", "conserje@x.cl")


def _cargo(db, seed, num, monto, venc, concepto="GC:ordinario:Admin", periodo="2026-09"):
    uid = seed["edificio_a", num].id
    db.add(Cargo(edificio_id="edificio_a", unidad_id=uid, periodo=periodo, concepto=concepto,
                 monto=monto, saldo=monto, vencimiento=venc))
    db.commit()
    return uid


# ---------------- comunicados
def test_comunicados_admin_publica_residente_lee_y_no_escribe(client, seed):
    ana, beto = login(client, "edificio_a", "ana@x.cl"), login(client, "edificio_a", "beto@x.cl")
    r = client.post(f"{A}/comunicados", headers=ana, json={"titulo": "Corte de agua", "cuerpo": "Martes 9-13 h",
                                                           "categoria": "mantencion"})
    assert r.status_code == 201
    client.post(f"{A}/comunicados", headers=ana, json={"titulo": "Asamblea", "cuerpo": "Sala común", "fijado": True,
                                                       "categoria": "asamblea"})
    muro = client.get(f"{A}/comunicados", headers=beto).json()
    assert [c["titulo"] for c in muro] == ["Asamblea", "Corte de agua"]  # fijado primero
    assert client.post(f"{A}/comunicados", headers=beto, json={"titulo": "Hack", "cuerpo": "x"}).status_code == 403
    assert client.delete(f"{A}/comunicados/{r.json()['id']}", headers=beto).status_code == 403


def test_comunicado_vencido_no_se_muestra_y_aislamiento_entre_edificios(client, seed):
    ana = login(client, "edificio_a", "ana@x.cl")
    ayer = (utcnow() - timedelta(days=1)).isoformat()
    client.post(f"{A}/comunicados", headers=ana, json={"titulo": "Viejo", "cuerpo": "x", "vigente_hasta": ayer})
    assert client.get(f"{A}/comunicados", headers=ana).json() == []
    assert len(client.get(f"{A}/comunicados?todos=true", headers=ana).json()) == 1
    carla = login(client, "edificio_b", "carla@x.cl")
    assert client.get(f"{A}/comunicados", headers=carla).status_code == 403


def test_editar_y_retirar_comunicado(client, seed):
    ana = login(client, "edificio_a", "ana@x.cl")
    cid = client.post(f"{A}/comunicados", headers=ana, json={"titulo": "Aviso", "cuerpo": "uno"}).json()["id"]
    assert client.patch(f"{A}/comunicados/{cid}", headers=ana, json={"cuerpo": "dos"}).json()["cuerpo"] == "dos"
    assert client.delete(f"{A}/comunicados/{cid}", headers=ana).status_code == 200
    assert client.delete(f"{A}/comunicados/{cid}", headers=ana).status_code == 404


# ---------------- encomiendas
def test_encomienda_ciclo_completo_con_firma(client, seed, db):
    _conserje(db, seed)
    db.add(Residente(edificio_id="edificio_a", unidad_id=seed["edificio_a", "101"].id, nombre="Dora Vecina",
                     rut="7.777.777-7", email="dora@x.cl", password_hash=hash_password("secreto123")))
    db.commit()
    con, beto, ana = login_c(client), login(client, "edificio_a", "beto@x.cl"), login(client, "edificio_a", "dora@x.cl")
    uid = seed["edificio_a", "102"].id  # unidad de Beto
    r = client.post(f"{A}/encomiendas", headers=con, json={"unidad_id": uid, "transportista": "Chilexpress"})
    assert r.status_code == 201
    eid = r.json()["id"]
    # el residente ve la suya; otra unidad no la ve
    assert [e["transportista"] for e in client.get(f"{A}/encomiendas?estado=pendiente", headers=beto).json()] == ["Chilexpress"]
    assert client.get(f"{A}/encomiendas", headers=ana).json() == []
    assert client.get(f"{A}/encomiendas?unidad_id={uid}", headers=ana).status_code == 403
    # el panel de fachada marca el paquete pendiente
    assert [u["encomiendas"] for u in client.get(f"{A}/panel", headers=con).json()["unidades"] if u["id"] == uid] == [1]
    # el residente no puede registrar ni entregar
    assert client.post(f"{A}/encomiendas", headers=beto, json={"unidad_id": uid}).status_code == 403
    assert client.post(f"{A}/encomiendas/{eid}/entregar", headers=beto, json={"retirada_por": "Beto"}).status_code == 403
    # entrega: queda fecha/hora y firmante; no se entrega dos veces
    e = client.post(f"{A}/encomiendas/{eid}/entregar", headers=con, json={"retirada_por": "Beto Soto"})
    assert e.status_code == 200 and e.json()["entregada_at"].endswith("Z")
    assert client.post(f"{A}/encomiendas/{eid}/entregar", headers=con, json={"retirada_por": "Beto Soto"}).status_code == 409
    fila = client.get(f"{A}/encomiendas?estado=entregada", headers=beto).json()[0]
    assert fila["retirada_por"] == "Beto Soto"


def test_encomienda_unidad_de_otro_edificio_rechazada(client, seed, db):
    _conserje(db, seed)
    con = login_c(client)
    ajena = seed["edificio_b", "101"].id
    assert client.post(f"{A}/encomiendas", headers=con, json={"unidad_id": ajena}).status_code == 404


# ---------------- avisos de pago
def test_aviso_de_pago_aprobado_abona_y_es_idempotente(client, seed, db):
    uid = _cargo(db, seed, "102", 50000, date.today() - timedelta(days=5))
    ana, beto = login(client, "edificio_a", "ana@x.cl"), login(client, "edificio_a", "beto@x.cl")
    body = {"monto": 30000, "banco": "Banco Estado", "nro_operacion": "OP-123456",
            "fecha_transferencia": date.today().isoformat()}
    r = client.post(f"{A}/avisos-pago", headers=beto, json=body)
    assert r.status_code == 201
    aid = r.json()["id"]
    assert client.post(f"{A}/avisos-pago", headers=beto, json=body).status_code == 409  # misma operación
    assert client.post(f"{A}/avisos-pago/{aid}/resolver", headers=beto, json={"aprobar": True}).status_code == 403
    assert len(client.get(f"{A}/avisos-pago?estado=pendiente", headers=ana).json()) == 1
    ok = client.post(f"{A}/avisos-pago/{aid}/resolver", headers=ana, json={"aprobar": True})
    assert ok.status_code == 200 and ok.json()["estado"] == "aprobado"
    assert finance.deuda_unidad(db, uid) == 20000
    assert client.post(f"{A}/avisos-pago/{aid}/resolver", headers=ana, json={"aprobar": True}).status_code == 409
    db.expire_all()
    assert finance.deuda_unidad(db, uid) == 20000  # no se abonó dos veces


def test_aviso_rechazado_exige_motivo_y_no_abona(client, seed, db):
    uid = _cargo(db, seed, "102", 50000, date.today())
    ana, beto = login(client, "edificio_a", "ana@x.cl"), login(client, "edificio_a", "beto@x.cl")
    aid = client.post(f"{A}/avisos-pago", headers=beto, json={
        "monto": 50000, "banco": "BCI", "nro_operacion": "777888", "fecha_transferencia": date.today().isoformat()}).json()["id"]
    assert client.post(f"{A}/avisos-pago/{aid}/resolver", headers=ana, json={"aprobar": False}).status_code == 422
    r = client.post(f"{A}/avisos-pago/{aid}/resolver", headers=ana, json={"aprobar": False, "motivo": "No llegó"})
    assert r.json()["estado"] == "rechazado"
    assert finance.deuda_unidad(db, uid) == 50000
    mine = client.get(f"{A}/avisos-pago", headers=beto).json()
    assert mine[0]["estado"] == "rechazado" and mine[0]["motivo"] == "No llegó"


def test_aviso_pago_validaciones_y_aislamiento_de_unidad(client, seed):
    beto = login(client, "edificio_a", "beto@x.cl")
    base = {"monto": 1000, "banco": "BCI", "nro_operacion": "ABC123", "fecha_transferencia": date.today().isoformat()}
    assert client.post(f"{A}/avisos-pago", headers=beto, json={**base, "unidad_id": seed["edificio_a", "101"].id}).status_code == 403
    futuro = (date.today() + timedelta(days=2)).isoformat()
    assert client.post(f"{A}/avisos-pago", headers=beto, json={**base, "fecha_transferencia": futuro}).status_code == 422
    assert client.post(f"{A}/avisos-pago", headers=beto, json={**base, "monto": 0}).status_code == 422


# ---------------- Mi Depto
def test_mi_depto_desglose_y_estado(client, seed, db):
    _cargo(db, seed, "102", 40000, date.today() + timedelta(days=10), "GC:ordinario:Administración")
    _cargo(db, seed, "102", 12000, date.today() + timedelta(days=10), "GC:ordinario:Agua caliente")
    _cargo(db, seed, "102", 2000, date.today() + timedelta(days=10), finance.CONCEPTO_FONDO)
    beto = login(client, "edificio_a", "beto@x.cl")
    d = client.get(f"{A}/mi-depto", headers=beto).json()
    assert d["unidad"]["numero"] == "102"
    assert d["cuenta"]["estado"] == "al_dia" and d["cuenta"]["deuda"] == 54000
    assert d["cuenta"]["desglose"] == {"cuota_base": 40000, "agua": 12000, "fondo_reserva": 2000,
                                       "intereses_multas": 0, "otros": 0}
    _cargo(db, seed, "102", 9000, date.today() - timedelta(days=3), "GC:ordinario:Otro")
    d = client.get(f"{A}/mi-depto", headers=beto).json()
    assert d["cuenta"]["estado"] == "moroso" and d["cuenta"]["vencida"] == 9000 and d["cuenta"]["deuda"] == 63000


def test_mi_depto_no_expone_otra_unidad(client, seed):
    beto = login(client, "edificio_a", "beto@x.cl")
    assert client.get(f"{A}/mi-depto?unidad_id={seed['edificio_a', '101'].id}", headers=beto).status_code == 403
    assert client.get(f"{A}/mi-depto").status_code == 401
    ana = login(client, "edificio_a", "ana@x.cl")  # admin puede consultar cualquier unidad
    assert client.get(f"{A}/mi-depto?unidad_id={seed['edificio_a', '102'].id}", headers=ana).json()["unidad"]["numero"] == "102"


def test_mi_depto_incluye_vehiculos_tags_y_paquetes(client, seed, db):
    from app.models import Edificio, TipoTag, Tag
    ed = db.get(Edificio, "edificio_a")
    uid = seed["edificio_a", "102"].id
    tag = Tag(edificio_id="edificio_a", unidad_id=uid, uid="E2801170AAAA0001", tipo=TipoTag.vehicular)
    db.add(tag)
    db.flush()
    access.registrar_vehiculo(db, ed, uid, "BBCD12", "Mazda 3", tag.id)
    db.commit()
    ana, beto = login(client, "edificio_a", "ana@x.cl"), login(client, "edificio_a", "beto@x.cl")
    client.post(f"{A}/comunicados", headers=ana, json={"titulo": "Hola", "cuerpo": "x"})
    d = client.get(f"{A}/mi-depto", headers=beto).json()
    assert d["vehiculos"][0]["patente"] == "BBCD12" and d["vehiculos"][0]["sticker"] is True
    assert d["tags"][0]["patente"] == "BBCD12" and d["tags"][0]["estado"] == "activo"
    assert d["comunicados"][0]["titulo"] == "Hola"


# ---------------- gastos: fondo de reserva e intereses
def test_fondo_de_reserva_se_suma_a_gastos_ordinarios(client, seed, db):
    ana = login(client, "edificio_a", "ana@x.cl")
    r = client.post(f"{A}/gastos-comunes/generar", headers=ana, json={
        "periodo": "2026-10", "vencimiento": "2026-11-10", "fondo_reserva_pct": 10,
        "gastos": [{"concepto": "Administración", "monto": 100000},
                   {"concepto": "Reparación", "monto": 50000, "tipo": "extraordinario"}]})
    assert r.status_code == 200 and r.json()["total"] == 160000  # 150.000 + 10 % de los ordinarios
    fondo = db.query(Cargo).filter(Cargo.concepto == finance.CONCEPTO_FONDO).all()
    assert sum(float(c.monto) for c in fondo) == 10000
    u101 = seed["edificio_a", "101"].id
    assert finance.estado_cuenta(db, u101)["desglose"]["fondo_reserva"] == 5000  # coeficiente 0.5


def test_intereses_mora_sobre_capital_vencido_e_idempotente(client, seed, db):
    ana = login(client, "edificio_a", "ana@x.cl")
    vencida = _cargo(db, seed, "102", 100000, date.today() - timedelta(days=40))
    _cargo(db, seed, "103", 80000, date.today() + timedelta(days=5))  # aún no vence
    r = client.post(f"{A}/cobranza/intereses", headers=ana, json={"tasa_mensual_pct": 1.5, "periodo": "2026-11"})
    assert r.json()["unidades"] == 1 and r.json()["total"] == 1500
    r2 = client.post(f"{A}/cobranza/intereses", headers=ana, json={"tasa_mensual_pct": 1.5, "periodo": "2026-11"})
    assert r2.json()["unidades"] == 0 and r2.json()["ya_aplicados"] == 1
    assert finance.estado_cuenta(db, vencida)["desglose"]["intereses_multas"] == 1500
    # el mes siguiente se calcula sobre el capital, sin interés sobre interés
    r3 = client.post(f"{A}/cobranza/intereses", headers=ana, json={"tasa_mensual_pct": 1.5, "periodo": "2026-12"})
    assert r3.json()["total"] == 1500
    beto = login(client, "edificio_a", "beto@x.cl")
    assert client.post(f"{A}/cobranza/intereses", headers=beto, json={"tasa_mensual_pct": 1, "periodo": "2026-11"}).status_code == 403


def test_resumen_de_finanzas(client, seed, db):
    _cargo(db, seed, "102", 100000, date.today() - timedelta(days=40))
    _cargo(db, seed, "103", 50000, date.today() + timedelta(days=5))
    ana = login(client, "edificio_a", "ana@x.cl")
    r = client.get(f"{A}/finanzas/resumen", headers=ana).json()
    assert r["deuda_total"] == 150000 and r["deuda_vencida"] == 100000
    assert r["unidades"] == 3 and r["unidades_morosas"] == 1 and r["morosidad_pct"] == 33.3


# ---------------- espacios: aforo, disponibilidad
def _quincho(db, aforo=10):
    db.add(EspacioComun(edificio_id="edificio_a", nombre="Quincho", accion="reservar_quincho", tarifa=15000, aforo=aforo))
    db.add(Regla(edificio_id="edificio_a", accion="reservar_quincho", tipo="horario",
                 params={"desde": "00:00", "hasta": "23:59"}))
    db.commit()
    return db.query(EspacioComun).one().id


def _reservar(client, h, eid, asistentes, horas=30):
    d = (utcnow() + timedelta(hours=horas)).replace(minute=0, second=0, microsecond=0)
    return client.post(f"{A}/reservas-espacio", headers=h, json={
        "espacio_id": eid, "desde": d.isoformat(), "hasta": (d + timedelta(hours=2)).isoformat(),
        "asistentes": asistentes}), d


def test_aforo_bloquea_reservas_con_demasiada_gente(client, seed, db):
    eid = _quincho(db, aforo=10)
    beto = login(client, "edificio_a", "beto@x.cl")
    r, _ = _reservar(client, beto, eid, 11)
    assert r.status_code == 422 and "Aforo" in r.json()["detail"]["motivos"][0]
    r, _ = _reservar(client, beto, eid, 10)
    assert r.status_code == 201


def test_aforo_cero_es_sin_limite_y_admin_lo_edita(client, seed, db):
    eid = _quincho(db, aforo=0)
    beto, ana = login(client, "edificio_a", "beto@x.cl"), login(client, "edificio_a", "ana@x.cl")
    assert _reservar(client, beto, eid, 80)[0].status_code == 201
    assert client.patch(f"{A}/espacios/{eid}", headers=beto, json={"aforo": 5}).status_code == 403
    assert client.patch(f"{A}/espacios/{eid}", headers=ana, json={"aforo": 5, "tarifa": 20000}).json()["aforo"] == 5
    assert client.patch(f"{A}/espacios/{eid}", headers=ana, json={"aforo": -1}).status_code == 422


def test_disponibilidad_muestra_franjas_ocupadas_y_horario(client, seed, db):
    eid = _quincho(db)
    beto, ana = login(client, "edificio_a", "beto@x.cl"), login(client, "edificio_a", "ana@x.cl")
    r, d = _reservar(client, beto, eid, 4)
    assert r.status_code == 201
    dia = client.get(f"{A}/espacios-comunes/{eid}/disponibilidad?fecha={d.date().isoformat()}", headers=ana).json()
    assert len(dia["ocupadas"]) == 1 and dia["horario"] == {"desde": "00:00", "hasta": "23:59"}
    assert "unidad" not in dia["ocupadas"][0]  # no se revela quién reservó
    # un segundo vecino ya no puede tomar la misma franja
    assert _reservar(client, ana, eid, 2)[0].status_code == 409
    lista = client.get(f"{A}/espacios-comunes", headers=beto).json()
    assert lista[0]["nombre"] == "Quincho" and lista[0]["aforo"] == 10


# ---------------- pase de visita por WhatsApp
def test_enlace_whatsapp_de_visita(client, seed, db):
    from app.models import Edificio
    ed = db.get(Edificio, "edificio_a")
    ini = utcnow() + timedelta(hours=3)
    v = access.reservar_visita(db, ed, seed["edificio_a", "102"].id, "Marcela Torres", ini, ini + timedelta(hours=2), "klpr45")
    db.commit()
    beto, ana = login(client, "edificio_a", "beto@x.cl"), login(client, "edificio_a", "ana@x.cl")
    r = client.get(f"{A}/visitas/{v.id}/whatsapp?telefono=%2B56%209%201234%205678", headers=beto).json()
    assert r["url"].startswith("https://wa.me/56912345678?text=")
    assert v.codigo_qr in r["mensaje"] and "KLPR45" in r["mensaje"] and "Marcela" in r["mensaje"]
    assert "secreto" not in r["url"]
    # otra unidad (Ana es admin y puede; un residente de otra unidad no)
    assert client.get(f"{A}/visitas/{v.id}/whatsapp", headers=ana).status_code == 200
    assert client.get(f"{A}/visitas/9999/whatsapp", headers=beto).status_code == 404
