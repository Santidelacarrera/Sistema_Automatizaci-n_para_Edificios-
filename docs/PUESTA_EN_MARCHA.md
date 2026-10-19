# Puesta en marcha

Guía para instalar el sistema, cargar un edificio, conectar WhatsApp y correo, y dejar listo el
portón. Todo lo sensible (contraseñas, claves de dispositivo, tokens) va en `.env` o en variables
de entorno, nunca en el repositorio.

> **Estado de lo probado.** Probado con ejecución real: migraciones, carga de datos por CLI,
> API y panel en modo demo (Chrome). Probado con mocks: WhatsApp (Evolution API) y correo SMTP.
> **Sin probar aún**: envío real por WhatsApp y por correo, firmware en hardware, cámara LPR,
> HTTPS en producción. Ver la lista de pruebas manuales al final.

## 1. Requisitos

- Python 3.12 y Node.js 20 o superior (sólo para el panel).
- Docker y Docker Compose (para el despliegue).
- PostgreSQL 16 y Redis 7 si se usa sin Docker (en Docker vienen incluidos).

## 2. Instalar en desarrollo

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env          # completar valores (ver sección 4)
alembic upgrade head                # crea las tablas; nunca uses create_all en producción
pytest                              # debe pasar todo
uvicorn app.main:app --reload       # API en http://localhost:8000 (docs en /docs)
```

Panel:

```bash
cd frontend
npm install
cp .env.example .env.local          # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                         # http://localhost:3000
```

Sin `NEXT_PUBLIC_API_URL` el panel sólo ofrece el modo demo: los datos son de ejemplo y no salen
del navegador.

## 3. Cargar datos

Orden recomendado. Todo se hace por línea de comandos, sin tocar la base a mano.

### 3.1 Edificio, departamentos y administrador

Crear un archivo YAML fuera del repositorio (por ejemplo `datos/edificio_a.yaml`):

```yaml
edificio:
  id: edificio_a            # minúsculas, números y guion bajo; no se puede cambiar después
  nombre: Edificio Alameda 1450
  cupos_visitas: 6
  max_estac_por_unidad: 2
  tolerancia_visita_min: 20
departamentos:
  - {numero: "101", coeficiente: 0.25, estacionamientos: 2, codigo_cobro: CC-A-101}
  - {numero: "102", coeficiente: 0.25, estacionamientos: 1, codigo_cobro: CC-A-102}
administrador: {nombre: Ana Pérez, rut: "12.345.678-5", email: ana@ejemplo.cl, telefono: "+56 9 1111 2222", unidad: "101"}
```

```bash
SEED_ADMIN_PASSWORD='una-clave-de-12-o-mas-caracteres' \
  python scripts/seed.py --archivo ../datos/edificio_a.yaml
```

El script imprime la **X-Device-Key** de los lectores y, si no diste contraseña, una contraseña
generada. Guárdalas en un gestor de contraseñas: no se vuelven a mostrar. Si el edificio ya
existe, el script se niega a sobrescribirlo.

### 3.2 Departamentos y residentes desde CSV

Plantilla: [`docs/plantillas/departamentos_residentes.csv`](plantillas/departamentos_residentes.csv).

```bash
python scripts/importar_csv.py --edificio edificio_a ../datos/departamentos.csv --dry-run   # revisar primero
python scripts/importar_csv.py --edificio edificio_a ../datos/departamentos.csv
```

- Acepta separador `,` o `;` (Excel en Chile suele usar `;`) y UTF-8 con o sin BOM.
- Es idempotente: reimportar el mismo archivo no duplica residentes (se identifican por RUT).
- Las filas con error se reportan con su número de línea y el resto se importa igual.
  Código de salida 1 si hubo filas rechazadas.

### 3.3 Superadmin (sólo si la empresa administra varios edificios)

```bash
SUPERADMIN_PASSWORD='clave-de-12-o-mas' python scripts/crear_superadmin.py \
  --edificio edificio_a --unidad 101 --nombre "Soporte" --rut 11.111.111-1 --email soporte@empresa.cl
