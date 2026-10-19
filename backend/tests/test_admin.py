"""Panel de administración: alta/edición de residentes, tags y reglas con validación clara."""
from app.models import EspacioComun, Regla, Residente, Tag
from app.rules import validar_params

from conftest import login

RUT_NUEVO = "22222222-2"   # DV verificado (módulo 11)
RUT_OTRO = "11111111-1"


def _residente(client, h, unidad_id, **extra):
    body = {"unidad_id": unidad_id, "nombre": "Nuevo Vecino", "rut": RUT_NUEVO, "email": "nuevo@x.cl",
            "telefono": "+56 9 7777 8888", "password": "secreto123"} | extra
    return client.post("/edificios/edificio_a/residentes", headers=h, json=body)


def test_login_devuelve_rol(client, seed):
    r = client.post("/auth/login", json={"edificio_id": "edificio_a", "email": "ana@x.cl", "password": "secreto123"})
    assert r.json()["rol"] == "admin" and r.json()["nombre"] == "Ana Pérez"


# ---------- residentes ----------
def test_crear_residente_valida_y_normaliza(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    uid = seed["edificio_a", "102"].id
    r = _residente(client, h, uid)
    assert r.status_code == 201, r.text
    lista = client.get("/edificios/edificio_a/residentes", headers=h).json()
    nuevo = next(x for x in lista if x["nombre"] == "Nuevo Vecino")
    assert nuevo["rut"] == "22.222.222-2" and nuevo["telefono"] == "56977778888" and nuevo["unidad"] == "102"


def test_crear_residente_errores_claros(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    uid = seed["edificio_a", "102"].id
    malo = _residente(client, h, uid, rut="12.345.678-4")
    assert malo.status_code == 422 and "RUT inválido" in malo.json()["detail"]
    dup = _residente(client, h, uid, rut="12.345.678-5")          # Ana ya tiene ese RUT en el edificio
    assert dup.status_code == 409 and "ya está registrado" in dup.json()["detail"]
    assert _residente(client, h, uid, email="no-es-correo").status_code == 422
    assert _residente(client, h, uid, telefono="12").status_code == 422
    assert _residente(client, h, seed["edificio_b", "101"].id).status_code == 422   # depto de otro edificio
    assert _residente(client, h, uid, rol="superadmin").status_code == 422
    assert _residente(client, h, uid, nombre="   ").status_code == 422


def test_editar_residente_cambia_unidad_y_rut_unico(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    beto = next(r for r in client.get("/edificios/edificio_a/residentes", headers=h).json() if r["nombre"] == "Beto Soto")
    ok = client.patch(f"/edificios/edificio_a/residentes/{beto['id']}", headers=h,
                      json={"unidad_id": seed["edificio_a", "103"].id, "email": "beto.nuevo@x.cl"})
    assert ok.status_code == 200
    beto2 = next(r for r in client.get("/edificios/edificio_a/residentes", headers=h).json() if r["id"] == beto["id"])
    assert beto2["unidad"] == "103" and beto2["email"] == "beto.nuevo@x.cl"
    choca = client.patch(f"/edificios/edificio_a/residentes/{beto['id']}", headers=h, json={"rut": "12.345.678-5"})
    assert choca.status_code == 409
    assert client.patch(f"/edificios/edificio_a/residentes/{beto['id']}", headers=h,
                        json={"nombre": None}).status_code == 200   # null = no cambiar


def test_no_se_puede_dejar_el_edificio_sin_administrador(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    ana = next(r for r in client.get("/edificios/edificio_a/residentes", headers=h).json() if r["nombre"] == "Ana Pérez")
    r = client.patch(f"/edificios/edificio_a/residentes/{ana['id']}", headers=h, json={"activo": False})
    assert r.status_code == 409 and "administrador activo" in r.json()["detail"]
    assert client.patch(f"/edificios/edificio_a/residentes/{ana['id']}", headers=h, json={"rol": "residente"}).status_code == 409


def test_desactivar_residente_corta_su_acceso_al_instante(client, seed):
    h_admin = login(client, "edificio_a", "ana@x.cl")
    h_beto = login(client, "edificio_a", "beto@x.cl")
    assert client.get("/edificios/edificio_a/unidades/%d/deuda" % seed["edificio_a", "102"].id,
                      headers=h_beto).status_code == 200
    beto = next(r for r in client.get("/edificios/edificio_a/residentes", headers=h_admin).json() if r["nombre"] == "Beto Soto")
    assert client.patch(f"/edificios/edificio_a/residentes/{beto['id']}", headers=h_admin,
                        json={"activo": False}).status_code == 200
    assert client.get("/edificios/edificio_a/unidades/%d/deuda" % seed["edificio_a", "102"].id,
                      headers=h_beto).status_code == 401
    assert client.post("/auth/login", json={"edificio_id": "edificio_a", "email": "beto@x.cl",
                                            "password": "secreto123"}).status_code == 401


def test_cambio_de_rol_surte_efecto_sin_nuevo_login(client, seed):
    h_admin = login(client, "edificio_a", "ana@x.cl")
    h_beto = login(client, "edificio_a", "beto@x.cl")
    assert client.get("/edificios/edificio_a/residentes", headers=h_beto).status_code == 403
    beto = next(r for r in client.get("/edificios/edificio_a/residentes", headers=h_admin).json() if r["nombre"] == "Beto Soto")
    client.patch(f"/edificios/edificio_a/residentes/{beto['id']}", headers=h_admin, json={"rol": "admin"})
    assert client.get("/edificios/edificio_a/residentes", headers=h_beto).status_code == 200


def test_residente_no_administra_residentes(client, seed):
    h = login(client, "edificio_a", "beto@x.cl")
    assert client.get("/edificios/edificio_a/residentes", headers=h).status_code == 403
    assert _residente(client, h, seed["edificio_a", "102"].id).status_code == 403


def test_admin_no_toca_otro_edificio(client, seed, db):
    h = login(client, "edificio_a", "ana@x.cl")
    carla = db.query(Residente).filter_by(edificio_id="edificio_b").one()
    assert client.patch(f"/edificios/edificio_b/residentes/{carla.id}", headers=h,
                        json={"activo": False}).status_code == 403


# ---------- tags ----------
def test_tags_uid_y_residente_del_mismo_depto(client, seed, db):
    h = login(client, "edificio_a", "ana@x.cl")
    u101 = seed["edificio_a", "101"].id
    ana = db.query(Residente).filter_by(edificio_id="edificio_a", nombre="Ana Pérez").one()
    beto = db.query(Residente).filter_by(edificio_id="edificio_a", nombre="Beto Soto").one()
    assert client.post("/edificios/edificio_a/tags", headers=h,
                       json={"unidad_id": u101, "uid": "XYZ", "tipo": "peatonal"}).status_code == 422
    assert client.post("/edificios/edificio_a/tags", headers=h,
                       json={"unidad_id": u101, "uid": "GHIJKLMN", "tipo": "peatonal"}).status_code == 422
    assert client.post("/edificios/edificio_a/tags", headers=h,
                       json={"unidad_id": u101, "uid": "AB12CD34", "tipo": "peatonal",
                             "residente_id": beto.id}).status_code == 422
    ok = client.post("/edificios/edificio_a/tags", headers=h,
                     json={"unidad_id": u101, "uid": "ab12cd34", "tipo": "peatonal", "residente_id": ana.id})
    assert ok.status_code == 201
    dup = client.post("/edificios/edificio_a/tags", headers=h,
                      json={"unidad_id": u101, "uid": "AB12CD34", "tipo": "peatonal"})
    assert dup.status_code == 409 and "ya registrado" in dup.json()["detail"]


def test_editar_tag_desactivar_y_desvincular(client, seed, db):
    h = login(client, "edificio_a", "ana@x.cl")
    u101 = seed["edificio_a", "101"].id
    ana = db.query(Residente).filter_by(edificio_id="edificio_a", nombre="Ana Pérez").one()
    tid = client.post("/edificios/edificio_a/tags", headers=h,
                      json={"unidad_id": u101, "uid": "AB12CD34", "tipo": "peatonal", "residente_id": ana.id}).json()["id"]
    assert client.patch(f"/edificios/edificio_a/tags/{tid}", headers=h, json={"residente_id": None}).status_code == 200
    fila = next(t for t in client.get("/edificios/edificio_a/tags", headers=h).json() if t["id"] == tid)
    assert fila["residente_id"] is None and fila["activo"] is True
    client.patch(f"/edificios/edificio_a/tags/{tid}", headers=h, json={"activo": False})
    api = client.post("/api/v1/edificio_a/validar-acceso", json={"edificio_id": "edificio_a", "token_acceso": "AB12CD34"},
                      headers={"X-Device-Key": "keyA"})
    assert api.status_code == 403 and "desactivado" in api.json()["detail"]
    assert db.get(Tag, tid).activo is False


# ---------- reglas ----------
def _espacio(db, nombre="quincho", accion="reservar_quincho", tarifa=0):
    db.add(EspacioComun(edificio_id="edificio_a", nombre=nombre, accion=accion, tarifa=tarifa))
    db.commit()


def test_validar_params_por_tipo():
    assert validar_params("horario", {"desde": "10:00", "hasta": "22:00", "dias": [5, 6]}) == []
    assert validar_params("horario", {"desde": "22:00", "hasta": "10:00"})
    assert validar_params("horario", {"desde": "9:00", "hasta": "10:00"})
    assert validar_params("horario", {"desde": "10:00", "hasta": "11:00", "dias": [7]})
    assert validar_params("max_por_mes", {"max": 0}) and validar_params("max_por_mes", {"max": True})
    assert validar_params("bloquear_morosos", {"deuda_max": -1})
    assert validar_params("anticipacion", {}) and validar_params("anticipacion", {"min_horas": 48, "max_dias": 1})
    assert validar_params("horario", {"desde": "10:00", "hasta": "11:00", "color": "rojo"})
    assert validar_params("cualquiera", {}) == ["Tipo de regla desconocido: cualquiera"]


def test_crear_regla_errores_y_duplicados(client, seed, db):
    _espacio(db)
    h = login(client, "edificio_a", "ana@x.cl")
    base = {"accion": "reservar_quincho", "tipo": "max_por_mes", "params": {"max": 2}}
    assert client.post("/edificios/edificio_a/reglas", headers=h, json=base | {"accion": "piscina"}).status_code == 422
    assert "No hay un espacio común" in client.post("/edificios/edificio_a/reglas", headers=h,
                                                     json=base | {"accion": "piscina"}).json()["detail"]
    assert client.post("/edificios/edificio_a/reglas", headers=h,
                       json=base | {"params": {"max": 99}}).status_code == 422
    assert client.post("/edificios/edificio_a/reglas", headers=h, json=base).status_code == 201
    dup = client.post("/edificios/edificio_a/reglas", headers=h, json=base)
    assert dup.status_code == 422 and "edítala" in dup.json()["detail"]


def test_editar_regla_y_desactivar(client, seed, db):
    _espacio(db)
    h = login(client, "edificio_a", "ana@x.cl")
    rid = client.post("/edificios/edificio_a/reglas", headers=h, json={
        "accion": "reservar_quincho", "tipo": "horario", "params": {"desde": "10:00", "hasta": "22:00"}}).json()["id"]
    bad = client.patch(f"/edificios/edificio_a/reglas/{rid}", headers=h, json={"params": {"desde": "23:00", "hasta": "08:00"}})
    assert bad.status_code == 422
    assert db.get(Regla, rid).params == {"desde": "10:00", "hasta": "22:00"}      # no cambió
    ok = client.patch(f"/edificios/edificio_a/reglas/{rid}", headers=h,
                      json={"params": {"desde": "12:00", "hasta": "23:00"}, "activa": False})
    assert ok.status_code == 200 and ok.json()["activa"] is False
    lista = client.get("/edificios/edificio_a/reglas", headers=h).json()
    assert lista[0]["params"] == {"desde": "12:00", "hasta": "23:00"} and lista[0]["activa"] is False
    assert client.get("/edificios/edificio_a/espacios", headers=h).json()[0]["accion"] == "reservar_quincho"
    assert client.patch(f"/edificios/edificio_a/reglas/999", headers=h, json={"activa": True}).status_code == 404
