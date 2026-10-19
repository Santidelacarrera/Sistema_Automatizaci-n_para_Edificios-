# Sistema de Automatización para Edificios

Backend multi-tenant (FastAPI + PostgreSQL + Celery/Redis) y firmware ESP32 (MicroPython) según la guía integral.

## Estado
| Módulo | Estado |
|---|---|
| 1.1 Multi-tenancy (`edificio_id`), JWT, motor de reglas | ✅ implementado y testeado |
| 1.2 WhatsApp (webhook Evolution API, identificación por teléfono, clasificación LLM/keywords) | ✅ webhook+clasificación; respuestas sólo informativas (ver pendientes) |
| 1.2 Correo masivo (Celery + SMTP, plantillas HTML) | ✅ código; no probado contra SMTP/SES real |
| 1.3 Acceso vehicular/peatonal, máx. estacionamientos, visitas con QR, cupos, no-show 20 min | ✅ |
| 1.4 Prorrata (coeficiente/consumo) y conciliación bancaria (RUT / código de cobro) | ✅ cartola CSV; sin webhook bancario real |
| 2 Firmware ESP32 + W5500 + RC522 | ⚠️ escrito, **no probado en hardware** |
| Panel web Next.js (`frontend/`): fachada, portón/patentes, visitas, cobranza | ✅ probado con navegador en modo demo; contra el backend real sin probar |
| Patentes (LPR) + sticker RFID | ✅ tabla `vehiculos`, el lector abre por patente o por tag |
| Cobranza: recordatorios WhatsApp/correo y `POST /pagos` para su sistema de pagos | ✅ |

## Puesta en marcha
Ver [docs/PUESTA_EN_MARCHA.md](docs/PUESTA_EN_MARCHA.md): instalación, carga de datos (seed, CSV), Evolution API, SMTP/SES, HTTPS y lista de pruebas manuales.

## Ejecutar
```bash
cd backend && pip install -r requirements.txt && pytest      # tests
alembic upgrade head && uvicorn app.main:app --reload         # dev (SQLite)
cp .env.example .env && docker compose up --build            # PostgreSQL + Redis + worker + beat
```
Docs interactivas: `/docs`. Lectores: `POST /api/v1/{edificio_id}/validar-acceso` con header `X-Device-Key`.

## Pendientes / decisiones
- Reserva de visitas/quincho conversacional por WhatsApp (hoy responde cupos/deuda/ayuda). El QR ya existe como PNG en la API.
- Conciliación: formato CSV genérico (`fecha,descripcion,monto,id`); adaptar al formato real del banco.
- Producción: HTTPS en lectores (urequests sobre TLS), rotación de claves, rate limiting, secreto JWT ≥32 bytes.

## Panel web
```bash
cd frontend && npm install && cp .env.example .env.local && npm run dev   # http://localhost:3000
```
Sin `NEXT_PUBLIC_API_URL` sólo ofrece el modo demo (datos de ejemplo en el navegador).
