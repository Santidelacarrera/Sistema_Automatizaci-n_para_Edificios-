# Manuales de Uso, Operación, IoT y Despliegue

> Guía unificada basada exclusivamente en los módulos y comandos reales del repositorio (`backend/`, `frontend/`, `firmware/`, `docker-compose.yml`).

---

## 1. Manual de Administración (`24.12`)
1. **Acceso y seguridad**: iniciar sesión en `/` con `edificio_id`, correo y contraseña (y código TOTP si MFA está habilitado). Los usuarios `admin` y `superadmin` acceden al panel completo; `superadmin` puede crear, editar, suspender o eliminar edificios vacíos (`POST/PATCH/DELETE /edificios`).
2. **Gastos comunes, multas y fondo de reserva**:
   - Prorratear gastos mensuales por coeficiente de copropiedad y aplicar intereses por mora.
   - Registrar multas (`POST /edificios/{id}/finanzas/multas`), aportes/uso de fondo de reserva (`GET/POST /edificios/{id}/finanzas/fondo-reserva`) y convenios de pago.
   - Conciliar cartolas bancarias (`POST /edificios/{id}/conciliacion`), emitir CSV compatible con Excel (`/finanzas/exportar.csv`) y PDF (`/finanzas/resumen.pdf`).
3. **Gestión comunitaria y analítica**:
   - Crear incidencias, asignar órdenes de trabajo a proveedores, programar planes de mantenimiento y revisar predicción de fallas y optimización de tareas (`GET /ia/analisis`).
   - Convocar asambleas, emitir actas PDF (`/asambleas/{id}/acta.pdf`), aprobar presupuestos por asamblea, enviar comunicados generales o por torre (`/comunicados-torre`) y publicar encuestas de satisfacción (`/encuestas`).

---

## 2. Manual de Residentes (`24.13`)
1. **Portal "Mi Depto"**: al iniciar sesión con rol `residente`, la aplicación abre `MiDepto.js` con el estado de cuenta, descarga de comprobantes PDF, historial de pagos y botón de pago en pasarela configurada (o Sandbox en desarrollo).
2. **Visitas y espacios comunes**: crear pases QR de visita, compartir enlace WhatsApp (`/visitas/{id}/whatsapp`), registrar visitas recurrentes (`/visitas-recurrentes`) y consultar disponibilidad de espacios comunes.
3. **Incidencias, asambleas y perfil**: reportar incidencias con adjuntos (`/adjuntos/incidencia/{id}`), votar en asambleas abiertas, responder encuestas (`/encuestas/{id}/responder`) y actualizar datos personales o contraseña (`/mi-perfil`).

---

## 3. Manual de Portería y Conserjería (`24.14`)
1. **Control de visitas y vehículos**: validar pases QR y patentes, registrar ingresos/salidas, consultar visitas recurrentes vigentes y adjuntar fotografías en portería **solo con autorización explícita** (`/adjuntos/porteria_visita/{id}`).
2. **Encomiendas**: registrar recepción (`POST /encomiendas`) y entrega con confirmación al residente.
3. **Reservas e incidentes**: revisar estado de garantías de reservas (`/reservas-espacio/{id}/garantia`) y reportar incidencias operativas del turno.

---

## 4. Manual de Instalación IoT en Laboratorio (`24.15`)
> Los dispositivos físicos permanecen en **modo laboratorio** (`Dispositivo.laboratorio = True`) hasta autorización explícita.
1. **Registro del controlador**: dar de alta el dispositivo en `POST /edificios/{id}/iot/dispositivos` con su punto (`porton_vehicular`, `acceso_peatonal`) y obtener su `device_api_key` (almacenado como hash SHA-256).
2. **Simulador y firmware (`firmware/`)**:
   - Para pruebas locales sin hardware: `python firmware/tools/simular_controlador.py`.
   - El controlador consulta `GET /iot/comandos/pendientes`, reporta estado vía `POST /iot/heartbeat` y confirma ejecución con nonce e idempotencia (`POST /iot/comandos/{id}/confirmar`).
3. **Lecturas offline**: cuando no hay Internet, el lector almacena eventos locales y los sincroniza por lote al recuperar conectividad manteniendo la clave de idempotencia.

---

## 5. Guía de Despliegue (`24.16`) y Uso General (`24.11`)
1. **Requisitos**: Docker + Docker Compose, PostgreSQL 16, Redis 7 y Node.js 20+ / Python 3.12+.
2. **Variables obligatorias**: definir `.env` a partir de `.env.example` con `ENTORNO=produccion`, `DATABASE_URL` PostgreSQL, `REDIS_URL`, `JWT_SECRET` robusto, `MFA_ENCRYPTION_KEY`, `CORS_ORIGINS` explícito y credenciales opcionales de pasarelas/mensajería/DOCMIND.
3. **Migraciones y arranque**:
   ```bash
   cd backend && alembic upgrade head && alembic check
   docker compose up -d --build
   ```
4. **Verificación post-despliegue**: comprobar `/health`, `/ready` (base + Redis) y ejecutar respaldos periódicos con `pg_dump -Fc`.
