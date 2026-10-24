from datetime import timedelta

from app.config import ahora_local, settings, utcnow
from app.models import AccesoLog, EstadoVisita, Evento, IntentoLogin, LecturaPendiente, Visita
from app.services import retencion


def _vieja(dias):
    return utcnow() - timedelta(days=dias)


def test_borra_lo_vencido_y_conserva_lo_reciente(db, seed):
    db.add_all([
        AccesoLog(edificio_id="edificio_a", token="BBCD12", punto="vehicular", permitido=True, creado=_vieja(settings.retencion_accesos_dias + 1)),
        AccesoLog(edificio_id="edificio_a", token="KLPR45", punto="vehicular", permitido=True, creado=_vieja(1)),
        Evento(edificio_id="edificio_a", tipo="x", payload={}, creado=_vieja(settings.retencion_eventos_dias + 1)),
        Evento(edificio_id="edificio_a", tipo="y", payload={}, creado=_vieja(2)),
        IntentoLogin(clave="a|b", creado=_vieja(settings.retencion_intentos_login_dias + 1)),
        LecturaPendiente(edificio_id="edificio_a", punto="p", fuente="sticker", valor="V", creado=_vieja(2)),
    ])
    db.flush()
    res = retencion.purgar(db)
    assert res["accesos"] == 1 and res["eventos"] == 1 and res["intentos_login"] == 1 and res["lecturas_pendientes"] == 1
    assert [a.token for a in db.query(AccesoLog).all()] == ["KLPR45"]
    assert [e.tipo for e in db.query(Evento).all()] == ["y"]


def test_visitas_viejas_se_anonimizan_sin_perder_el_registro(db, seed):
    vieja = ahora_local() - timedelta(days=settings.retencion_visitas_dias + 5)
    reciente = ahora_local() - timedelta(days=2)
    uid = seed["edificio_a", "101"].id
    for i, fin in enumerate((vieja, reciente)):
        db.add(Visita(edificio_id="edificio_a", unidad_id=uid, nombre_visita=f"Persona {i}", patente="BBCD12",
                      desde=fin - timedelta(hours=2), hasta=fin, codigo_qr=f"qr{i}", estado=EstadoVisita.llego))
    db.flush()
    assert retencion.purgar(db)["visitas_anonimizadas"] == 1
    por_qr = {v.codigo_qr: v for v in db.query(Visita)}
    assert por_qr["qr0"].nombre_visita == "[eliminado]" and por_qr["qr0"].patente == ""
    assert por_qr["qr1"].nombre_visita == "Persona 1" and por_qr["qr1"].patente == "BBCD12"
    assert retencion.purgar(db)["visitas_anonimizadas"] == 0  # idempotente


def test_plazo_cero_desactiva_la_purga(db, seed, monkeypatch):
    monkeypatch.setattr(settings, "retencion_accesos_dias", 0)
    db.add(AccesoLog(edificio_id="edificio_a", token="T", punto="p", permitido=True, creado=_vieja(9999)))
    db.flush()
    assert retencion.purgar(db)["accesos"] == 0
