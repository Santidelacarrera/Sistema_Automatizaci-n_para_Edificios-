"""Servidor HTTP del traductor: la cámara (o su puente) hace POST /lpr/evento con X-LPR-Token.

Arranque:  uvicorn integraciones.lpr.servidor:app --host 0.0.0.0 --port 8090   (desde backend/)
Configuración por variables de entorno: ver integraciones/lpr/README.md.
"""
import hmac
import logging

from fastapi import FastAPI, Header, HTTPException, Request

from . import adaptadores
from .config import Config
from .lectura import LecturaInvalida, validar
from .traductor import Traductor

logging.basicConfig(level=logging.INFO, format='{"nivel":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')

app = FastAPI(title="Traductor LPR", version="0.1.0")
_estado: dict = {}


def _traductor() -> Traductor:
    if "t" not in _estado:
        cfg = Config.desde_entorno()
        _estado["cfg"] = cfg
        _estado["parsear"] = adaptadores.cargar(cfg.adaptador)
        _estado["t"] = Traductor(cfg)
    return _estado["t"]


@app.post("/lpr/evento", status_code=202)
async def evento(request: Request, x_lpr_token: str | None = Header(None)):
    t = _traductor()
    if not x_lpr_token or not hmac.compare_digest(x_lpr_token, _estado["cfg"].token_camara):
        raise HTTPException(401, "Token de cámara no autorizado")
    try:
        lectura = validar(_estado["parsear"](await request.json()))
    except LecturaInvalida as e:
        raise HTTPException(422, str(e))
    except NotImplementedError as e:  # adaptador de marca aún no confirmado
        raise HTTPException(501, str(e))
    res = t.procesar(lectura)
    # nunca se devuelve la patente en la respuesta: sólo el resultado
    return {"estado": res.estado, "abrir": res.abrir, "motivo": res.motivo}


@app.get("/health")
def health():
    return {"ok": True}
