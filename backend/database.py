"""SQLite engine, session factory and declarative Base.

Paths in the .env file are relative to the project root, so always launch the
app from the repository root (``uv run uvicorn backend.main:app``).
"""

import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./campus_lost_found.db")

# check_same_thread=False: FastAPI serves requests from a thread pool, and a
# SQLite connection is otherwise pinned to the thread that created it.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create every table declared on ``Base``. Called on app startup."""
    from backend import models  # noqa: F401  — registers the mappers

    Base.metadata.create_all(bind=engine)
