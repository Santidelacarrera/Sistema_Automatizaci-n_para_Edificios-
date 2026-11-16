# Auditoría de seguridad

Fecha de revisión: 2026-11-16. No es una certificación ni un pentest externo.

## Modelo de amenazas

Actores: residente de otra unidad/edificio, conserje sin privilegios financieros, sesión robada,
lector comprometido, webhook falsificado y proveedor externo indisponible. Activos: información personal,
credenciales, fondos, documentos privados y actuadores físicos.

| Frontera | Control existente | Brecha inicial |
|---|---|---|
| Navegador/API | JWT, rol consultado en BD, HTTPS/Caddy, cabeceras | Sin MFA, recuperación ni revocación individual |
| Edificio/recurso | tenant_of y filtros | Auditar todas las rutas, especialmente finanzas y claves foráneas |
| Operación financiera | Rol admin, referencias únicas | Carreras, excedentes no persistidos, cancelación ambigua |
| Transacción/envío | Evento persistido | Efectos de red anteriores al commit |
| Lector/API | Hash de clave, fail-closed, antirrebote | Clave compartida, sin comandos individuales confirmados |
| Archivos | Sólo cartola con límite 5 MB | No existe repositorio documental privado |
| Respaldo/base | Scripts pg_dump/pg_restore | Error de expansión shell activa --clean sin intención |

Los hallazgos A01–A13 y su evidencia están en FULL_PROJECT_AUDIT. Su estado final se registrará en el informe,
incluidos los resultados de escaneo de secretos y dependencias ejecutados en esta sesión.
No se copiarán valores del `.env` al informe. Los tests deben neutralizar adaptadores externos para no emitir mensajes.

## Criterios de verificación

Pruebas de 401/403/404 por rol y recurso, intentos de acceso cruzado, repetición de solicitudes,
rollback sin envío, concurrencia real PostgreSQL, restauración en destino vacío y descarga privada.
El proxy TLS, cifrado de discos, políticas de retención y revisión jurídica necesitan verificación operativa.

## Controles implementados y comprobados

- JWT con expiración obligatoria, principal leído desde BD y versión de sesión. Logout/cambio de rol/contraseña
  revocan sesiones. TOTP cifrado, ventana limitada, código no reutilizable y bloqueo temporal; token de alta MFA
  no autoriza acceso a recursos normales.
- Conserjería no recibe importes del panel ni accede a cobranza, estados de cuenta o dashboard financiero.
- Operaciones de pago y reserva serializadas en PostgreSQL; anticipo persistente, aplicaciones por cargo,
  idempotencia, reversa con motivo y validación de desglose. Datos históricos incompletos rechazan reversa automática.
- Incidencias/documentos/soporte/asambleas autorizados por tenant y recurso. Padrón fijado, voto único por unidad,
  acta cerrada y recibo verificable dentro de la aplicación; no constituye firma legal ni prueba externa inmutable.
- Descargas documentales autorizadas. Consulta IA limitada a documentos seleccionados; citas ajenas se rechazan,
  respuestas sin fuentes se abstienen. No demuestra que cada afirmación del modelo esté sustentada por el fragmento.
- Dispositivos nuevos con clave individual almacenada como hash, rotación, nonce, expiración, confirmación y
  reautenticación. Sólo dispositivos de laboratorio aceptan órdenes de apertura desde el panel nuevo.
- Exportación CSV protege frente a fórmulas. Respuestas de IntegrityError no exponen SQL ni datos internos.
- Los límites comerciales se comprueban bajo bloqueo y se probaron con altas concurrentes. Los contratos no
  conceden permisos globales ni cambian decisiones de acceso físico.

## Análisis ejecutados

`npm audit`: cero vulnerabilidades en el árbol del lockfile examinado. `pip-audit -r backend/requirements.txt`:
cero vulnerabilidades conocidas en la resolución auditada, incluidas las dependencias añadidas. El backend
usa rangos sin lockfile: este resultado no certifica todos los entornos instalados ni futuras resoluciones.
Escáner de secretos ampliado a archivos nuevos no ignorados: cero hallazgos al cierre. Es heurístico y no
constituye prueba de ausencia de secretos. Ruff pasó los selectores de errores usados por CI.

## Riesgos y trabajo pendiente

1. No hay recuperación autoservicio de contraseñas/MFA ni códigos de emergencia; pérdida de MFA requiere
   procedimiento operativo verificado. Respaldar MFA_ENCRYPTION_KEY separada y cifrada; perderla impide descifrar TOTP.
2. JWT en sessionStorage queda expuesto si hay XSS. Falta política CSP integral, prueba dinámica de XSS y límites
   de tráfico en todos los endpoints. No hay certificación de pentest, SOC 2 o ISO 27001.
3. RBAC de cuatro roles, sin permisos delegables ni membresías múltiples. Aislamiento en aplicación, sin RLS.
4. Auditar privilegios del operador de base, cifrado en reposo, acceso al backup y rotación de secretos en infraestructura.
5. Auditar y retener texto libre de incidencias, comentarios, soporte, actas y documentos; el mecanismo de privacidad
   legado todavía no realiza exportación/supresión completa de esos dominios.
6. Los documentos dependen de DOCMIND para inspección del contenido, OCR y almacenamiento. Falta integración
   antivirus/cuarentena. El archivo se limita por tamaño/extensión; eso no valida su seguridad interna.
7. Outbox con entrega al menos una vez; Redis/worker local comprobados, falta failover y observabilidad de producción. Transacciones de envío
   conservan locks mientras esperan al proveedor, por lo que deben medirse y acotarse operacionalmente.
8. Clave compartida de los lectores legados sigue vigente; nuevo inventario no actualiza ESP32 instalados.
9. No hay pasarela ni webhook financiero nuevo; los avisos/conciliaciones manuales no sustituyen esa verificación.
10. Los planes no limitan scripts de administración ejecutados directamente en la base; el control está en las altas
    de API. Las herramientas operativas requieren acceso restringido y revisión de cuotas tras importación.
