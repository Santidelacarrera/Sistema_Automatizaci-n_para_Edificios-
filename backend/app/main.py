from contextlib import asynccontextmanager

import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import jwt
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, TimeoutError as SATimeoutError
from fastapi.middleware.cors import CORSMiddleware

from . import handlers  # noqa: F401  (registra suscriptores del bus)
from .config import settings, validar_para_arranque
from .db import Base, SessionLocal, engine
from .services.logging_json import emitir_log_json
from .routers import administracion, auth, comunidad, devices, edificio, panel, webhooks
from .routers import asambleas, comercial, documentos, gestion, iot, mfa, operaciones, reportes
from .services.realtime import realtime_manager

validar_para_arranque()  # falla al importar si la configuración no es segura para el entorno


@asynccontextmanager
async def lifespan(_):
    if settings.entorno == "desarrollo":
        Base.metadata.create_all(engine)  # sólo desarrollo y pruebas; en producción manda Alembic
    yield


app = FastAPI(title="Sistema de Automatización para Edificios", version="0.1.0", lifespan=lifespan)
_INICIO = time.monotonic()
_METRICS = {"http_requests_total": 0}


@app.exception_handler(IntegrityError)
async def conflicto_integridad(request, exc):
    # Nunca revelar SQL, claves ni valores del registro que provocó el conflicto.
    return JSONResponse({"detail": "Conflicto con un registro existente. Recargue los datos antes de reintentar."}, status_code=409)


@app.exception_handler(SATimeoutError)
async def base_saturada(request, exc):
    """Sin conexión libre a la base: se responde rápido con 503 en vez de colgar al lector y al panel."""
    return JSONResponse({"detail": "El servidor está ocupado. Reintente en unos segundos."}, status_code=503,
                        headers={"Retry-After": "2"})


@app.exception_handler(Exception)
async def error_no_controlado(request, exc):
    """Captura centralizada de errores no controlados en JSON + tabla errores_log (24.10)."""
    from .operations_models import ErrorLog
    emitir_log_json("error", "http.error_no_controlado", metodo=request.method, ruta=request.url.path, clase=exc.__class__.__name__)
    try:
        with SessionLocal() as db:
            db.add(ErrorLog(
                ruta=str(request.url.path)[:200],
                metodo=str(request.method)[:12],
                mensaje=f"{exc.__class__.__name__}: {str(exc)[:240]}",
                detalle="",
            ))
            db.commit()
    except Exception:
        pass
    return JSONResponse({"detail": "Error interno del servidor."}, status_code=500)


@app.middleware("http")
async def cabeceras_de_seguridad(request, call_next):
    _METRICS["http_requests_total"] += 1
    emitir_log_json("info", "http.request", metodo=request.method, ruta=request.url.path)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith(("/auth", "/edificios", "/api")):
        resp.headers.setdefault("Cache-Control", "no-store")  # respuestas con datos personales: no cachear
    if settings.entorno == "produccion":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


app.add_middleware(CORSMiddleware,
                   allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, devices.router, edificio.router, panel.router, comunidad.router, administracion.router, webhooks.router):
    app.include_router(r)
    app.include_router(r, prefix="/api/v1")
app.include_router(administracion.edificios_router)
for modulo in (operaciones, asambleas, gestion, documentos, mfa, reportes, iot, comercial):
    app.include_router(modulo.router)
    app.include_router(modulo.router, prefix="/api/v1")
app.include_router(administracion.edificios_router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/v1/health")
def health():
    """Vivo: el proceso responde. No toca la base (sirve para que el orquestador sepa si reiniciar)."""
    return {"ok": True}


@app.get("/metrics")
def metrics():
    """Métricas operativas básicas del servicio (19.16)."""
    return {
        "uptime_s": round(time.monotonic() - _INICIO, 2),
        "http_requests_total": _METRICS["http_requests_total"],
        "ws_salas_activas": len(realtime_manager._salas),
    }


@app.get("/ready")
def ready():
    """Listo para recibir tráfico: la base responde y, si hay cola real, Redis también."""
    from fastapi.responses import JSONResponse
    from sqlalchemy import text
    estado = {"base": "ok"}
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - cualquier fallo de conexión significa "no listo"
        estado["base"] = "falla"
    if not settings.celery_eager:
        try:
            import redis
            redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
            estado["redis"] = "ok"
        except Exception:  # noqa: BLE001
            estado["redis"] = "falla"
    ok = all(v == "ok" for v in estado.values())
    return JSONResponse({"ok": ok, **estado}, status_code=200 if ok else 503)


@app.websocket("/ws/edificios/{edificio_id}")
async def ws_edificio(websocket: WebSocket, edificio_id: str, token: str | None = None):
    """Canal WebSocket autenticado por edificio para eventos en tiempo real."""
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        await websocket.close(code=4401)
        return
    if payload.get("rol") != "superadmin" and payload.get("edificio_id") != edificio_id:
        await websocket.close(code=4403)
        return
    await realtime_manager.conectar(edificio_id, websocket)
    try:
        await websocket.send_json({"tipo": "conectado", "edificio_id": edificio_id})
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"tipo": "pong"})
    except WebSocketDisconnect:
        realtime_manager.desconectar(edificio_id, websocket)
