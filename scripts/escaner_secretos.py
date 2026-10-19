"""Detecta secretos reales en archivos versionados (claves, contraseñas, URLs de base con usuario y clave).

Lo usan la prueba automática (backend/tests/test_secretos.py) y el chequeo pre-commit
(scripts/pre_commit_secretos.py). Los valores de ejemplo y los marcadores (cambiar, pegar, usuario...)
se ignoran a propósito: la documentación los usa.

Nunca imprime el valor encontrado: sólo el archivo, la línea y el tipo de hallazgo.
"""
import re
import subprocess
from pathlib import Path

PATRONES = [
    ("URL de base de datos con usuario y clave",
     re.compile(r"\b(?:postgres(?:ql)?(?:\+\w+)?|mysql(?:\+\w+)?|rediss?)://([^:/\s'\"]+):([^@\s/'\"]+)@"), 2),
    ("clave de API de Anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), 0),
    ("clave privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), 0),
    ("secreto asignado en un archivo de configuración",
     re.compile(r"(?m)^\s*(JWT_SECRET|SMTP_PASSWORD|EVOLUTION_APIKEY|WHATSAPP_WEBHOOK_TOKEN|DB_PASSWORD|"
                r"ANTHROPIC_API_KEY|DEVICE_KEY\w*|SUPABASE\w*)\s*[=:]\s*['\"]?([^\s'\"#]+)"), 2),
]
# Valores que son ejemplos o marcadores, no secretos reales.
MARCADORES = ("cambiar", "pegar", "ejemplo", "example", "usuario", "clave", "password", "contrasena",
              "xxx", "<", "${", "tu-", "your", "changeme", "placeholder", "host", "...", "secreto",
              "none", "edificio")
LARGO_MINIMO_ASIGNADO = 12
EXCLUIR_SIEMPRE = {"scripts/escaner_secretos.py"}  # su propio código describe los patrones


def _es_marcador(valor: str) -> bool:
    v = valor.lower()
    return any(m in v for m in MARCADORES)


def hallazgos_en_texto(texto: str) -> list[tuple[int, str]]:
    """Devuelve [(número_de_línea, tipo)] para cada posible secreto real en ``texto``."""
    resultado = []
    for numero, linea in enumerate(texto.splitlines(), 1):
        for tipo, patron, grupo in PATRONES:
            for m in patron.finditer(linea):
                if grupo:
                    valor = m.group(grupo)
                    if _es_marcador(valor):
                        continue
                    if tipo.startswith("secreto") and len(valor) < LARGO_MINIMO_ASIGNADO:
                        continue
                resultado.append((numero, tipo))
    return resultado


def archivos_versionados(raiz: Path) -> list[Path]:
    """Lista de archivos rastreados por Git (o vacío si no es un repositorio)."""
    try:
        salida = subprocess.run(["git", "ls-files", "-z"], cwd=raiz, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [raiz / n for n in salida.decode("utf-8", "replace").split("\0") if n]


def escanear_repo(raiz: Path) -> list[tuple[str, int, str]]:
    """[(ruta_relativa, línea, tipo)] de todos los archivos de texto versionados."""
    hallazgos = []
    for ruta in archivos_versionados(raiz):
        rel = ruta.relative_to(raiz).as_posix()
        if rel in EXCLUIR_SIEMPRE or not ruta.is_file():
            continue
        data = ruta.read_bytes()
        if b"\0" in data or len(data) > 2_000_000:  # binarios y archivos enormes no son código fuente
            continue
        for linea, tipo in hallazgos_en_texto(data.decode("utf-8", "replace")):
            hallazgos.append((rel, linea, tipo))
    return hallazgos


if __name__ == "__main__":
    import sys
    raiz = Path(__file__).resolve().parents[1]
    encontrados = escanear_repo(raiz)
    for rel, linea, tipo in encontrados:
        print(f"{rel}:{linea}: posible secreto ({tipo})")
    print(f"{len(encontrados)} hallazgo(s).")
    sys.exit(1 if encontrados else 0)
