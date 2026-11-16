"""Pruebas de contabilidad, presupuestos, convenios, pasarelas de pago, personal, IA, DOCMIND avanzado,
WhatsApp Cloud API oficial y recuperación segura de cuentas."""
from datetime import timedelta
import hashlib
import hmac
import json
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.config import hoy_local, settings
from app.models import Cargo, Pago, Residente, Unidad
from app.operations_models import Documento
from app.services import docmind
from conftest import login

BASE = "/edificios/edificio_a"


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def test_contabilidad_presupuestos_balance_convenios_y_ajustes(client, seed, db):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    uid = seed["edificio_a", "102"].id

    # Residente no puede ver ni escribir contabilidad
    assert client.get(BASE + "/contabilidad/balance", headers=residente).status_code == 403
    assert client.post(BASE + "/contabilidad/movimientos", headers=residente, json={}).status_code == 403

    # Registrar presupuesto y movimientos contables
    periodo = hoy_local().strftime("%Y-%m")
    pres = ok(client.post(BASE + "/contabilidad/presupuestos", headers=admin, json={
        "periodo": periodo, "categoria": "ascensores", "monto_presupuestado": 150000, "notas": "Mantención mensual"
    }), 201)
    assert float(pres["monto_presupuestado"]) == 150000

    prov = ok(client.post(BASE + "/proveedores", headers=admin, json={
        "nombre": "Ascensores Chile", "rut": "11.111.111-1", "servicio": "Mantención"
    }), 201)

    egreso = ok(client.post(BASE + "/contabilidad/movimientos", headers=admin, json={
        "tipo": "egreso", "categoria": "ascensores", "concepto": "Factura mantención",
        "monto": 200000, "proveedor_id": prov["id"], "estado": "pendiente"
    }), 201)
    assert egreso["estado"] == "pendiente" and egreso["cuenta_haber"] == "cuentas_por_pagar"

    # Aprobar y pagar cuenta por pagar
    ok(client.patch(BASE + f"/contabilidad/movimientos/{egreso['id']}", headers=admin, json={"estado": "pagado"}))

    # Generar cargo, aplicar descuento autorizado y crear convenio
    c = Cargo(edificio_id="edificio_a", unidad_id=uid, periodo=periodo, concepto="GC:ordinario:Cuota",
              categoria="cuota_base", monto=100000, saldo=100000, vencimiento=hoy_local() - timedelta(days=40))
    db.add(c)
    db.commit()

    ajuste = ok(client.post(BASE + f"/cargos/{c.id}/ajustar", headers=admin, json={
        "descuento": 15000, "motivo": "Descuento aprobado por comité"
    }))
    assert ajuste["saldo"] == 85000

    conv = ok(client.post(BASE + "/convenios-pago", headers=admin, json={
        "unidad_id": uid, "monto_total": 85000, "pie_inicial": 15000, "cuotas": 4,
        "tasa_interes_pct": 1.5, "primer_vencimiento": str(hoy_local() + timedelta(days=15))
    }), 201)
    assert conv["cuotas"] == 4
    assert len(ok(client.get(BASE + "/convenios-pago", headers=residente))) == 1

    bal = ok(client.get(BASE + "/contabilidad/balance", headers=admin))
    assert bal["egresos_totales"] == 200000
    assert bal["cuentas_por_cobrar"] == 85000
    assert bal["presupuestos_registrados"] == 1


