# Uso de los módulos ampliados

## Administración

Inicie sesión con edificio, correo y contraseña. Producción exige MFA a administradores: registre el secreto
en una aplicación TOTP y confirme un código. Después se solicitará el código en cada nuevo inicio de sesión.
Cerrar sesión invalida todas las sesiones del usuario. Cambiar su rol o contraseña exige volver a autenticarse.

En **Gestión comunitaria**, el resumen muestra información de la base del edificio seleccionado. Desde allí
se pueden registrar unidades, consultar pagos, descargar CSV/PDF y revertir un pago con motivo obligatorio.
La reversa restituye los cargos exactos y queda auditada. Un pago histórico sin desglose requiere revisión manual.
El saldo a favor se aplica al generar nuevos gastos comunes. CSV bancario y registro manual no son checkout de pago.

**Incidencias** permite crear un problema, fijar prioridad, responsable y vencimiento; los comentarios y cambios
quedan registrados. El control de versión rechaza guardar sobre cambios ajenos. Una incidencia puede generar
una orden con proveedor/presupuesto y recorrer aprobación, ejecución y término. Una orden pendiente impide cerrar
la incidencia. Se puede valorar el servicio al terminar. Adjuntos y calendario visual aún no están disponibles.

**Proveedores y mantenimiento** registra RUT/contacto/servicios/vencimiento. Los planes preventivos crean incidencias
cuando llega su fecha y avanzan a la próxima revisión; pueden pausarse. **Automatizaciones** habilita/deshabilita
reglas y límites, incluidos recordatorios de deuda optativos. “Ejecutar revisión ahora” procesa esas reglas.

**Asambleas**: cree borrador con agenda/opciones, agregue representantes por unidad y abra la votación para fijar
el padrón. Los participantes confirman asistencia y emiten un voto único. El administrador cierra y guarda acta;
entonces se muestran resultados. No se ofrece validez jurídica automática, quorum legal ni firma electrónica.

**Documentos** requiere DOCMIND configurado por el operador. Suba archivo/título/categoría y decida si se publica
a residentes. Las consultas sólo usan documentos seleccionados y muestran sus fuentes. Un error de configuración
no se presenta como procesamiento exitoso. “Ver procesamiento” informa el estado del proveedor.

**Dispositivos** registra identidad y punto de acceso. La clave se muestra al crear/rotar y debe guardarse de forma
segura. Sólo un controlador de laboratorio admite el comando de apertura simulado. Exige volver a escribir la
contraseña y explicar el motivo. Revise expiración y confirmación en el historial; nunca interprete un ACK simulado
como prueba de movimiento físico.

**Mi suscripción** muestra plan, vigencia y uso. **Soporte** permite enviar una solicitud al operador y consultar
la conversación. La atención no se envía a un servicio externo de terceros.

## Residentes

**Mi Depto** reúne deuda, saldo a favor, cargos y visitas/reservas. Puede descargar el estado de cuenta y comprobantes
disponibles, avisar una transferencia, generar QR de visita, consultar encomiendas y comunicados, reservar espacios
y reportar incidencias. Las notificaciones se marcan como leídas dentro de la aplicación.

En **Gestión comunitaria** puede seguir sus incidencias, comentar, consultar documentos publicados y participar
en asambleas para las que esté en el padrón. No puede leer documentos privados de administración, incidencias de
otra unidad ni respuestas de soporte comercial. No hay pasarela de pago ni app nativa publicada en tiendas.

## Conserjería

El panel presenta visitas, accesos y encomiendas sin saldos ni cobranza. Consulte permisos/estado de cada visita,
registre recepción y retiro de paquetes y use las herramientas disponibles para su rol. Las funciones administrativas
o financieras no se habilitan por conocer su URL. La operación física de emergencia sigue el procedimiento del edificio.
Consulte también [OPERACION.md](OPERACION.md) y [PORTON_UHF.md](PORTON_UHF.md).

## Operador SaaS

El superadministrador puede crear/activar/suspender edificios. **Suspender un edificio invalida acceso de usuarios
y lectores**; el panel exige confirmación. Esto es distinto de suspender el contrato comercial.

En **Administración SaaS**, registre el cliente, cree un plan con precio/límites y asigne el contrato al edificio.
Los precios/límites del plan son inmutables; cambiar condiciones requiere otro plan y un cambio de contrato auditado.
Puede retirar un plan de nuevas contrataciones. La asignación verifica que los datos existentes quepan y rechaza
versiones desactualizadas. Renovar es guardar una nueva vigencia y motivo. Un estado “prueba” tiene fecha de término.

Un contrato vencido/suspendido/cancelado impide nuevas altas por API; conserva consulta, datos y operación de acceso.
Los registros inactivos también cuentan para las cuotas. Los edificios antiguos sin contrato se identifican explícitamente.

**Cobros SaaS** registra una cuota por edificio/período al precio contratado. Repetir una solicitud idéntica devuelve
el mismo registro. Puede registrar pago manual verificado o anulación con referencia y motivo; después no se reescribe.
No se genera movimiento bancario, cargo comunitario ni documento tributario. **Soporte** permite responder solicitudes
y su respuesta crea una notificación interna para administración.

## Puesta en marcha de estos cambios

1. Instalar dependencias de `backend/requirements.txt` y `npm ci` en frontend. Se añadieron pyotp, cryptography y reportlab.
2. Preparar una base de staging aislada, respaldar y probar restauración antes de actualizar una instalación existente.
3. Aplicar `alembic upgrade head` en backend y revisar `alembic check`. Las revisiones nuevas son 0008, 0009, 0010 y 0011.
4. Configurar MFA_ENCRYPTION_KEY (Fernet, independiente del JWT). Sin esa clave no puede completarse el alta de MFA.
   Activar MFA_REQUIRED_PRIVILEGED en desarrollo/staging si se desea probar el flujo obligatorio; en producción ya es obligatorio.
5. Configurar DOCMIND sólo cuando exista proyecto/API key exclusiva por edificio. Mantener vacíos los canales no disponibles.
6. Ejecutar API, worker y un único beat. Verificar `/ready`; en modo eager no se ejecutan periódicamente las tareas de beat.
7. Compilar frontend con NEXT_PUBLIC_API_URL correcto y ejecutar los recorridos de aceptación de cada rol.

Guías base: [PUESTA_EN_MARCHA.md](PUESTA_EN_MARCHA.md), [CREDENCIALES.md](CREDENCIALES.md),
[EXTERNAL_INTEGRATIONS.md](EXTERNAL_INTEGRATIONS.md), [SECURITY_AUDIT.md](SECURITY_AUDIT.md).
No se desplegó ni actualizó una base operativa durante esta ejecución.

Para probar Redis y Celery reales sin proveedores, ejecute `python scripts/verificar_worker_local.py`.
Crea una base temporal y su propio contenedor Redis, comprueba persistencia de una tarea sin worker y limpia
el contenedor al terminar. Los logs quedan en `.artifacts/worker`; no envía mensajes externos.
