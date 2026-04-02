from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from core.config import get_settings
from .base import Base


def _get_engine():
    settings = get_settings()
    url = settings.resolved_database_url
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, echo=False)


engine = _get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import core.db.models  # noqa: F401 - register all models with Base
    Base.metadata.create_all(bind=engine)
