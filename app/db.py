"""Database engine, session factory and startup helpers."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(attempts: int = 30, delay_seconds: float = 1.0) -> None:
    """Wait for Postgres, then create any missing tables.

    Safe to run on every startup: ``create_all`` only creates what is missing.
    Compose already waits for the database healthcheck; the retry loop covers
    running the app outside Compose, where Postgres may still be starting.
    """
    from app import models  # noqa: F401  (registers the tables on Base.metadata)

    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            break
        except SQLAlchemyError as exc:
            if attempt == attempts:
                raise RuntimeError(
                    "the database is not reachable; is Postgres running?"
                ) from exc
            logger.warning(
                "database not ready (attempt %s/%s): %s", attempt, attempts, exc
            )
            time.sleep(delay_seconds)

    Base.metadata.create_all(bind=engine)
    logger.info("database ready, missing tables created")


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
