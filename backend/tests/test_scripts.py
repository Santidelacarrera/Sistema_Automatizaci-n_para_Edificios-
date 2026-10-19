"""Carga inicial (seed) e importación CSV: validación, idempotencia y errores por línea."""
from app import validacion
from app.models import Edificio, Residente, Rol, Unidad
from scripts import importar_csv, seed

RUT_A = "12345678-5"   # DV verificado a mano (módulo 11)
RUT_B = "11111111-1"
RUT_C = "22222222-2"


def _seed(*extra):
    base = ["--id", "edificio_c", "--nombre", "Edificio C", "--departamentos", "101,102",
            "--admin-nombre", "Ana Pérez", "--admin-rut", RUT_A, "--admin-unidad", "101",
            "--admin-password", "clave-segura-1"]
    return seed.main(base + list(extra))


def test_seed_crea_edificio_unidades_y_admin(db):
    assert _seed() == 0
    ed = db.get(Edificio, "edificio_c")
    assert ed and len(ed.device_api_key) >= 32
    unidades = db.query(Unidad).filter_by(edificio_id="edificio_c").order_by(Unidad.numero).all()
    assert [u.numero for u in unidades] == ["101", "102"]
    assert [u.codigo_cobro for u in unidades] == ["CC-EDIFICIOC-101", "CC-EDIFICIOC-102"]
    admin = db.query(Residente).filter_by(edificio_id="edificio_c").one()
    assert admin.rol == Rol.admin and admin.rut == RUT_A and admin.unidad.numero == "101"
    assert admin.password_hash and "clave-segura-1" not in admin.password_hash


def test_seed_no_sobrescribe_edificio_existente(db):
    assert _seed() == 0
    clave = db.get(Edificio, "edificio_c").device_api_key
    assert _seed() == 1
    assert db.get(Edificio, "edificio_c").device_api_key == clave


def test_seed_rechaza_datos_invalidos_sin_crear_nada(db):
    assert _seed("--admin-rut", "12345678-4") == 1          # DV incorrecto
    assert _seed("--admin-unidad", "999") == 1             # unidad fuera de la lista
    assert _seed("--admin-password", "corta") == 1         # menos de 8 caracteres
    assert db.get(Edificio, "edificio_c") is None


def test_seed_lee_yaml(db, tmp_path):
    archivo = tmp_path / "edificio.yaml"
    archivo.write_text(
        "edificio:\n  id: edificio_d\n  nombre: Edificio D\n  cupos_visitas: 4\n"
        "departamentos:\n"
        "  - {numero: '201', coeficiente: 0.6, estacionamientos: 2, codigo_cobro: CC-D-201}\n"
        "  - {numero: '202', coeficiente: 0.4, estacionamientos: 1}\n"
        "administrador: {nombre: Beto Soto, rut: '11111111-1', email: beto@x.cl, unidad: '202'}\n",
        encoding="utf-8")
    assert seed.main(["--archivo", str(archivo), "--admin-password", "clave-segura-1"]) == 0
    ed = db.get(Edificio, "edificio_d")
    assert ed.cupos_visitas == 4
    assert db.query(Unidad).filter_by(numero="202", edificio_id="edificio_d").one().codigo_cobro == "CC-EDIFICIOD-202"
    assert db.query(Residente).filter_by(edificio_id="edificio_d").one().unidad.numero == "202"


def test_seed_genera_contrasena_si_no_se_entrega(db, capsys, monkeypatch):
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)
    args = ["--id", "edificio_e", "--nombre", "E", "--departamentos", "1", "--admin-nombre", "X",
            "--admin-rut", RUT_B, "--admin-unidad", "1"]
    assert seed.main(args) == 0
    out = capsys.readouterr().out
    assert "Contraseña generada" in out and "X-Device-Key" in out


def test_rut_y_telefono():
    assert validacion.rut_valido("12.345.678-5") and validacion.rut_valido(RUT_B)
    assert not validacion.rut_valido("12.345.678-4")
    assert validacion.rut_normalizar("12.345.678-5") == RUT_A
    assert validacion.rut_formato(RUT_A) == "12.345.678-5"
    assert validacion.telefono_normalizar("+56 9 1111 2222") == "56911112222"
    assert validacion.telefono_normalizar("911112222") == "56911112222"
    assert not validacion.telefono_valido("123")


