"""Asistente para crear el archivo .env con tus credenciales, sin pasarlas por el chat ni por Git.

Ejecútelo usted, en su computador:   python scripts/configurar_entorno.py

- Los datos secretos se escriben con entrada oculta (getpass). No se muestran completos en ningún momento.
- Los opcionales pueden dejarse vacíos; el asistente dice qué funciones quedan desactivadas.
- Si .env ya existe, pregunta antes de tocarlo y guarda una copia en .env.bak.
- Escribe .env con permisos restringidos (600 en Linux/macOS; en Windows el archivo queda en su carpeta de usuario).
- Verifica que .env, .env.bak y config_local.py estén ignorados por Git.

Este módulo sólo usa la biblioteca estándar. Las funciones de validación y escritura están separadas
de la interacción para poder probarlas sin credenciales reales.
"""
import getpass
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

RAIZ = Path(__file__).resolve().parents[1]
LARGO_MINIMO_SECRETO = 32
JWT_POR_DEFECTO = "cambiar-en-produccion"
PUERTO_POOLER_TRANSACCION = 6543
ENTRADAS_GITIGNORE = (".env", ".env.bak", "*.env.bak", "config_local.py")


# ---------- validación (sin imprimir valores) ----------
def mascara(valor: str) -> str:
    """Forma segura de mostrar un secreto: sólo los últimos 4 caracteres."""
    if not valor:
        return "(vacío)"
    return "****" + valor[-4:] if len(valor) >= 8 else "****"


def generar_secreto() -> str:
    return secrets.token_urlsafe(48)  # 64 caracteres, sobre el mínimo de 32


def validar_secreto(nombre: str, valor: str) -> str | None:
    """Mensaje de error o None si el secreto es aceptable. Nunca incluye el valor."""
    if not valor:
        return f"{nombre} no puede estar vacío"
    if len(valor) < LARGO_MINIMO_SECRETO:
        return f"{nombre} debe tener al menos {LARGO_MINIMO_SECRETO} caracteres (tiene {len(valor)})"
    if " " in valor:
        return f"{nombre} no debe contener espacios"
    return None


def validar_jwt(valor: str) -> str | None:
    if valor == JWT_POR_DEFECTO:
        return "JWT_SECRET no puede ser el valor de ejemplo: genere uno propio"
    return validar_secreto("JWT_SECRET", valor)


def normalizar_database_url(url: str) -> tuple[str, list[str]]:
    """Convierte la cadena de Supabase (o cualquier PostgreSQL) al prefijo de SQLAlchemy.

    Devuelve (url_normalizada, avisos). Lanza ValueError con un mensaje explicado si no sirve.
    Nunca incluye la clave en el mensaje de error.
    """
    url = (url or "").strip()
    avisos: list[str] = []
    if "YOUR-PASSWORD" in url or "[" in url or "]" in url:
        raise ValueError("La cadena aún tiene el marcador [YOUR-PASSWORD]: reemplácelo por su contraseña real")
    if url.startswith("sqlite"):
        return url, ["SQLite: sólo sirve para desarrollo, no para producción"]
    for prefijo in ("postgres://", "postgresql://", "postgresql+psycopg://"):
        if url.startswith(prefijo):
            resto = url[len(prefijo):]
            break
    else:
        raise ValueError("La cadena debe empezar con postgresql:// (cópiela tal como la entrega Supabase)")
    partes = urlsplit("postgresql://" + resto)
    if not partes.hostname or not partes.username:
        raise ValueError("Faltan el servidor o el usuario en la cadena de conexión")
    if partes.password is None or partes.password == "":
        raise ValueError("Falta la contraseña en la cadena de conexión (reemplace [YOUR-PASSWORD] por su clave)")
    puerto = partes.port or 5432
    if puerto == PUERTO_POOLER_TRANSACCION:
        raise ValueError(
            "El puerto 6543 es el pooler de Supabase en modo 'transaction'. Alembic, las transacciones "
            "largas y los prepared statements fallan ahí. Use el puerto 5432 (modo 'session' o conexión directa).")
    consulta = dict(parse_qsl(partes.query))
    if partes.hostname.endswith(("supabase.co", "supabase.com")) and "sslmode" not in consulta:
        consulta["sslmode"] = "require"
        avisos.append("Supabase exige SSL: se agregó sslmode=require")
    usuario = quote(unquote(partes.username), safe="")
    clave = quote(unquote(partes.password), safe="")
    host = partes.hostname
    netloc = f"{usuario}:{clave}@{host}:{puerto}"
    normalizada = urlunsplit(("postgresql+psycopg", netloc, partes.path or "/postgres", urlencode(consulta), ""))
    if partes.port is None:
        avisos.append("No indicó puerto: se usa el 5432")
    return normalizada, avisos


