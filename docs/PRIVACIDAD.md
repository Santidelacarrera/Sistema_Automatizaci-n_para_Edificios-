# Privacidad y datos personales

> **Esto no es asesoría legal.** Marca lo que hay que revisar con un abogado antes de operar.
> La Ley 21.719 (protección de datos personales, Chile) entra en vigor el **1 de diciembre de 2026**.

## Qué datos trata el sistema

| Dato | De quién | Finalidad | Base (a confirmar) | Dónde queda | Retención | Riesgo | Acción pendiente |
|---|---|---|---|---|---|---|---|
| Nombre, RUT, correo, teléfono | Residentes y administradores | Identificar, cobrar gastos comunes, avisar | Relación contractual / reglamento de copropiedad | PostgreSQL (Supabase) | Mientras sea residente; luego, plazo a fijar con abogado | **Alto** (RUT) | Definir plazo; informar al titular |
| Patente y descripción del vehículo | Residentes | Abrir el portón | Contractual | PostgreSQL | Mientras viva el vehículo en el departamento | Medio | Informar al titular |
| Código del sticker (EPC) | Residentes | Abrir el portón | Contractual | PostgreSQL | Mientras esté activo; bloqueado queda para trazabilidad | Medio | — |
| Bitácora del portón (patente o código leído, hora, resultado) | Residentes y visitas | Seguridad y resolución de reclamos | Interés legítimo (a confirmar) | PostgreSQL | **180 días** (`RETENCION_ACCESOS_DIAS`), borrado automático diario | Medio (permite reconstruir movimientos) | Aviso en el edificio |
| Nombre y patente de visitas | Visitas | Controlar acceso y cupos | Interés legítimo | PostgreSQL | **90 días** tras la visita; luego se anonimiza (`RETENCION_VISITAS_DIAS`) | Medio | Aviso a quien reserva |
| Cargos y pagos | Residentes | Contabilidad de la copropiedad | Obligación legal / contable | PostgreSQL | Plazo contable/tributario: **confirmar con contador** | Medio | Fijar plazo |
| Eventos y auditoría | Administradores | Trazabilidad de cambios | Interés legítimo | PostgreSQL | **365 días** (`RETENCION_EVENTOS_DIAS`) | Bajo | — |
| Intentos de inicio de sesión (correo, IP) | Cualquiera que intente entrar | Seguridad (bloqueo por fuerza bruta) | Interés legítimo | PostgreSQL | **30 días** | Bajo | — |
| Mensajes de WhatsApp | Residentes | Responder consultas | Consentimiento al escribir | El sistema **no guarda el texto**; sí lo guarda Evolution API y WhatsApp | Según Evolution/WhatsApp | Medio | Revisar la configuración de Evolution |
| Texto del mensaje enviado a un modelo de lenguaje | Residentes | Clasificar la intención | Consentimiento | **Sale a un tercero (Anthropic)** si se configura `ANTHROPIC_API_KEY` | Según el proveedor | **Alto** | Dejar sin clave (clasifica por palabras clave) salvo evaluación y aviso |
| Correos de cobranza y circulares | Residentes | Comunicar | Contractual | Proveedor SMTP/SES | Según el proveedor | Medio | Contrato con el proveedor |
| Imágenes de la cámara de patentes | Todos los que pasan | Leer la patente | A evaluar | **Las guarda la cámara o su grabador, no este sistema** | A definir | **Alto** | Decidir si graba, cuánto y dónde; cartel de aviso |
| Copias de seguridad | Todos | Recuperación | — | Supabase | Según el plan contratado | Medio | Confirmar plazo y región |

## Lo que ya hace el sistema
- **Borrado automático:** la tarea diaria `purgar_datos` (`backend/app/services/retencion.py`) elimina bitácora, eventos e intentos de login vencidos y **anonimiza** visitas viejas. Plazos en `.env`; `0` desactiva cada purga.
- **Acceso del titular:** `GET /edificios/{id}/residentes/{id}/datos-personales` entrega una copia legible (queda registrado en eventos).
- **Supresión:** `POST /edificios/{id}/residentes/{id}/anonimizar` borra nombre, RUT, correo, teléfono y clave, quita el acceso y bloquea sus stickers. **Conserva** cargos y pagos del departamento y los vehículos de la unidad. No se puede deshacer.
- **Rectificación:** se edita el residente desde el panel.
- **Sin datos reales en el repositorio:** las pruebas usan datos sintéticos y el escáner de secretos corre en CI.
- **El RUT** sólo se muestra al administrador, nunca en pantallas públicas.

## Lo que falta y requiere decisión humana
1. **Revisión de un abogado** de bases legales, plazos y excepciones (contabilidad, seguridad).
2. **Aviso de privacidad** para residentes y visitas (en el reglamento, en la reserva de visitas y con cartel en el portón si hay cámara).
3. **Registro de actividades de tratamiento** y, si corresponde, evaluación de impacto por el uso de cámara y bitácora de movimientos.
4. **Cámara de patentes:** definir si guarda video, por cuánto tiempo y quién accede. Hoy no está bajo el control de este sistema.
5. **Proveedores** (Supabase, SMTP/SES, Evolution/WhatsApp, Anthropic si se usa): contratos de tratamiento y dónde alojan los datos.
6. **Procedimiento y plazo** para responder solicitudes de titulares, y quién las atiende.
7. **Brechas:** definir quién avisa y cómo si se filtran datos (ver `docs/CREDENCIALES.md` para secretos filtrados).
