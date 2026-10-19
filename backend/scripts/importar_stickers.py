"""Importa stickers UHF desde CSV. Idempotente; rechaza códigos repetidos en el lote o ya registrados.

    python scripts/importar_stickers.py --edificio edificio_a ../datos/stickers.csv --dry-run
    python scripts/importar_stickers.py --edificio edificio_a ../datos/stickers.csv

Plantilla: docs/plantillas/stickers.csv. Exit code: 0 sin errores, 1 con filas rechazadas, 2 si no se pudo leer.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal  # noqa: E402
from app.models import Edificio  # noqa: E402
from app.services import stickers  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Importa stickers UHF desde CSV.")
    p.add_argument("archivo")
    p.add_argument("--edificio", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    try:
        with open(a.archivo, encoding="utf-8-sig") as f:
            texto = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"No se pudo leer el archivo: {e}", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        ed = db.get(Edificio, a.edificio)
        if not ed:
            print(f"El edificio '{a.edificio}' no existe.", file=sys.stderr)
            return 2
        rep = stickers.importar(db, ed, texto, dry_run=a.dry_run)
    modo = " (simulación, nada se escribió)" if a.dry_run else ""
    print(f"Stickers: {rep.creados} creados, {rep.sin_cambios} sin cambios, "
          f"{rep.vinculados_patente} patentes vinculadas{modo}")
    for linea, msg in sorted(rep.errores):
        print(f"Línea {linea}: {msg}", file=sys.stderr)
    if rep.errores:
        print(f"{len(rep.errores)} fila(s) rechazada(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
