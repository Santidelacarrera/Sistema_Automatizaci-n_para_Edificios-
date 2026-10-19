# Configuración del lector del portón. SIN SECRETOS: la clave de dispositivo va en config_local.py
# (copiado de config_local.example.py, no se versiona). Ver README.md de esta carpeta.

EDIFICIO_ID = "edificio_a"
API_BASE = "http://192.168.10.10:8000"  # servidor central (HTTPS en producción: pendiente)
PUNTO = "vehicular"                     # "vehicular" (portón) | "peatonal" (puerta de llaveros)
DIRECCION = None                        # "entrada" | "salida" | None. Sólo con anti-passback activo en el edificio
IP = ("192.168.10.50", "255.255.255.0", "192.168.10.1", "8.8.8.8")  # IP fija del equipo (Ethernet W5500)

# ---- modelo de lector: "wiegand" | "rs485" | "rc522" | "simulado" ----
LECTOR = "wiegand"

# Wiegand (UHF con salida Wiegand). Entradas con pull-up; ADAPTADOR DE NIVEL OBLIGATORIO si el lector es de 5 V.
WIEGAND_D0 = 32
WIEGAND_D1 = 33
WIEGAND_BITS = 26            # 26 o 34: confirmar con la hoja de datos del lector
WIEGAND_TRAMA_MS = 25        # si no llegan más bits en este tiempo, la trama está incompleta

# RS485 / UART (trama configurable). NO PROBADO: ajustar con la hoja de datos del lector.
RS485_UART = 2
RS485_TX = 17
RS485_RX = 16
RS485_DE = 27                # control de dirección del transceptor (None si es UART directa)
RS485_BAUD = 9600
RS485_FIN = b"\r"            # terminador de trama
RS485_PATRON = r"([0-9A-Fa-f]{8,24})"

# RC522 (llaveros MIFARE 13,56 MHz). Sólo para la puerta peatonal; NO lee stickers UHF.
RC522_SCK = 18
RC522_MOSI = 23
RC522_MISO = 19
RC522_RST = 22
RC522_CS = 21

# ---- comportamiento ----
RELAY_MS = 1000             # tiempo que el relé mantiene abierto el portón
ANTIRREBOTE_MS = 1500       # misma credencial dentro de este tiempo: no se vuelve a enviar
REINTENTOS = 2              # reintentos sólo ante error de red (nunca ante una respuesta 403)
REINTENTO_MS = 300
TIMEOUT_HTTP_S = 3          # el servidor debe responder en pocos segundos; si no, no se abre
WATCHDOG_MS = 20000         # el equipo se reinicia si el bucle principal se bloquea más de este tiempo

# ---- modo simulado (sin hardware, sin relé, sin red real) ----
SIMULAR = False
SIMULAR_CODIGOS = [("E280117000000000000000A1", "sticker")]   # lecturas que entrega el lector simulado
SIMULAR_ACEPTADOS = ["E280117000000000000000A1"]               # respuestas 200 simuladas

# Clave de dispositivo: se importa de config_local.py (no versionado).
try:
    from config_local import DEVICE_KEY  # noqa: F401
except ImportError:
    DEVICE_KEY = None
