# Firmware del lector del portón (ESP32, MicroPython)

> **Estado: SIN PROBAR EN EQUIPO REAL.** La lógica de decodificación y el cruce con el backend están
> probados con tests (`backend/tests/test_firmware.py`) y con el simulador de PC. Nada de lo que
> toca hardware (pines, relé, Ethernet, interrupciones del lector) se ha ejecutado todavía.

## Qué hace

1. Lee una credencial del lector configurado (`LECTOR` en `config.py`).
2. Descarta repeticiones locales (`ANTIRREBOTE_MS`).
3. Envía `POST /api/v1/{edificio}/validar-acceso` con `X-Device-Key`, `punto` y, si corresponde,
   `tipo: "sticker"`. Para llaveros RC522 no envía `tipo`.
4. Activa el relé **sólo con HTTP 200**. Cualquier otra respuesta, sin red o sin respuesta: no abre.
5. Reintenta **sólo** ante errores de red (`REINTENTOS`); nunca reintenta una respuesta 403.
6. Si no hay enlace Ethernet, reinicia la interfaz y no abre hasta reconectar.
7. Watchdog de hardware (`WATCHDOG_MS`): reinicia el equipo si el bucle principal se bloquea.

En la consola se muestran los eventos. La credencial se escribe enmascarada (`****A1B2`).

## Archivos

| Archivo | Para qué |
|---|---|
| `config.py` | Parámetros no secretos: edificio, punto, modelo de lector, pines, tiempos. |
| `config_local.py` | **Crear en el equipo** a partir de `config_local.example.py`. Contiene `DEVICE_KEY`. No se versiona. |
| `lectores.py` | Clase base `Lector` y las implementaciones: Wiegand, RS485/UART, RC522 y simulado. Fábrica `crear_lector()`. |
| `wiegand_codec.py` | Decodificación Wiegand 26/34 con paridad. Módulo puro: corre en el ESP32 y en la PC. |
| `main.py` | Bucle principal: lectura, envío, relé, red, watchdog. |

Herramienta de PC: `firmware/tools/simular_lector.py` (envía lecturas al backend, incluidas tramas Wiegand).

## Elegir el lector

En `config.py`:

```python
LECTOR = "wiegand"   # wiegand | rs485 | rc522 | simulado
```

Cambiar de modelo de lector sólo implica escribir una clase nueva en `lectores.py` y ajustar
`config.py`; `main.py` no cambia.

## Cableado

### Lector Wiegand (UHF con salida Wiegand)

| Señal | Pin ESP32 | Notas |
|---|---|---|
| D0 (bit 0) | GPIO 32 | Entrada con pull-up interno; pulso a nivel bajo por cada 0. |
| D1 (bit 1) | GPIO 33 | Entrada con pull-up interno; pulso a nivel bajo por cada 1. |
| GND | GND | **Común obligatorio** con el lector. |
| Alimentación del lector | fuente del lector | Según su hoja de datos (a menudo 12 V o 5 V). No alimentar desde el ESP32. |

> **ADVERTENCIA DE NIVELES LÓGICOS.** La mayoría de los lectores Wiegand entregan sus líneas a
> **5 V** (a veces en colector abierto con resistencias a 5 V). El ESP32 opera a **3,3 V** y **no
> tolera 5 V** en sus GPIO sin dañarse. **No conectar D0/D1 directo.** Usar un adaptador de nivel en
> cada línea: un divisor resistivo (por ejemplo 10 kΩ / 20 kΩ, que deja unos 3,3 V con 5 V de
> entrada) o un conversor de nivel bidireccional. Con el divisor, verificar con un multímetro que
> el nivel bajo es menor a 0,8 V y el alto cerca de 3,3 V antes de conectar el ESP32.

### Relé y LED

| Señal | Pin | Notas |
|---|---|---|
| Relé (activo en alto) | GPIO 25 | Usar un módulo con optoacoplador y driver; no excitar la bobina directo desde el pin. |
| LED de estado | GPIO 2 | Opcional. |

### Ethernet (W5500) y RC522 (sólo si `LECTOR="rc522"`)

Pines de `main.py` (W5500: SCK 14, MOSI 13, MISO 12, CS 15, RST 4) y de `config.py` (RC522: SCK 18,
MOSI 23, MISO 19, RST 22, CS 21). Revisar que no choquen con el lector elegido.

