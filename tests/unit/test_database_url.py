import pytest

from src.backend.db.session import normalize_database_url


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://"])
def test_database_url_normalizes_render_postgres_connection_strings(scheme):
    url = f"{scheme}stage_user:stage_password@internal-host:5432/organizationai"

    assert normalize_database_url(url) == (
        "postgresql+psycopg://stage_user:stage_password@internal-host:5432/organizationai"
    )


def test_database_url_accepts_only_postgresql_unless_migration_tests_opt_in():
    sqlite_url = "sqlite+pysqlite:///isolated-test.db"

    with pytest.raises(RuntimeError, match="PostgreSQL"):
        normalize_database_url(sqlite_url)

    assert normalize_database_url(sqlite_url, allow_sqlite_test=True) == sqlite_url
