"""Lectores intercambiables: la clase base define el contrato; cada modelo de lector es una implementación.

Contrato:  leer() -> (token, tipo) cuando hay una credencial completa, o None si no hay nada que enviar.
  tipo: "sticker" (UHF/Wiegand), None (llavero RC522, el backend lo identifica por punto).

El modelo se elige en config.py (LECTOR = "wiegand" | "rs485" | "rc522" | "simulado").
Hardware: las implementaciones con machine/mfrc522/UART NO están probadas en equipo real.
"""
import config
import wiegand_codec

try:
    import micropython
    micropython.alloc_emergency_exception_buf(100)  # las interrupciones pueden fallar sin buffer de emergencia
except ImportError:  # CPython (pruebas)
    micropython = None


def _ms():
    try:
        import time
        return time.ticks_ms()
    except AttributeError:
        import time
        return int(time.time() * 1000)


def _log(msg):
    print("[lector] %s" % msg)


def _seccion_critica():
    try:
        import machine
        return machine.disable_irq()
    except (ImportError, AttributeError):  # CPython: no hay interrupciones que proteger
        return None


def _fin_seccion_critica(estado):
    if estado is not None:
        import machine
        machine.enable_irq(estado)


class Lector:
    nombre = "base"

    def leer(self):
        raise NotImplementedError


class LectorWiegand(Lector):
    """Wiegand 26 o 34 por interrupciones en D0 (bit 0, línea baja) y D1 (bit 1, línea baja).

    ADVERTENCIA: la mayoría de lectores Wiegand salen a 5 V. El ESP32 no tolera 5 V en GPIO:
    usar adaptador de nivel (divisor resistivo o conversor bidireccional) en cada línea.
    """
    nombre = "wiegand"

    def __init__(self, pin_d0, pin_d1, largo=26, trama_ms=25):
        from machine import Pin
        self.largo = largo
        self.trama_ms = trama_ms
        self._bits = []
        self._ultimo_ms = 0
        self._ultimo_flanco = 0
        self._d0 = Pin(pin_d0, Pin.IN, Pin.PULL_UP)
        self._d1 = Pin(pin_d1, Pin.IN, Pin.PULL_UP)
        self._d0.irq(trigger=Pin.IRQ_FALLING, handler=self._flanco_0)
        self._d1.irq(trigger=Pin.IRQ_FALLING, handler=self._flanco_1)

    def _agregar(self, bit):
        ahora = _ms()
        if ahora == self._ultimo_flanco:  # antirrebote de línea: flancos simultáneos se descartan
            return
        self._ultimo_flanco = ahora
        if len(self._bits) < 64:
            self._bits.append(bit)
        self._ultimo_ms = ahora

    def _flanco_0(self, _pin):
        self._agregar(0)

    def _flanco_1(self, _pin):
        self._agregar(1)

    def leer(self):
        estado = _seccion_critica()  # la interrupción escribe _bits: no leer a medias
        try:
            if not self._bits:
                return None
            if len(self._bits) < self.largo:
                if _ms() - self._ultimo_ms > self.trama_ms:  # trama incompleta: se descarta
                    _log("trama incompleta (%d de %d bits)" % (len(self._bits), self.largo))
                    self._bits = []
                return None
            bits, self._bits = self._bits[:self.largo], self._bits[self.largo:]
        finally:
            _fin_seccion_critica(estado)
        try:
            fac, card = wiegand_codec.decodificar(bits, self.largo)
        except wiegand_codec.TramaWiegand as e:
            _log("descartada: %s" % e)
            return None
        return wiegand_codec.token(fac, card, self.largo), "sticker"


class LectorRS485(Lector):
    """Lector con salida serie (RS485 vía transceptor, o UART directa). Trama configurable.

    La trama termina en ``fin`` (bytes). El código se extrae con la expresión regular ``patron``
    (la primera captura del grupo 1, o la coincidencia completa si no hay grupo).
    NO PROBADO: ajustar fin y patrón con la hoja de datos del lector real.
    """
    nombre = "rs485"

    def __init__(self, uart_id, tx, rx, baud, fin, patron, de_pin=None):
        import re
        from machine import UART, Pin
        self._re = re.compile(patron)
        self._fin = fin
        self._buf = b""
        self._de = Pin(de_pin, Pin.OUT, value=0) if de_pin is not None else None  # driver: 0 = recibir
        self._uart = UART(uart_id, baudrate=baud, tx=tx, rx=rx, timeout=0)

    def leer(self):
        n = self._uart.any()
        if n:
            self._buf += self._uart.read(n)
        if self._fin not in self._buf:
            if len(self._buf) > 256:  # basura sin terminador: se descarta
                _log("trama RS485 sin terminador: descartada")
                self._buf = b""
            return None
        trama, _, self._buf = self._buf.partition(self._fin)
        texto = trama.decode("ascii", "ignore")
        m = self._re.search(texto)
        if not m:
            _log("trama RS485 sin código: %r" % texto)
            return None
        codigo = (m.group(1) if m.groups() else m.group(0)).upper()
        return codigo, "sticker"


class LectorRC522(Lector):
    """Llaveros MIFARE 13,56 MHz para la puerta peatonal. NO sirve para stickers UHF."""
    nombre = "rc522"

    def __init__(self, sck, mosi, miso, rst, cs):
        import mfrc522
        self._rdr = mfrc522.MFRC522(sck=sck, mosi=mosi, miso=miso, rst=rst, cs=cs)
        self._ultimo, self._ultimo_ms = None, 0

    def leer(self):
        stat, _ = self._rdr.request(self._rdr.REQIDL)
        if stat != self._rdr.OK:
            return None
        stat, raw = self._rdr.anticoll()
        if stat != self._rdr.OK:
            return None
        uid = "".join("{:02X}".format(x) for x in raw)
        ahora = _ms()
        if uid == self._ultimo and ahora - self._ultimo_ms < 3000:  # antirrebote de llavero
            return None
        self._ultimo, self._ultimo_ms = uid, ahora
        return uid, None


class LectorSimulado(Lector):
    """Sin hardware: entrega los códigos de config.SIMULAR_CODIGOS una vez cada uno, con pausa."""
    nombre = "simulado"

    def __init__(self, codigos, pausa_ms=2000):
        self._cola = list(codigos)
        self._pausa_ms = pausa_ms
        self._proximo = 0

    def leer(self):
        if not self._cola or _ms() < self._proximo:
            return None
        self._proximo = _ms() + self._pausa_ms
        return self._cola.pop(0)


def crear_lector():
    """Construye el lector elegido en config.py. Los pines vienen de config, no están fijados aquí."""
    modelo = config.LECTOR
    if modelo == "wiegand":
        return LectorWiegand(config.WIEGAND_D0, config.WIEGAND_D1, config.WIEGAND_BITS, config.WIEGAND_TRAMA_MS)
    if modelo == "rs485":
        return LectorRS485(config.RS485_UART, config.RS485_TX, config.RS485_RX, config.RS485_BAUD,
                           config.RS485_FIN, config.RS485_PATRON, config.RS485_DE)
    if modelo == "rc522":
        return LectorRC522(config.RC522_SCK, config.RC522_MOSI, config.RC522_MISO, config.RC522_RST, config.RC522_CS)
    if modelo == "simulado":
        return LectorSimulado(config.SIMULAR_CODIGOS)
    raise RuntimeError("LECTOR desconocido en config.py: %s" % modelo)
