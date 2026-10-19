"""Lógica del traductor: umbral de confianza, deduplicación y llamada a /validar-acceso.

Regla de seguridad: sólo se abre con respuesta 200 explícita del backend. Cualquier otra cosa
(rechazo, error, timeout, respuesta inesperada) deja el portón cerrado.
"""
import logging
import time
from dataclasses import dataclass

import httpx

from .config import Config
from .lectura import Lectura

log = logging.getLogger("lpr")

ESTADOS = ("enviada", "error_backend", "rechazada_confianza", "duplicada")


@dataclass(frozen=True)
class Resultado:
    estado: str           # enviada (el backend respondió) | error_backend | rechazada_confianza | duplicada
    abrir: bool = False
    motivo: str = ""


class Traductor:
    def __init__(self, cfg: Config, http: httpx.Client | None = None, reloj=time.monotonic):
        self.cfg = cfg
        self.http = http or httpx.Client(base_url=cfg.backend_url, timeout=5)
        self.reloj = reloj
        self._vistas: dict[str, float] = {}  # patente -> último instante enviado (monotónico)

    def _es_duplicada(self, patente: str) -> bool:
        ahora = self.reloj()
        # limpieza simple: descarta lo que ya venció para que el dict no crezca sin límite
        self._vistas = {p: t for p, t in self._vistas.items() if ahora - t < self.cfg.dedup_segundos}
        return patente in self._vistas

    def procesar(self, lectura: Lectura) -> Resultado:
        if lectura.confianza < self.cfg.confianza_minima:
            log.info("lectura descartada por baja confianza: %.2f < %.2f", lectura.confianza, self.cfg.confianza_minima)
            return Resultado("rechazada_confianza", motivo=f"confianza {lectura.confianza:.2f} bajo el mínimo")
        if self._es_duplicada(lectura.patente):
            return Resultado("duplicada", motivo="misma patente dentro de la ventana de deduplicación")
        self._vistas[lectura.patente] = self.reloj()
        cuerpo = {"edificio_id": self.cfg.edificio_id, "token_acceso": lectura.patente, "punto": "vehicular",
                  "tipo": "patente", "confianza": lectura.confianza}
        try:
            r = self.http.post(f"/api/v1/{self.cfg.edificio_id}/validar-acceso", json=cuerpo,
                               headers={"X-Device-Key": self.cfg.device_key})
        except httpx.HTTPError as e:
            # no se cachea la patente como enviada: si el backend volvió, la siguiente lectura sí va
            self._vistas.pop(lectura.patente, None)
            log.error("backend no disponible: %s", e.__class__.__name__)
            return Resultado("error_backend", abrir=False, motivo="backend no disponible: portón cerrado")
        if r.status_code >= 500:
            self._vistas.pop(lectura.patente, None)
            return Resultado("error_backend", abrir=False, motivo=f"backend respondió {r.status_code}")
        if r.status_code == 200 and r.json().get("abrir") is True:
            return Resultado("enviada", abrir=True, motivo=r.json().get("motivo", ""))
        return Resultado("enviada", abrir=False, motivo=f"backend respondió {r.status_code}")