```

El superadmin inicia sesión en un edificio base y desde el panel cambia de edificio con el selector.

### 3.4 Tags y patentes

Los tags RFID y las patentes se registran desde el panel, en **Administración**. El UID del tag
va en hexadecimal (8 a 20 caracteres). Cada departamento tiene como máximo los estacionamientos
que indique su ficha y el máximo del edificio.

## 4. Variables de entorno

| Variable | Obligatoria | Para qué |
|---|---|---|
| `DB_PASSWORD` | sí (Docker) | Contraseña de PostgreSQL. |
| `DATABASE_URL` | sí fuera de Docker | Ej. `postgresql+psycopg://usuario:clave@host:5432/edificios`. Por defecto SQLite (sólo desarrollo). |
| `JWT_SECRET` | sí | Al menos 32 caracteres aleatorios. Generar con `python -c "import secrets;print(secrets.token_urlsafe(48))"`. |
| `WHATSAPP_WEBHOOK_TOKEN` | sí si usas WhatsApp | Secreto compartido con Evolution API (cabecera `X-Webhook-Token`). Sin él, el webhook rechaza todo. |
| `EVOLUTION_URL` | WhatsApp | URL base de Evolution API, sin barra final. |
| `EVOLUTION_INSTANCE` | WhatsApp | Nombre de la instancia (ej. `edificio-a`). |
| `EVOLUTION_APIKEY` | WhatsApp | API key de Evolution API. |
| `ANTHROPIC_API_KEY` | no | Clasificación de mensajes con LLM. Sin ella se usan palabras clave. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | correo | Servidor de envío (ver sección 6). |
| `REDIS_URL` | Celery | Broker de tareas. |
| `CELERY_EAGER` | no | `false` en producción (tareas en el worker). `true` ejecuta en la misma petición: sólo desarrollo. |
| `CORS_ORIGINS` | sí | Dominio del panel, ej. `https://panel.ejemplo.cl`. |
| `LPR_*` | lector de patentes | Ver `backend/integraciones/lpr/README.md`. |

Revisa el diagnóstico (`GET /edificios/{id}/diagnostico`, sólo admin; todavía no tiene pantalla): indica
qué canales están configurados y advierte si queda algún valor de ejemplo. No muestra secretos.

## 5. WhatsApp con Evolution API

1. Crear una instancia en Evolution API (desde su panel o su API de administración). Anotar el
   nombre y la API key y ponerlos en `EVOLUTION_INSTANCE` y `EVOLUTION_APIKEY`.
2. Escanear el **código QR** que muestra la instancia con el teléfono del edificio (WhatsApp →
   Dispositivos vinculados). Mientras la sesión esté desconectada, los mensajes no salen.
3. Configurar el **webhook** de la instancia:
   - URL: `https://TU-DOMINIO/webhooks/whatsapp`
   - Evento: `messages.upsert`
   - Cabecera: `X-Webhook-Token: <valor de WHATSAPP_WEBHOOK_TOKEN>`

   Los nombres exactos de los campos de configuración cambian según la versión de Evolution API:
   verifícalos en su documentación para tu versión.
4. Probar: el diagnóstico debe mostrar WhatsApp configurado. Luego, enviar un
   recordatorio de cobranza a un departamento de prueba. El panel muestra el resultado de cada
   envío: enviado, no configurado (con la variable que falta) o error (con el motivo).

Notas de seguridad: el webhook sólo responde a mensajes de números registrados como residentes.
A quien no esté registrado se le responde que contacte a la administración, sin revelar datos.

## 6. Correo (SMTP o Amazon SES)

Con SES, el servidor SMTP es `email-smtp.<región>.amazonaws.com` puerto `587` (STARTTLS). Las
credenciales SMTP se generan en la consola de SES, no son las credenciales de AWS normales.

Antes de enviar:

1. Verificar el dominio o la dirección remitente en SES (`SMTP_FROM`). Si la cuenta está en modo
   sandbox, sólo se puede enviar a direcciones verificadas.
