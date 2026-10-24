"""Las horas que escribe una persona se interpretan en la zona del negocio, no en UTC."""
from datetime import timedelta

from app import config
from app.config import ahora_local, utcnow


def test_ahora_local_sigue_la_zona_configurada(monkeypatch):
    monkeypatch.setattr(config.settings, "zona_horaria", "Pacific/Auckland")  # UTC+12/+13, nunca igual a UTC
    dif = ahora_local() - utcnow()
    assert timedelta(hours=11, minutes=59) < dif < timedelta(hours=13, minutes=1)


def test_santiago_esta_atras_de_utc():
    dif = utcnow() - ahora_local()
    assert timedelta(hours=2, minutes=59) <= dif <= timedelta(hours=4, minutes=1)  # UTC-3 verano / UTC-4 invierno


def test_visita_con_hora_local_abre_el_qr(db, seed):
    from app.models import Edificio
    from app.services import access
    ed = db.get(Edificio, "edificio_a")
    uid = seed["edificio_a", "101"].id
    ini = ahora_local() - timedelta(minutes=1)
    v = access.reservar_visita(db, ed, uid, "Visita", ini, ini + timedelta(hours=2))
    ok = access.validar_acceso(db, ed, v.codigo_qr, "peatonal")
    assert (ok[0] if isinstance(ok, tuple) else ok.permitido)
