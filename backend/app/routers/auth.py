from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Residente
from ..schemas import LoginIn
from ..security import create_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    r = db.scalar(select(Residente).where(Residente.edificio_id == body.edificio_id,
                                          Residente.email == body.email, Residente.activo.is_(True)))
    if not r or not verify_password(body.password, r.password_hash):
        raise HTTPException(401, "Credenciales inválidas")
    return {"access_token": create_token(r.id, r.edificio_id, r.rol), "token_type": "bearer"}
