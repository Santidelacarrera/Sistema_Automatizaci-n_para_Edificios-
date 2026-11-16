from datetime import date
from pathlib import PurePath
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Rol
from ..operation_schemas import Entrada
from ..operations_models import Documento
from ..services import docmind
from .operaciones import Admin, User, auditar, edificio, ficha, recurso

router = APIRouter(prefix="/edificios/{edificio_id}/documentos", tags=["documentos"])
CAMPOS = "id titulo categoria publico_comunidad vence creado"


def autorizado(db, user, eid, did):
    d = recurso(db, Documento, eid, did)
    if not d.publico_comunidad and user.rol not in (Rol.admin, Rol.superadmin):
        raise HTTPException(404, "Documento no existe")
    return d


def archivo(file):
    nombre = PurePath((file.filename or "").replace("\\", "/")).name
    if PurePath(nombre).suffix.lower() not in (".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg"):
        raise HTTPException(415, "Formatos admitidos: PDF, DOCX, XLSX, PNG y JPEG")
    data = file.file.read(docmind.MAX_BYTES + 1)
    if not data or len(data) > docmind.MAX_BYTES:
        raise HTTPException(413, "El archivo debe contener datos y pesar como máximo 20 MiB")
    return nombre, data, file.content_type or "application/octet-stream"


@router.get("")
def listar(edificio_id: str, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    q = select(Documento).where(Documento.edificio_id == edificio_id)
    if user.rol not in (Rol.admin, Rol.superadmin):
        q = q.where(Documento.publico_comunidad.is_(True))
    return [ficha(d, CAMPOS) for d in db.scalars(q.order_by(Documento.id.desc()).limit(200))]


@router.post("", status_code=201)
def subir(edificio_id: str, user: Admin, file: UploadFile = File(...), titulo: str = Form(..., min_length=3, max_length=160),
          categoria: str = Form("general", max_length=30), publico_comunidad: bool = Form(False),
          vence: date | None = Form(None), db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    cfg = docmind.configuracion(edificio_id)
    result = docmind.request(edificio_id, "POST", "/documents", params={"project_id": cfg["project_id"]},
                             files={"file": archivo(file)})
    try:
        externo_id = str(UUID(result["document_id"]))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(502, "DOCMIND no confirmó un identificador de documento") from None
    previo = db.scalar(select(Documento).where(Documento.edificio_id == edificio_id, Documento.externo_id == externo_id))
    if previo:
        return {**ficha(previo, CAMPOS), "duplicado": True}
    d = Documento(edificio_id=edificio_id, externo_id=externo_id, titulo=titulo.strip(), categoria=categoria,
                   publico_comunidad=publico_comunidad, vence=vence, creado_por=user.residente_id)
    db.add(d)
    db.flush()
    auditar(db, user, edificio_id, "documento.creado", d.id)
    db.commit()
    return ficha(d, CAMPOS)


@router.get("/{documento_id}/estado")
def estado(edificio_id: str, documento_id: int, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    d = autorizado(db, user, edificio_id, documento_id)
    return docmind.request(edificio_id, "GET", f"/documents/{d.externo_id}/status")


@router.get("/{documento_id}/descargar")
def descargar(edificio_id: str, documento_id: int, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    d = autorizado(db, user, edificio_id, documento_id)
    data, tipo = docmind.request(edificio_id, "GET", f"/documents/{d.externo_id}/download", binario=True)
    return Response(data, media_type=tipo, headers={"Content-Disposition": 'attachment; filename="documento"',
                                                   "Cache-Control": "no-store"})


@router.post("/{documento_id}/versiones", status_code=202)
def version(edificio_id: str, documento_id: int, user: Admin, file: UploadFile = File(...), db: Session = Depends(get_db)):
    edificio(db, user, edificio_id, True)
    d = autorizado(db, user, edificio_id, documento_id)
    result = docmind.request(edificio_id, "POST", f"/documents/{d.externo_id}/versions", files={"file": archivo(file)})
    auditar(db, user, edificio_id, "documento.version", d.id)
    db.commit()
    return result


class Pregunta(Entrada):
    pregunta: str = Field(min_length=3, max_length=500)
    documentos: list[int] = Field(min_length=1, max_length=25)


@router.post("/preguntar")
def preguntar(edificio_id: str, body: Pregunta, user: User, db: Session = Depends(get_db)):
    edificio(db, user, edificio_id)
    docs = [autorizado(db, user, edificio_id, did) for did in set(body.documentos)]
    permitidos = {d.externo_id: d for d in docs}
    result = docmind.request(edificio_id, "POST", "/ask", json={"question": body.pregunta, "document_ids": list(permitidos)})
    if not isinstance(result, dict):
        raise HTTPException(502, "DOCMIND devolvió una respuesta inválida")
    fuentes = result.get("citations", [])
    if not isinstance(fuentes, list) or any(not isinstance(c, dict) or c.get("document_id") not in permitidos for c in fuentes):
        raise HTTPException(502, "La respuesta contiene fuentes fuera del alcance autorizado")
    if not fuentes or result.get("abstained"):
        return {"respuesta": "No hay evidencia documental suficiente para responder.", "fuentes": [], "abstencion": True}
    return {"respuesta": result.get("answer", ""), "abstencion": False,
            "fuentes": [{"id": permitidos[c["document_id"]].id, "titulo": permitidos[c["document_id"]].titulo,
                         "pagina": c.get("page"), "fragmento": c.get("excerpt", "")} for c in fuentes]}