CABECERA = "numero,coeficiente,estacionamientos,codigo_cobro,nombre,rut,email,telefono,depto\n"


def test_importar_departamentos_y_residentes(db, seed):
    csv = (CABECERA
           + "301,0.5,2,CC-A-301,Carla Díaz,22222222-2,carla@x.cl,+56 9 8888 7777,\n"
           + "302,0.5,1,CC-A-302,,,,,\n"
           + ",,,,Diego Ruiz,11111111-1,diego@x.cl,,302\n")
    rep = importar_csv.importar(db, "edificio_a", csv)
    assert rep.errores == [] and rep.unidades_creadas == 2 and rep.residentes_creados == 2
    r = db.query(Residente).filter_by(rut=RUT_C).one()
    assert r.telefono == "56988887777" and r.unidad.numero == "301"


def test_importar_es_idempotente(db, seed):
    csv = CABECERA + "301,0.5,2,CC-A-301,Carla Díaz,22222222-2,carla@x.cl,,\n"
    importar_csv.importar(db, "edificio_a", csv)
    rep = importar_csv.importar(db, "edificio_a", csv)
    assert rep.unidades_creadas == 0 and rep.residentes_creados == 0 and rep.sin_cambios == 2
    assert db.query(Residente).filter_by(rut=RUT_C).count() == 1


def test_importar_reporta_errores_por_linea_sin_abortar(db, seed):
    csv = (CABECERA
           + "301,0.5,2,CC-A-301,Carla,22222222-2,,,\n"          # ok
           + "302,abc,1,CC-A-302,,,,,\n"                           # coeficiente inválido
           + "303,0.2,1,CC-A-303,Luis,33333333-4,,,\n"           # RUT con DV malo (el correcto es -3)
           + "304,0.2,1,CC-A-304,Marta,44444444-4,marta@,,\n"      # email inválido
           + "305,0.2,1,CC-A-305,Pedro,11111111-1,,,999\n"          # depto inexistente
           + "301,0.5,2,CC-A-399,,,,,\n"                           # depto repetido en el archivo
           + "306,0.2,1,CC-B-101,,,,,\n")                          # código de cobro de otro edificio
    rep = importar_csv.importar(db, "edificio_a", csv)
    lineas = {linea: msg for linea, msg in rep.errores}
    assert set(lineas) == {3, 4, 5, 6, 7, 8}
    assert "coeficiente" in lineas[3]
    assert "RUT inválido" in lineas[4]
    assert "email" in lineas[5]
    assert "no existe" in lineas[6]
    assert "definido más de una vez" in lineas[7]
    assert "ya lo usa otro" in lineas[8]
    # la fila válida sí entró
    assert db.query(Unidad).filter_by(numero="301", edificio_id="edificio_a").one().codigo_cobro == "CC-A-301"
    assert db.query(Residente).filter_by(rut=RUT_C).count() == 1


def test_importar_dry_run_no_escribe(db, seed):
    csv = CABECERA + "301,0.5,2,CC-A-301,Carla,22222222-2,,,\n"
    rep = importar_csv.importar(db, "edificio_a", csv, dry_run=True)
    assert rep.unidades_creadas == 1 and rep.residentes_creados == 1
    assert db.query(Unidad).filter_by(numero="301").count() == 0


def test_importar_separador_punto_y_coma_y_bom(db, seed):
    csv = "﻿" + CABECERA.replace(",", ";") + "301;0,5;2;CC-A-301;Carla;22222222-2;;;\n"
    rep = importar_csv.importar(db, "edificio_a", csv)
    assert rep.errores == [] and rep.unidades_creadas == 1 and rep.residentes_creados == 1


def test_importar_sin_cabecera_numero(db, seed):
    rep = importar_csv.importar(db, "edificio_a", "unidad,coef\n301,0.5\n")
    assert rep.errores and rep.errores[0][0] == 1
