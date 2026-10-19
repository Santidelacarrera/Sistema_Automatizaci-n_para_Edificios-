# Credenciales y secretos

Regla única: **las credenciales viven sólo en `.env` (raíz del repositorio), en su computador.** Nunca
en el chat, en el código, en `docker-compose.yml`, en la documentación ni en Git. El repositorio
ignora `.env`, `.env.bak` y `config_local.py`, y el chequeo pre-commit bloquea esos archivos y los
secretos que aparezcan en el código.

Ningún script ni asistente muestra un secreto completo: sólo los últimos 4 caracteres (`****abcd`).

## 1. Cómo configurar (paso a paso, en su computador)

```bash
python scripts/configurar_entorno.py     # 1. asistente: pide cada dato, oculta los secretos, escribe .env
python scripts/verificar_conexiones.py   # 2. prueba cada servicio sin enviar mensajes ni datos
docker compose up -d --build             # 3. (opcional) levanta API, worker y beat con ese .env
docker compose exec api python scripts/seed.py --archivo ...   # 4. carga el edificio (ver PUESTA_EN_MARCHA.md)
```

El asistente pregunta en este orden: `ENTORNO`, `DATABASE_URL`, `JWT_SECRET`,
`WHATSAPP_WEBHOOK_TOKEN`, claves de dispositivo (opcional), Evolution API, SMTP, `ANTHROPIC_API_KEY`
y `CORS_ORIGINS`. Los datos opcionales se pueden dejar vacíos: el resumen final indica qué queda
desactivado. Si `.env` ya existe, pregunta antes de reemplazarlo y guarda una copia en `.env.bak`.

Para ejecutar sólo la verificación sobre un archivo distinto: `python scripts/verificar_conexiones.py --env ruta/.env`.

## 2. Dónde se consigue cada dato

### Base de datos (Supabase) — `DATABASE_URL`

1. Panel de Supabase → tu proyecto → **Project Settings → Database**.
2. En **Connection string**, elija **Session pooler** (puerto **5432**) o la conexión directa.
   Copie la cadena completa. Reemplace `[YOUR-PASSWORD]` por la contraseña de la base
   (si no la recuerda: **Reset database password** en la misma pantalla).
3. **No use el puerto 6543** (pooler en modo *transaction*): Alembic y las transacciones largas fallan
   ahí. El asistente lo rechaza y explica por qué.
4. Pegue la cadena en el asistente. Él la convierte al prefijo `postgresql+psycopg://` y agrega
   `sslmode=require`, que Supabase exige.

### WhatsApp (Evolution API) — `EVOLUTION_URL`, `EVOLUTION_INSTANCE`, `EVOLUTION_APIKEY`

- **URL**: la dirección donde está instalado su Evolution API (por ejemplo `https://evolution.ejemplo.cl`).
- **Instancia**: el nombre de la instancia de WhatsApp que creó en Evolution.
- **API key**: la clave de administración de Evolution API (la define su instalación; no se obtiene del
  número de WhatsApp).
- **Código QR**: escanee el QR de la instancia con el teléfono del edificio (WhatsApp → Dispositivos
  vinculados) para conectarla. Sin conexión, los mensajes no salen.
- **Webhook**: URL `https://SU-DOMINIO/webhooks/whatsapp` con la cabecera
  `X-Webhook-Token` igual a `WHATSAPP_WEBHOOK_TOKEN`. Los nombres exactos de los campos dependen de la
  versión de Evolution: verifíquelos en su documentación.

### Correo (SMTP o Amazon SES) — `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`

- En **Amazon SES → SMTP settings** obtiene el servidor (`email-smtp.<región>.amazonaws.com`), puerto
  587 y las **credenciales SMTP** (no son las credenciales de AWS normales: se generan en esa pantalla).
- `SMTP_FROM` debe ser una dirección o dominio **verificado** en SES. En modo *sandbox* sólo se envía a
  direcciones verificadas.

### Clasificación con IA — `ANTHROPIC_API_KEY` (opcional)

Consola de Anthropic → API keys. Sin clave, los mensajes se clasifican por palabras clave.

