"""Validate a PostgreSQL acceptance target before migrations or test writes."""
from __future__ import annotations

from collections.abc import Mapping
import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url


_REQUIRED_TEST_USERS = frozenset({"oa_test", "organizationai_test"})
_ALLOWED_TEST_HOSTS = frozenset({"127.0.0.1", "localhost", "postgres"})
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,48}$")


def _rejected_target() -> RuntimeError:
    return RuntimeError(
        "PostgreSQL test target rejected; expected a runner-provisioned, uniquely "
        "named temporary database. No database writes were attempted."
    )


def _parse_runner_target(environment: Mapping[str, str]) -> tuple[URL, str, str]:
    raw_url = environment.get("DATABASE_URL", "").strip()
    database = environment.get("POSTGRES_TEST_DATABASE", "").strip()
    username = environment.get("POSTGRES_TEST_USER", "").strip()
    run_id = environment.get("POSTGRES_TEST_RUN_ID", "").strip()

    if (
        not _RUN_ID_PATTERN.fullmatch(run_id)
        or not database.startswith("organizationai_test_")
        or not database.endswith(run_id)
        or username not in _REQUIRED_TEST_USERS
    ):
        raise _rejected_target()

    try:
        url = make_url(raw_url)
        valid = (
            url.drivername == "postgresql+psycopg"
            and url.host in _ALLOWED_TEST_HOSTS
            and url.port is not None
            and 1 <= url.port <= 65535
            and url.database == database
            and url.username == username
            and bool(url.password)
        )
    except Exception:
        raise _rejected_target() from None

    if not valid:
        raise _rejected_target()
    return url, database, username


def verify_runner_provisioned_database(environment: Mapping[str, str]) -> URL:
    """Read-only verify that DATABASE_URL matches the temporary runner target.

    The URL shape and run identity are checked before connecting. A read-only
    PostgreSQL identity query then confirms the server's current database and role.
    No URL or driver exception text is included in failures.
    """
    url, expected_database, expected_user = _parse_runner_target(environment)
    engine = None
    try:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"options": "-c default_transaction_read_only=on"},
        )
        with engine.connect() as connection:
            actual_database, actual_user = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()
    except Exception as error:
        raise RuntimeError(
            "PostgreSQL test target identity could not be verified "
            f"({type(error).__name__}); no database writes were attempted."
        ) from None
    finally:
        if engine is not None:
            engine.dispose()

    if actual_database != expected_database or actual_user != expected_user:
        raise RuntimeError(
            "Connected PostgreSQL identity did not match the runner-provisioned "
            "temporary target. No database writes were attempted."
        )
    return url
