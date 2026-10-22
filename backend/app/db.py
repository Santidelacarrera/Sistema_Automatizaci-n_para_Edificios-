from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

_sqlite = settings.database_url.startswith("sqlite")
# Base remota (p. ej. Supabase): pool_pre_ping descarta conexiones caídas y el timeout evita colgar la API.
_args = {"check_same_thread": False} if _sqlite else {"connect_timeout": 10}
_pool = {} if _sqlite else {"pool_size": settings.db_pool_size, "max_overflow": settings.db_max_overflow}
engine = create_engine(settings.database_url, connect_args=_args, pool_pre_ping=True, pool_recycle=300, **_pool)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
