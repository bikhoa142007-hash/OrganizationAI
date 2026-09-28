import pytest

from src.backend.db.session import _database_url
from src.backend.seed_auth import main


def test_runtime_auth_database_rejects_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")

    with pytest.raises(RuntimeError, match="requires DATABASE_URL with PostgreSQL"):
        _database_url()


def test_local_auth_seed_requires_explicit_enable_flag(monkeypatch):
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.delenv("AUTH_SEED_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_SEED_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="AUTH_SEED_ENABLED=true"):
        main()