def test_pasarela_pago_sandbox_transbank_y_aislamiento(client, seed, db, monkeypatch):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    otro = login(client, "edificio_b", "carla@x.cl")
    uid = seed["edificio_a", "102"].id

    c = Cargo(edificio_id="edificio_a", unidad_id=uid, periodo="2026-11", concepto="GC:ordinario:Mes",
              categoria="cuota_base", monto=60000, saldo=60000, vencimiento=hoy_local())
    db.add(c)
    db.commit()

    # Iniciar y confirmar pago en pasarela sandbox por el residente
    tx = ok(client.post(BASE + "/pagos/pasarela/iniciar", headers=residente, json={
        "proveedor": "sandbox", "idempotencia": "idemp-residente-1"
    }), 201)
    assert tx["estado"] == "iniciada" and tx["monto"] == 60000
    # Idempotencia devuelve la misma transacción
    assert ok(client.post(BASE + "/pagos/pasarela/iniciar", headers=residente, json={
        "proveedor": "sandbox", "idempotencia": "idemp-residente-1"
    }), 201)["id"] == tx["id"]

    # Otro edificio no puede confirmar
    assert client.post(BASE + f"/pagos/pasarela/{tx['id']}/confirmar", headers=otro, json={}).status_code == 403

    conf = ok(client.post(BASE + f"/pagos/pasarela/{tx['id']}/confirmar", headers=residente, json={
        "resultado_sandbox": "autorizada"
    }))
    assert conf["estado"] == "autorizada" and conf["pago_id"] is not None
    db.expire_all()
    assert float(db.get(Cargo, c.id).saldo) == 0.0
    assert db.query(Pago).filter_by(id=conf["pago_id"]).one().conciliado is True

    # Transbank sin credenciales responde 503 claro
    assert client.post(BASE + "/pagos/pasarela/iniciar", headers=admin, json={
        "unidad_id": uid, "monto": 10000, "proveedor": "transbank", "idempotencia": "tbk-1"
    }).status_code == 503

    # Transbank con credenciales de integración simuladas por MockTransport
    monkeypatch.setattr(settings, "transbank_commerce_code", "597055555532")
    monkeypatch.setattr(settings, "transbank_api_key", "clave-integracion")
    real_client = httpx.Client
    def handler(req):
        if req.method == "POST":
            return httpx.Response(200, json={"token": "tbk_tok_123", "url": "https://webpay3gint.transbank.cl/ pay"})
        return httpx.Response(200, json={"status": "AUTHORIZED", "response_code": 0, "amount": 25000, "authorization_code": "1213"})
    monkeypatch.setattr("app.services.payment_gateways.httpx.Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    tx_tbk = ok(client.post(BASE + "/pagos/pasarela/iniciar", headers=admin, json={
        "unidad_id": uid, "monto": 25000, "proveedor": "transbank", "idempotencia": "tbk-2"
    }), 201)
    conf_tbk = ok(client.post(BASE + f"/pagos/pasarela/{tx_tbk['id']}/confirmar", headers=admin, json={}))
    assert conf_tbk["estado"] == "autorizada" and conf_tbk["codigo_autorizacion"] == "1213"
    db.expire_all()
    assert float(db.get(Unidad, uid).saldo_favor) == 25000.0


def test_personal_asistencia_registros_comunidad_y_compromisos_asamblea(client, seed, db):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")

    # Personal y asistencia
    t = ok(client.post(BASE + "/personal", headers=admin, json={
        "nombre": "Pedro Conserje", "rut": "22.222.222-2", "cargo": "conserje", "turno": "Nocturno"
    }), 201)
    assert len(ok(client.get(BASE + "/personal", headers=admin))) == 1
    asis = ok(client.post(BASE + "/personal/asistencia", headers=admin, json={
        "trabajador_id": t["id"], "tipo": "asistencia", "entrada": "20:00", "salida": "08:00"
    }), 201)
    assert asis["tipo"] == "asistencia"

    # Registros de comunidad: residente puede registrar mascota/contacto_emergencia de su unidad, pero no comité
    assert client.post(BASE + "/registros-comunidad", headers=residente, json={
        "categoria": "comite", "titulo": "Presidente"
    }).status_code == 403
    masc = ok(client.post(BASE + "/registros-comunidad", headers=residente, json={
        "categoria": "mascota", "titulo": "Perro Golden", "detalle": "Vacunas al día"
    }), 201)
    assert masc["unidad_id"] == seed["edificio_a", "102"].id
    cop = ok(client.post(BASE + "/registros-comunidad", headers=admin, json={
        "categoria": "copropietario", "unidad_id": seed["edificio_a", "101"].id,
        "titulo": "Inversiones Sur", "rut": "12.345.678-5"
    }), 201)
    assert cop["categoria"] == "copropietario"

    # Asamblea: compromisos y acta en PDF
    rid = db.scalar(select(Residente.id).where(Residente.email == "beto@x.cl"))
    asamblea = ok(client.post(BASE + "/asambleas", headers=admin, json={
        "titulo": "Asamblea Ordinaria", "agenda": "Rendición y comité",
        "fecha": "2027-05-10T19:00:00", "opciones": ["Aprobar", "Rechazar"]
    }), 201)
    aid = asamblea["id"]
    ok(client.post(BASE + f"/asambleas/{aid}/participantes", headers=admin, json={"residente_id": rid}), 201)
    ok(client.post(BASE + f"/asambleas/{aid}/abrir", headers=admin))
    ok(client.post(BASE + f"/asambleas/{aid}/cerrar", headers=admin, json={"acta": "Se aprueba la cuenta anual."}))

    comp = ok(client.post(BASE + f"/asambleas/{aid}/compromisos", headers=admin, json={
        "titulo": "Publicar balance firmado", "responsable_id": rid, "vencimiento": str(hoy_local() + timedelta(days=10))
    }), 201)
    ok(client.patch(BASE + f"/asambleas/{aid}/compromisos/{comp['id']}", headers=admin, json={"estado": "cumplido"}))
    assert ok(client.get(BASE + f"/asambleas/{aid}/compromisos", headers=residente))[0]["estado"] == "cumplido"

    pdf_res = client.get(BASE + f"/asambleas/{aid}/acta.pdf", headers=residente)
    assert pdf_res.status_code == 200 and pdf_res.content.startswith(b"%PDF-")


