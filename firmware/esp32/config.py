# Copiar a config.py en el dispositivo y ajustar por edificio/punto de acceso.
API_BASE = "http://192.168.10.10:8000"   # IP/host del servidor central (usar HTTPS en producción)
EDIFICIO_ID = "edificio_a"
DEVICE_KEY = "keyA"                      # X-Device-Key del edificio
PUNTO = "vehicular"                      # "vehicular" | "peatonal"
IP = ("192.168.10.50", "255.255.255.0", "192.168.10.1", "8.8.8.8")  # IP fija del lector
RELAY_MS = 1000
