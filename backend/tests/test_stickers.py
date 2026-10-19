"""Stickers UHF, modos de acceso vehicular, correlación sticker↔patente, antirrebote, anti-passback,
bloqueo, importación y aislamiento entre edificios."""
from datetime import timedelta
from pathlib import Path

import pytest

from app.config import utcnow
from app.models import AccesoLog, Edificio, Evento, LecturaPendiente, Tag, TipoTag
from app.services import access, stickers
from app.services.credenciales import CredencialInvalida, normalizar, normalizar_epc, normalizar_wiegand

from conftest import login

RAIZ = Path(__file__).resolve().parents[2]


def epc(i: int) -> str:
    return f"E2801170{i:016X}"  # 24 hexadecimales, longitud par


@pytest.fixture(autouse=True)
def sin_antirrebote(db, seed):
    """Estas pruebas miden la lógica de cada lectura; el antirrebote tiene sus propias pruebas."""
    ed = db.get(Edificio, "edificio_a")
    ed.antirrebote_s = 0
    db.commit()


def leer(client, token, tipo="sticker", punto="vehicular", direccion=None, confianza=None, clave="keyA",
         edificio="edificio_a"):
    body = {"edificio_id": edificio, "token_acceso": token, "punto": punto}
    if tipo:
        body["tipo"] = tipo
    if direccion:
        body["direccion"] = direccion
    if confianza is not None:
        body["confianza"] = confianza
    return client.post(f"/api/v1/{edificio}/validar-acceso", json=body, headers={"X-Device-Key": clave})


def _vehiculo(db, seed, unidad_numero, patente, codigo, residente_id=None, edificio="edificio_a"):
    ed = db.get(Edificio, edificio)
    u = seed[edificio, unidad_numero]
    tag = access.asignar_tag(db, ed, u.id, codigo, TipoTag.vehicular, residente_id)
    veh = access.registrar_vehiculo(db, ed, u.id, patente, "auto de prueba", tag.id)
    db.commit()
    return tag, veh


def _modo(db, modo, **extra):
    ed = db.get(Edificio, "edificio_a")
    ed.modo_acceso = modo
    for k, v in extra.items():
        setattr(ed, k, v)
    db.commit()
    return ed


# ---------- normalización ----------
def test_epc_y_wiegand_canonicos():
    assert normalizar_epc("e2 80-11:70 00000000 000000a1") == "E280117000000000000000A1"
    assert normalizar_wiegand("w26:42:12345") == "W26:42:12345"
    assert normalizar("E280117000000000000000A1", "epc") == "E280117000000000000000A1"


@pytest.mark.parametrize("texto", ["ZZ11223344AA", "E28011", "E280117000000000000000A", "E2801170000000000000000A1B2"])
def test_epc_invalido(texto):
    with pytest.raises(CredencialInvalida):
        normalizar_epc(texto)


@pytest.mark.parametrize("texto", ["W26:300:1", "W26:1:70000", "W34:70000:1", "W99:1:1", "W26:1"])
def test_wiegand_fuera_de_rango_o_mal_formado(texto):
    with pytest.raises(CredencialInvalida):
        normalizar_wiegand(texto)


def test_wiegand_34_admite_mas_bits():
    assert normalizar_wiegand("W34:65535:4294967295") == "W34:65535:4294967295"