def test_ia_analitica_asistente_y_docmind_inteligencia_comparacion(client, seed, db, monkeypatch):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")

    analisis = ok(client.get(BASE + "/ia/analisis", headers=admin))
    assert "resumen_financiero" in analisis and "recomendaciones" in analisis

    r_admin = ok(client.post(BASE + "/ia/asistente", headers=admin, json={
        "pregunta": "Genera un borrador de circular sobre el estado del edificio"
    }))
    assert r_admin["borrador_circular"] is not None

    r_res = ok(client.post(BASE + "/ia/asistente", headers=residente, json={
        "pregunta": "¿Cuánto debo en mi departamento?"
    }))
    assert r_res["modo"] == "determinista_residente"

    # DOCMIND inteligencia y comparación
    org, proj, d1_ext, d2_ext = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    monkeypatch.setattr(settings, "docmind_url", "https://docmind.example.test")
    monkeypatch.setattr(settings, "docmind_tenants", {
        "edificio_a": {"organization_id": org, "project_id": proj, "api_key": "k-test"}
    })
    ana_id = db.scalar(select(Residente.id).where(Residente.email == "ana@x.cl"))
    d1 = Documento(edificio_id="edificio_a", externo_id=d1_ext, titulo="Contrato 2025", categoria="contrato",
                   publico_comunidad=True, creado_por=ana_id)
    d2 = Documento(edificio_id="edificio_a", externo_id=d2_ext, titulo="Contrato 2026", categoria="contrato",
                   publico_comunidad=False, creado_por=ana_id)
    db.add_all([d1, d2])
    db.commit()

    monkeypatch.setattr(docmind, "request", lambda eid, m, p, **kw: (
        {"summary": "Contrato de mantención", "entities": ["Ascensores Chile"],
         "fields": {"monto": "150000"}, "obligations": ["Visitar mensualmente"]}
        if p.endswith("/summary") else
        {"differences": ["Reajuste de 5%"], "contradictions": [], "summary": "Actualización de tarifa"}
    ))
    intel = ok(client.get(BASE + f"/documentos/{d1.id}/inteligencia", headers=residente))
    assert intel["resumen"] == "Contrato de mantención" and "Visitar mensualmente" in intel["obligaciones"]
    assert client.get(BASE + f"/documentos/{d2.id}/inteligencia", headers=residente).status_code == 404

    comp = ok(client.post(BASE + "/documentos/comparar", headers=admin, json={"documentos": [d1.id, d2.id]}))
    assert comp["diferencias"] == ["Reajuste de 5%"]


def test_recuperacion_cuenta_mi_perfil_y_whatsapp_cloud_oficial(client, seed, db, monkeypatch):
    residente = login(client, "edificio_a", "beto@x.cl")
    perf = ok(client.patch(BASE + "/mi-perfil", headers=residente, json={
        "nombre": "Beto Soto Actualizado", "telefono": "+56 9 8888 7777"
    }))
    assert perf["nombre"] == "Beto Soto Actualizado" and perf["telefono"] == "56988887777"

    # Recuperación de contraseña de un solo uso
    sol = ok(client.post("/auth/recuperar/solicitar", json={"edificio_id": "edificio_a", "email": "beto@x.cl"}))
    tok = sol["token_desarrollo"]
    ok(client.post("/auth/recuperar/confirmar", json={"token": tok, "nueva_password": "nuevaPasswordSegura99"}))
    # El token no se puede reutilizar y la sesión anterior queda revocada
    assert client.post("/auth/recuperar/confirmar", json={"token": tok, "nueva_password": "otraPassword99"}).status_code == 401
    assert client.get(BASE + "/mi-perfil", headers=residente).status_code == 401
    nuevo_login = client.post("/auth/login", json={
        "edificio_id": "edificio_a", "email": "beto@x.cl", "password": "nuevaPasswordSegura99"
    })
    assert nuevo_login.status_code == 200

    # WhatsApp Business Cloud API (Meta) verificación y webhook firmado
    monkeypatch.setattr(settings, "whatsapp_verify_token", "meta-verify-secret")
    monkeypatch.setattr(settings, "whatsapp_app_secret", "meta-app-secret")
    monkeypatch.setattr(settings, "whatsapp_cloud_token", "meta-cloud-token")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "123456789")
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(200, request=httpx.Request("POST", a[0])))

    ver = client.get("/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=meta-verify-secret&hub.challenge=ret99")
    assert ver.status_code == 200 and ver.text == "ret99"

    payload_bytes = json.dumps({
        "entry": [{"changes": [{"value": {"messages": [
            {"id": "wamid.1", "from": "56988887777", "type": "text", "text": {"body": "cuánto debo"}}
        ]}}]}]
    }).encode()
    sig = "sha256=" + hmac.new(b"meta-app-secret", payload_bytes, hashlib.sha256).hexdigest()
    w = client.post("/webhooks/whatsapp/cloud", content=payload_bytes,
                    headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert w.status_code == 200 and w.json()["intent"] == "consultar_deuda" and w.json()["envio"] == "enviado"
