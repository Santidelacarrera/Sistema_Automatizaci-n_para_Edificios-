"""Pruebas de las 18 funcionalidades completadas:
visitas recurrentes, fotos/adjuntos, garantías y penalizaciones de reservas,
comunicados por torre, push/SMS, padrón de copropietarios, presupuesto normativo,
WebSockets, caché, búsqueda global, predicción/optimización IA y encuestas.
"""
import base64
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

from app.config import hoy_local, settings
from app.models import EspacioComun, ReservaEspacio, Unidad
from app.services.cache import cache_get, cache_invalidate, cache_set
from conftest import login

BASE = "/edificios/edificio_a"


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def test_visitas_recurrentes_y_adjuntos_autorizados(client, seed):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")

    # 07.08 Visitas recurrentes
    vr = ok(client.post(BASE + "/visitas-recurrentes", headers=residente, json={
        "nombre_visita": "Kinesióloga Sofía",
        "patente": "ABCD12",
        "dias_semana": [0, 2, 4],
        "hora_desde": "09:00",
        "hora_hasta": "12:00",
    }), 201)
    assert vr["nombre_visita"] == "Kinesióloga Sofía"
    lista = ok(client.get(BASE + "/visitas-recurrentes", headers=residente))
    assert any(x["id"] == vr["id"] for x in lista)
    ok(client.delete(f"{BASE}/visitas-recurrentes/{vr['id']}", headers=residente))

    # 07.13 Fotografías en portería (requiere autorización explícita y rol staff/admin)
    png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfakeimg").decode()
    r_sin_auth = client.post(BASE + "/adjuntos/porteria_visita/1", headers=admin, json={
        "nombre_archivo": "ingreso.png",
        "mime_type": "image/png",
        "contenido_base64": png_b64,
        "autorizacion_residente": False,
    })
    assert r_sin_auth.status_code == 422

    foto = ok(client.post(BASE + "/adjuntos/porteria_visita/1", headers=admin, json={
        "nombre_archivo": "ingreso.png",
        "mime_type": "image/png",
        "contenido_base64": png_b64,
        "autorizacion_residente": True,
    }), 201)
    assert foto["tamano_bytes"] > 0

    # 09.02 Adjuntos en incidencias
    inc = ok(client.post(BASE + "/incidencias", headers=residente, json={
        "titulo": "Fuga en pasillo", "descripcion": "Gotera junto al ascensor", "prioridad": "alta",
    }), 201)
    adj_inc = ok(client.post(f"{BASE}/adjuntos/incidencia/{inc['id']}", headers=residente, json={
        "nombre_archivo": "gotera.png",
        "mime_type": "image/png",
        "contenido_base64": png_b64,
    }), 201)
    assert len(ok(client.get(f"{BASE}/adjuntos/incidencia/{inc['id']}", headers=admin))) == 1
    assert adj_inc["entidad"] == "incidencia"


def test_reservas_garantias_penalizaciones_y_comunicado_torre(client, seed, db):
    admin = login(client, "edificio_a", "ana@x.cl")
    uid = seed["edificio_a", "102"].id
    u = db.get(Unidad, uid)
    u.torre = "Torre Norte"
    esp = db.scalar(select(EspacioComun).where(EspacioComun.edificio_id == "edificio_a"))
    if not esp:
        esp = EspacioComun(edificio_id="edificio_a", nombre="Quincho", accion="quincho", tarifa=10000, garantia=25000, aforo=20)
        db.add(esp)
        db.flush()
    else:
        esp.garantia = 25000
    res = ReservaEspacio(
        edificio_id="edificio_a",
        espacio_id=esp.id,
        unidad_id=uid,
        desde=datetime.now() + timedelta(days=2),
        hasta=datetime.now() + timedelta(days=2, hours=2),
        estado="confirmada",
    )
    db.add(res)
    db.commit()
    db.refresh(res)

    # 08.16 Garantía ejecutada genera cargo
    g = ok(client.post(f"{BASE}/reservas-espacio/{res.id}/garantia", headers=admin, json={"estado": "ejecutada"}))
    assert g["garantia_estado"] == "ejecutada"

    # 08.18 Penalización configurable
    p = ok(client.post(f"{BASE}/reservas-espacio/{res.id}/penalizar", headers=admin, json={
        "monto": 15000, "motivo": "Exceso de horario",
    }))
    assert p["penalizacion"] == 15000.0
    assert p["cargo_id"] > 0

    # 10.03 Comunicado segmentado por torre
    com = ok(client.post(BASE + "/comunicados-torre", headers=admin, json={
        "torre": "Torre Norte",
        "titulo": "Mantención de ascensor",
        "cuerpo": "Corte programado entre 10:00 y 12:00.",
    }), 201)
    assert com["unidades"] >= 1
    assert com["notificados"] >= 1


