"""Reserva de visitas por WhatsApp: entender, preguntar lo que falta, confirmar y enviar el QR."""
from datetime import datetime, timedelta

import pytest

from app.config import ahora_local, utcnow
from app.models import ConversacionWA, EstadoVisita, Visita
from app.services import wa_parser
from app.services.resultado import ENVIADO, ResultadoEnvio

BETO = "56933334444"  # residente de edificio_a, depto 102 (ver conftest)
ANA = "56911112222"
H = {"X-Webhook-Token": "tok"}


@pytest.fixture()
def enviados(monkeypatch):
    """Captura lo que el sistema enviaría por WhatsApp (sin tocar Evolution API)."""
    sal = []
    monkeypatch.setattr("app.services.whatsapp.enviar", lambda tel, txt: sal.append(("texto", tel, txt)) or ResultadoEnvio("whatsapp", ENVIADO))
    monkeypatch.setattr("app.services.whatsapp.enviar_imagen", lambda tel, png, ley="": sal.append(("imagen", tel, ley, png)) or ResultadoEnvio("whatsapp", ENVIADO))
    return sal


def _msg(tel, texto, id_="m1"):
    return {"event": "messages.upsert", "data": {"key": {"remoteJid": f"{tel}@s.whatsapp.net", "fromMe": False, "id": id_},
                                                  "message": {"conversation": texto}}}


_n = iter(range(1, 10_000))


def decir(client, tel, texto):
    return client.post("/webhooks/whatsapp", json=_msg(tel, texto, f"id{next(_n)}"), headers=H)


# ---------- parser ----------
AHORA = datetime(2026, 11, 2, 10, 0)  # lunes


@pytest.mark.parametrize("texto,esperado", [
    ("visita Juan Pérez mañana 18:00 patente BBCD12", {"nombre": "Juan Pérez", "fecha": "2026-11-03", "hora": "18:00", "patente": "BBCD12", "usa_estacionamiento": True}),
    ("Quiero reservar una visita para María González el viernes a las 7 pm con auto", {"nombre": "María González", "fecha": "2026-11-06", "hora": "19:00", "usa_estacionamiento": True}),
    ("visita de Pedro hoy a las 6", {"nombre": "Pedro", "fecha": "2026-11-02", "hora": "18:00"}),
    ("registrar visita Ana Soto 15/11 20h a pie", {"nombre": "Ana Soto", "fecha": "2026-11-15", "hora": "20:00", "usa_estacionamiento": False}),
    ("visita Luis BB-CD-12 mañana 9:30 por 2 horas", {"nombre": "Luis", "patente": "BBCD12", "hora": "09:30", "duracion_h": 2}),
    ("mi hermano llega mañana", {"fecha": "2026-11-03"}),
])
def test_parser_entiende_frases_comunes(texto, esperado):
    out = wa_parser.extraer_visita(texto, AHORA)
    for k, v in esperado.items():
        assert out.get(k) == v, f"{k}: {out}"


def test_parser_no_confunde_apellido_y_dia_con_patente():
    assert "patente" not in wa_parser.extraer_visita("visita Ana Soto 15/11 20h", AHORA)


def test_el_mismo_dia_de_la_semana_va_a_la_semana_siguiente():
    assert wa_parser.extraer_visita("visita Pedro lunes 18:00", AHORA)["fecha"] == "2026-11-09"


