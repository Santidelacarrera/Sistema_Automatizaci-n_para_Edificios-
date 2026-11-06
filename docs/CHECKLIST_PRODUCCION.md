# Checklist de puesta en producción

Lo que el código ya resuelve y lo que sólo puede hacer una persona con acceso al servidor, a las cuentas y al hardware.

## Resuelto en el repositorio
- `ENTORNO=produccion` por defecto en Docker Compose (API, worker y beat): exige `JWT_SECRET` propio y PostgreSQL, activa HSTS y desactiva `create_all`.
- `/docs`, `/redoc` y `/openapi.json` no se publican en producción ni pasan por el proxy.
- Logs de todos los contenedores con rotación (10 MB x 5 archivos): el disco del VPS no se llena.
- Redis con healthcheck; `api`, `worker` y `beat` esperan a Redis sano; el proxy espera a la API sana.
- Verificado el 2026-11-05 en local: `docker compose up` completo (api, worker, beat, panel, Redis, Caddy, PostgreSQL local) sano; `/ready` ok; `/docs` y `/openapi.json` dan 404; migraciones 0001 a 0007 (subida, bajada y subida) y la suite completa contra PostgreSQL 16 real (273 pasadas); Playwright 36 pasadas.
- Integrada la rama `claude/comunidad-y-portal` (Mi Depto real, comunidad, migraciones 0006 y 0007).
- CI: pruebas con SQLite y PostgreSQL real, migraciones, respaldo/restauración, imágenes Docker, E2E, escáner de secretos.

## Pendiente: requiere acción humana
- [ ] Contratar VPS y dominio; apuntar el DNS; abrir puertos 80 y 443 (docs/PUESTA_EN_MARCHA.md §7).
- [ ] Crear `.env` con `python scripts/configurar_entorno.py` (ENTORNO, DATABASE_URL, JWT_SECRET, CORS_ORIGINS, DOMINIO).
- [ ] `docker compose up -d --build` y comprobar `https://DOMINIO/ready` (primer certificado real).
- [ ] Migraciones contra Supabase/PostgreSQL de producción (corren al arrancar la API).
- [ ] Cargar la nómina de los 4 edificios (`scripts/seed.py`, `scripts/importar_csv.py`).
- [ ] Evolution API: instancia, QR, webhook con `X-Webhook-Token`; probar un envío y el QR de visita.
- [ ] SMTP/SES: dominio verificado, salir del sandbox, probar `scripts/verificar_conexiones.py`.
- [ ] Programar `scripts/respaldo_db.sh` diario (cron), copiar fuera del servidor y probar una restauración.
- [ ] ESP32: cargar firmware con HTTPS al dominio real; probar relé y lector Wiegand en terreno.
- [ ] Cámara LPR (Hikvision/Dahua): confirmar modelo y adaptador; definir `LPR_REDIS_URL`.
- [ ] Completar la tabla "A quién avisar" de docs/OPERACION.md.
- [ ] Revisar `docs/PRIVACIDAD.md` con el responsable de datos de cada comunidad.
