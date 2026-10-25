from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import handlers  # noqa: F401  (registra suscriptores del bus)
from .config import settings, validar_para_arranque
from .db import Base, engine
from .routers import administracion, auth, devices, edificio, panel, webhooks

validar_para_arranque()  # falla al importar si la configuración no es segura para el entorno


@asynccontextmanager
async def lifespan(_):
    if settings.entorno == "desarrollo":
        Base.metadata.create_all(engine)  # sólo desarrollo y pruebas; en producción manda Alembic
    yield


app = FastAPI(title="Sistema de Automatización para Edificios", version="0.1.0", lifespan=lifespan)
@app.middleware("http")
async def cabeceras_de_seguridad(request, call_next):
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
for r in (auth.router, devices.router, edificio.router, panel.router, administracion.router, webhooks.router):
    app.include_router(r)
app.include_router(administracion.edificios_router)


@app.get("/health")
def health():
    """Vivo: el proceso responde. No toca la base (sirve para que el orquestador sepa si reiniciar)."""
    return {"ok": True}


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
