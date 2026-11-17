"""Simulador del protocolo individual. No importa drivers ni acciona relés.

SIM_DEVICE_KEY en entorno; ejemplo:
python firmware/tools/simular_controlador.py --api http://localhost:8000 --edificio edificio_a --dispositivo 1
"""
import argparse
from datetime import datetime, timezone
import json
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--edificio", required=True)
    p.add_argument("--dispositivo", type=int, required=True)
    args = p.parse_args()
    parsed = urlparse(args.api)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")):
        p.error("Sólo HTTPS o HTTP local")
    key = os.environ.get("SIM_DEVICE_KEY")
    if not key:
        p.error("Configure SIM_DEVICE_KEY en el entorno")
    base = f"{args.api.rstrip('/')}/api/v1/{args.edificio}/dispositivos/{args.dispositivo}"
    def post(path, body):
        req = Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "X-Device-Key": key}, method="POST")
        with urlopen(req, timeout=5) as response:
            return json.load(response)
    estado = post("/heartbeat", {"firmware": "simulador-1.0", "bateria": 100})
    if not estado.get("laboratorio"):
        p.error("Este controlador no está marcado como laboratorio")
    comando = post("/comandos/obtener", {}).get("comando")
    if comando is None:
        print("Sin comandos. Autorice uno en el panel y vuelva a ejecutar dentro de 30 segundos.")
        return
    if comando["accion"] != "simular_apertura" or datetime.fromisoformat(comando["expira"]) <= datetime.now(timezone.utc):
        p.error("Comando desconocido o expirado: no se ejecuta")
    post(f"/comandos/{comando['id']}/confirmar", {"nonce": comando["nonce"], "estado": "ejecutado"})
    print(f"Comando {comando['id']} simulado y confirmado. Ningún actuador físico fue utilizado.")


if __name__ == "__main__":
    main()