def enmascarar_url(url: str) -> str:
    """postgresql+psycopg://user:****abcd@host:5432/db (para mostrar al usuario)."""
    partes = urlsplit(url)
    if not partes.password:
        return url
    return url.replace(quote(unquote(partes.password), safe=""), mascara(unquote(partes.password)), 1)


def validar_url_http(nombre: str, valor: str) -> str | None:
    if not re.match(r"^https?://[^\s/]+", valor):
        return f"{nombre} debe empezar con http:// o https:// y tener un servidor"
    return None


def validar_correo(valor: str) -> str | None:
    return None if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", valor) else "El correo no tiene un formato válido"


def validar_puerto(valor: str) -> str | None:
    return None if valor.isdigit() and 1 <= int(valor) <= 65535 else "El puerto debe ser un número entre 1 y 65535"


# ---------- archivo .env ----------
PLANTILLA = [
    "ENTORNO", "DATABASE_URL", "JWT_SECRET", "WHATSAPP_WEBHOOK_TOKEN", "CORS_ORIGINS",
    "EVOLUTION_URL", "EVOLUTION_INSTANCE", "EVOLUTION_APIKEY",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM",
    "ANTHROPIC_API_KEY",
]


def _valor_env(valor: str) -> str:
    """Valor listo para una línea KEY=valor. Entre comillas sólo si tiene espacios, '#' o comillas."""
    if not valor:
        return ""
    if re.search(r"[\s#\"']", valor):
        escapado = valor.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escapado}"'
    return valor


def construir_env(valores: dict[str, str]) -> str:
    """Contenido de .env: primero las claves de la plantilla en orden fijo, luego las claves de dispositivo."""
    lineas = ["# Generado por scripts/configurar_entorno.py. NO subir a Git.", ""]
    for clave in PLANTILLA:
        if clave in valores:
            lineas.append(f"{clave}={_valor_env(valores[clave])}")
    for clave in sorted(valores):
        if clave.startswith("DEVICE_KEY_"):
            lineas.append(f"{clave}={_valor_env(valores[clave])}")
    return "\n".join(lineas) + "\n"


def escribir_env(ruta: Path, contenido: str) -> Path | None:
    """Escribe ``ruta``. Si ya existía, lo copia a .env.bak antes. Devuelve la ruta del respaldo o None."""
    respaldo = None
    if ruta.exists():
        respaldo = ruta.with_name(ruta.name + ".bak")
        shutil.copy2(ruta, respaldo)
        os.chmod(respaldo, 0o600)
    ruta.write_text(contenido, encoding="utf-8", newline="\n")
    os.chmod(ruta, 0o600)
    return respaldo


def asegurar_ignorados(raiz: Path) -> list[str]:
    """Agrega a .gitignore las entradas de secretos que falten. Devuelve las agregadas."""
    gi = raiz / ".gitignore"
    actual = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    faltan = [e for e in ENTRADAS_GITIGNORE if e not in actual]
    if faltan:
        bloque = (["", "# Secretos locales (scripts/configurar_entorno.py)"] + faltan)
        gi.write_text("\n".join(actual + bloque) + "\n", encoding="utf-8", newline="\n")
    return faltan


