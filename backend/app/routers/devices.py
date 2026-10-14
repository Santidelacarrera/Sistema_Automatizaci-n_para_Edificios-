from fastapi import APIRouter, Depends, HTTPException
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
    if body.edificio_id != edificio.id:
        raise HTTPException(400, "edificio_id del cuerpo no coincide con la ruta")
    ok, motivo = access.validar_acceso(db, edificio, body.token_acceso, body.punto)
    db.commit()
    if not ok:
        raise HTTPException(403, motivo)  # el firmware abre sólo con 200
    return {"abrir": True, "motivo": motivo}