# ---------- conversación completa ----------
def test_reserva_completa_con_confirmacion_y_qr(client, seed, db, enviados):
    r = decir(client, BETO, "visita Juan Pérez mañana 18:00 patente BBCD12")
    assert r.status_code == 200 and r.json()["intent"] == "reservar_visita"
    assert "Responde *SÍ*" in enviados[-1][2] and "BBCD12" in enviados[-1][2]
    assert db.query(Visita).count() == 0  # nada se reserva sin confirmar
    decir(client, BETO, "sí")
    assert enviados[-1][0] == "imagen" and enviados[-1][3][:8] == b"\x89PNG\r\n\x1a\n"
    v = db.query(Visita).one()
    assert (v.nombre_visita, v.patente, v.usa_estacionamiento, v.estado) == ("Juan Pérez", "BBCD12", True, EstadoVisita.reservada)
    assert v.unidad_id == seed["edificio_a", "102"].id  # la unidad de quien escribe, no otra
    assert v.desde == (ahora_local() + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    assert v.hasta - v.desde == timedelta(hours=3)
    assert db.query(ConversacionWA).count() == 0  # la conversación terminó


def test_pregunta_lo_que_falta_paso_a_paso(client, seed, db, enviados):
    decir(client, BETO, "quiero reservar una visita")
    assert "llama tu visita" in enviados[-1][2]
    decir(client, BETO, "María González")
    assert "Para qué día" in enviados[-1][2]
    decir(client, BETO, "mañana")
    assert "qué hora" in enviados[-1][2]
    decir(client, BETO, "17:30")
    assert "María González" in enviados[-1][2] and "17:30" in enviados[-1][2] and "a pie" in enviados[-1][2]
    decir(client, BETO, "con auto BBCD12")  # corrige antes de confirmar y vuelve a pedir confirmación
    assert "BBCD12" in enviados[-1][2] and "Responde *SÍ*" in enviados[-1][2]
    decir(client, BETO, "si")
    v = db.query(Visita).one()
    assert v.usa_estacionamiento and v.patente == "BBCD12"


def test_no_cancela_y_no_reserva(client, seed, db, enviados):
    decir(client, BETO, "visita Juan mañana 18:00")
    decir(client, BETO, "no")
    assert "no reservé nada" in enviados[-1][2]
    assert db.query(Visita).count() == 0 and db.query(ConversacionWA).count() == 0


def test_fecha_muy_lejana_o_pasada_se_rechaza(client, seed, db, enviados):
    decir(client, BETO, "visita Juan 01/01 18:00")  # sin año: cae al próximo 1 de enero
    ahora = ahora_local()
    if (datetime(ahora.year + (1 if ahora.month > 1 or ahora.day > 1 else 0), 1, 1) - ahora).days > 30:
        assert "30 días" in enviados[-1][2]
    assert db.query(Visita).count() == 0


def test_sin_cupos_avisa_y_no_reserva(client, seed, db, enviados):
    from app.models import Edificio
    from app.services import access
    ed = db.get(Edificio, "edificio_a")
    manana = (ahora_local() + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    for i in range(ed.cupos_visitas):
        access.reservar_visita(db, ed, seed["edificio_a", "101"].id, f"V{i}", manana, manana + timedelta(hours=3))
    db.commit()
    decir(client, BETO, "visita Juan mañana 18:00 patente BBCD12")
    assert "0 cupo(s)" in enviados[-1][2]
    decir(client, BETO, "si")
    assert "No pude reservar" in enviados[-1][2] and "cupos" in enviados[-1][2]
    assert db.query(Visita).count() == ed.cupos_visitas


def test_webhook_repetido_no_reserva_dos_veces(client, seed, db, enviados):
    msg = _msg(BETO, "visita Juan mañana 18:00", "idfijo")
    assert client.post("/webhooks/whatsapp", json=msg, headers=H).json().get("duplicado") is None
    assert client.post("/webhooks/whatsapp", json=msg, headers=H).json() == {"duplicado": True}
    assert len([e for e in enviados if e[0] == "texto"]) == 1


def test_cada_residente_tiene_su_propia_conversacion(client, seed, db, enviados):
    decir(client, BETO, "visita Juan mañana 18:00")
    decir(client, ANA, "visita Pedro mañana 19:00")
    decir(client, ANA, "si")
    visitas = db.query(Visita).all()
    assert len(visitas) == 1 and visitas[0].nombre_visita == "Pedro" and visitas[0].unidad_id == seed["edificio_a", "101"].id
    decir(client, BETO, "si")
    assert db.query(Visita).count() == 2


def test_conversacion_vencida_no_confirma(client, seed, db, enviados):
    decir(client, BETO, "visita Juan mañana 18:00")
    c = db.query(ConversacionWA).one()
    c.actualizado = utcnow() - timedelta(minutes=30)
    db.commit()
    decir(client, BETO, "si")
    assert db.query(Visita).count() == 0  # un «sí» suelto, 30 minutos después, no reserva nada


def test_sin_credencial_no_hay_conversacion(client, seed, enviados):
    msg = _msg(BETO, "visita Juan mañana 18:00", "x1")
    assert client.post("/webhooks/whatsapp", json=msg).status_code == 401
