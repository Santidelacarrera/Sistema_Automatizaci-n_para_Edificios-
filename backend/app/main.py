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
    return {"ok": True}
