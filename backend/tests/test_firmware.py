"""Firmware del lector: codificador Wiegand (compartido con el ESP32) y cruce de punta a punta con el backend.

Esto NO prueba el hardware: prueba la lógica de decodificación y que una trama Wiegand se convierte en el
mismo código que el backend acepta. La prueba en equipo real está en firmware/esp32/README.md.
"""
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "firmware" / "esp32"))
sys.path.insert(0, str(RAIZ / "firmware" / "tools"))

import wiegand_codec as wg  # noqa: E402
import simular_lector  # noqa: E402

from app.models import TipoTag  # noqa: E402
from app.services import access  # noqa: E402
from conftest import login  # noqa: E402


@pytest.mark.parametrize("largo,fac,card", [(26, 42, 12345), (26, 0, 0), (26, 255, 65535),
                                            (34, 65535, 65535), (34, 1, 2)])
def test_codificar_decodificar_ida_y_vuelta(largo, fac, card):
    bits = wg.codificar(fac, card, largo)
    assert len(bits) == largo
    assert wg.decodificar(bits, largo) == (fac, card)


@pytest.mark.parametrize("posicion", [0, 5, 12, 13, 20, 25])
def test_un_bit_alterado_se_detecta_con_26(posicion):
    bits = wg.codificar(42, 12345, 26)
    bits[posicion] ^= 1
    with pytest.raises(wg.TramaWiegand):
        wg.decodificar(bits, 26)


def test_largo_y_rango_invalidos():
    with pytest.raises(wg.TramaWiegand):
        wg.decodificar([0] * 25, 26)
    with pytest.raises(wg.TramaWiegand):
        wg.codificar(256, 1, 26)  # facility de 8 bits
    with pytest.raises(wg.TramaWiegand):
        wg.codificar(1, 1, 30)    # formato no soportado


def test_token_coincide_con_el_formato_canonico_del_backend():
    from app.services.credenciales import normalizar_wiegand
    token = wg.token(42, 12345, 26)
    assert token == "W26:42:12345"
    assert normalizar_wiegand(token) == token


def test_lectura_wiegand_abre_el_porton_con_el_backend_real(client, seed, db):
    """Trama -> token -> validar-acceso con X-Device-Key -> 200, igual que el firmware."""
    from app.models import Edificio
    ed = db.get(Edificio, "edificio_a")
    access.asignar_tag(db, ed, seed["edificio_a", "101"].id, "W26:42:12345", TipoTag.vehicular, formato="wiegand")
    db.commit()
    bits = wg.codificar(42, 12345, 26)
    fac, card = wg.decodificar(bits, 26)
    codigo, cuerpo = simular_lector.enviar_lectura(client, "edificio_a", "keyA", wg.token(fac, card, 26), "sticker")
    assert codigo == 200 and cuerpo["abrir"] is True
    otra = wg.codificar(42, 12346, 26)  # tarjeta que no existe
    codigo, _ = simular_lector.enviar_lectura(client, "edificio_a", "keyA", wg.token(*wg.decodificar(otra, 26), 26), "sticker")
    assert codigo == 403


def test_simulador_token_invalido_no_abre(client, seed):
    """Un código con formato inválido se rechaza sin error de servidor."""
    codigo, cuerpo = simular_lector.enviar_lectura(client, "edificio_a", "keyA", "E28011", "sticker")
    assert codigo == 403 and cuerpo.get("detail")  # token desconocido, sin excepción
