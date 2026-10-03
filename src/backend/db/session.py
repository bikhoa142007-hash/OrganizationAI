from collections.abc import Iterator
from functools import lru_cache
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def normalize_database_url(url: str, *, allow_sqlite_test: bool = False) -> str:
    url = url.strip()
    if url.startswith(("postgres://", "postgresql://")):
        return "postgresql+psycopg://" + url.split("://", 1)[1]
    if url.startswith("postgresql+psycopg://"):
        return url
    if allow_sqlite_test and url.startswith("sqlite+"):
        return url
    raise RuntimeError("Authentication requires DATABASE_URL with PostgreSQL and psycopg 3.")


def _database_url() -> str:
    return normalize_database_url(os.getenv("DATABASE_URL", ""))


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(_database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with get_session_factory()() as session:
        yield session
