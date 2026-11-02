"""Prueba de carga del endpoint del portón (validar-acceso): el que más importa que responda rápido.

Uso (contra una API ya levantada y con datos sembrados):
    python scripts/prueba_carga.py --api http://localhost:8000 --edificio edificio_a --clave-dispositivo CLAVE \\
        --patentes BBCD12,KLPR45 --peticiones 2000 --concurrencia 25

Manda lecturas de patentes registradas y desconocidas mezcladas, con distintas patentes para no activar el
antirrebote, y reporta latencias (p50/p95/p99), errores y peticiones por segundo. Sólo envía a la URL indicada.
"""
import argparse
import asyncio
import random
import statistics
import string
import time

import httpx


async def main(a) -> int:
    conocidas = [p.strip().upper() for p in a.patentes.split(",") if p.strip()]
    letras = string.ascii_uppercase
    lat, estados = [], {}
    sem = asyncio.Semaphore(a.concurrencia)
    # Cada petición usa una patente distinta (sufijo numérico único) para esquivar el antirrebote de 3 s.
    async with httpx.AsyncClient(base_url=a.api, headers={"X-Device-Key": a.clave_dispositivo}, timeout=15) as c:
        async def una(i):
            if conocidas and random.random() < 0.5:
                token = conocidas[i % len(conocidas)]
                tipo = "patente"
            else:
                token = "".join(random.choices(letras, k=4)) + f"{i % 100:02d}"
                tipo = "patente"
            async with sem:
                t0 = time.perf_counter()
                try:
                    r = await c.post(f"/api/v1/{a.edificio}/validar-acceso",
                                     json={"edificio_id": a.edificio, "token_acceso": token, "punto": "vehicular",
                                           "tipo": tipo, "confianza": 0.97})
                    estados[r.status_code] = estados.get(r.status_code, 0) + 1
                except httpx.HTTPError as e:
                    estados[e.__class__.__name__] = estados.get(e.__class__.__name__, 0) + 1
                lat.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        await asyncio.gather(*(una(i) for i in range(a.peticiones)))
        total = time.perf_counter() - t0
    lat.sort()
    q = lambda p: lat[min(len(lat) - 1, int(len(lat) * p))]
    print(f"{a.peticiones} peticiones, concurrencia {a.concurrencia}, {total:.1f} s, {a.peticiones / total:.0f} pet/s")
    print(f"latencia ms: p50={q(.50):.0f} p95={q(.95):.0f} p99={q(.99):.0f} máx={lat[-1]:.0f} media={statistics.mean(lat):.0f}")
    print("respuestas:", dict(sorted(estados.items(), key=str)))
    fallas = sum(n for k, n in estados.items() if k not in (200, 403, 409))  # 403 y 409 son respuestas normales del portón
    if fallas:
        print(f"FALLÓ: {fallas} respuestas inesperadas")
        return 1
    if q(.95) > a.max_p95_ms:
        print(f"FALLÓ: p95 {q(.95):.0f} ms supera el máximo de {a.max_p95_ms} ms")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", required=True)
    p.add_argument("--edificio", required=True)
    p.add_argument("--clave-dispositivo", required=True, dest="clave_dispositivo")
    p.add_argument("--patentes", default="")
    p.add_argument("--peticiones", type=int, default=1000)
    p.add_argument("--concurrencia", type=int, default=20)
    p.add_argument("--max-p95-ms", type=float, default=500, dest="max_p95_ms")
    raise SystemExit(asyncio.run(main(p.parse_args())))
