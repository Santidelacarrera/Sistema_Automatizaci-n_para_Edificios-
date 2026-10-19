# Lector de patentes (LPR)

Puente entre una cámara con reconocimiento de patentes y el backend. La cámara (o un programa en
el mismo equipo) envía cada lectura al traductor; el traductor decide si la lectura merece
consultar al backend y llama a `POST /api/v1/{edificio}/validar-acceso` con `X-Device-Key` y
`punto="vehicular"`.

```
cámara ──POST /lpr/evento──▶ traductor (puerto 8090) ──POST /api/v1/{edificio}/validar-acceso──▶ backend
                              · descarta confianza baja     · X-Device-Key del edificio
                              · deduplica patentes          · 200 = abrir, 403 = no
```

## Qué hace y qué no hace

- Rechaza lecturas con confianza bajo `LPR_CONFIANZA_MINIMA` **sin llamar al backend**.
- Ignora una misma patente dentro de `LPR_DEDUP_SEGUNDOS` (la cámara suele repetir la lectura).
- Sólo se considera abierto con un `200` explícito del backend. Red caída, `5xx` o respuesta
  inesperada: portón cerrado (estado `error_backend`).
- No guarda la patente en disco. La respuesta del traductor no repite la patente.
- No decide accesos por sí mismo: la regla vive en el backend (`services/access.py`).
- Envía `tipo: "patente"` y la `confianza`. Con el modo `sticker_y_patente` el backend empareja la
  patente con la lectura del sticker dentro de la ventana de coincidencia (ver
  `docs/PORTON_UHF.md`).
- Formatos de patente chilena de 6 caracteres: antiguo `AA1234` y nuevo `BCDF12`
  (`formato_patente`). Motos y otros formatos de 5 a 7 caracteres se aceptan como `otro`.

## Configuración (variables de entorno)

| Variable | Obligatoria | Ejemplo | Notas |
|---|---|---|---|
| `LPR_BACKEND_URL` | sí | `http://api:8000` | Sin barra final. |
| `LPR_EDIFICIO_ID` | sí | `edificio_a` | Tenant del lector. |
| `LPR_DEVICE_KEY` | sí | (secreto) | `X-Device-Key` del edificio; la entrega `scripts/seed.py`. **Sólo en `.env`.** |
| `LPR_TOKEN_CAMARA` | sí | (secreto) | Token que la cámara o su puente envían en `X-LPR-Token`. **Sólo en `.env`.** |
| `LPR_CONFIANZA_MINIMA` | no | `0.85` | Decimal entre 0 y 1. |
| `LPR_DEDUP_SEGUNDOS` | no | `30` | |
| `LPR_ADAPTADOR` | no | `generico` | `generico`, `hikvision` (pendiente), `dahua` (pendiente). |

Arranque (desde `backend/`):

```bash
uvicorn integraciones.lpr.servidor:app --host 0.0.0.0 --port 8090
```

## Formato genérico

`POST /lpr/evento` con cabecera `X-LPR-Token` y cuerpo JSON:

```json
{"patente": "BB-CD-12", "confianza": 0.97, "camara": "entrada-1", "fecha": "2026-10-19T12:00:00Z"}
```

- `patente`: se normaliza (mayúsculas, sin guiones ni espacios). Entre 5 y 7 caracteres.
- `confianza`: decimal entre 0 y 1. **Un valor como `93` se rechaza (422)**: el puente debe
  convertir porcentajes antes de llamar.
- `fecha` y `camara` son opcionales.

Respuestas: `202` con `estado` (`enviada`, `error_backend`, `rechazada_confianza`, `duplicada`),
`abrir` (bool) y `motivo`. `401` si falta o no coincide `X-LPR-Token`. `422` si el formato es
inválido. `501` si el adaptador de la marca aún no está confirmado.

## Marcas de cámara

- **Genérico**: probado con pruebas automáticas (`backend/tests/test_lpr.py`).
- **Hikvision y Dahua**: sólo esqueleto (`adaptadores/hikvision.py`, `adaptadores/dahua.py`).
  Fallan con `501` a propósito. Para implementarlos hay que confirmar el evento exacto del modelo
  instalado (campos de matrícula y de confianza, y su escala).

## Probar sin cámara

```bash
python -m integraciones.lpr.simulador --url http://localhost:8090 --token "$LPR_TOKEN_CAMARA" BBCD12 0.95
```

Pruebas automáticas (sin red ni cámara):

```bash
cd backend && pytest tests/test_lpr.py
```

## Pendiente antes de producción

- Probar con la cámara real y ajustar `LPR_CONFIANZA_MINIMA` con lecturas reales.
- HTTPS entre cámara, traductor y backend (hoy HTTP en la red local).
- La deduplicación vive en memoria: con más de un proceso del traductor habría que moverla a Redis.
