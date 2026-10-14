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
| Panel web Next.js | ❌ no implementado |

## Ejecutar
```bash
cd backend && pip install -r requirements.txt && pytest      # tests
uvicorn app.main:app --reload                                # dev (SQLite)
cp .env.example .env && docker compose up --build            # PostgreSQL + Redis + worker + beat
```
Docs interactivas: `/docs`. Lectores: `POST /api/v1/{edificio_id}/validar-acceso` con header `X-Device-Key`.

## Pendientes / decisiones
- Migraciones (Alembic), seed de los 4 edificios y alta de edificios/API keys (hoy se crean por SQL/consola).
- Panel web, generación de imagen QR, reserva de visitas/quincho conversacional por WhatsApp (hoy responde cupos/deuda/ayuda).
- Conciliación: formato CSV genérico (`fecha,descripcion,monto,id`); adaptar al formato real del banco.
- Multas por cancelación: la regla se evalúa pero aún no hay endpoint de cancelación que la cobre.
- Producción: HTTPS en lectores (urequests sobre TLS), rotación de claves, rate limiting, secreto JWT ≥32 bytes.
