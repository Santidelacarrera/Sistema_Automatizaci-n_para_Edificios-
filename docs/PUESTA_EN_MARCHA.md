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

> **Credenciales:** no las escriba en ningún archivo del repositorio. Ejecute `python scripts/configurar_entorno.py` (crea `.env`) y `python scripts/verificar_conexiones.py`. Ver [docs/CREDENCIALES.md](CREDENCIALES.md).

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

Para el portón (stickers UHF, lector Wiegand y patentes) ver [docs/PORTON_UHF.md](PORTON_UHF.md) y el README del firmware en `firmware/esp32/`.

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

El proyecto trae un proxy **Caddy** que obtiene y renueva solo el certificado de Let's Encrypt.

1. Compre o use un dominio (p. ej. `administracion.miempresa.cl`) y haga que apunte a la IP pública del servidor.
2. Abra los puertos **80 y 443** en el servidor. No abra el 8000 ni el 3000: la API y el panel quedan sólo detrás del proxy.
3. Escriba el dominio en `.env` (`DOMINIO=administracion.miempresa.cl`, sin `https://`) y en `CORS_ORIGINS`.
4. `docker compose up -d --build`. El panel y la API comparten dominio: el panel en `/` y la API en `/auth`, `/edificios`, `/api`, `/webhooks`.

Qué hace el `Caddyfile`: redirige HTTP a HTTPS, comprime, limita los cuerpos a 6 MB, agrega HSTS y reenvía la IP real del cliente
(la API la usa para el bloqueo de intentos de login). Los certificados se guardan en el volumen `caddy_datos`: no lo borre.

Los lectores (ESP32) deben apuntar a `https://TU-DOMINIO` en producción. Hoy el firmware se probó sólo con HTTP en la red local.

> Estado: la configuración de Compose valida y el panel se verificó como imagen standalone, pero **no se ha levantado
> el conjunto con Docker ni se ha emitido un certificado real**; haga esa prueba con su dominio antes de instalar el portón.

## 8. Docker Compose

```bash
cp .env.example .env          # completar, incluido DB_PASSWORD
docker compose up -d --build  # redis, api (migra al arrancar), panel, proxy HTTPS, worker, beat
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

Comprobar que el sistema está sano: `curl https://TU-DOMINIO/ready` responde `{"ok": true, ...}` cuando la base y Redis contestan
(`/health` sólo dice que el proceso está vivo).

### Respaldos

Funcionan con la base que use (Supabase o PostgreSQL propio). Necesita `pg_dump` (paquete `postgresql-client`) en la máquina que los corre.

```bash
scripts/respaldo_db.sh                    # crea respaldos/edificios-AAAAMMDD-HHMMSS.dump (permiso 600)
RESPALDO_DIAS=30 scripts/respaldo_db.sh   # conserva 30 días en vez de 14
```

Programe uno diario con cron, por ejemplo `15 3 * * *  cd /ruta/al/proyecto && scripts/respaldo_db.sh >> respaldos/respaldo.log 2>&1`,
y copie la carpeta `respaldos/` fuera del servidor. El script comprueba que el archivo se pueda leer y nunca imprime la contraseña.

**Pruebe la restauración** en una base vacía (nunca sobre la que está en uso):

```bash
createdb prueba_restauracion
scripts/restaurar_db.sh respaldos/edificios-AAAAMMDD-HHMMSS.dump postgresql://usuario:clave@host/prueba_restauracion
```

Muestra cuántas filas trae cada tabla clave. El script se niega a restaurar sobre la base en uso salvo que agregue `--sobrescribir`.
Un respaldo que nunca se restauró no se puede dar por bueno.

## Pendientes conocidos

- Probar `docker compose up` con su dominio y emitir el primer certificado (sección 7).
- Firmware ESP32: sin probar en hardware; HTTP en la red local.
- Lector de patentes: sólo formato genérico; Hikvision y Dahua pendientes de confirmar el modelo.
- Envío real por WhatsApp y correo: no probado contra servicios reales.
