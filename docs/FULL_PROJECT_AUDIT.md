# Auditoría integral — 16 de noviembre de 2026

## Alcance y método

Inventario inicial: 164 archivos versionados; árbol limpio al comenzar. Revisión de modelos, routers,
servicios, frontend, migraciones 0001–0007, pruebas, firmware, adaptadores LPR, scripts, CI y documentación.
No se usó el `.env` para conectarse a la base operativa ni se inspeccionaron valores secretos.
Las afirmaciones históricas de README/VERIFICACION no son resultados de esta ejecución.
La suite inicial ejecutada sobre SQLite temporal dio 269 aprobadas y 2 omitidas. Resultados posteriores en FINAL_COMPLETION_REPORT.

## Arquitectura encontrada

Monolito modular FastAPI/SQLAlchemy, PostgreSQL en producción, SQLite en desarrollo, siete migraciones;
Next.js 15/React 19; Celery/Redis; firmware MicroPython y traductor LPR independiente. El README aún
describe Next 14/React 18 en su tabla inicial. La interfaz conserva un modo demo explícito en memoria.
No hay API de DOCMIND en este repositorio. Existe un proyecto local vecino `C:/Proyectos/DOCMIND_AI`,
que se examinó para identificar su contrato de organizaciones, proyectos, documentos y preguntas, sin modificarlo.

## Hallazgos reproducibles por inspección

| ID | Prioridad | Evidencia | Consecuencia |
|---|---|---|---|
| A01 | Alta | `scripts/restaurar_db.sh`: `${SOBRE:+--clean --if-exists}` con SOBRE=0 | Activa limpieza incluso sin solicitar sobrescritura. |
| A02 | Alta | `routers/edificio.py`: comprobar solapamiento sin bloqueo | Reservas simultáneas pueden ocupar el mismo espacio. |
| A03 | Alta | Cancelar reserva busca cargo por concepto/mes | Dos reservas del mismo mes pueden anular el cargo incorrecto. |
| A04 | Alta | `services/reconciliation.py`: `_aplicar` devuelve excedente sin persistirlo | Pago anticipado se pierde como saldo utilizable. |
| A05 | Alta | Pagos/gastos/intereses: comprobar duplicado sin bloqueo transaccional | Carreras financieras, doble aplicación o error 500. |
| A06 | Alta | `handlers.py` envía WhatsApp antes de commit | Puede comunicar una operación que luego se revierte; envío sin outbox. |
| A07 | Alta | `/mi-depto`, `/deuda`, `/panel` permiten finanzas a conserjes | Permisos financieros inconsistentes entre rutas. |
| A08 | Media | `frontend/app/page.js` siempre pide `/cobranza` | Login de conserje queda atrapado cargando por 403. |
| A09 | Media | `verify_password` no captura hex inválido | Hash malformado produce 500. JWT sin revocación de sesiones. |
| A10 | Alta | Clave de lector compartida por edificio | No hay identidad, revocación ni confirmación por dispositivo individual. |
| A11 | Alta | `ConversacionWA` y `identificar_residente` por teléfono global | Ambigüedad si una persona pertenece a varias comunidades. |
| A12 | Media | Consultas con `min(limit, 200)` sin mínimo | Límites negativos pueden quitar el límite en SQLite. |
| A13 | Alta | Sin MFA/recuperación segura | Autenticación privilegiada incompleta. |

## Cobertura funcional inicial

Existen gastos prorrateados, interés simple, cartolas CSV, avisos de transferencia, QR, UHF/RFID,
reservas con tarifas, comunicados, encomiendas, residentes, reglas, retención y exportación personal.
No equivalen a contabilidad completa, pasarela de pagos, inventario de dispositivos o plataforma SaaS comercial.
No existen mantenimiento/órdenes de trabajo, asambleas/votos, documentos/versionado/RAG, contratos,
suscripciones/soporte ni un motor general de automatizaciones. Se registran como pendientes reales.

## Dependencias externas

Hardware ESP32/cámaras, credenciales sandbox de pagos, SMTP, WhatsApp oficial, DOCMIND desplegado,
revisión jurídica y decisiones comerciales. No se realizarán pagos, aperturas físicas ni despliegues.
Docker local está disponible: permite pruebas aisladas de PostgreSQL/Redis sin servicios contratados.

## Referencias verificadas

Benchmark funcional: [portal de residentes Edifito](https://www.edifito.com/guia-practica-todo-lo-que-puedes-hacer-desde-la-app-de-edifito/).
Se usa como comparación de consultas, pagos y reservas; no se copia diseño ni código.
Fuentes legales y proveedores: [EXTERNAL_INTEGRATIONS.md](EXTERNAL_INTEGRATIONS.md).

## Seguimiento de correcciones

A01–A09 y A11–A12 tienen cambios y pruebas de regresión: restauración sin limpieza implícita,
bloqueo transaccional PostgreSQL, relación reserva/cargo, anticipos persistidos, ledger de aplicaciones de pago,
outbox, permisos de conserjería, carga del portal, validación de hashes/JWT y rechazo de teléfonos ambiguos.
A10 cuenta con inventario y claves individuales en el protocolo nuevo de laboratorio; el lector legado mantiene
su clave por edificio y no se migró hardware. A13 cuenta con MFA privilegiado; la recuperación autónoma sigue pendiente.

La matriz actual reemplaza el inventario inicial como referencia de estado. Se agregaron cuatro migraciones
0008–0011 (0008 agrupa operaciones y finanzas), API y pantallas conectadas.
Las nuevas pruebas de navegador detectaron y corrigieron mezcla de datos entre pestañas, etiqueta ambigua
del estado de incidencia, desaparición del mensaje de guardado y contraste insuficiente en móvil.
Los contratos comerciales tienen límites comprobados bajo concurrencia y no modifican la seguridad física.
