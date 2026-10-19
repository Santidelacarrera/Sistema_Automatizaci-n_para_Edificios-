"""Codificación y decodificación Wiegand 26/34 con verificación de paridad.

Módulo puro (sin ``machine``): corre igual en el ESP32 (MicroPython) y en la PC (CPython, para pruebas).

Formato Wiegand 26 (estándar):   P | facility (8 bits) | card (16 bits) | P
  - primer bit: paridad PAR de los bits 1..12
  - último bit: paridad IMPAR de los bits 13..24

Formato Wiegand 34 (estándar):   P | facility (16 bits) | card (16 bits) | P
  - primer bit: paridad PAR de los bits 1..16
  - último bit: paridad IMPAR de los bits 17..32

Los bits llegan como lista de 0/1 en el orden en que los emite el lector (el primero es el de paridad).
"""

LARGO_FAC = {26: 8, 34: 16}
LARGO_CARD = {26: 16, 34: 16}


class TramaWiegand(ValueError):
    """Trama con largo incorrecto o paridad inválida. Se descarta y se registra en la consola."""


def _paridad_par(bits):
    return sum(bits) % 2


def decodificar(bits, largo):
    """Devuelve (facility, card) o lanza TramaWiegand."""
    if largo not in LARGO_FAC:
        raise TramaWiegand("largo no soportado: %s" % largo)
    if len(bits) != largo:
        raise TramaWiegand("trama de %d bits, se esperaban %d" % (len(bits), largo))
    mitad = largo // 2  # 13 para 26, 17 para 34: el primer bloque de paridad son bits[1:mitad]
    par_inicial, par_final = bits[0], bits[-1]
    if par_inicial != _paridad_par(bits[1:mitad]):
        raise TramaWiegand("paridad inicial inválida")
    if par_final != 1 - _paridad_par(bits[mitad:-1]):
        raise TramaWiegand("paridad final inválida")
    datos = bits[1:-1]
    fac_bits, card_bits = datos[:LARGO_FAC[largo]], datos[LARGO_FAC[largo]:]
    return _a_entero(fac_bits), _a_entero(card_bits)


def codificar(facility, card, largo):
    """Bits de una trama válida (para pruebas y simulador)."""
    if largo not in LARGO_FAC:
        raise TramaWiegand("largo no soportado: %s" % largo)
    nf, nc = LARGO_FAC[largo], LARGO_CARD[largo]
    if not (0 <= facility < (1 << nf)) or not (0 <= card < (1 << nc)):
        raise TramaWiegand("facility o card fuera de rango para Wiegand %d" % largo)
    datos = _a_bits(facility, nf) + _a_bits(card, nc)   # sin paridades: 24 bits (26) o 32 bits (34)
    mitad = largo // 2 - 1                                # 12 o 16 bits por bloque de paridad
    par_inicial = _paridad_par(datos[:mitad])
    par_final = 1 - _paridad_par(datos[mitad:])
    return [par_inicial] + datos + [par_final]


def token(facility, card, largo):
    """Código canónico que espera el backend: 'W26:<facility>:<card>' (ver services/credenciales.py)."""
    return "W%d:%d:%d" % (largo, facility, card)


def _a_entero(bits):
    valor = 0
    for b in bits:
        valor = (valor << 1) | b
    return valor


def _a_bits(valor, n):
    return [(valor >> (n - 1 - i)) & 1 for i in range(n)]