def verificar_ignorados(raiz: Path, rutas: list[str]) -> dict[str, bool] | None:
    """{ruta: está_ignorada}. None si la carpeta no es un repositorio Git."""
    resultado = {}
    for ruta in rutas:
        try:
            r = subprocess.run(["git", "check-ignore", "-q", ruta], cwd=raiz, capture_output=True)
        except OSError:
            return None
        if r.returncode == 128:  # no es un repositorio
            return None
        resultado[ruta] = r.returncode == 0
    return resultado


# ---------- interacción ----------
class Entrada:
    """Interfaz de consola. Los tests la reemplazan por una que devuelve respuestas predefinidas."""

    def texto(self, pregunta: str, por_defecto: str = "") -> str:
        sufijo = f" [{por_defecto}]" if por_defecto else ""
        respuesta = input(f"{pregunta}{sufijo}: ").strip()
        return respuesta or por_defecto

    def secreto(self, pregunta: str) -> str:
        return getpass.getpass(f"{pregunta} (entrada oculta, Enter para dejar vacío): ").strip()

    def si_no(self, pregunta: str, por_defecto: bool = True) -> bool:
        marca = "S/n" if por_defecto else "s/N"
        r = input(f"{pregunta} [{marca}]: ").strip().lower()
        if not r:
            return por_defecto
        return r in ("s", "si", "sí", "y", "yes")

    def info(self, mensaje: str) -> None:
        print(mensaje)

    def error(self, mensaje: str) -> None:
        print(f"  ✖ {mensaje}", file=sys.stderr)


AYUDA_DB = """
DATABASE_URL — base de datos (Supabase):
  Panel de Supabase -> Project Settings -> Database -> Connection string.
  Use la conexión 'Session pooler' o la directa, puerto 5432. NO use el puerto 6543 (transaction).
  Pegue la cadena tal cual; reemplace [YOUR-PASSWORD] por la contraseña de la base.
  Si lo deja vacío en desarrollo, se usa SQLite local (no sirve para producción)."""


def _pedir_valido(entrada: Entrada, pregunta: str, validar, secreto: bool = False, por_defecto: str = ""):
    """Repite la pregunta hasta que el valor sea válido. Devuelve el valor (puede ser vacío si es opcional)."""
    while True:
        valor = entrada.secreto(pregunta) if secreto else entrada.texto(pregunta, por_defecto)
        if not valor:
            return ""
        error = validar(valor)
        if error is None:
            return valor
        entrada.error(error)


def _secreto_generado_o_pedido(entrada: Entrada, nombre: str, validar) -> str:
    if entrada.si_no(f"¿Generar {nombre} aleatorio (recomendado)?", True):
        return generar_secreto()
    return _pedir_valido(entrada, f"Ingrese {nombre}", validar, secreto=True)


