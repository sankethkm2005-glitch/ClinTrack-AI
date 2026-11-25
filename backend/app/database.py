"""SQLite database engine, session management, and health check helper."""

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


def _build_engine():
    db_url = settings.resolved_database_url
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine_instance = create_engine(
        db_url,
        connect_args=connect_args,
        future=True,
    )

    if db_url.startswith("sqlite"):
        @event.listens_for(engine_instance, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine_instance


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> bool:
    """Verify database connectivity without exposing internal exceptions."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
