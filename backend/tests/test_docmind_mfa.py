import json
import time
from uuid import uuid4

from cryptography.fernet import Fernet
import httpx
import pyotp
import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Residente
from app.operations_models import Documento, SegundoFactor
from app.services import docmind
from conftest import login

BASE = "/edificios/edificio_a"


def test_mfa_obligatorio_alta_y_codigo_no_reutilizable(client, seed, db, monkeypatch):
    monkeypatch.setattr(settings, "mfa_required_privileged", True)
    monkeypatch.setattr(settings, "mfa_encryption_key", Fernet.generate_key().decode())
    body = {"edificio_id": "edificio_a", "email": "ana@x.cl", "password": "secreto123"}
    r = client.post("/auth/login", json=body)
    assert r.status_code == 200 and r.json()["mfa_setup_required"]
    h = {"Authorization": "Bearer " + r.json()["setup_token"]}
    assert client.get(BASE + "/panel", headers=h).status_code == 401
    prep = client.post("/auth/mfa/preparar", headers=h, json={"password": "secreto123"})
    assert prep.status_code == 200
    secret = prep.json()["secreto"]
    assert secret not in db.query(SegundoFactor).first().secreto_cifrado
    codigo = pyotp.TOTP(secret).now()
    confirmado = client.post("/auth/mfa/confirmar", headers=h, json={"codigo": codigo})
    assert confirmado.status_code == 200, confirmado.text
    full = {"Authorization": "Bearer " + confirmado.json()["access_token"]}
    assert client.get(BASE + "/panel", headers=full).status_code == 200
    assert client.post("/auth/login", json=body).status_code == 401
    assert client.post("/auth/login", json={**body, "codigo_mfa": codigo}).status_code == 401
    # Control de reloj, sin esperar ni enviar códigos reales.
    siguiente = time.time() + 30
    monkeypatch.setattr("app.services.mfa.time.time", lambda: siguiente)
    nuevo = pyotp.TOTP(secret).at(siguiente)
    assert client.post("/auth/login", json={**body, "codigo_mfa": nuevo}).status_code == 200


def test_mfa_bloquea_intentos_de_alta(client, seed, db, monkeypatch):
    monkeypatch.setattr(settings, "mfa_encryption_key", Fernet.generate_key().decode())
    h = login(client, "edificio_a", "ana@x.cl")
    for _ in range(5):
        assert client.post("/auth/mfa/preparar", headers=h, json={"password": "incorrecta"}).status_code == 401
    assert client.post("/auth/mfa/preparar", headers=h, json={"password": "secreto123"}).status_code == 429


def test_docmind_upload_pregunta_fuentes_y_privacidad(client, seed, db, monkeypatch):
    admin = login(client, "edificio_a", "ana@x.cl")
    residente = login(client, "edificio_a", "beto@x.cl")
    org, project, remote_id = str(uuid4()), str(uuid4()), str(uuid4())
    monkeypatch.setattr(settings, "docmind_url", "https://docmind.example.test")
    monkeypatch.setattr(settings, "docmind_tenants", {"edificio_a": {"organization_id": org, "project_id": project, "api_key": "clave-de-prueba"}})
    real_client = httpx.Client
    calls = []
    def handler(req):
        calls.append(req)
        assert req.url.params["organization_id"] == org
        assert req.headers["authorization"] == "Bearer clave-de-prueba"
        if req.url.path == "/api/v1/documents":
            assert req.url.params["project_id"] == project
            return httpx.Response(202, json={"document_id": remote_id})
        if req.url.path.endswith("/download"):
            return httpx.Response(200, content=b"%PDF-test", headers={"content-type": "application/pdf"})
        payload = json.loads(req.content)
        assert payload["document_ids"] == [remote_id]
        return httpx.Response(200, json={"answer": "El plazo es 30 días.", "citations": [
            {"document_id": remote_id, "page": 2, "excerpt": "Plazo: 30 días."}]})
    monkeypatch.setattr(docmind.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    response = client.post(BASE + "/documentos", headers=admin,
        data={"titulo": "Contrato de prueba"}, files={"file": ("contrato.pdf", b"%PDF-test", "application/pdf")})
    assert response.status_code == 201, response.text
    did = response.json()["id"]
    assert client.get(BASE + "/documentos", headers=residente).json() == []
    assert client.get(BASE + f"/documentos/{did}/descargar", headers=residente).status_code == 404
    assert client.post(BASE + "/documentos/preguntar", headers=residente,
        json={"pregunta": "¿Cuál es el plazo?", "documentos": [did]}).status_code == 404
    assert len(calls) == 1
    result = client.post(BASE + "/documentos/preguntar", headers=admin,
        json={"pregunta": "¿Cuál es el plazo?", "documentos": [did]})
    assert result.status_code == 200 and result.json()["fuentes"][0]["id"] == did
    assert client.get(BASE + f"/documentos/{did}/descargar", headers=admin).content == b"%PDF-test"


@pytest.mark.parametrize("respuesta,status", [({"answer": "Sin sustento", "citations": []}, 200),
    ([], 502),
    ({"answer": "Filtración", "citations": [{"document_id": "otro-tenant"}]}, 502)])
def test_ia_no_acepta_fuentes_ajenas_o_sin_evidencia(client, seed, db, monkeypatch, respuesta, status):
    h = login(client, "edificio_a", "ana@x.cl")
    r = db.scalar(select(Residente).where(Residente.email == "ana@x.cl"))
    d = Documento(edificio_id="edificio_a", externo_id=str(uuid4()), titulo="Contrato", creado_por=r.id)
    db.add(d)
    db.commit()
    monkeypatch.setattr(docmind, "request", lambda *a, **kw: respuesta)
    response = client.post(BASE + "/documentos/preguntar", headers=h, json={"pregunta": "Plazo contractual", "documentos": [d.id]})
    assert response.status_code == status
    if status == 200:
        assert response.json()["abstencion"] and "Sin sustento" not in response.text


def test_docmind_sin_configuracion_no_aparenta_exito(client, seed):
    h = login(client, "edificio_a", "ana@x.cl")
    r = client.post(BASE + "/documentos", headers=h, data={"titulo": "Prueba de documento"},
                    files={"file": ("archivo.pdf", b"%PDF-test")})
    assert r.status_code == 503