### RS485 / UART (`LECTOR="rs485"`)

Pines `RS485_TX` / `RS485_RX` en UART 2 y `RS485_DE` para el sentido del transceptor. La trama se
termina en `RS485_FIN` y el código se extrae con `RS485_PATRON`. **No probado**: confirmar baudios,
terminador y formato con la hoja de datos del lector.

## Configuración del equipo

1. Copiar `config_local.example.py` a `config_local.py` y pegar la `X-Device-Key` del edificio
   (la entrega `scripts/seed.py` o la rotación desde el panel). **No subir este archivo a Git.**
2. Ajustar en `config.py`: `EDIFICIO_ID`, `API_BASE`, `IP`, `PUNTO`, `DIRECCION` (sólo si el
   edificio usa anti-passback) y `WIEGAND_BITS` (26 o 34 según el lector).
3. Copiar `main.py`, `config.py`, `config_local.py`, `lectores.py` y `wiegand_codec.py` al ESP32
   (por ejemplo con `mpremote` o Thonny). Requiere `mfrc522.py` sólo si se usa RC522.

## Modo simulado

Sin hardware: en `config.py` poner `SIMULAR = True`. El equipo no toca pines, no abre relé y no usa
la red: lee `SIMULAR_CODIGOS` y muestra lo que enviaría. Para probar el backend real desde la PC:

```bash
export DEVICE_KEY=...    # en PowerShell: $env:DEVICE_KEY="..."
python firmware/tools/simular_lector.py --url http://localhost:8000 --edificio edificio_a sticker E280117000000000000000A1
python firmware/tools/simular_lector.py --url http://localhost:8000 --edificio edificio_a wiegand --bits 26 --fac 42 --card 12345
python firmware/tools/simular_lector.py --url http://localhost:8000 --edificio edificio_a sticker E280117000000000000000A1 --repetir 3 --intervalo 0.5
```

El simulador de PC usa el mismo `wiegand_codec.py` y el mismo cuerpo de petición que el firmware.

## Pruebas de banco (pendientes, en el equipo real)

Marcar cada una con fecha y resultado antes de instalar en el portón.

- [ ] **Lectura de sticker**: a 1 m, cada sticker se lee una vez y el relé se activa.
- [ ] **Lectura Wiegand con niveles**: con el divisor, un multímetro confirma 0 V/3,3 V en D0 y D1.
- [ ] **Paridad**: una tarjeta leída con el bit de paridad alterado (o cable cruzado) no abre y aparece en consola.
- [ ] **Trama incompleta**: desconectar un hilo a mitad de la lectura no abre ni deja el equipo bloqueado.
- [ ] **Antirrebote**: mantener el sticker en el lector: un solo envío por ventana de `ANTIRREBOTE_MS`.
- [ ] **Relé**: se activa `RELAY_MS` y vuelve a cero; el portón no queda abierto si el relé se queda pegado (revisar el cableado del contacto).
- [ ] **Corte de red**: desenchufar el cable Ethernet: no abre, la consola lo indica, y al reconectar vuelve a leer.
- [ ] **Servidor caído**: apagar el backend: no abre y no reintenta más de `REINTENTOS` veces.
- [ ] **Respuesta 403**: un sticker perdido no abre y no se reintenta.
- [ ] **Reinicio de corriente**: tras un corte de luz el equipo arranca solo y vuelve a conectarse.
- [ ] **Watchdog**: forzar un bloqueo de prueba y verificar que el equipo se reinicia.
- [ ] **Alcance real**: anotar desde qué distancia deja de leer cada sticker (herramienta de alcance del panel, Fase 4).
- [ ] **Metal y agua**: sticker en parabrisas metalizado, con lluvia, y de noche.

## Limitaciones conocidas

- El envío HTTP usa `urequests`. Su timeout depende de la versión de MicroPython; verificar en el
  equipo que `TIMEOUT_HTTP_S` realmente se aplica. Sin timeout, una conexión colgada puede demorar
  más de lo deseado (el watchdog lo cubre como último recurso).
- Sin HTTPS: el tráfico entre el equipo y el servidor viaja en claro en la red local. Pendiente.
- La clave `DEVICE_KEY` queda en el equipo; quien tenga acceso físico puede leerla. Rotarla si el equipo sale del portón.
