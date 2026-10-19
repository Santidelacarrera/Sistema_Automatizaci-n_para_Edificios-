"""Chequeo pre-commit: impide subir .env, copias de respaldo y secretos en el contenido que se va a commitear.

Uso manual:            python scripts/pre_commit_secretos.py
Instalar el hook:      python scripts/pre_commit_secretos.py --instalar
(el hook queda en .git/hooks/pre-commit y se ejecuta en cada commit; no reemplaza la prueba automática).
"""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import escaner_secretos  # noqa: E402


def _es_archivo_de_secretos(ruta: str) -> bool:
    nombre = ruta.replace("\\", "/").rsplit("/", 1)[-1]
    if nombre.endswith(".example"):
        return False
    return nombre == ".env" or nombre.startswith(".env.") or nombre.endswith(".env.bak") \
        or nombre == "config_local.py"


def archivos_en_stage() -> list[str]:
    salida = subprocess.run(["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACM"],
                            cwd=RAIZ, capture_output=True, check=True).stdout
    return [n for n in salida.decode("utf-8", "replace").split("\0") if n]


def contenido_en_stage(ruta: str) -> str:
    data = subprocess.run(["git", "show", f":{ruta}"], cwd=RAIZ, capture_output=True, check=True).stdout
    return data.decode("utf-8", "replace") if b"\0" not in data else ""


def revisar() -> list[str]:
    problemas = []
    for ruta in archivos_en_stage():
        if _es_archivo_de_secretos(ruta):
            problemas.append(f"{ruta}: archivo de secretos; no debe subirse a Git")
            continue
        for linea, tipo in escaner_secretos.hallazgos_en_texto(contenido_en_stage(ruta)):
            problemas.append(f"{ruta}:{linea}: posible secreto ({tipo})")
    return problemas


HOOK = "#!/bin/sh\n# Generado por scripts/pre_commit_secretos.py --instalar\nexec python scripts/pre_commit_secretos.py\n"


def instalar() -> Path:
    ruta = RAIZ / ".git" / "hooks" / "pre-commit"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(HOOK, encoding="utf-8", newline="\n")
    return ruta


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--instalar" in argv:
        print(f"Hook instalado en {instalar()}")
        return 0
    problemas = revisar()
    for p in problemas:
        print(f"BLOQUEADO: {p}", file=sys.stderr)
    if problemas:
        print("Commit cancelado: retire esos archivos o valores del stage (git rm --cached ...).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
