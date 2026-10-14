"""Lector de acceso RFID (ESP32 + W5500 Ethernet + RC522 + relé) en MicroPython.

Cableado SPI (bus 2 = lector RC522, bus 1 = W5500):
  RC522: SCK=18 MOSI=23 MISO=19 SDA(CS)=21 RST=22      Relé: GPIO25 (activo en alto)
  W5500: SCK=14 MOSI=13 MISO=12 CS=15 RST=4
Requiere mfrc522.py (wendlers/micropython-mfrc522) copiado al dispositivo.
Hardware NO probado en este repositorio: validar en banco antes de instalar.
"""
import time

import mfrc522
import network
import ujson
import urequests
from machine import Pin, SPI

import config

relay = Pin(25, Pin.OUT, value=0)
led = Pin(2, Pin.OUT, value=0)


def conectar_ethernet():
    spi = SPI(1, 10_000_000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
    nic = network.WIZNET5K(spi, Pin(15), Pin(4))
    nic.active(True)
    nic.ifconfig(config.IP)
    for _ in range(50):
        if nic.isconnected():
            return nic
        time.sleep_ms(200)
    raise RuntimeError("Sin enlace Ethernet")


def abrir():
    relay.value(1)
    time.sleep_ms(config.RELAY_MS)
    relay.value(0)


def validar_y_abrir(token):
    url = "%s/api/v1/%s/validar-acceso" % (config.API_BASE, config.EDIFICIO_ID)
    headers = {"Content-Type": "application/json", "X-Device-Key": config.DEVICE_KEY}
    body = ujson.dumps({"edificio_id": config.EDIFICIO_ID, "token_acceso": token, "punto": config.PUNTO})
    resp = None
    try:
        resp = urequests.post(url, data=body, headers=headers)
        if resp.status_code == 200:
            abrir()  # sólo abre con 200 explícito: ante error de red/servidor permanece cerrado (fail-closed)
            return True
        print("Acceso denegado:", resp.status_code)
    except Exception as e:
        print("Error de conexión:", e)
    finally:
        if resp:
            resp.close()
    return False


def main():
    conectar_ethernet()
    rdr = mfrc522.MFRC522(sck=18, mosi=23, miso=19, rst=22, cs=21)
    ultimo, t_ultimo = None, 0
    while True:
        stat, _ = rdr.request(rdr.REQIDL)
        if stat == rdr.OK:
            stat, raw_uid = rdr.anticoll()
            if stat == rdr.OK:
                uid = "".join("{:02X}".format(x) for x in raw_uid)  # mayúsculas, como en el backend
                ahora = time.ticks_ms()
                if uid != ultimo or time.ticks_diff(ahora, t_ultimo) > 3000:  # antirrebote
                    validar_y_abrir(uid)
                    ultimo, t_ultimo = uid, ahora
        time.sleep_ms(200)


try:
    main()
except Exception as e:  # watchdog simple: reiniciar ante fallo irrecuperable
    print("Fatal:", e)
    import machine
    time.sleep(5)
    machine.reset()