2. Completar `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.
3. Revisar el diagnóstico: correo debe figurar como configurado.

El correo masivo va por cola: el panel muestra "encolado". El resultado final (enviado o error)
queda en el log del worker. Los errores de red se reintentan hasta 5 veces con espera creciente.
Un error permanente (credenciales o destinatario rechazado) no se reintenta.

## 7. HTTPS y dominio

El sistema no trae proxy HTTPS incluido. Opciones:

- **Caddy** o **Nginx** delante de la API y del panel, con certificado de Let's Encrypt.
  Redirigir HTTP a HTTPS y reenviar a `api:8000` (API) y `frontend:3000` (panel).
- Los lectores (ESP32) deben usar HTTPS en producción. Hoy el firmware usa HTTP en la red local:
  es un pendiente de seguridad, no un valor por defecto aceptable.

Pendiente de decisión: dominio y proxy. Ver la sección de pendientes.

## 8. Docker Compose

```bash
cp .env.example .env          # completar, incluido DB_PASSWORD
docker compose up -d --build  # db, redis, api (migra al arrancar), worker, beat
docker compose ps
docker compose logs -f api
```

- `api` aplica `alembic upgrade head` antes de iniciar uvicorn.
- `worker` ejecuta las tareas de correo y avisos; `beat` libera las visitas no llegadas.
- Carga inicial dentro del contenedor (el archivo YAML debe estar en el host):

```bash
docker compose run --rm -v "$PWD/datos:/datos:ro" api python scripts/seed.py --archivo /datos/edificio_a.yaml
docker compose run --rm -v "$PWD/datos:/datos:ro" api python scripts/importar_csv.py --edificio edificio_a /datos/departamentos.csv
```

Respaldo de la base:

```bash
docker compose exec db pg_dump -U edificios edificios | gzip > respaldo_$(date +%F).sql.gz
```

Restaurar en una base vacía: `gunzip -c respaldo.sql.gz | docker compose exec -T db psql -U edificios edificios`.
Guardar los respaldos fuera del servidor y probar la restauración al menos una vez.

## 9. Lista de pruebas manuales antes de poner el portón en producción

Marca cada una con fecha y responsable. No abrir el portón a residentes hasta completar todas.

**Portón y lectores**
- [ ] Tag peatonal de un residente abre la puerta peatonal; el vehicular no lo acepta.
- [ ] Tag vehicular abre el portón a menos de 15 m; una tarjeta desconocida no.
- [ ] Tag desactivado en el panel deja de abrir de inmediato (cada lectura consulta al backend).
- [ ] Sin red: el lector no abre y lo indica (fail-closed).
- [ ] El relé se activa 1 segundo y el portón se cierra solo.
- [ ] Lectura de patente de residente abre; de visita con reserva vigente, abre; sin reserva, no.
- [ ] QR de visita: abre hasta el número de usos; fuera de su ventana horaria, no.

**Visitas**
- [ ] Reserva con cupos llenos se rechaza con mensaje claro.
- [ ] Visita que no llega en 20 min libera su cupo.
- [ ] El QR se ve bien en pantalla de celular y se puede imprimir.

**Cobranza y pagos**
- [ ] Gasto común generado con la prorrata correcta (suma exacta del total).
- [ ] Recordatorio por WhatsApp llega a un teléfono de prueba y el panel lo muestra como enviado.
- [ ] Recordatorio por correo llega (revisar spam) y el log del worker no muestra errores.
- [ ] Pago registrado con referencia repetida no se aplica dos veces.
- [ ] Cancelar una reserva con poco aviso (vía API `POST .../reservas-espacio/{id}/cancelar`) carga la multa.

**Seguridad**
- [ ] Un residente no ve ni cambia datos de otro edificio.
- [ ] Un residente no entra a Administración.
- [ ] `JWT_SECRET` y contraseñas del `.env` son los definitivos (no los de ejemplo).
- [ ] El webhook de WhatsApp rechaza una llamada sin token.
- [ ] HTTPS activo con certificado válido en API y panel.

**Operación**
- [ ] Respaldo generado y restauración probada en otra base.
- [ ] Reinicio del servidor: los servicios vuelven solos (con `restart: unless-stopped` en `docker-compose.yml`).
- [ ] Persona de contacto del edificio sabe qué hacer si el portón falla (falta escribir `docs/OPERACION.md`).

## Pendientes conocidos

- Decisión de dominio y proxy HTTPS (sección 7).
- Firmware ESP32: sin probar en hardware; HTTP en la red local.
- Lector de patentes: sólo formato genérico; Hikvision y Dahua pendientes de confirmar el modelo.
- Envío real por WhatsApp y correo: no probado contra servicios reales.
