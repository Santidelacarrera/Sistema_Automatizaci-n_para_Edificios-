"""Configuración del traductor LPR, leída del entorno (nunca del repositorio)."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    backend_url: str          # p. ej. http://api:8000
    edificio_id: str          # tenant al que pertenece el lector
    device_key: str           # X-Device-Key del edificio (secreto)
    token_camara: str         # token que la cámara o el puente envían en X-LPR-Token (secreto)
    confianza_minima: float   # lecturas por debajo se rechazan sin llamar al backend
    dedup_segundos: int       # misma patente dentro de esta ventana se ignora
    adaptador: str            # generico | hikvision | dahua

    @classmethod
    def desde_entorno(cls, env=os.environ) -> "Config":
        faltan = [v for v in ("LPR_BACKEND_URL", "LPR_EDIFICIO_ID", "LPR_DEVICE_KEY", "LPR_TOKEN_CAMARA")
                  if not env.get(v)]
        if faltan:
            raise RuntimeError(f"Faltan variables de entorno: {', '.join(faltan)}")
        return cls(
            backend_url=env["LPR_BACKEND_URL"].rstrip("/"),
            edificio_id=env["LPR_EDIFICIO_ID"],
            device_key=env["LPR_DEVICE_KEY"],
            token_camara=env["LPR_TOKEN_CAMARA"],
            confianza_minima=float(env.get("LPR_CONFIANZA_MINIMA", "0.85")),
            dedup_segundos=int(env.get("LPR_DEDUP_SEGUNDOS", "30")),
            adaptador=env.get("LPR_ADAPTADOR", "generico"),
        )
