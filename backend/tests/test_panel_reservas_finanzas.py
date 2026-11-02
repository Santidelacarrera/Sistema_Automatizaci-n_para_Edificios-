from datetime import date, timedelta

from app.config import ahora_local
from app.models import EspacioComun
from app.services import finance

from conftest import login


def test_listar_reservas_y_cancelar_con_multa(client, seed, db):
    h = login(client, "edificio_a", "ana@x.cl")
    db.add(EspacioComun(edificio_id="edificio_a", nombre="quincho", accion="reservar_quincho", tarifa=10000))
    db.commit()
    esp = db.query(EspacioComun).one()
    ini = (ahora_local() + timedelta(days=3)).replace(hour=12, minute=0, second=0, microsecond=0)
    r = client.post("/edificios/edificio_a/reservas-espacio", headers=h,
                    json={"espacio_id": esp.id, "desde": ini.isoformat(), "hasta": (ini + timedelta(hours=3)).isoformat()})
    assert r.status_code == 201
    lista = client.get("/edificios/edificio_a/reservas-espacio", headers=h).json()
    assert len(lista) == 1 and lista[0]["espacio"] == "quincho" and lista[0]["unidad"] == "101" and lista[0]["estado"] == "confirmada"
    assert not lista[0]["desde"].endswith("Z")  # hora local, sin sufijo de UTC
    assert client.post(f"/edificios/edificio_a/reservas-espacio/{lista[0]['id']}/cancelar", headers=h).status_code == 200
    assert client.get("/edificios/edificio_a/reservas-espacio", headers=h).json()[0]["estado"] == "cancelada"


def test_reservas_y_periodos_respetan_edificio_y_rol(client, seed):
    ha = login(client, "edificio_a", "ana@x.cl")
    assert client.get("/edificios/edificio_b/reservas-espacio", headers=ha).status_code == 403
    assert client.get("/edificios/edificio_b/gastos-comunes", headers=ha).status_code == 403
    hr = login(client, "edificio_a", "beto@x.cl")  # residente
    assert client.get("/edificios/edificio_a/reservas-espacio", headers=hr).status_code == 403
    assert client.get("/edificios/edificio_a/gastos-comunes", headers=hr).status_code == 403


def test_periodos_generados_muestran_emitido_y_pendiente(client, seed, db):
    h = login(client, "edificio_a", "ana@x.cl")
    assert client.get("/edificios/edificio_a/gastos-comunes", headers=h).json() == []
    finance.generar_cargos(db, "edificio_a", "2026-09", date(2026, 10, 10),
                           [{"concepto": "Administración", "monto": 1000000, "tipo": "ordinario"}])
    db.commit()
    p = client.get("/edificios/edificio_a/gastos-comunes", headers=h).json()
    assert p == [{"periodo": "2026-09", "emitido": 1000000.0, "pendiente": 1000000.0, "unidades": 3}]