### Claves propias — `JWT_SECRET`, `WHATSAPP_WEBHOOK_TOKEN`

El asistente las genera con `secrets` (64 caracteres). No necesita obtenerlas en ningún lado.
Mínimo 32 caracteres; `JWT_SECRET` no puede ser el valor de ejemplo.

### Claves de dispositivo — `X-Device-Key` de cada edificio

La clave real vive en la base: la crea `scripts/seed.py` al cargar el edificio y se muestra **una sola
vez**. Guárdela en el gestor de contraseñas y úsela en el `config_local.py` del lector. Sólo guárdela en
`.env` si ya la tiene; generar una nueva aquí no coincidiría con la base.

## 3. Reglas de uso

- **No use la API automática de Supabase** (PostgREST / *Data API*) para estas tablas. Contienen datos
  personales de residentes (RUT, teléfonos, correos). El sistema accede a la base sólo desde el backend.
  Si la Data API está activa, desactívela para el esquema del proyecto.
- **No use la clave `service_role` de Supabase** en ningún archivo: el sistema usa sólo la cadena de
  conexión de PostgreSQL.
- Un secreto por propósito: no reutilice la clave de la base como contraseña de otro servicio.
- El `.env` de producción debe estar en el servidor, con permisos de lectura sólo para el usuario que
  ejecuta el servicio (`chmod 600 .env` en Linux).
- `ENTORNO=produccion` impide arrancar con `JWT_SECRET` de ejemplo o con SQLite.

## 4. Cómo rotar un secreto

| Secreto | Procedimiento |
|---|---|
| `JWT_SECRET` | Ejecute el asistente y acepte generar uno nuevo. Todas las sesiones del panel se cierran: los usuarios vuelven a entrar. |
| `DATABASE_URL` (contraseña) | En Supabase: **Reset database password**. Luego ejecute el asistente con la nueva cadena. Reinicie `api`, `worker` y `beat`. |
| `WHATSAPP_WEBHOOK_TOKEN` | Genere uno nuevo en el asistente y actualice la cabecera `X-Webhook-Token` en Evolution API **antes** de reiniciar. Mientras no coincidan, el webhook rechaza los mensajes. |
| `EVOLUTION_APIKEY` | Regenere la clave en Evolution API y ejecute el asistente. |
| `SMTP_PASSWORD` | En SES, cree nuevas credenciales SMTP, actualice `.env` y desactive las anteriores. |
| `ANTHROPIC_API_KEY` | En la consola de Anthropic, cree una nueva clave, actualice `.env` y revoque la anterior. |
| `X-Device-Key` | Rote la clave del edificio (desde el panel de administración, cuando esté disponible) y actualice `config_local.py` de **cada** lector. Hasta entonces el lector anterior sigue funcionando. |

Después de rotar: ejecute `python scripts/verificar_conexiones.py` y pruebe un recordatorio a un
teléfono de prueba.

## 5. Si se filtra un secreto

1. **Revoque o cambie el secreto de inmediato** (sección 4). No espere a confirmar el alcance.
2. Revise la bitácora de accesos (`accesos_log` y `eventos`) desde la fecha probable de la filtración.
3. Si la filtración fue en Git (un commit, aunque se haya borrado después), **considérelo público**:
   el historial de Git conserva el valor. Rote el secreto; reescribir el historial no basta.
4. Si eran datos de residentes, evalúe la obligación de informar según la normativa de protección de
   datos personales vigente en Chile, con apoyo legal.
5. Anote en un registro interno qué secreto, cuándo, cómo se detectó y qué se cambió.

## 6. Verificación automática

- `backend/tests/test_seguridad_config.py`: el repositorio no
  debe contener URLs de base con clave, claves de Anthropic, claves privadas ni secretos asignados.
- `python scripts/escaner_secretos.py`: el mismo chequeo desde la línea de comandos.
- `python scripts/pre_commit_secretos.py --instalar`: instala un chequeo que impide el commit de
  `.env`, `.env.bak` o `config_local.py`, y de contenido con secretos.
