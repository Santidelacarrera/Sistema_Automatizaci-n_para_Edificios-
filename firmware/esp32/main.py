"""Lector de acceso del portón: ESP32 + W5500 (Ethernet) + lector configurable + relé. MicroPython.

Flujo: leer credencial -> antirrebote local -> POST /api/v1/{edificio}/validar-acceso (X-Device-Key)
       -> relé SÓLO con HTTP 200. Sin red o sin respuesta: no abre. Errores de red: reintento corto.
Watchdog de hardware: reinicia el equipo si el bucle principal se queda bloqueado.

ESTADO: sin probar en equipo real. Probado con simulador (modo SIMULAR y firmware/tools/simular_lector.py).
Ver firmware/esp32/README.md para cableado, advertencias de niveles lógicos y lista de pruebas de banco.
"""
import time

import machine
import network
import ujson
import urequests
from machine import Pin

import config
from lectores import LectorSimulado, crear_lector

relay = None if config.SIMULAR else Pin(25, Pin.OUT, value=0)
led = None if config.SIMULAR else Pin(2, Pin.OUT, value=0)


def log(msg):
    print("[%7ds] %s" % (time.ticks_ms() // 1000, msg))


def _enmascarar(token):
    """Nunca se escribe la credencial completa en la consola: sólo los últimos 4 caracteres."""
    return "****" + token[-4:] if len(token) > 4 else "****"


def conectar_ethernet():
    from machine import SPI
    spi = SPI(1, 10_000_000, sck=Pin(14), mosi=Pin(13), miso=Pin(12))
    nic = network.WIZNET5K(spi, Pin(15), Pin(4))
    nic.active(True)
    nic.ifconfig(config.IP)
    return _esperar_enlace(nic, 50)


def _esperar_enlace(nic, intentos):
    for _ in range(intentos):
        if nic.isconnected():
            return nic
        time.sleep_ms(200)
    return nic


def reconectar(nic):
    """Reinicia la interfaz Ethernet. Mientras no haya enlace, el portón no abre."""
    log("reconectando Ethernet")
    nic.active(False)
    time.sleep_ms(500)
    nic.active(True)
    _esperar_enlace(nic, 25)
    log("Ethernet %s" % ("conectada" if nic.isconnected() else "sin enlace"))


def abrir():
    if config.SIMULAR:
        log("SIMULADO: relé activo %d ms" % config.RELAY_MS)
        return
    relay.value(1)
    time.sleep_ms(config.RELAY_MS)
    relay.value(0)


def enviar(token, tipo):
    """Devuelve el código HTTP de la respuesta, o None si no hubo respuesta (sin red o tiempo agotado)."""
    cuerpo = {"edificio_id": config.EDIFICIO_ID, "token_acceso": token, "punto": config.PUNTO}
    if tipo:
        cuerpo["tipo"] = tipo
    if config.DIRECCION:
        cuerpo["direccion"] = config.DIRECCION
    if config.SIMULAR:
        codigo = 200 if token in config.SIMULAR_ACEPTADOS else 403
        log("SIMULADO POST validar-acceso %s -> %d" % (_enmascarar(token), codigo))
        return codigo
    url = "%s/api/v1/%s/validar-acceso" % (config.API_BASE, config.EDIFICIO_ID)
    headers = {"Content-Type": "application/json", "X-Device-Key": config.DEVICE_KEY}
    for intento in range(1 + config.REINTENTOS):
        resp = None
        try:
            resp = urequests.post(url, data=ujson.dumps(cuerpo), headers=headers)
            return resp.status_code
        except Exception as e:  # error de red: se reintenta; una respuesta 403 nunca se reintenta
            log("red, intento %d: %s" % (intento + 1, e))
            time.sleep_ms(config.REINTENTO_MS)
        finally:
            if resp:
                resp.close()
    return None


def main():
    if config.DEVICE_KEY is None and not config.SIMULAR:
        raise RuntimeError("falta DEVICE_KEY: crear config_local.py a partir de config_local.example.py")
    nic = None if config.SIMULAR else conectar_ethernet()
    lector = LectorSimulado(config.SIMULAR_CODIGOS) if config.SIMULAR else crear_lector()
    wdt = None if config.SIMULAR else machine.WDT(timeout=config.WATCHDOG_MS)
    log("listo: lector=%s punto=%s direccion=%s simulado=%s" % (
        lector.nombre, config.PUNTO, config.DIRECCION, config.SIMULAR))
    ultimo, ultimo_ms = None, 0
    proximo_chequeo = 0
    while True:
        if wdt:
            wdt.feed()
        if nic is not None and time.ticks_ms() >= proximo_chequeo:
            proximo_chequeo = time.ticks_ms() + 5000
            if not nic.isconnected():
                reconectar(nic)
        lectura = lector.leer()
        if lectura is None:
            time.sleep_ms(50)
            continue
        token, tipo = lectura
        ahora = time.ticks_ms()
        if token == ultimo and time.ticks_diff(ahora, ultimo_ms) < config.ANTIRREBOTE_MS:
            log("lectura repetida %s: ignorada (antirrebote)" % _enmascarar(token))
            continue
        ultimo, ultimo_ms = token, ahora
        if nic is not None and not nic.isconnected():
            log("sin red: no se abre")
            continue
        codigo = enviar(token, tipo)
        if codigo == 200:
            log("ABRE %s" % _enmascarar(token))
            abrir()
        elif codigo is None:
            log("sin respuesta del servidor: no se abre %s" % _enmascarar(token))
        else:
            log("no abre %s: HTTP %d" % (_enmascarar(token), codigo))


try:
    main()
except Exception as e:  # fallo irrecuperable: reiniciar tras una pausa
    log("fatal: %s" % e)
    time.sleep(5)
    machine.reset()
