"""Simula las lecturas del lector del portón contra el backend, sin hardware.

Ejemplos (la clave de dispositivo se pasa por variable de entorno, nunca en el historial):

  set DEVICE_KEY=...                                    (PowerShell: $env:DEVICE_KEY="...")
  python firmware/tools/simular_lector.py --url http://localhost:8000 --edificio edificio_a sticker E280117000000000000000A1
  python firmware/tools/simular_lector.py --url http://localhost:8000 --edificio edificio_a wiegand --bits 26 --fac 42 --card 12345
  python firmware/tools/simular_lector.py --url http://localhost:8000 --edificio edificio_a patente BBCD12 --confianza 0.95
  python firmware/tools/simular_lector.py ... wiegand --bits 26 --fac 42 --card 12345 --repetir 3 --intervalo 0.5

Muestra la respuesta igual que lo vería el relé: 200 = abre; 409 = lectura repetida; 403 = no abre (con motivo).
"""
import argparse
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "esp32"))
import wiegand_codec  # noqa: E402  (módulo compartido con el firmware)


def enviar_lectura(cliente, edificio, clave, token, tipo=None, punto="vehicular", direccion=None, confianza=None):
    """Devuelve (codigo_http, cuerpo_json). Mismo cuerpo que envía el firmware."""
    cuerpo = {"edificio_id": edificio, "token_acceso": token, "punto": punto}
    if tipo:
        cuerpo["tipo"] = tipo
    if direccion:
        cuerpo["direccion"] = direccion
    if confianza is not None:
        cuerpo["confianza"] = confianza
    r = cliente.post(f"/api/v1/{edificio}/validar-acceso", json=cuerpo, headers={"X-Device-Key": clave})
    try:
        datos = r.json()
    except ValueError:
        datos = {}
    return r.status_code, datos


def _token_de_argumentos(a):
    if a.modo == "sticker":
        return a.epc, "sticker", None
    if a.modo == "wiegand":
        bits = wiegand_codec.codificar(a.fac, a.card, a.bits)
        # verifica la trama como lo haría el firmware antes de enviar
        fac, card = wiegand_codec.decodificar(bits, a.bits)
        return wiegand_codec.token(fac, card, a.bits), "sticker", bits
    return a.patente, "patente", None


def main(argv=None):
    p = argparse.ArgumentParser(description="Simulador del lector del portón.")
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--edificio", required=True)
    p.add_argument("--punto", default="vehicular", choices=["vehicular", "peatonal"])
    p.add_argument("--direccion", choices=["entrada", "salida"], default=None)
    p.add_argument("--repetir", type=int, default=1)
    p.add_argument("--intervalo", type=float, default=1.0, help="segundos entre lecturas repetidas")
    sub = p.add_subparsers(dest="modo", required=True)
    s = sub.add_parser("sticker", help="EPC hexadecimal de un sticker UHF")
    s.add_argument("epc")
    w = sub.add_parser("wiegand", help="código de un lector Wiegand")
    w.add_argument("--bits", type=int, choices=[26, 34], default=26)
    w.add_argument("--fac", type=int, required=True)
    w.add_argument("--card", type=int, required=True)
    pa = sub.add_parser("patente", help="patente leída por la cámara")
    pa.add_argument("patente")
    pa.add_argument("--confianza", type=float, default=0.95)
    a = p.parse_args(argv)

    clave = os.environ.get("DEVICE_KEY")
    if not clave:
        print("Falta la variable de entorno DEVICE_KEY (X-Device-Key del edificio).", file=sys.stderr)
        return 2
    token, tipo, bits = _token_de_argumentos(a)
    if bits is not None:
        print("trama Wiegand:", "".join(str(b) for b in bits), "->", token)
    confianza = a.confianza if a.modo == "patente" else None
    tipo_envio = "patente" if a.modo == "patente" else "sticker"
    with httpx.Client(base_url=a.url, timeout=5) as cliente:
        for i in range(a.repetir):
            codigo, cuerpo = enviar_lectura(cliente, a.edificio, clave, token, tipo_envio, a.punto,
                                            a.direccion, confianza)
            motivo = cuerpo.get("motivo") or cuerpo.get("detail", "")
            print(f"[{i + 1}/{a.repetir}] HTTP {codigo}: {'ABRE' if codigo == 200 else 'no abre'} {motivo}")
            if i + 1 < a.repetir:
                time.sleep(a.intervalo)
    return 0 if codigo == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
