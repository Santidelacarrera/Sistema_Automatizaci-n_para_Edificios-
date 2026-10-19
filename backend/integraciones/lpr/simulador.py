"""Simula eventos de cámara para probar sin hardware.

    python -m integraciones.lpr.simulador --url http://localhost:8090 --token TOKEN_CAMARA BBCD12 0.95
"""
import argparse
import json
import sys

import httpx


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Envía una lectura simulada al traductor LPR.")
    p.add_argument("patente")
    p.add_argument("confianza", type=float)
    p.add_argument("--url", default="http://localhost:8090")
    p.add_argument("--token", required=True, help="X-LPR-Token configurado en el traductor")
    p.add_argument("--camara", default="simulador")
    a = p.parse_args(argv)
    cuerpo = {"patente": a.patente, "confianza": a.confianza, "camara": a.camara}
    r = httpx.post(f"{a.url}/lpr/evento", json=cuerpo, headers={"X-LPR-Token": a.token}, timeout=10)
    print(r.status_code, json.dumps(r.json(), ensure_ascii=False))
    return 0 if r.status_code == 202 else 1


if __name__ == "__main__":
    sys.exit(main())
