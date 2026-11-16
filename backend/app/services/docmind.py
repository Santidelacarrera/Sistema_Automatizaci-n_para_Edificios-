"""Contrato de DOCMIND_AI/backend/app/routers, inspeccionado el 2026-11-16.

La API key debe estar restringida al proyecto exclusivo del edificio y a documents:read/write.
Nunca se acepta organization_id, project_id ni URL desde una solicitud de un residente.
"""
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import HTTPException

from ..config import settings

MAX_BYTES = 20 * 1024 * 1024


def configuracion(eid):
    cfg = settings.docmind_tenants.get(eid, {})
    parsed = urlparse(settings.docmind_url)
    seguro = parsed.scheme == "https" or (settings.entorno != "produccion" and
              parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "docmind"))
    if not seguro or parsed.username or parsed.password or parsed.query or parsed.fragment or not all(
            cfg.get(k) for k in ("organization_id", "project_id", "api_key")):
        raise HTTPException(503, "DOCMIND no está configurado para este edificio")
    try:
        UUID(cfg["organization_id"])
        UUID(cfg["project_id"])
    except ValueError:
        raise HTTPException(503, "Configuración de DOCMIND inválida") from None
    for otro, valor in settings.docmind_tenants.items():
        if otro != eid and valor.get("project_id") == cfg["project_id"]:
            raise HTTPException(503, "Cada edificio requiere un proyecto DOCMIND exclusivo")
    return cfg


def request(eid, method, path, *, params=None, json=None, files=None, binario=False):
    cfg = configuracion(eid)
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            with client.stream(method, settings.docmind_url.rstrip("/") + "/api/v1" + path,
                               headers={"Authorization": f"Bearer {cfg['api_key']}"},
                               params={"organization_id": cfg["organization_id"], **(params or {})},
                               json=json, files=files) as response:
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(502, "DOCMIND devolvió un archivo demasiado grande")
                    chunks.append(chunk)
                data = b"".join(chunks)
                if not response.is_success:
                    if response.status_code == 409 and path == "/documents":
                        import json as codec
                        previo = codec.loads(data)
                        if previo.get("detail") == "DUPLICATE_DOCUMENT":
                            return {"document_id": previo["document_id"], "duplicado": True}
                    raise HTTPException(503 if response.status_code >= 500 else 422,
                                        "DOCMIND no pudo completar la operación; revise permisos, formato y estado del documento")
                if binario:
                    return data, response.headers.get("content-type", "application/octet-stream")
                import json as codec
                return codec.loads(data)
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(503, "DOCMIND no está disponible o devolvió una respuesta inválida") from None
