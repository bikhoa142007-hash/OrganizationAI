from collections.abc import Iterator
from functools import lru_cache
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("Authentication requires DATABASE_URL with PostgreSQL and psycopg 3.")
    return url


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(_database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with get_session_factory()() as session:
        yield session
