from contextlib import asynccontextmanager

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import handlers  # noqa: F401  (registra suscriptores del bus)
from .db import Base, engine
from .routers import auth, devices, edificio, panel, webhooks

@asynccontextmanager
async def lifespan(_):
    Base.metadata.create_all(engine)  # dev/tests; en producción usar migraciones (Alembic)
    yield


app = FastAPI(title="Sistema de Automatización para Edificios", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, devices.router, edificio.router, panel.router, webhooks.router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"ok": True}
