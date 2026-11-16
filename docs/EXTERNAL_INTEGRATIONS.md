# Integraciones y requisitos externos

Revisión de documentación oficial: 2026-11-16. No se contrataron servicios ni se hicieron pagos o envíos externos.

## DOCMIND AI

Se inspeccionó el código local de `C:/Proyectos/DOCMIND_AI/backend/app/routers`. El adaptador usa Bearer API key,
`organization_id` en query y un `project_id` exclusivo por edificio. Contrato:

- `POST /api/v1/documents`: multipart, organización/proyecto, respuesta con `document_id`.
- `POST /api/v1/documents/{id}/versions`: nueva versión.
- `GET /api/v1/documents/{id}/status` y `/download`.
- `POST /api/v1/ask`: pregunta y lista explícita de IDs; respuesta con citas, página y fragmento.

Configurar DOCMIND_URL sin `/api/v1`, y DOCMIND_TENANTS como JSON de mapas por edificio con
`organization_id`, `project_id` y `api_key`. La clave debe tener sólo los permisos necesarios y alcance exclusivo
del proyecto. El servidor exige UUIDs válidos/proyectos distintos; esa comprobación no sustituye verificar
los permisos de la API key en DOCMIND. No se aceptan URLs ni organizaciones desde el navegador.
HTTPS obligatorio fuera del desarrollo local; límite 20 MiB, timeout y redirecciones desactivadas.

Pruebas HTTP con MockTransport: subida, consulta, descarga, autorización y fuentes ajenas. No se ejecutó OCR,
embeddings, versionado ni RAG con el servicio vivo. Falta validar extracción, calidad de citas, errores del worker,
restauración de archivos y latencia. La clasificación automática no se duplica en este repositorio.

## Pasarelas de pago

Las tres opciones se evaluaron por su documentación oficial. **No hay adaptador ni sandbox implementado todavía.**
Ese trabajo de software no debe describirse como un simple bloqueo por credenciales.

| Proveedor | Evidencia oficial consultada | Pendiente |
|---|---|---|
| Transbank Webpay Plus | [Documentación](https://transbankdevelopers.com/documentacion/webpay-plus), [ambiente de integración](https://transbankdevelopers.com/documentacion/como_empezar) | Crear/confirmar/consultar transacciones con configuración explícita de integración, probar retornos y conciliación; condiciones comerciales para producción. |
| Mercado Pago | [Webhooks](https://www.mercadopago.cl/developers/en/docs/checkout-pro-preferences/additional-content/notifications/webhooks) | Credenciales de prueba, firma, consulta de estado al proveedor, importes/moneda/tenant, reintentos e idempotencia. |
| Khipu | [Inicio API 3.0](https://docs.khipu.com/en/quick-start) | API key de desarrollo, creación de cobro y confirmación de notificación; verificar contrato v3 antes de reutilizar ejemplos v2. |

Registrar una transferencia manual o una cuota SaaS no equivale a ejecutar un pago de pasarela.
No hay afirmación de disponibilidad comercial, tarifa contractual, certificación o pago sandbox exitoso.

## Mensajería

Correo SMTP y el adaptador Evolution legado tienen pruebas con dobles. El outbox persiste estado y reintentos,
con broker/worker locales comprobados; falta validar red y entrega real al proveedor. Las notificaciones dentro de la aplicación sí están integradas.

Para WhatsApp oficial se revisó [WhatsApp Business Platform](https://developers.facebook.com/documentation/business-messaging/whatsapp/overview/).
Faltan adaptador oficial, cuenta/número autorizados, plantillas y validación del webhook. La existencia del adaptador
Evolution no acredita autorización de Meta. No se conectó ninguna instancia ni se envió mensaje alguno.
Push y SMS no están implementados.

## Controladores y cámaras

El simulador `firmware/tools/simular_controlador.py` usa una clave individual desde SIM_DEVICE_KEY;
registra heartbeat, consulta un comando y confirma ejecución simulada. No tiene acceso a relés.
Faltan pruebas físicas de lector/antena/Wiegand, temporización, detección real de barrera, sensores,
pérdida de red/energía, firmware y compatibilidad de cámaras. Hikvision/Dahua conservan adaptadores pendientes;
no se presentan como integraciones certificadas. El modo offline actual es fail-closed, sin caché local de permisos.

## Chile: referencias para revisión profesional

Se consultaron la [Ley 21.442](https://www.bcn.cl/leychile/Navegar?idNorma=1174663&idVersion=2026-09-23),
su [Reglamento, Decreto 7](https://www.bcn.cl/leychile/navegar?idNorma=1210089&idVersion=2025-01-09) y la
[Ley 21.719](https://www.bcn.cl/leychile/Navegar/imprimir?idNorma=1209272).
BCN indica entrada en vigencia de esta última el 1 de diciembre de 2026, posterior a la fecha de esta revisión.
No se afirma cumplimiento jurídico ni se inventan porcentajes/quórums legales.

La revisión profesional debe definir representación, padrón, quórums, firma/conservación de actas, cuentas,
retención por categoría, bases de tratamiento, consentimiento, atención de derechos y contratos de encargados.
Las consultas comunitarias implementadas no se presentan como votaciones con efectos jurídicos certificados.
La exportación/anonimización existente no cubre todavía todo el texto libre de los módulos nuevos.

## Benchmark funcional

Se revisó la [guía de la aplicación de Edifito](https://www.edifito.com/guia-practica-todo-lo-que-puedes-hacer-desde-la-app-de-edifito/)
para comparar consulta de gastos, comunicación y reservas. No se copió marca, código o diseño.
La plataforma actual no ha demostrado paridad funcional integral con ese producto.
