from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Edificio
from ..schemas import ValidarAccesoIn
from ..security import device_building
from ..services import access

router = APIRouter(prefix="/api/v1/{edificio_id}", tags=["dispositivos"])


@router.post("/validar-acceso")
def validar_acceso(body: ValidarAccesoIn, edificio: Edificio = Depends(device_building),
                   db: Session = Depends(get_db)):
    """200 = abrir. 409 = lectura repetida (rebote). 403 = denegada o esperando la otra lectura.
    El firmware del portón sólo acciona el relé con 200."""
    if body.edificio_id != edificio.id:
        raise HTTPException(400, "edificio_id del cuerpo no coincide con la ruta")
    d = access.decidir(db, edificio, body.token_acceso, body.punto, body.tipo, body.confianza, body.direccion)
    db.commit()
    if d.abrir:
        return {"abrir": True, "motivo": d.motivo, "codigo": d.codigo}
    estado = 409 if d.codigo == "duplicada" else 403
    return JSONResponse(status_code=estado, content={"detail": d.motivo, "codigo": d.codigo, "abrir": False})
