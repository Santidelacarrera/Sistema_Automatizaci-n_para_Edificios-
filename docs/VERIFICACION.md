# Verificación

Registro de lo que se **ejecutó de verdad** (fecha: 24-10-2026, entorno de desarrollo Linux con PostgreSQL 16 y
Redis locales). Cada fila dice qué se probó, con qué comando y qué quedó sin probar.

## Resultado

| Qué | Comando | Resultado |
|---|---|---|
| Suite del backend (SQLite) | `cd backend && pytest -q` | 215 pasan, 2 se omiten (las de PostgreSQL) |
| Suite del backend (PostgreSQL 16 real) | `TEST_DATABASE_URL=postgresql+psycopg://… pytest -q` | 216 pasan, 1 se omite (prueba específica de SQLite) |
| Carreras de concurrencia (PostgreSQL) | `pytest tests/test_concurrencia_pg.py` | Pasan con el bloqueo de filas; **sin él fallan** (se aceptaban 10 y 11 reservas con 6 cupos) |
| Migraciones en PostgreSQL | `alembic upgrade head && alembic check` | Sin diferencias entre modelos y migraciones |
| Panel, modo demo | `npx playwright test` (en `frontend/`) | 15/15 |
| Panel contra el backend real | `scripts/e2e_real.sh` | 3/3: login con error, recorrido (vehículo, lecturas del portón, bitácora) y sesión inválida |
| Celery + Redis reales | worker `--pool=solo` y `.delay()` | `purgar_datos`, `liberar_no_show` y `enviar_email` ejecutadas por la cola |
| Build del panel | `npm run build` (Next 15.5, React 19) | Compila |
| Escáner de secretos | `python scripts/escaner_secretos.py` | 0 hallazgos |
| `docker compose config` | con `.env` de prueba | Válido; el servicio `db` sólo aparece con `--profile db-local` |

## Defectos que esta verificación encontró y se corrigieron

1. **La migración 0002 fallaba en PostgreSQL** (`activo = 0` sobre una columna booleana). Habría impedido
   `alembic upgrade head` en Supabase. Sólo apareció al probar contra PostgreSQL real.
2. **Carreras en cupos de visita y límites de vehículos/tags**: dos solicitudes simultáneas veían el mismo cupo
   libre. Ahora se bloquea la fila del edificio o del departamento durante la operación.
3. **Hora**: las reglas de horario, las ventanas de visitas y los vencimientos usaban UTC. Ahora usan la hora del
   negocio (`ZONA_HORARIA`, por defecto `America/Santiago`).
4. **Login sin límite de intentos** y respuesta más lenta para cuentas existentes: ahora hay bloqueo temporal y
   un hash de relleno para igualar tiempos.
5. **Clave de lector guardada en claro**: ahora se guarda su hash SHA-256 y se puede rotar desde el panel.
6. **Panel mostraba datos viejos** al cambiar de sección (hasta 10 s): ahora refresca al cambiar.
7. **Next.js 14.2.15** con avisos críticos: actualizado a 15.5.
8. **Cartolas sin límite de tamaño** (riesgo de agotar memoria): ahora se rechazan sobre 5 MB con 413.
9. **Sin cabeceras de seguridad** en API y panel: ahora hay `nosniff`, anti-marcos, `no-store` en datos personales, HSTS en producción y una política de contenido (CSP) en el panel.

## Qué NO se probó

- **Su proyecto de Supabase.** El motor es PostgreSQL y está probado, pero la conexión, el SSL y el pooler de su
  proyecto sólo se comprueban con `python scripts/verificar_conexiones.py` y sus credenciales.
- **`docker compose up`:** este entorno no tiene el servicio de Docker. Sólo se validó la configuración.
- **WhatsApp (Evolution API) y correo (SMTP/SES) reales.** Se probaron con dobles; sin credenciales el sistema
  informa "no configurado".
- **Hardware:** lector UHF, ESP32, relé, Ethernet y cámara de patentes. El firmware se probó con simulador; la
  lista de pruebas de banco está en `firmware/esp32/README.md`.
- **Flujo de GitHub Actions:** el workflow `.github/workflows/ci.yml` está validado como YAML pero aún no se ha
  ejecutado en GitHub.
- **Carga con muchos usuarios simultáneos** y recuperación ante caída de la base.
- **Revisión legal** (`docs/PRIVACIDAD.md`).

## Cómo repetirlo

```bash
# Backend contra PostgreSQL local
createdb edificios_test
cd backend && TEST_DATABASE_URL=postgresql+psycopg://usuario@localhost/edificios_test pytest -q

# Panel + API reales con datos sembrados (requiere Chrome o PW_CHROMIUM=/ruta/chromium)
scripts/e2e_real.sh
```
