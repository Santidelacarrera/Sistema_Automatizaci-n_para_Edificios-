from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import handlers  # noqa: F401  (registra suscriptores del bus)
from .db import Base, engine
from .routers import auth, devices, edificio, webhooks

@asynccontextmanager
async def lifespan(_):
    Base.metadata.create_all(engine)  # dev/tests; en producción usar migraciones (Alembic)
    yield


app = FastAPI(title="Sistema de Automatización para Edificios", version="0.1.0", lifespan=lifespan)
for r in (auth.router, devices.router, edificio.router, webhooks.router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"ok": True}