def recoger_valores(entrada: Entrada, produccion_por_defecto: bool = False) -> dict[str, str]:
    """Hace todas las preguntas y devuelve el dict de variables. No escribe nada."""
    v: dict[str, str] = {}
    entrada.info("Asistente de configuración. Puede interrumpir con Ctrl+C; nada se escribe hasta confirmar.")

    v["ENTORNO"] = entrada.texto("ENTORNO (desarrollo | produccion)", "produccion" if produccion_por_defecto else "desarrollo")
    while v["ENTORNO"] not in ("desarrollo", "produccion"):
        entrada.error("Escriba 'desarrollo' o 'produccion'")
        v["ENTORNO"] = entrada.texto("ENTORNO (desarrollo | produccion)", "desarrollo")

    entrada.info(AYUDA_DB)
    while True:
        bruto = entrada.secreto("DATABASE_URL")
        if not bruto:
            if v["ENTORNO"] == "produccion":
                entrada.error("En producción la base es obligatoria (no se usa SQLite)")
                continue
            entrada.info("  Se usará SQLite local (sólo desarrollo).")
            break
        try:
            url, avisos = normalizar_database_url(bruto)
        except ValueError as e:
            entrada.error(str(e))
            continue
        if v["ENTORNO"] == "produccion" and url.startswith("sqlite"):
            entrada.error("En producción no se usa SQLite")
            continue
        for a in avisos:
            entrada.info(f"  ! {a}")
        entrada.info(f"  Se guardará como: {enmascarar_url(url)}")
        v["DATABASE_URL"] = url
        break

    entrada.info("\nJWT_SECRET firma las sesiones del panel. Mínimo 32 caracteres; no puede ser el de ejemplo.")
    v["JWT_SECRET"] = _secreto_generado_o_pedido(entrada, "JWT_SECRET", validar_jwt)

    entrada.info("\nWHATSAPP_WEBHOOK_TOKEN: secreto compartido con Evolution API (cabecera X-Webhook-Token).")
    if entrada.si_no("¿Configurar WhatsApp ahora?", True):
        v["WHATSAPP_WEBHOOK_TOKEN"] = _secreto_generado_o_pedido(entrada, "WHATSAPP_WEBHOOK_TOKEN",
                                                                 lambda x: validar_secreto("WHATSAPP_WEBHOOK_TOKEN", x))
    else:
        v["WHATSAPP_WEBHOOK_TOKEN"] = ""
        entrada.info("  WhatsApp: desactivado. El webhook rechazará todas las llamadas.")

    entrada.info("\nX-Device-Key de cada edificio: la clave real vive en la base (la crea scripts/seed.py).")
    entrada.info("Guárdela aquí sólo si ya la tiene. No genere una nueva: no coincidiría con la base.")
    while entrada.si_no("¿Guardar la X-Device-Key de un edificio?", False):
        edificio = entrada.texto("Id del edificio (p. ej. edificio_a)")
        if not re.fullmatch(r"[a-z0-9_]{3,40}", edificio):
            entrada.error("Use minúsculas, números o guion bajo (3 a 40)")
            continue
        clave = _pedir_valido(entrada, f"X-Device-Key de {edificio}",
                              lambda x: validar_secreto("X-Device-Key", x), secreto=True)
        if clave:
            v[f"DEVICE_KEY_{edificio.upper()}"] = clave

    entrada.info("\nEvolution API (WhatsApp). Déjelo vacío si aún no lo tiene.")
    url_evo = _pedir_valido(entrada, "EVOLUTION_URL (p. ej. https://evolution.ejemplo.cl)",
                            lambda x: validar_url_http("EVOLUTION_URL", x))
    if url_evo:
        v["EVOLUTION_URL"] = url_evo.rstrip("/")
        v["EVOLUTION_INSTANCE"] = entrada.texto("EVOLUTION_INSTANCE (nombre de la instancia)")
        v["EVOLUTION_APIKEY"] = _pedir_valido(entrada, "EVOLUTION_APIKEY",
                                              lambda x: validar_secreto("EVOLUTION_APIKEY", x), secreto=True)
    else:
        entrada.info("  WhatsApp sin proveedor: los recordatorios mostrarán 'no configurado'.")

    entrada.info("\nCorreo (SMTP o Amazon SES). Déjelo vacío si aún no lo tiene.")
    host = entrada.texto("SMTP_HOST (p. ej. email-smtp.us-east-1.amazonaws.com)")
    if host:
        v["SMTP_HOST"] = host
        v["SMTP_PORT"] = _pedir_valido(entrada, "SMTP_PORT", validar_puerto, por_defecto="587")
        v["SMTP_USER"] = entrada.texto("SMTP_USER")
        v["SMTP_PASSWORD"] = _pedir_valido(entrada, "SMTP_PASSWORD (credencial SMTP, no la de AWS)",
                                           lambda x: None, secreto=True)
        v["SMTP_FROM"] = _pedir_valido(entrada, "SMTP_FROM (remitente verificado)", validar_correo)
    else:
        entrada.info("  Correo desactivado: los avisos por correo quedarán 'no configurados'.")

    entrada.info("\nANTHROPIC_API_KEY (opcional): clasifica mensajes de WhatsApp con un modelo.")
    clave_ant = _pedir_valido(entrada, "ANTHROPIC_API_KEY", lambda x: validar_secreto("ANTHROPIC_API_KEY", x), secreto=True)
    if clave_ant:
        v["ANTHROPIC_API_KEY"] = clave_ant
    else:
        entrada.info("  Sin clave: los mensajes se clasifican por palabras clave.")

    por_defecto_cors = "https://panel.ejemplo.cl" if v["ENTORNO"] == "produccion" else "http://localhost:3000"
    v["CORS_ORIGINS"] = entrada.texto("CORS_ORIGINS (dirección del panel, separadas por coma)", por_defecto_cors)
    return v