def test_push_sms_padron_presupuesto_normativo_y_encuestas(client, seed, monkeypatch):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    uid = seed["edificio_a", "102"].id

    # 10.17 & 10.19 Push y SMS (sin credenciales reportan no_configurado y con mock envían OK)
    ok(client.post(BASE + "/push/suscribir", headers=residente, json={"token": "fcm_token_demo_1234567890", "plataforma": "web"}), 201)
    p_nocfg = ok(client.post(BASE + "/notificaciones/enviar-externo", headers=admin, json={
        "canal": "push", "titulo": "Aviso", "mensaje": "Reunión hoy",
    }))
    assert p_nocfg["resultados"][0]["estado"] == "no_configurado"

    s_nocfg = ok(client.post(BASE + "/notificaciones/enviar-externo", headers=admin, json={
        "canal": "sms", "telefono": "+56912345678", "mensaje": "Corte de agua",
    }))
    assert s_nocfg["estado"] == "no_configurado"

    monkeypatch.setattr(settings, "fcm_server_key", "test-fcm-key")
    monkeypatch.setattr(settings, "twilio_account_sid", "ACtest")
    monkeypatch.setattr(settings, "twilio_auth_token", "toktest")
    monkeypatch.setattr(settings, "twilio_from_number", "+56900000000")

    class FakeResp:
        def __init__(self, code=200, data=None):
            self.status_code = code
            self.is_success = 200 <= code < 300
            self._data = data or {"sid": "SM123", "success": 1}

        def json(self):
            return self._data

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: FakeResp())
    p_ok = ok(client.post(BASE + "/notificaciones/enviar-externo", headers=admin, json={
        "canal": "push", "titulo": "Aviso", "mensaje": "Enviado",
    }))
    assert p_ok["resultados"][0]["estado"] == "enviado"
    s_ok = ok(client.post(BASE + "/notificaciones/enviar-externo", headers=admin, json={
        "canal": "sms", "telefono": "+56912345678", "mensaje": "Enviado",
    }))
    assert s_ok["estado"] == "enviado"

    # 17.06 Padrón formal de copropietarios
    ok(client.post(BASE + "/registros-comunidad", headers=admin, json={
        "categoria": "copropietario", "unidad_id": uid, "titulo": "Beto Copropietario", "contacto": "beto@x.cl",
    }), 201)
    padron = ok(client.get(BASE + "/padron-copropietarios", headers=admin))
    assert padron["total_copropietarios"] >= 1

    # 17.07 Presupuestos normativos vinculados a asamblea
    periodo = hoy_local().strftime("%Y-%m")
    pres = ok(client.post(BASE + "/contabilidad/presupuestos", headers=admin, json={
        "periodo": periodo, "categoria": "seguridad", "monto_presupuestado": 400000,
    }), 201)
    asam = ok(client.post(BASE + "/asambleas", headers=admin, json={
        "titulo": "Asamblea Presupuesto", "agenda": "Aprobación presupuesto anual", "fecha": "2026-12-01T19:00:00", "opciones": ["Aprobar", "Rechazar"],
    }), 201)
    aprob = ok(client.post(f"{BASE}/contabilidad/presupuestos/{pres['id']}/aprobar", headers=admin, json={
        "asamblea_id": asam["id"],
    }))
    assert aprob["aprobado_asamblea_id"] == asam["id"]

    # 22.22 Encuestas / índice de satisfacción
    enc = ok(client.post(BASE + "/encuestas", headers=admin, json={
        "titulo": "Evaluación Conserjería", "pregunta": "¿Cómo evalúa la atención recibida?",
    }), 201)
    ok(client.post(f"{BASE}/encuestas/{enc['id']}/responder", headers=residente, json={"puntaje": 5, "comentario": "Excelente"}), 201)
    encuestas = ok(client.get(BASE + "/encuestas", headers=residente))
    target = next(e for e in encuestas if e["id"] == enc["id"])
    assert target["total_respuestas"] == 1
    assert target["indice_satisfaccion"] == 5.0


def test_websocket_cache_busqueda_global_y_prediccion_ia(client, seed):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    token_admin = admin["Authorization"].split(" ", 1)[1]

    # 19.07 WebSocket en tiempo real autenticado por edificio
    with client.websocket_connect(f"/ws/edificios/edificio_a?token={token_admin}") as ws:
        hello = ws.receive_json()
        assert hello == {"tipo": "conectado", "edificio_id": "edificio_a"}
        ws.send_text("ping")
        assert ws.receive_json() == {"tipo": "pong"}

    # 19.22 Caché TTL en memoria/Redis + dashboard y espacios
    cache_set("test:clave", {"ok": True}, ttl_s=10)
    assert cache_get("test:clave") == {"ok": True}
    cache_invalidate("test:clave")
    assert cache_get("test:clave") is None
    assert "unidades" in ok(client.get(BASE + "/dashboard", headers=admin))
    assert isinstance(ok(client.get(BASE + "/espacios-comunes", headers=residente)), list)

    # 21.07 Búsqueda global transversal
    busq_admin = ok(client.get(BASE + "/buscar?q=102", headers=admin))
    assert len(busq_admin["unidades"]) >= 1
    busq_res = ok(client.get(BASE + "/buscar?q=101", headers=residente))
    assert all(u["numero"] != "101" for u in busq_res["unidades"])

    # 22.06 Predicción de mantenimientos & 22.09 Optimización de tareas
    prov = ok(client.post(BASE + "/proveedores", headers=admin, json={
        "nombre": "Elevadores Chile", "rut": "76123456-0", "servicio": "ascensor",
    }), 201)
    inc_id = None
    for i in range(2):
        inc_creada = ok(client.post(BASE + "/incidencias", headers=admin, json={
            "titulo": f"Falla ascensor {i}", "descripcion": "Ruido en cabina de ascensor", "prioridad": "alta",
        }), 201)
        inc_id = inc_creada["id"]
    ok(client.post(f"{BASE}/incidencias/{inc_id}/orden", headers=admin, json={
        "proveedor_id": prov["id"], "detalle": "Revisar motor ascensor", "presupuesto": 180000,
    }), 201)
    ia = ok(client.get(BASE + "/ia/analisis", headers=admin))
    assert any(p["categoria"] == "ascensor" and p["eventos"] >= 2 for p in ia["prediccion_mantenimientos"])
    assert len(ia["optimizacion_tareas"]) >= 1
