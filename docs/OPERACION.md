# Operación diaria y qué hacer cuando algo falla

Para quien administra el sistema. Los comandos suponen que está en la carpeta del proyecto y usa Docker Compose.

## Revisión rápida (1 minuto)
1. Abra `https://TU-DOMINIO/ready`: debe decir `{"ok": true, ...}`. Si dice `falla` en `base` o `redis`, vaya a "El sistema no responde".
2. En el panel, sección **Portón**: las últimas lecturas deben ser recientes. Si hace horas que no hay ninguna y el edificio tiene movimiento, revise el lector.
3. Sección **Cobranza**: el número junto al nombre es la cantidad de departamentos con saldo.

## El portón no abre
Siga en este orden; casi siempre es uno de los primeros tres.
1. **¿El auto o el sticker está registrado y activo?** Panel → ficha del departamento. Un sticker marcado perdido o bloqueado no abre.
2. **¿Qué dice la bitácora?** Panel → Portón. Cada lectura muestra por qué abrió o no: «Credencial desconocida», «faltó la patente», «el sticker pertenece a otro vehículo», «fuera de horario», etc.
3. **¿Es el modo de acceso?** Si el modo es *Sticker y patente* y la cámara no lee la patente (suciedad, luz, lluvia), el portón no abre. Solución rápida: Administración → Acceso → cambiar a *Sólo sticker* mientras se limpia o ajusta la cámara. Anote el cambio y vuélvalo a *Sticker y patente* después.
4. **¿Llegan lecturas del lector?** Si en el Portón no aparece nada al pasar un sticker: el lector, el ESP32 o la red están caídos. Revise la alimentación del equipo y el cable de red. El ESP32 se reinicia solo ante fallos; si sigue mudo, desconecte y conecte la alimentación.
5. **¿Aparece «No autorizado» o error 401?** La clave del lector no coincide (se rotó o se cambió). Administración → Acceso → *Generar clave nueva* y cárguela en el lector (`config_local.py`).
6. **Apertura manual:** el portón debe conservar siempre su llave o control manual. El sistema abre sólo con una respuesta afirmativa del servidor; si el servidor o la red fallan, el portón **no abre solo** a propósito.

## El sistema no responde
1. `docker compose ps`: todos los servicios deben estar `running`/`healthy`.
2. `docker compose logs --tail=100 api` muestra el último error.
3. Si `/ready` dice que la base falla: revise el estado de su proyecto en Supabase (puede estar pausado por inactividad en el plan gratuito) y que `DATABASE_URL` siga vigente.
4. Si dice que Redis falla: `docker compose restart redis worker beat`.
5. Un **503** con «El servidor está ocupado» significa demasiadas peticiones a la vez; el lector reintenta solo. Si es frecuente, suba `DB_POOL_SIZE` y `DB_MAX_OVERFLOW` sin pasar el límite de conexiones de su plan.
6. Reinicio general: `docker compose restart api worker beat`. Los datos no se pierden: están en la base.

## Los avisos por WhatsApp o correo no salen
- Panel → Administración muestra el **diagnóstico**: qué canales están configurados. «No configurado» indica la variable que falta en `.env`.
- WhatsApp: en Evolution API, la instancia debe estar conectada (si se cerró la sesión, vuelva a escanear el QR). Después de reiniciar el servidor de Evolution verifique que el webhook siga apuntando a `https://TU-DOMINIO/webhooks/whatsapp` con la cabecera `X-Webhook-Token`.
- Correo: pruebe las credenciales SMTP con `python scripts/verificar_conexiones.py`.
- Las tareas de envío van por una cola: `docker compose logs --tail=100 worker` dice qué falló y cuántas veces se reintentó.

## Pagos y gastos comunes
- **Generar el mes:** Finanzas → Gastos comunes. Un mes ya generado no se repite; si se equivocó de monto, avise a soporte antes de intentar corregir a mano.
- **Conciliar:** Finanzas → Cartola bancaria. Los pagos «sin identificar» se revisan a mano (suele faltar el código de pago o el RUT en la glosa). Subir la misma cartola dos veces no duplica abonos.
- **Residente que dice que pagó y sigue con deuda:** busque su pago en la cartola; si no está identificado, el residente debe indicar el código de pago de su departamento (`CC-…`) en la transferencia.

## Altas y bajas
- **Nuevo residente o cambio de dueño:** Administración → Residentes. Si se va alguien, *dar de baja* (conserva el historial). Para borrar sus datos personales a petición suya, use *anonimizar* (no se puede deshacer; ver `docs/PRIVACIDAD.md`).
- **Sticker perdido:** ficha del departamento → *Marcar perdido*: deja de abrir al instante. Asigne uno nuevo.
- **Cambio de vehículo:** dar de baja la patente anterior y registrar la nueva (cada departamento tiene un máximo según sus estacionamientos).

## Respaldos y restauración
- Debe haber un respaldo diario programado (`scripts/respaldo_db.sh`, ver `docs/PUESTA_EN_MARCHA.md`). Compruebe cada semana que el archivo más reciente existe y pesa algo razonable.
- **Probar la restauración** al menos una vez al trimestre en una base vacía con `scripts/restaurar_db.sh`.
- Si pierde la base: cree una base vacía, restaure el último respaldo, apunte `DATABASE_URL` a ella y reinicie (`alembic upgrade head` corre al arrancar la API).

## Actualizar el sistema
1. Haga un respaldo (`scripts/respaldo_db.sh`).
2. `git pull` en la rama aprobada y `docker compose up -d --build`. Las migraciones de la base corren solas al iniciar la API.
3. Revise `/ready` y haga una lectura de prueba en el portón.
4. Si algo falla: vuelva a la versión anterior (`git checkout <versión>` y `docker compose up -d --build`). Una migración nueva no siempre se puede deshacer: por eso el respaldo previo.

## Seguridad: cuándo cambiar claves
- **Al perder un lector o un equipo**, o si un técnico que tenía la clave deja de trabajar con ustedes: generar clave nueva de lectores.
- **Si se filtra `.env` o una contraseña** (por ejemplo, se pegó en un chat): cámbiela en el servicio de origen y en `.env`; ver `docs/CREDENCIALES.md`. Para el secreto de sesiones (`JWT_SECRET`), cambiarlo cierra todas las sesiones abiertas.
- **Intentos de inicio de sesión bloqueados:** tras 5 fallos una cuenta se bloquea 15 minutos. No hay que hacer nada; si es un ataque, el bloqueo también protege.

## A quién avisar
Complete esta tabla con su gente antes de la puesta en marcha.

| Qué falla | Quién lo resuelve | Contacto |
|---|---|---|
| Servidor / Docker / dominio | | |
| Base de datos (Supabase) | | |
| Lector del portón y cámara | | |
| WhatsApp (Evolution) | | |
| Dudas de datos personales | | |