def resumen(valores: dict[str, str]) -> list[str]:
    """Líneas para mostrar al final: secretos enmascarados y qué quedó desactivado."""
    secretos = {"JWT_SECRET", "WHATSAPP_WEBHOOK_TOKEN", "EVOLUTION_APIKEY", "SMTP_PASSWORD", "ANTHROPIC_API_KEY"}
    lineas = []
    for clave in PLANTILLA + sorted(k for k in valores if k.startswith("DEVICE_KEY_")):
        if clave not in valores:
            continue
        valor = valores[clave]
        if clave == "DATABASE_URL":
            lineas.append(f"  {clave} = {enmascarar_url(valor)}")
        elif clave in secretos or clave.startswith("DEVICE_KEY_"):
            lineas.append(f"  {clave} = {mascara(valor)}")
        else:
            lineas.append(f"  {clave} = {valor}")
    desactivado = []
    if not valores.get("EVOLUTION_URL"):
        desactivado.append("WhatsApp (recordatorios y respuestas)")
    if not valores.get("WHATSAPP_WEBHOOK_TOKEN"):
        desactivado.append("webhook de WhatsApp")
    if not valores.get("SMTP_HOST"):
        desactivado.append("envío de correos")
    if not valores.get("ANTHROPIC_API_KEY"):
        desactivado.append("clasificación de mensajes con IA (usa palabras clave)")
    if not valores.get("DATABASE_URL"):
        desactivado.append("base de datos remota: se usará SQLite (sólo desarrollo)")
    lineas.append("")
    lineas.append("Desactivado: " + (", ".join(desactivado) if desactivado else "nada") + ".")
    return lineas


def ejecutar(entrada: Entrada, ruta_env: Path = RAIZ / ".env", raiz: Path = RAIZ,
             produccion_por_defecto: bool = False) -> int:
    if ruta_env.exists():
        if not entrada.si_no(f"Ya existe {ruta_env.name}. ¿Reemplazarlo? (se guardará una copia en {ruta_env.name}.bak)", False):
            entrada.info("No se modificó nada.")
            return 0
    valores = recoger_valores(entrada, produccion_por_defecto)
    entrada.info("\nResumen (secretos enmascarados):")
    for linea in resumen(valores):
        entrada.info(linea)
    if not entrada.si_no("\n¿Escribir el archivo con estos valores?", True):
        entrada.info("Cancelado: no se escribió nada.")
        return 1
    respaldo = escribir_env(ruta_env, construir_env(valores))
    entrada.info(f"Archivo escrito: {ruta_env}")
    if respaldo:
        entrada.info(f"Copia anterior: {respaldo}")
    agregadas = asegurar_ignorados(raiz)
    if agregadas:
        entrada.info(f"Agregado a .gitignore: {', '.join(agregadas)}")
    estado = verificar_ignorados(raiz, [ruta_env.name, ruta_env.name + ".bak", "config_local.py"])
    if estado is None:
        entrada.info("Aviso: no es un repositorio Git; no se pudo verificar la exclusión.")
    else:
        for ruta, ok in estado.items():
            entrada.info(f"  {'✔' if ok else '✖'} {ruta} {'ignorado por Git' if ok else 'NO ignorado'}")
    entrada.info("\nSiguiente paso: python scripts/verificar_conexiones.py")
    return 0


def main() -> int:
    try:
        return ejecutar(Entrada(), produccion_por_defecto=False)
    except (KeyboardInterrupt, EOFError):
        print("\nInterrumpido: no se escribió nada.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
