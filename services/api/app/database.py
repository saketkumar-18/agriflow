"""Database engine + session factory. SQLite default, PostgreSQL via DATABASE_URL."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # WAL + FK enforcement
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

if settings.database_url.startswith("postgres") and settings.pg_schema:
    @event.listens_for(engine, "connect")
    def _pg_search_path(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        safe = settings.pg_schema.replace("'", "''")
        cur.execute("CREATE SCHEMA IF NOT EXISTS " + safe)
        cur.execute("SET search_path TO " + safe + ", public")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