# ---------- alta y unicidad ----------
def test_alta_de_sticker_valida_formato_y_rechaza_duplicados(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    u101 = seed["edificio_a", "101"].id
    ok = client.post("/edificios/edificio_a/tags", headers=h,
                     json={"unidad_id": u101, "uid": epc(1).lower(), "tipo": "vehicular"})
    assert ok.status_code == 201, ok.text
    fila = next(t for t in client.get("/edificios/edificio_a/tags", headers=h).json() if t["uid"] == epc(1))
    assert fila["formato"] == "epc" and fila["estado"] == "activo" and fila["fecha_alta"]
    assert client.post("/edificios/edificio_a/tags", headers=h,
                       json={"unidad_id": u101, "uid": epc(1), "tipo": "vehicular"}).status_code == 409
    corto = client.post("/edificios/edificio_a/tags", headers=h,
                        json={"unidad_id": u101, "uid": "E28011", "tipo": "vehicular"})
    assert corto.status_code == 422 and "EPC" in corto.json()["detail"]


def test_mismo_codigo_en_otro_edificio_se_rechaza(client, seed, db):
    _vehiculo(db, seed, "101", "AAAA11", epc(2), edificio="edificio_a")
    h = login(client, "edificio_b", "carla@x.cl")
    r = client.post("/edificios/edificio_b/tags", headers=h,
                    json={"unidad_id": seed["edificio_b", "101"].id, "uid": epc(2), "tipo": "vehicular"})
    assert r.status_code == 409


# ---------- modos de acceso ----------
def test_modo_sticker_o_patente_abre_con_cualquiera_de_las_dos(client, seed, db):
    _vehiculo(db, seed, "101", "BBCD12", epc(10))
    assert leer(client, epc(10)).status_code == 200
    assert leer(client, "BBCD12", tipo="patente", confianza=0.95).status_code == 200
    assert leer(client, epc(99)).status_code == 403  # sticker desconocido


def test_modo_solo_sticker_no_abre_con_patente(client, seed, db):
    _modo(db, "solo_sticker")
    _vehiculo(db, seed, "101", "BBCD12", epc(11))
    assert leer(client, "BBCD12", tipo="patente", confianza=0.95).json()["detail"] == \
        "Este edificio abre sólo con sticker"
    assert leer(client, epc(11)).status_code == 200


def test_modo_solo_patente_no_abre_con_sticker(client, seed, db):
    _modo(db, "solo_patente")
    _vehiculo(db, seed, "101", "BBCD12", epc(12))
    assert leer(client, epc(12)).json()["detail"] == "Este edificio abre sólo con patente"
    assert leer(client, "BBCD12", tipo="patente", confianza=0.95).status_code == 200


def test_sticker_perdido_deja_de_abrir_de_inmediato(client, seed, db):
    _vehiculo(db, seed, "101", "BBCD12", epc(13))
    h = login(client, "edificio_a", "ana@x.cl")
    tid = next(t["id"] for t in client.get("/edificios/edificio_a/tags", headers=h).json() if t["uid"] == epc(13))
    assert leer(client, epc(13)).status_code == 200
    assert client.post(f"/edificios/edificio_a/tags/{tid}/perder", headers=h, json={"motivo": "lo perdió"}).status_code == 200
    r = leer(client, epc(13))
    assert r.status_code == 403 and "perdido" in r.json()["detail"]
    assert client.post(f"/edificios/edificio_a/tags/{tid}/activar", headers=h).status_code == 200
    assert leer(client, epc(13)).status_code == 200
    client.post(f"/edificios/edificio_a/tags/{tid}/bloquear", headers=h, json={})
    assert "bloqueado" in leer(client, epc(13)).json()["detail"]
    eventos = [e.payload for e in db.query(Evento).filter_by(tipo="tag.estado")]
    assert [e["a"] for e in eventos] == ["perdido", "activo", "bloqueado"]


# ---------- sticker_y_patente ----------
def test_y_abre_cuando_sticker_y_patente_son_del_mismo_vehiculo(client, seed, db):
    _modo(db, "sticker_y_patente")
    _vehiculo(db, seed, "101", "BBCD12", epc(20))
    primero = leer(client, epc(20))
    assert primero.status_code == 403 and "Esperando la patente" in primero.json()["detail"]
    segundo = leer(client, "BBCD12", tipo="patente", confianza=0.95)
    assert segundo.status_code == 200 and segundo.json()["motivo"] == "Sticker y patente coinciden"


def test_y_orden_inverso_tambien_abre(client, seed, db):
    _modo(db, "sticker_y_patente")
    _vehiculo(db, seed, "101", "BBCD12", epc(21))
    assert leer(client, "BBCD12", tipo="patente", confianza=0.95).status_code == 403
    assert leer(client, epc(21)).status_code == 200


def test_y_detecta_clonacion_sticker_de_otro_vehiculo(client, seed, db):
    """Sticker válido del vehículo A pegado en el vehículo B: la patente de B no debe abrir."""
    _modo(db, "sticker_y_patente")
    _vehiculo(db, seed, "101", "AAAA11", epc(30))   # dueño legítimo del sticker
    _vehiculo(db, seed, "102", "BBBB22", epc(31))   # el auto que intenta pasar
    assert leer(client, epc(30)).status_code == 403   # se lee el sticker clonado
    r = leer(client, "BBBB22", tipo="patente", confianza=0.95)
    assert r.status_code == 403 and "vehículos distintos" in r.json()["detail"]
    assert db.query(LecturaPendiente).count() == 0    # ambas lecturas se consumen


def test_y_la_lectura_se_consume_y_no_sirve_dos_veces(client, seed, db):
    _modo(db, "sticker_y_patente")
    _vehiculo(db, seed, "101", "BBCD12", epc(40))
    leer(client, epc(40))
    assert leer(client, "BBCD12", tipo="patente", confianza=0.95).status_code == 200
    # la siguiente patente sola ya no basta: el sticker tiene que volver a leerse
    assert leer(client, "BBCD12", tipo="patente", confianza=0.95).status_code == 403


def test_y_fuera_de_la_ventana_no_coincide(client, seed, db):
    _modo(db, "sticker_y_patente", ventana_coincidencia_s=10)
    _vehiculo(db, seed, "101", "BBCD12", epc(41))
    leer(client, epc(41))
    viejo = db.query(LecturaPendiente).one()
    viejo.creado = utcnow() - timedelta(seconds=30)  # la lectura del sticker quedó atrás de la ventana
    db.commit()
    r = leer(client, "BBCD12", tipo="patente", confianza=0.95)
    assert r.status_code == 403 and "Esperando el sticker" in r.json()["detail"]


def test_y_ventana_configurable(client, seed, db):
    _modo(db, "sticker_y_patente", ventana_coincidencia_s=60)
    _vehiculo(db, seed, "101", "BBCD12", epc(42))
    leer(client, epc(42))
    pend = db.query(LecturaPendiente).one()
    pend.creado = utcnow() - timedelta(seconds=30)  # dentro de 60 s, fuera de 10 s
    db.commit()
    assert leer(client, "BBCD12", tipo="patente", confianza=0.95).status_code == 200


def test_y_sticker_sin_vehiculo_asociado_no_puede_abrir(client, seed, db):
    _modo(db, "sticker_y_patente")
    ed = db.get(Edificio, "edificio_a")
    access.asignar_tag(db, ed, seed["edificio_a", "101"].id, epc(50), TipoTag.vehicular)
    db.commit()
    r = leer(client, epc(50))
    assert r.status_code == 403 and "sin vehículo asociado" in r.json()["detail"]


# ---------- confianza, antirrebote, anti-passback ----------
def test_patente_bajo_el_umbral_se_rechaza(client, seed, db):
    _vehiculo(db, seed, "101", "BBCD12", epc(60))
    r = leer(client, "BBCD12", tipo="patente", confianza=0.40)
    assert r.status_code == 403 and "bajo el umbral" in r.json()["detail"]


def test_lectura_repetida_no_abre_dos_veces(client, seed, db):
    _modo(db, "sticker_o_patente", antirrebote_s=3)
    _vehiculo(db, seed, "101", "BBCD12", epc(70))
    assert leer(client, epc(70)).status_code == 200
    r = leer(client, epc(70))
    assert r.status_code == 409 and r.json()["codigo"] == "duplicada"
    bitacora = db.query(AccesoLog).filter(AccesoLog.token == epc(70)).order_by(AccesoLog.id).all()
    assert [b.permitido for b in bitacora] == [True, False]
    assert bitacora[1].motivo.startswith("Lectura duplicada")


def test_antirrebote_cero_permite_lecturas_seguidas(client, seed, db):
    _modo(db, "sticker_o_patente", antirrebote_s=0)
    _vehiculo(db, seed, "101", "BBCD12", epc(71))
    assert leer(client, epc(71)).status_code == 200
    assert leer(client, epc(71)).status_code == 200


def test_anti_passback_impide_entrar_dos_veces_sin_salir(client, seed, db):
    _modo(db, "sticker_o_patente", anti_passback=True)
    _vehiculo(db, seed, "101", "BBCD12", epc(80))
    assert leer(client, epc(80), direccion="entrada").status_code == 200
    r = leer(client, epc(80), direccion="entrada")
    assert r.status_code == 403 and "Anti-passback" in r.json()["detail"]
    assert leer(client, epc(80), direccion="salida").status_code == 200
    assert leer(client, epc(80), direccion="entrada").status_code == 200


def test_anti_passback_sin_direccion_no_bloquea(client, seed, db):
    _modo(db, "sticker_o_patente", anti_passback=True)
    _vehiculo(db, seed, "101", "BBCD12", epc(81))
    assert leer(client, epc(81)).status_code == 200
    assert leer(client, epc(81)).status_code in (200, 409)  # sólo el antirrebote, nunca anti-passback


# ---------- reasignar y aislamiento ----------
def test_reasignar_sticker_cambia_de_departamento_y_desvincula_el_auto(client, seed, db):
    tag, veh = _vehiculo(db, seed, "101", "BBCD12", epc(90))
    h = login(client, "edificio_a", "ana@x.cl")
    tid = tag.id
    r = client.post(f"/edificios/edificio_a/tags/{tid}/reasignar", headers=h,
                    json={"unidad_id": seed["edificio_a", "102"].id})
    assert r.status_code == 200
    db.refresh(veh)
    assert veh.tag_id is None
    fila = next(t for t in client.get("/edificios/edificio_a/tags", headers=h).json() if t["id"] == tid)
    assert fila["unidad"] == "102" and fila["patente"] == ""


def test_reasignar_a_residente_de_otra_unidad_falla(client, seed, db):
    tag, _ = _vehiculo(db, seed, "101", "BBCD12", epc(91))
    h = login(client, "edificio_a", "ana@x.cl")
    beto = next(r for r in client.get("/edificios/edificio_a/residentes", headers=h).json() if r["nombre"] == "Beto Soto")
    r = client.post(f"/edificios/edificio_a/tags/{tag.id}/reasignar", headers=h,
                    json={"unidad_id": seed["edificio_a", "101"].id, "residente_id": beto["id"]})
    assert r.status_code == 422


def test_aislamiento_entre_edificios(client, seed, db):
    _vehiculo(db, seed, "101", "BBCD12", epc(100), edificio="edificio_a")
    # la clave del edificio B no sirve para el lector de A
    assert leer(client, epc(100), clave="keyB", edificio="edificio_a").status_code == 401
    # el lector de B no puede abrir con un sticker de A
    r = leer(client, epc(100), edificio="edificio_b", clave="keyB")
    assert r.status_code == 403
    # un admin de B no ve ni cambia el sticker de A
    hb = login(client, "edificio_b", "carla@x.cl")
    tid = db.query(Tag).filter_by(edificio_id="edificio_a").one().id
    assert client.post(f"/edificios/edificio_b/tags/{tid}/perder", headers=hb, json={}).status_code == 404
    assert client.post(f"/edificios/edificio_b/tags/{tid}/reasignar", headers=hb,
                       json={"unidad_id": seed["edificio_b", "101"].id}).status_code == 404


def test_bitacora_registra_fuente_y_motivo(client, seed, db):
    _modo(db, "solo_sticker")
    _vehiculo(db, seed, "101", "BBCD12", epc(110))
    leer(client, "BBCD12", tipo="patente", confianza=0.95)
    registro = db.query(AccesoLog).order_by(AccesoLog.id.desc()).first()
    assert registro.fuente == "patente" and not registro.permitido
    assert "sólo con sticker" in registro.motivo


# ---------- importación ----------
def _csv(*filas):
    return "epc;depto;patente;rut_residente\n" + "\n".join(filas) + "\n"


def test_importar_rechaza_repetidos_en_lote_y_contra_la_base(db, seed):
    ed = db.get(Edificio, "edificio_a")
    _vehiculo(db, seed, "102", "ZZZZ99", epc(120))
    texto = _csv(f"{epc(121)};101;;", f"{epc(121)};101;;", f"{epc(120)};101;;", "E28011;101;;")
    rep = stickers.importar(db, ed, texto)
    lineas = dict(rep.errores)
    assert set(lineas) == {2, 3, 4, 5}
    assert "repetido en el lote" in lineas[2] and "repetido en el lote" in lineas[3]
    assert "otro departamento" in lineas[4]
    assert rep.creados == 0 and db.query(Tag).filter_by(uid=epc(121)).count() == 0


def test_importar_es_idempotente(db, seed):
    ed = db.get(Edificio, "edificio_a")
    texto = _csv(f"{epc(130)};101;BBCD12;12.345.678-5", f"{epc(131)};102;;")
    primera = stickers.importar(db, ed, texto)
    assert primera.errores == [] and primera.creados == 2 and primera.vinculados_patente == 1
    segunda = stickers.importar(db, ed, texto)
    assert segunda.errores == [] and segunda.creados == 0 and segunda.sin_cambios == 2


def test_importar_valida_residente_y_patente(db, seed):
    ed = db.get(Edificio, "edificio_a")
    rep = stickers.importar(db, ed, _csv(
        f"{epc(140)};102;;12.345.678-5",       # Ana vive en 101, no en 102
        f"{epc(141)};999;;",                   # depto inexistente
        f"{epc(142)};103;;",                   # 103 no tiene estacionamientos: no admite sticker vehicular
        f"W26:42:12345;102;CDFG34;"))          # wiegand con patente
    lineas = dict(rep.errores)
    assert set(lineas) == {2, 3, 4}
    assert "no pertenece" in lineas[2] and "no existe" in lineas[3] and "máx. 0" in lineas[4]
    assert db.query(Tag).filter_by(uid="W26:42:12345").one().formato == "wiegand"


def test_plantilla_de_stickers_se_importa_sin_errores(db, seed):
    ed = db.get(Edificio, "edificio_a")
    texto = (RAIZ / "docs" / "plantillas" / "stickers.csv").read_text(encoding="utf-8")
    rep = stickers.importar(db, ed, texto, dry_run=True)
    assert rep.errores == [] and rep.creados == 3
    assert db.query(Tag).count() == 0  # dry-run no escribe
