"""Fail-closed Windows live cutover runner for the pinned Auth migrations.

The companion PowerShell entry point validates the chosen interpreter and
isolates its process environment. This module owns the hidden URL prompt,
read-only preflight, confirmation gate, Alembic upgrade, and post-checks.
"""
from __future__ import annotations

import contextlib
import getpass
import hashlib
import io
from importlib.metadata import version as package_version
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url


PINNED_SHA = "0d17887cf1d6a6571fc8b02b74706343e2555e19"
DATABASE_NAME = "organizationai_db"
SCHEMA_NAME = "public"
START_REVISION = "20261003_07"
TARGET_REVISION = "20261011_12"
EXPECTED_POSTGRES_MAJOR = 16
CONNECT_TIMEOUT_SECONDS = 10
STATEMENT_TIMEOUT_MS = 60_000
LOCK_TIMEOUT_MS = 10_000
BACKUP_RECEIPT_NAME = "auth-migration-rehearsal.json"
MAX_FINAL_BACKUP_AGE_SECONDS = 12 * 60 * 60
MAX_FINAL_BACKUP_FUTURE_SKEW_SECONDS = 5 * 60
REQUIRED_START_TABLES = ("alembic_version", "users", "roles", "user_roles")
PINNED_ARCHIVE_PATHS = ("alembic.ini", "alembic", "src/backend/db", "requirements.txt")
SYNTHETIC_CLIENT_IMAGE = (
    "python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1"
)
NEW_EMPTY_TABLES = (
    "auth_management_tokens",
    "admin_audit_events",
    "auth_workflow_notifications",
    "auth_workflow_sla_configurations",
    "auth_workflow_sla_rounds",
)
PROCESS_ENVIRONMENT_NAMES = (
    "DATABASE_URL", "AUTH_ALLOW_SQLITE_MIGRATION_TESTS", "PYTHONPATH",
    "PGHOST", "PGHOSTADDR", "PGPORT", "PGUSER", "PGDATABASE", "PGPASSWORD",
    "PGPASSFILE", "PGSSLMODE", "PGSSLCERT", "PGSSLKEY", "PGSSLROOTCERT",
    "PGSSLCRL", "PGSSLCRLDIR", "PGSSLNEGOTIATION", "PGGSSENCMODE",
    "PGREQUIRESSL", "PGCHANNELBINDING", "PGAPPNAME", "PGCONNECT_TIMEOUT",
    "PGOPTIONS", "PGSERVICE", "PGSERVICEFILE", "PGTARGETSESSIONATTRS",
)


class SafeRunnerFailure(RuntimeError):
    """A controlled failure containing only a non-secret diagnostic code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def safe_exception_fields(exc: BaseException) -> dict[str, str]:
    """Return only allowlisted exception metadata; never include its message."""
    name = type(exc).__name__
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", name):
        name = "Exception"
    original = getattr(exc, "orig", None)
    sqlstate = (
        getattr(original, "sqlstate", None)
        or getattr(original, "pgcode", None)
        or getattr(exc, "sqlstate", None)
        or getattr(exc, "pgcode", None)
    )
    if not isinstance(sqlstate, str) or not re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
        sqlstate = "unavailable"
    original_type = type(original).__name__ if original is not None else "unavailable"
    cause = getattr(original, "__cause__", None) if original is not None else None
    cause_type = type(cause).__name__ if cause is not None else "unavailable"
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", original_type):
        original_type = "unavailable"
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", cause_type):
        cause_type = "unavailable"
    return {
        "exception_type": name,
        "sqlstate": sqlstate,
        "driver_exception_type": original_type,
        "cause_type": cause_type,
    }


def build_secure_url(raw_url: str) -> URL:
    """Normalize a PostgreSQL URL and force TLS plus finite driver timeouts."""
    if not isinstance(raw_url, str) or not raw_url.strip() or len(raw_url) > 8192:
        raise SafeRunnerFailure("POSTGRES_URL_INVALID")
    try:
        parsed = make_url(raw_url.strip())
    except Exception as exc:
        raise SafeRunnerFailure("POSTGRES_URL_INVALID") from exc
    if parsed.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise SafeRunnerFailure("POSTGRESQL_URL_REQUIRED")
    if not parsed.host or not parsed.username or not parsed.database:
        raise SafeRunnerFailure("POSTGRESQL_URL_INCOMPLETE")
    query = {
        key: value
        for key, value in parsed.query.items()
        if key.lower() not in {"sslmode", "connect_timeout", "options", "application_name"}
    }
    query.update({
        "sslmode": "require",
        "connect_timeout": str(CONNECT_TIMEOUT_SECONDS),
        "options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS} -c lock_timeout={LOCK_TIMEOUT_MS}",
        "application_name": "organizationai-auth-live-cutover",
    })
    return parsed.set(drivername="postgresql+psycopg", query=query)


def verify_rehearsal_receipt(
    receipt_path: str | Path,
    archive_path: str | Path,
    expected_hash: str,
    *,
    expected_database: str,
    expected_pg_major: int,
    source_sha: str,
    start_revision: str,
    target_revision: str,
) -> dict[str, Any]:
    """Verify the exact private backup bytes and successful rehearsal receipt."""
    receipt_file = Path(receipt_path)
    archive_file = Path(archive_path)
    try:
        if (not re.fullmatch(r"[A-Fa-f0-9]{64}", expected_hash)
                or not archive_file.is_file() or archive_file.is_symlink()
                or archive_file.stat().st_size <= 0
                or receipt_file.name != BACKUP_RECEIPT_NAME
                or receipt_file.parent.resolve() != archive_file.parent.resolve()):
            raise ValueError
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        actual_hash = hashlib.sha256()
        with archive_file.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                actual_hash.update(block)
        digest = actual_hash.hexdigest().upper()
        sidecar_path = archive_file.with_name(archive_file.name + ".sha256")
        if sidecar_path.is_symlink():
            raise ValueError
        sidecar = sidecar_path.read_text(encoding="ascii").strip()
        if sidecar != f"{digest}  {archive_file.name}":
            raise ValueError
        expected = {
            "result": "PASS",
            "cleanup_complete": True,
            "writers_paused": True,
            "source_sha": source_sha,
            "database": expected_database,
            "schema": SCHEMA_NAME,
            "start_revision": start_revision,
            "target_revision": target_revision,
            "postgres_major": expected_pg_major,
            "backup_filename": archive_file.name,
            "backup_sha256": digest,
            "data_preservation_verified": True,
        }
        if not isinstance(receipt, dict) or any(receipt.get(k) != v for k, v in expected.items()):
            raise ValueError
        if receipt.get("cleanup_complete") is not True or receipt.get("writers_paused") is not True:
            raise ValueError
        if receipt.get("receipt_version") != 1:
            raise ValueError
        datetime.fromisoformat(str(receipt.get("created_utc", "")))
        if expected_hash.upper() != digest:
            raise ValueError
        if not re.fullmatch(r"[0-9a-f]{8}T[0-9]{6}Z-[0-9a-f]{20}", str(receipt.get("run_id", ""))):
            raise ValueError
        return receipt
    except Exception as exc:
        raise SafeRunnerFailure("REHEARSAL_RECEIPT_INVALID") from exc


def validate_final_backup_freshness(
    receipt: dict[str, Any], *, archive_path: str | Path | None = None,
    now: datetime | None = None,
) -> None:
    """Reject rehearsal receipts too old to serve as the final cutover backup."""
    try:
        created = datetime.fromisoformat(str(receipt["created_utc"]))
        if created.tzinfo is None or created.utcoffset() is None:
            raise ValueError
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError
        age = (current.astimezone(timezone.utc) - created.astimezone(timezone.utc)).total_seconds()
        if (age < -MAX_FINAL_BACKUP_FUTURE_SKEW_SECONDS
                or age > MAX_FINAL_BACKUP_AGE_SECONDS):
            raise SafeRunnerFailure("FINAL_BACKUP_RECEIPT_STALE")
        if archive_path is not None:
            archive = Path(archive_path)
            if not archive.is_file() or archive.is_symlink():
                raise SafeRunnerFailure("FINAL_BACKUP_ARCHIVE_INVALID")
            archive_age = current.astimezone(timezone.utc).timestamp() - archive.stat().st_mtime
            if (archive_age < -MAX_FINAL_BACKUP_FUTURE_SKEW_SECONDS
                    or archive_age > MAX_FINAL_BACKUP_AGE_SECONDS
                    or archive.stat().st_mtime - created.timestamp() > MAX_FINAL_BACKUP_FUTURE_SKEW_SECONDS):
                raise SafeRunnerFailure("FINAL_BACKUP_ARCHIVE_STALE")
    except SafeRunnerFailure:
        raise
    except Exception as exc:
        raise SafeRunnerFailure("FINAL_BACKUP_RECEIPT_TIMESTAMP_INVALID") from exc


def _private_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
    return base / "OrganizationAI" / "AuthLiveMigration"


def _protect_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False)
    if os.name != "nt":
        path.chmod(0o700)
        return
    whoami = shutil.which("whoami.exe") or shutil.which("whoami")
    icacls = shutil.which("icacls.exe") or shutil.which("icacls")
    if not whoami or not icacls:
        raise SafeRunnerFailure("PRIVATE_DIRECTORY_ACL_TOOLS_UNAVAILABLE")
    identity_result = subprocess.run(
        [whoami], capture_output=True, text=True, timeout=10, check=False,
    )
    identity = identity_result.stdout.strip()
    if identity_result.returncode != 0 or not re.fullmatch(r"[^\r\n]{1,256}", identity):
        raise SafeRunnerFailure("PRIVATE_DIRECTORY_IDENTITY_FAILED")
    grants = [
        f"{identity}:(OI)(CI)F",
        "SYSTEM:(OI)(CI)F",
    ]
    result = subprocess.run(
        [icacls, str(path), "/inheritance:r", "/grant:r", *grants, "/c"],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if result.returncode != 0:
        raise SafeRunnerFailure("PRIVATE_DIRECTORY_ACL_FAILED")


def _prepare_pinned_source(repository_root: Path, run_root: Path) -> Path:
    return _prepare_source_archive(repository_root, run_root, PINNED_SHA)


def _prepare_source_archive(
    repository_root: Path,
    run_root: Path,
    source_sha: str,
    *,
    git_executable: str | None = None,
    run_process=None,
) -> Path:
    """Archive one exact commit without checking it out or changing the worktree.

    Production only calls this through ``_prepare_pinned_source`` with the
    reviewed constant above. The explicit SHA/process seam keeps the archive
    and shallow-fetch behavior testable using temporary local Git repositories.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise SafeRunnerFailure("PINNED_SOURCE_SHA_INVALID")
    run_process = run_process or subprocess.run
    git = git_executable or shutil.which("git.exe") or shutil.which("git")
    if not git:
        raise SafeRunnerFailure("PINNED_SOURCE_GIT_UNAVAILABLE")
    resolve_args = [git, "rev-parse", "--verify", f"{source_sha}^{{commit}}"]
    resolved = run_process(
        resolve_args,
        capture_output=True, text=True, timeout=20, check=False, cwd=repository_root,
    )
    if resolved.returncode != 0 or resolved.stdout.strip().lower() != source_sha:
        fetch_args = [
            git,
            "fetch",
            "--no-tags",
            "--depth=1",
            "--no-write-fetch-head",
            "origin",
            source_sha,
        ]
        try:
            fetched = run_process(
                fetch_args,
                capture_output=True, text=True, timeout=90, check=False, cwd=repository_root,
            )
        except subprocess.TimeoutExpired as exc:
            raise SafeRunnerFailure("PINNED_SOURCE_FETCH_TIMEOUT") from exc
        except OSError as exc:
            raise SafeRunnerFailure("PINNED_SOURCE_FETCH_FAILED") from exc
        if fetched.returncode != 0:
            raise SafeRunnerFailure("PINNED_SOURCE_FETCH_FAILED")
        resolved = run_process(
            resolve_args,
            capture_output=True, text=True, timeout=20, check=False, cwd=repository_root,
        )
    if resolved.returncode != 0 or resolved.stdout.strip().lower() != source_sha:
        raise SafeRunnerFailure("PINNED_SOURCE_SHA_UNAVAILABLE")
    archive_path = run_root / "pinned-source.tar"
    with archive_path.open("wb") as archive_stream:
        archived = run_process(
            [git, "archive", "--format=tar", source_sha, *PINNED_ARCHIVE_PATHS],
            stdout=archive_stream, stderr=subprocess.DEVNULL, timeout=120, check=False,
            cwd=repository_root,
        )
    if archived.returncode != 0 or archive_path.stat().st_size == 0:
        raise SafeRunnerFailure("PINNED_SOURCE_ARCHIVE_FAILED")
    source_root = run_root / "source"
    source_root.mkdir()
    try:
        with tarfile.open(archive_path, "r:") as archive:
            archive.extractall(source_root, filter="data")
    except Exception as exc:
        raise SafeRunnerFailure("PINNED_SOURCE_ARCHIVE_INVALID") from exc
    finally:
        archive_path.unlink(missing_ok=True)
    if not (source_root / "alembic.ini").is_file():
        raise SafeRunnerFailure("PINNED_SOURCE_CONFIGURATION_MISSING")
    if not (source_root / "alembic" / "versions" / "20261011_12_approval_round_sla.py").is_file():
        raise SafeRunnerFailure("PINNED_TARGET_MIGRATION_MISSING")
    _validate_pinned_migration_chain(source_root)
    return source_root


def _validate_pinned_migration_chain(source_root: Path) -> None:
    old_sys_path = list(sys.path)
    try:
        sys.path.insert(0, str(source_root))
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        script = ScriptDirectory.from_config(_alembic_config(source_root))
        if script.get_heads() != [TARGET_REVISION]:
            raise SafeRunnerFailure("PINNED_ALEMBIC_HEAD_MISMATCH")
        current = script.get_revision(TARGET_REVISION)
        seen = set()
        chain = []
        while current is not None and current.revision not in seen:
            seen.add(current.revision)
            chain.append(current.revision)
            parent = current.down_revision
            if current.revision == START_REVISION:
                break
            if isinstance(parent, tuple) or parent is None:
                raise SafeRunnerFailure("PINNED_MIGRATION_CHAIN_NOT_LINEAR")
            current = script.get_revision(parent)
        if not chain or chain[-1] != START_REVISION:
            raise SafeRunnerFailure("PINNED_MIGRATION_CHAIN_MISMATCH")
    except SafeRunnerFailure:
        raise
    except Exception as exc:
        raise _failure_from_exception("PINNED_MIGRATION_GRAPH_INVALID", "pinned_source_validation", exc)
    finally:
        sys.path[:] = old_sys_path


def _alembic_config(source_root: Path):
    from alembic.config import Config

    config = Config(str(source_root / "alembic.ini"))
    config.set_main_option("script_location", str(source_root / "alembic"))
    return config


def _engine(url: URL):
    return create_engine(
        url,
        connect_args={
            "sslmode": "require",
            "connect_timeout": CONNECT_TIMEOUT_SECONDS,
            "options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS} -c lock_timeout={LOCK_TIMEOUT_MS}",
        },
        pool_pre_ping=False,
        echo=False,
        hide_parameters=True,
    )


def _read_revision(connection) -> tuple[str, int]:
    schema = connection.dialect.identifier_preparer.quote_schema(SCHEMA_NAME)
    value, count = connection.execute(text(
        f"SELECT COALESCE(string_agg(version_num, ',' ORDER BY version_num), ''), count(*) "
        f"FROM {schema}.alembic_version"
    )).one()
    return str(value), int(count)


def _schema_relation(connection, table: str) -> str | None:
    return connection.execute(text("""
        SELECT n.nspname
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE c.oid = pg_catalog.to_regclass(CAST(:table_name AS text))
          AND c.relkind IN ('r', 'p')
    """), {"table_name": table}).scalar_one_or_none()


def _fingerprint_table(connection, table_name: str, columns: list[str], primary_key: list[str]) -> tuple[int, str]:
    if not primary_key:
        raise SafeRunnerFailure("BASELINE_TABLE_WITHOUT_PRIMARY_KEY")
    preparer = connection.dialect.identifier_preparer
    qualified = f"{preparer.quote_schema(SCHEMA_NAME)}.{preparer.quote(table_name)}"
    selected = ", ".join(preparer.quote(name) for name in columns)
    ordering = ", ".join(preparer.quote(name) for name in primary_key)
    result = connection.execution_options(stream_results=True).execute(
        text(f"SELECT {selected} FROM {qualified} ORDER BY {ordering}")
    )
    digest = hashlib.sha256()
    row_count = 0
    for row in result:
        encoded = json.dumps(
            list(row), sort_keys=True, default=str, ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(encoded)
        digest.update(b"\n")
        row_count += 1
    return row_count, digest.hexdigest()


def _preflight_and_snapshot(url: URL) -> tuple[dict[str, Any], dict[str, Any]]:
    engine = _engine(url)
    phase = "connect"
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                phase = "identity"
                tls = connection.execute(text("""
                    SELECT ssl FROM pg_catalog.pg_stat_ssl WHERE pid = pg_backend_pid()
                """)).scalar_one_or_none()
                if tls is not True:
                    raise SafeRunnerFailure("TLS_NOT_CONFIRMED_ON_PREFLIGHT_CONNECTION")
                database, current_schema, search_schemas, version_number = connection.execute(text("""
                    SELECT current_database(), current_schema(), current_schemas(false),
                           current_setting('server_version_num')
                """)).one()
                major = int(version_number) // 10000
                if database != DATABASE_NAME or current_schema != SCHEMA_NAME:
                    raise SafeRunnerFailure("DATABASE_OR_SCHEMA_MISMATCH")
                if SCHEMA_NAME not in search_schemas:
                    raise SafeRunnerFailure("EXPECTED_SCHEMA_NOT_IN_SEARCH_PATH")
                if major != EXPECTED_POSTGRES_MAJOR:
                    raise SafeRunnerFailure("POSTGRES_MAJOR_MISMATCH")
                resolved = {}
                for table in REQUIRED_START_TABLES:
                    schema = _schema_relation(connection, table)
                    if schema != SCHEMA_NAME:
                        raise SafeRunnerFailure("AUTH_TABLE_SEARCH_PATH_RESOLUTION_MISMATCH")
                    resolved[table] = schema
                revision, revision_count = _read_revision(connection)
                if revision_count != 1 or revision != START_REVISION:
                    raise SafeRunnerFailure("START_REVISION_MISMATCH")

                phase = "schema_snapshot"
                inspector = inspect(connection)
                tables = sorted(inspector.get_table_names(schema=SCHEMA_NAME))
                snapshots: dict[str, Any] = {}
                rows_total = 0
                for table in tables:
                    if table == "alembic_version":
                        continue
                    relation = _schema_relation(connection, table)
                    if relation != SCHEMA_NAME:
                        raise SafeRunnerFailure("TABLE_SEARCH_PATH_RESOLUTION_MISMATCH")
                    columns = [col["name"] for col in inspector.get_columns(table, schema=SCHEMA_NAME)]
                    primary_key = inspector.get_pk_constraint(table, schema=SCHEMA_NAME).get("constrained_columns") or []
                    count, fingerprint = _fingerprint_table(connection, table, columns, list(primary_key))
                    snapshots[table] = {
                        "columns": columns,
                        "primary_key": list(primary_key),
                        "row_count": count,
                        "sha256": fingerprint,
                    }
                    rows_total += count
                identity = {
                    "database": str(database),
                    "schema": str(current_schema),
                    "revision": revision,
                    "postgres_major": major,
                    "tls": True,
                    "resolved_auth_tables": resolved,
                    "baseline_table_count": len(snapshots),
                    "baseline_row_count": rows_total,
                }
            finally:
                if transaction.is_active:
                    transaction.rollback()
        return identity, snapshots
    except SafeRunnerFailure:
        raise
    except Exception as exc:
        raise _failure_from_exception("READ_ONLY_PREFLIGHT_FAILED", phase, exc)
    finally:
        engine.dispose()


def _failure_from_exception(code: str, phase: str, exc: BaseException) -> "PhaseFailure":
    fields = safe_exception_fields(exc)
    return PhaseFailure(
        code, phase, fields["exception_type"], fields["sqlstate"],
        fields["driver_exception_type"], fields["cause_type"],
        _safe_reason_code(exc),
    )


def _safe_reason_code(exc: BaseException) -> str:
    """Classify common driver failures without retaining or emitting their text."""
    parts = list(getattr(exc, "args", ()))
    original = getattr(exc, "orig", None)
    if original is not None:
        parts.extend(getattr(original, "args", ()))
    message = " ".join(part.lower() for part in parts if isinstance(part, str))
    categories = (
        ("password authentication failed", "DATABASE_AUTHENTICATION_REJECTED"),
        ("no password supplied", "DATABASE_AUTHENTICATION_REJECTED"),
        ("connection refused", "CONNECTION_REFUSED"),
        ("timeout expired", "CONNECT_TIMEOUT"),
        ("could not translate host", "DNS_RESOLUTION_FAILED"),
        ("ssl", "TLS_HANDSHAKE_FAILED"),
        ("server closed the connection", "SERVER_CLOSED_CONNECTION"),
        ("database \"", "DATABASE_SELECTION_FAILED"),
    )
    for marker, code in categories:
        if marker in message:
            return code
    return "UNCLASSIFIED_DRIVER_FAILURE"


class PhaseFailure(SafeRunnerFailure):
    def __init__(
        self, code: str, phase: str, exception_type: str, sqlstate: str,
        driver_type: str = "unavailable", cause_type: str = "unavailable",
        reason_code: str = "UNCLASSIFIED_DRIVER_FAILURE",
    ):
        super().__init__(code)
        self.phase = phase
        self.exception_type = exception_type
        self.sqlstate = sqlstate
        self.driver_type = driver_type
        self.cause_type = cause_type
        self.reason_code = reason_code


def _verify_model_schema(connection, source_root: Path) -> None:
    sys.path.insert(0, str(source_root))
    try:
        from src.backend.db.base import Base
        from src.backend.db import models  # noqa: F401
    except Exception as exc:
        raise _failure_from_exception("PINNED_MODEL_IMPORT_FAILED", "schema_check", exc)
    inspector = inspect(connection)
    actual_tables = set(inspector.get_table_names(schema=SCHEMA_NAME))
    missing_tables = []
    missing_columns = []
    for table in Base.metadata.sorted_tables:
        schema = table.schema or SCHEMA_NAME
        if schema != SCHEMA_NAME or table.name not in actual_tables:
            missing_tables.append(table.name)
            continue
        actual_columns = {col["name"] for col in inspector.get_columns(table.name, schema=SCHEMA_NAME)}
        if not {column.name for column in table.columns} <= actual_columns:
            missing_columns.append(table.name)
    if missing_tables or missing_columns:
        raise SafeRunnerFailure("POST_MIGRATION_ORM_SCHEMA_MISMATCH")


def _verify_pinned_indexes(connection) -> None:
    expected = (
        ("auth_management_tokens", "ix_auth_management_tokens_user_purpose", ["user_id", "purpose", "consumed_at"]),
        ("admin_audit_events", "ix_admin_audit_events_created_at", ["created_at"]),
    )
    query = text("""
        SELECT idx.indisvalid, idx.indisready, idx.indisunique,
               idx.indpred IS NULL, idx.indexprs IS NULL,
               idx.indnatts = idx.indnkeyatts, idx.indisprimary,
               ARRAY(
                   SELECT attr.attname
                   FROM unnest(idx.indkey) WITH ORDINALITY AS key(attnum, ordinality)
                   JOIN pg_catalog.pg_attribute AS attr
                     ON attr.attrelid = tbl.oid AND attr.attnum = key.attnum
                   WHERE key.ordinality <= idx.indnkeyatts
                   ORDER BY key.ordinality
               )
        FROM pg_catalog.pg_class AS idx_relation
        JOIN pg_catalog.pg_namespace AS index_schema ON index_schema.oid = idx_relation.relnamespace
        JOIN pg_catalog.pg_index AS idx ON idx.indexrelid = idx_relation.oid
        JOIN pg_catalog.pg_class AS tbl ON tbl.oid = idx.indrelid
        WHERE index_schema.nspname = :schema_name
          AND tbl.relname = :table_name
          AND idx_relation.relname = :index_name
          AND idx_relation.relkind = 'i'
    """)
    for table, index_name, columns in expected:
        row = connection.execute(query, {
            "schema_name": SCHEMA_NAME,
            "table_name": table,
            "index_name": index_name,
        }).one_or_none()
        if row is None:
            raise SafeRunnerFailure("POST_MIGRATION_PINNED_INDEX_MISSING")
        valid, ready, unique, unfiltered, no_expressions, no_include, primary, actual_columns = row
        if (not valid or not ready or unique or not unfiltered or not no_expressions
                or not no_include or primary or list(actual_columns) != columns):
            raise SafeRunnerFailure("POST_MIGRATION_PINNED_INDEX_MISMATCH")


def _verify_post_migration(url: URL, source_root: Path, snapshots: dict[str, Any]) -> dict[str, int]:
    engine = _engine(url)
    phase = "post_connect"
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                tls = connection.execute(text("""
                    SELECT ssl FROM pg_catalog.pg_stat_ssl WHERE pid = pg_backend_pid()
                """)).scalar_one_or_none()
                if tls is not True:
                    raise SafeRunnerFailure("TLS_NOT_CONFIRMED_ON_POSTCHECK_CONNECTION")
                database, current_schema, version_number = connection.execute(text("""
                    SELECT current_database(), current_schema(), current_setting('server_version_num')
                """)).one()
                if (database != DATABASE_NAME or current_schema != SCHEMA_NAME
                        or int(version_number) // 10000 != EXPECTED_POSTGRES_MAJOR):
                    raise SafeRunnerFailure("POST_MIGRATION_DATABASE_IDENTITY_MISMATCH")
                phase = "post_revision"
                revision, revision_count = _read_revision(connection)
                if revision_count != 1 or revision != TARGET_REVISION:
                    raise SafeRunnerFailure("TARGET_REVISION_MISMATCH")

                phase = "schema_check"
                _verify_model_schema(connection, source_root)
                _verify_pinned_indexes(connection)
                for table, before in snapshots.items():
                    if table not in set(inspect(connection).get_table_names(schema=SCHEMA_NAME)):
                        raise SafeRunnerFailure("PREEXISTING_TABLE_MISSING")
                    actual_columns = {col["name"] for col in inspect(connection).get_columns(table, schema=SCHEMA_NAME)}
                    if not set(before["columns"]) <= actual_columns:
                        raise SafeRunnerFailure("PREEXISTING_COLUMN_MISSING")
                    phase = "data_check"
                    count, digest = _fingerprint_table(
                        connection, table, before["columns"], before["primary_key"],
                    )
                    if count != before["row_count"] or digest != before["sha256"]:
                        raise SafeRunnerFailure("PREEXISTING_DATA_FINGERPRINT_MISMATCH")

                phase = "migration_data_check"
                profile_count = int(connection.execute(text(
                    "SELECT count(*) FROM public.employee_profiles"
                )).scalar_one())
                user_count = int(connection.execute(text(
                    "SELECT count(*) FROM public.users"
                )).scalar_one())
                mismatch_count = int(connection.execute(text("""
                    SELECT count(*)
                    FROM public.users AS u
                    LEFT JOIN public.employee_profiles AS p ON p.user_id = u.id
                    WHERE p.id IS NULL
                       OR p.user_code IS DISTINCT FROM u.user_code
                       OR p.display_name IS DISTINCT FROM u.display_name
                       OR p.email IS DISTINCT FROM u.email
                       OR p.phone IS DISTINCT FROM u.phone
                       OR p.department IS DISTINCT FROM u.department
                       OR p.job_title IS DISTINCT FROM u.job_title
                       OR p.employment_start_date IS DISTINCT FROM u.employment_start_date
                       OR p.employment_status IS DISTINCT FROM u.employment_status
                """)).scalar_one())
                orphan_count = int(connection.execute(text("""
                    SELECT count(*) FROM public.employee_profiles AS p
                    WHERE p.user_id IS NULL
                       OR NOT EXISTS (SELECT 1 FROM public.users AS u WHERE u.id = p.user_id)
                """)).scalar_one())
                if profile_count != user_count or mismatch_count != 0 or orphan_count != 0:
                    raise SafeRunnerFailure("EMPLOYEE_PROFILE_BACKFILL_MISMATCH")
                empty_counts = {}
                for table in NEW_EMPTY_TABLES:
                    count = int(connection.execute(text(
                        f'SELECT count(*) FROM public."{table}"'
                    )).scalar_one())
                    empty_counts[table] = count
                    if count != 0:
                        raise SafeRunnerFailure("UNEXPECTED_NEW_HISTORY_ROWS")
                trigger_state = connection.execute(text("""
                    SELECT
                      to_regprocedure('public.reject_auth_workflow_sla_configuration_mutation()') IS NOT NULL,
                      to_regprocedure('public.guard_auth_workflow_sla_round_snapshot()') IS NOT NULL,
                      EXISTS (SELECT 1 FROM pg_catalog.pg_trigger
                        WHERE tgrelid = to_regclass('public.auth_workflow_sla_configurations')
                          AND tgname = 'trg_auth_workflow_sla_configurations_immutable' AND NOT tgisinternal),
                      EXISTS (SELECT 1 FROM pg_catalog.pg_trigger
                        WHERE tgrelid = to_regclass('public.auth_workflow_sla_rounds')
                          AND tgname = 'trg_auth_workflow_sla_rounds_immutable' AND NOT tgisinternal)
                """)).one()
                if not all(trigger_state):
                    raise SafeRunnerFailure("SLA_TRIGGER_SCHEMA_MISMATCH")
                result = {
                    "revision": revision_count,
                    "preserved_tables": len(snapshots),
                    "users": user_count,
                    "employee_profiles": profile_count,
                    "new_history_rows": sum(empty_counts.values()),
                }
            finally:
                if transaction.is_active:
                    transaction.rollback()
        return result
    except (SafeRunnerFailure, PhaseFailure):
        raise
    except Exception as exc:
        raise _failure_from_exception("POST_MIGRATION_CHECK_FAILED", phase, exc)
    finally:
        engine.dispose()


def _run_alembic_upgrade(source_root: Path, url: URL) -> None:
    old_sys_path = list(sys.path)
    environment_snapshot = {name: os.environ.get(name) for name in PROCESS_ENVIRONMENT_NAMES}
    phase = "alembic_upgrade"
    try:
        for name in PROCESS_ENVIRONMENT_NAMES:
            if name not in {"DATABASE_URL", "PYTHONPATH"}:
                os.environ.pop(name, None)
        url_text = url.render_as_string(hide_password=False)
        os.environ["DATABASE_URL"] = url_text
        os.environ["PYTHONPATH"] = str(source_root)
        os.environ.pop("AUTH_ALLOW_SQLITE_MIGRATION_TESTS", None)
        sys.path.insert(0, str(source_root))
        # Suppress Alembic/SQLAlchemy stderr so a driver message cannot leak URL,
        # SQL parameters, or row data. Only allowlisted exception fields escape.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from alembic import command
            command.upgrade(_alembic_config(source_root), TARGET_REVISION)
    except Exception as exc:
        raise _failure_from_exception("PINNED_ALEMBIC_UPGRADE_FAILED", phase, exc)
    finally:
        sys.path[:] = old_sys_path
        url_text = ""
        for name, value in environment_snapshot.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _diagnostic_directory() -> Path:
    directory = _private_root() / "diagnostics"
    if not directory.exists():
        directory.parent.mkdir(parents=True, exist_ok=True)
        _protect_directory(directory)
    return directory


def _write_safe_diagnostic(run_id: str, phase: str, code: str, exc: BaseException) -> Path | None:
    try:
        directory = _diagnostic_directory()
        fields = safe_exception_fields(exc)
        record = {
            "run_id": run_id,
            "phase": phase,
            "code": code,
            "exception_type": getattr(exc, "exception_type", fields["exception_type"]),
            "sqlstate": getattr(exc, "sqlstate", fields["sqlstate"]),
            "source_sha": PINNED_SHA,
            "target_revision": TARGET_REVISION,
        }
        destination = directory / f"{run_id}.json"
        temporary = directory / f"{run_id}.tmp"
        temporary.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
        if os.name == "nt":
            icacls = shutil.which("icacls.exe") or shutil.which("icacls")
            whoami = shutil.which("whoami.exe") or shutil.which("whoami")
            if icacls and whoami:
                identity = subprocess.run([whoami], capture_output=True, text=True, timeout=10).stdout.strip()
                result = subprocess.run(
                    [icacls, str(temporary), "/inheritance:r", "/grant:r",
                     f"{identity}:F", "SYSTEM:F", "/c"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    temporary.unlink(missing_ok=True)
                    return None
        temporary.replace(destination)
        return destination
    except Exception:
        return None


def _prompt_backup() -> tuple[Path, Path, str]:
    backup_directory = Path(input("Final backup directory (private AppData path): ").strip()).expanduser()
    expected_hash = input("Final backup SHA-256: ").strip().upper()
    if not backup_directory.is_dir() or not re.fullmatch(r"[A-F0-9]{64}", expected_hash):
        raise SafeRunnerFailure("FINAL_BACKUP_INPUT_INVALID")
    expected_root = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "OrganizationAI" / "AuthSchemaRehearsal"
    try:
        if os.path.commonpath([str(backup_directory.resolve()), str(expected_root.resolve())]).lower() != str(expected_root.resolve()).lower():
            raise SafeRunnerFailure("FINAL_BACKUP_OUTSIDE_PRIVATE_ROOT")
    except (OSError, ValueError) as exc:
        raise SafeRunnerFailure("FINAL_BACKUP_OUTSIDE_PRIVATE_ROOT") from exc
    archives = sorted(backup_directory.glob(f"{DATABASE_NAME}-*.dump"))
    if len(archives) != 1:
        raise SafeRunnerFailure("FINAL_BACKUP_ARCHIVE_COUNT_INVALID")
    receipt = verify_rehearsal_receipt(
        backup_directory / BACKUP_RECEIPT_NAME,
        archives[0],
        expected_hash,
        expected_database=DATABASE_NAME,
        expected_pg_major=EXPECTED_POSTGRES_MAJOR,
        source_sha=PINNED_SHA,
        start_revision=START_REVISION,
        target_revision=TARGET_REVISION,
    )
    validate_final_backup_freshness(receipt, archive_path=archives[0])
    return backup_directory, archives[0], expected_hash


def _human_confirmation(identity: dict[str, Any], backup_hash: str, synthetic: bool) -> bool:
    print(f"TARGET_DATABASE={identity['database']}")
    print(f"TARGET_SCHEMA={identity['schema']}")
    print(f"SOURCE_SHA={PINNED_SHA}")
    print(f"CURRENT_REVISION={START_REVISION}")
    print(f"TARGET_REVISION={TARGET_REVISION}")
    print(f"BACKUP_SHA256={backup_hash}")
    print(f"TLS=verified_on_connection")
    print(f"BASELINE_TABLES={identity['baseline_table_count']}")
    print(f"BASELINE_ROWS={identity['baseline_row_count']}")
    confirmation = (
        f"MIGRATE {DATABASE_NAME} {SCHEMA_NAME} {START_REVISION} {TARGET_REVISION} {PINNED_SHA}"
    )
    print("The next step writes the target database. The Auth API and every other writer must remain paused.")
    if synthetic:
        return True
    return input(f"Type exactly: {confirmation}\n> ").strip() == confirmation


def _live_run(repository_root: Path, run_id: str) -> int:
    phase = "initialization"
    run_root = _private_root() / run_id
    source_root: Path | None = None
    url: URL | None = None
    engine = None
    try:
        print(f"RUN_ID={run_id}")
        print(f"PINNED_SOURCE_SHA={PINNED_SHA}; EXPECTED_START={START_REVISION}; TARGET={TARGET_REVISION}")
        if input(
            "Confirm the Auth API DATABASE_URL is linked to the intended PostgreSQL service in Dashboard, "
            "the API is suspended, and all other writers are stopped; type AUTH_CUTOVER_READY: "
        ).strip() != "AUTH_CUTOVER_READY":
            raise SafeRunnerFailure("WRITER_PAUSE_NOT_CONFIRMED")
        phase = "backup_verification"
        _backup_directory, _archive_path, backup_hash = _prompt_backup()
        _protect_directory(run_root)
        phase = "pinned_source_preparation"
        source_root = _prepare_pinned_source(repository_root, run_root)
        phase = "hidden_source_url_input"
        raw_url = getpass.getpass("External PostgreSQL URL for the verified Auth database (hidden): ").strip()
        url = build_secure_url(raw_url)
        raw_url = ""
        phase = "read_only_preflight"
        identity, snapshots = _preflight_and_snapshot(url)
        print("READ_ONLY_PREFLIGHT=PASS; transaction=rolled_back; TLS=verified")
        if not _human_confirmation(identity, backup_hash, synthetic=False):
            raise SafeRunnerFailure("MIGRATION_CONFIRMATION_NOT_MATCHED")

        phase = "alembic_upgrade"
        _run_alembic_upgrade(source_root, url)
        print(f"MIGRATION=completed; revision={TARGET_REVISION}")

        phase = "post_migration_verification"
        checks = _verify_post_migration(url, source_root, snapshots)
        print(f"POST_REVISION={TARGET_REVISION}")
        print("POST_SCHEMA=PASS; preexisting_data_fingerprints=PASS")
        print(f"EMPLOYEE_PROFILES_MATCH_USERS=true; users={checks['users']}")
        print(f"NEW_TOKEN_AUDIT_NOTIFICATION_SLA_ROWS={checks['new_history_rows']}")
        print("RESULT=PASS")
        return 0
    except KeyboardInterrupt as exc:
        phase = phase if phase else "interrupted"
        path = _write_safe_diagnostic(run_id, phase, "RUN_CANCELLED", exc)
        print(f"FAILURE_PHASE={phase}; CODE=RUN_CANCELLED; diagnostic={path or 'not_written'}")
        return 130
    except BaseException as exc:
        code = getattr(exc, "code", "UNEXPECTED_REDACTED_FAILURE")
        failure_phase = getattr(exc, "phase", phase)
        fields = safe_exception_fields(exc)
        path = _write_safe_diagnostic(run_id, failure_phase, code, exc)
        print(f"FAILURE_PHASE={failure_phase}")
        print(f"FAILURE_EXCEPTION_TYPE={getattr(exc, 'exception_type', fields['exception_type'])}")
        print(f"FAILURE_SQLSTATE={getattr(exc, 'sqlstate', fields['sqlstate'])}")
        print(f"FAILURE_CODE={code}")
        print(f"SAFE_DIAGNOSTIC={path or 'not_written'}")
        print("No retry, downgrade, stamp, seed, or live restore was attempted.")
        return 1
    finally:
        raw_url = ""
        if engine is not None:
            engine.dispose()
        if source_root is not None:
            shutil.rmtree(source_root, ignore_errors=True)
        try:
            if run_root.exists():
                shutil.rmtree(run_root)
        except Exception:
            print("RUN_PRIVATE_SOURCE_CLEANUP=pending")
        if url is not None:
            url = None


def _docker_run(args: list[str], *, timeout: int = 60, env=None) -> subprocess.CompletedProcess:
    docker = shutil.which("docker.exe") or shutil.which("docker")
    if not docker:
        raise SafeRunnerFailure("DOCKER_CLI_UNAVAILABLE")
    try:
        return subprocess.run(
            [docker, *args], capture_output=True, text=True, timeout=timeout,
            env=env, check=False,
        )
    except FileNotFoundError as exc:
        raise SafeRunnerFailure("DOCKER_EXECUTABLE_NOT_FOUND") from exc
    except subprocess.TimeoutExpired as exc:
        raise SafeRunnerFailure("DOCKER_OPERATION_TIMEOUT") from exc


def _synthetic_tls_setup(container: str, username: str, database: str, password: str) -> None:
    shell_script = (
        "set -eu; "
        "openssl req -x509 -newkey rsa:2048 -nodes -days 1 "
        "-subj /CN=localhost "
        "-keyout /tmp/oa-server.key "
        "-out /tmp/oa-server.crt >/dev/null 2>&1; "
        "chmod 600 /tmp/oa-server.key; "
        "psql -v ON_ERROR_STOP=1 -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" "
        "-c \"ALTER SYSTEM SET ssl = 'on'\" "
        "-c \"ALTER SYSTEM SET ssl_cert_file = '/tmp/oa-server.crt'\" "
        "-c \"ALTER SYSTEM SET ssl_key_file = '/tmp/oa-server.key'\""
    )
    env = os.environ.copy()
    result = _docker_run(["exec", "--user", "postgres", container, "sh", "-c", shell_script], timeout=45, env=env)
    if result.returncode != 0:
        raise SafeRunnerFailure("SYNTHETIC_TLS_SETUP_FAILED")
    restarted = _docker_run(["restart", container], timeout=45, env=env)
    if restarted.returncode != 0:
        raise SafeRunnerFailure("SYNTHETIC_POSTGRES_RESTART_FAILED")
    for _ in range(60):
        probe = _docker_run(["exec", container, "pg_isready", "-U", username, "-d", database], timeout=5, env=env)
        if probe.returncode == 0:
            break
        import time
        time.sleep(0.5)
    else:
        raise SafeRunnerFailure("SYNTHETIC_POSTGRES_NOT_READY")
    tls_env = os.environ.copy()
    tls_env["PGPASSWORD"] = password
    tls_probe = _docker_run([
        "exec", "--user", "postgres", "--env", "PGPASSWORD", container,
        "psql", "-h", "127.0.0.1", "-U", username, "-d", database,
        "-At", "-c", "SELECT ssl FROM pg_catalog.pg_stat_ssl WHERE pid = pg_backend_pid()",
    ], timeout=15, env=tls_env)
    tls_env.pop("PGPASSWORD", None)
    if tls_probe.returncode != 0 or tls_probe.stdout.strip() != "t":
        raise SafeRunnerFailure("SYNTHETIC_TLS_SERVER_PROBE_FAILED")


def _insert_synthetic_user(url: URL, source_root: Path, run_id: str) -> None:
    engine = _engine(url)
    try:
        with engine.begin() as connection:
            role_id = connection.execute(text(
                "SELECT id FROM public.roles WHERE code = 'MAKER'"
            )).scalar_one()
            user_id = uuid4()
            suffix = run_id.replace("-", "")[:8]
            connection.execute(text("""
                INSERT INTO public.users
                    (id, user_code, username, email, password_hash, display_name, status)
                VALUES (:id, :user_code, :username, :email, :password_hash, :display_name, 'ACTIVE')
            """), {
                "id": user_id,
                "user_code": f"CUTOVER-{suffix}",
                "username": f"cutover_{suffix}",
                "email": f"cutover-{suffix}@example.invalid",
                "password_hash": "synthetic-not-a-real-password-hash",
                "display_name": "Synthetic Cutover User",
            })
            connection.execute(text("""
                INSERT INTO public.user_roles (user_id, role_id) VALUES (:user_id, :role_id)
            """), {"user_id": user_id, "role_id": role_id})
    except Exception as exc:
        raise _failure_from_exception("SYNTHETIC_FIXTURE_SETUP_FAILED", "synthetic_fixture", exc)
    finally:
        engine.dispose()


def _synthetic_run(repository_root: Path, run_id: str) -> int:
    run_root = _private_root() / run_id
    source_root: Path | None = None
    container_name = f"oa-auth-live-test-{run_id.replace('-', '')[:24]}"
    client_name = f"oa-auth-client-{run_id.replace('-', '')[:24]}"
    network_name = f"oa-auth-net-{run_id.replace('-', '')[:24]}"
    env_snapshot = {name: os.environ.get(name) for name in PROCESS_ENVIRONMENT_NAMES}
    container_creation_attempted = False
    client_creation_attempted = False
    network_creation_attempted = False
    phase = "synthetic_setup"
    env_file: Path | None = None
    try:
        _protect_directory(run_root)
        source_root = _prepare_pinned_source(repository_root, run_root)
        docker = shutil.which("docker.exe") or shutil.which("docker")
        if not docker:
            raise SafeRunnerFailure("DOCKER_CLI_UNAVAILABLE")
        absent = _docker_run(["container", "inspect", container_name], timeout=10)
        if absent.returncode == 0:
            raise SafeRunnerFailure("SYNTHETIC_CONTAINER_NAME_COLLISION")
        absent = _docker_run(["container", "inspect", client_name], timeout=10)
        if absent.returncode == 0:
            raise SafeRunnerFailure("SYNTHETIC_CLIENT_NAME_COLLISION")
        absent = _docker_run(["network", "inspect", network_name], timeout=10)
        if absent.returncode == 0:
            raise SafeRunnerFailure("SYNTHETIC_NETWORK_NAME_COLLISION")

        network_creation_attempted = True
        network_result = _docker_run([
            "network", "create",
            "--label", f"organizationai.auth-live.run-id={run_id}",
            "--label", "organizationai.auth-live.kind=synthetic-test",
            network_name,
        ], timeout=30)
        if network_result.returncode != 0 or not network_result.stdout.strip():
            raise SafeRunnerFailure("SYNTHETIC_NETWORK_CREATE_FAILED")

        synthetic_password = os.urandom(32).hex()
        username = "oa_cutover_test"
        database = "organizationai_db"
        docker_env = os.environ.copy()
        docker_env["POSTGRES_PASSWORD"] = synthetic_password
        container_creation_attempted = True
        started = _docker_run([
            "run", "--detach", "--rm", "--name", container_name,
            "--label", f"organizationai.auth-live.run-id={run_id}",
            "--label", "organizationai.auth-live.kind=synthetic-test",
            "--env", "POSTGRES_USER=oa_cutover_test",
            "--env", "POSTGRES_DB=organizationai_db",
            "--env", "POSTGRES_PASSWORD",
            "--network", network_name,
            "--network-alias", "postgres",
            "postgres:16",
        ], timeout=90, env=docker_env)
        docker_env.pop("POSTGRES_PASSWORD", None)
        if started.returncode != 0 or not started.stdout.strip():
            raise SafeRunnerFailure("SYNTHETIC_CONTAINER_START_FAILED")
        labels = _docker_run([
            "inspect", "--format",
            '{{ index .Config.Labels "organizationai.auth-live.run-id" }}|'
            '{{ index .Config.Labels "organizationai.auth-live.kind" }}|'
            '{{.HostConfig.NetworkMode}}',
            container_name,
        ], timeout=10)
        if (labels.returncode != 0
                or labels.stdout.strip() != f"{run_id}|synthetic-test|{network_name}"):
            raise SafeRunnerFailure("SYNTHETIC_CONTAINER_IDENTITY_MISMATCH")
        for _ in range(60):
            ready = _docker_run([
                "exec", container_name, "pg_isready", "-U", username, "-d", database,
            ], timeout=5, env=os.environ.copy())
            if ready.returncode == 0:
                break
            import time
            time.sleep(0.5)
        else:
            raise SafeRunnerFailure("SYNTHETIC_POSTGRES_NOT_READY")

        phase = "synthetic_tls_setup"
        _synthetic_tls_setup(container_name, username, database, synthetic_password)

        phase = "synthetic_client_setup"
        env_file = run_root / "synthetic-client.env"
        environment_values = {
            "OA_TEST_RUN_ID": run_id,
            "OA_TEST_SOURCE_SHA": PINNED_SHA,
            "OA_TEST_PG_HOST": "postgres",
            "OA_TEST_PG_DATABASE": database,
            "OA_TEST_PG_USER": username,
            "OA_TEST_PG_PASSWORD": synthetic_password,
            "OA_TEST_ALEMBIC_VERSION": package_version("alembic"),
            "OA_TEST_SQLALCHEMY_VERSION": package_version("SQLAlchemy"),
            "OA_TEST_PSYCOPG_VERSION": package_version("psycopg"),
        }
        env_file.write_text(
            "".join(f"{key}={value}\n" for key, value in environment_values.items()),
            encoding="ascii",
        )
        if os.name != "nt":
            env_file.chmod(0o600)
        synthetic_password = ""

        client_creation_attempted = True
        client_result = _docker_run([
            "run", "--rm", "--name", client_name,
            "--label", f"organizationai.auth-live.run-id={run_id}",
            "--label", "organizationai.auth-live.kind=synthetic-test-client",
            "--network", network_name,
            "--env-file", str(env_file),
            "--mount", f"type=bind,source={source_root.resolve()},target=/pinned,readonly",
            "--mount", f"type=bind,source={Path(__file__).resolve()},target=/run_auth_live_migration.py,readonly",
            "--mount", f"type=bind,source={Path(__file__).with_name('run_auth_live_migration_synthetic_client.py').resolve()},target=/run_synthetic_client.py,readonly",
            SYNTHETIC_CLIENT_IMAGE,
            "python", "-B", "/run_synthetic_client.py",
        ], timeout=420, env=os.environ.copy())
        allowed_client_lines = re.compile(
            r"^(?:SYNTHETIC_CLIENT_(?:BASE_REVISION|TLS|TARGET_REVISION|SCHEMA|"
            r"EXISTING_DATA_FINGERPRINT|EMPLOYEE_PROFILE_BACKFILL|RESULT)="
            r"[A-Za-z0-9_.-]{1,80}|SYNTHETIC_CLIENT_FAILURE_(?:PHASE|CODE)="
            r"[A-Za-z0-9_.-]{1,80}|SYNTHETIC_CLIENT_FAILURE_(?:EXCEPTION_TYPE|"
            r"SQLSTATE|REASON)=[A-Za-z0-9_.-]{1,80})$"
        )
        client_lines = [
            line.strip() for line in client_result.stdout.splitlines()
            if allowed_client_lines.fullmatch(line.strip())
        ]
        for line in client_lines:
            print(line)
        if client_result.returncode != 0 or "SYNTHETIC_CLIENT_RESULT=PASS" not in client_lines:
            failure_phase = next((
                line.split("=", 1)[1] for line in client_lines
                if line.startswith("SYNTHETIC_CLIENT_FAILURE_PHASE=")
            ), "synthetic_client")
            failure_code = next((
                line.split("=", 1)[1] for line in client_lines
                if line.startswith("SYNTHETIC_CLIENT_FAILURE_CODE=")
            ), "SYNTHETIC_CLIENT_EXECUTION_FAILED")
            failure_exception = next((
                line.split("=", 1)[1] for line in client_lines
                if line.startswith("SYNTHETIC_CLIENT_FAILURE_EXCEPTION_TYPE=")
            ), "SyntheticClientFailure")
            failure_sqlstate = next((
                line.split("=", 1)[1] for line in client_lines
                if line.startswith("SYNTHETIC_CLIENT_FAILURE_SQLSTATE=")
            ), "unavailable")
            failure_reason = next((
                line.split("=", 1)[1] for line in client_lines
                if line.startswith("SYNTHETIC_CLIENT_FAILURE_REASON=")
            ), "SYNTHETIC_CLIENT_FAILED")
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", failure_phase):
                failure_phase = "synthetic_client"
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", failure_code):
                failure_code = "SYNTHETIC_CLIENT_EXECUTION_FAILED"
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", failure_exception):
                failure_exception = "SyntheticClientFailure"
            if not re.fullmatch(r"[0-9A-Z]{5}|unavailable", failure_sqlstate):
                failure_sqlstate = "unavailable"
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}|unclassified", failure_reason):
                failure_reason = "SYNTHETIC_CLIENT_FAILED"
            raise PhaseFailure(
                failure_code, failure_phase, failure_exception, failure_sqlstate,
                reason_code=failure_reason,
            )
        print("SYNTHETIC_READ_ONLY_PREFLIGHT=PASS; TLS=verified")
        print("SYNTHETIC_SCHEMA=PASS; existing_data_fingerprint=PASS; TLS=PASS")
        print("SYNTHETIC_RESULT=PASS")
        return 0
    except BaseException as exc:
        failure_phase = getattr(exc, "phase", phase)
        fields = safe_exception_fields(exc)
        print(f"SYNTHETIC_FAILURE_PHASE={failure_phase}")
        print(f"SYNTHETIC_FAILURE_EXCEPTION_TYPE={getattr(exc, 'exception_type', fields['exception_type'])}")
        print(f"SYNTHETIC_FAILURE_SQLSTATE={getattr(exc, 'sqlstate', fields['sqlstate'])}")
        print(f"SYNTHETIC_FAILURE_DRIVER_TYPE={getattr(exc, 'driver_type', fields['driver_exception_type'])}")
        print(f"SYNTHETIC_FAILURE_CAUSE_TYPE={getattr(exc, 'cause_type', fields['cause_type'])}")
        if isinstance(exc, PhaseFailure):
            print(f"SYNTHETIC_FAILURE_REASON={exc.reason_code}")
        print(f"SYNTHETIC_FAILURE_CODE={getattr(exc, 'code', 'UNEXPECTED_REDACTED_FAILURE')}")
        return 1
    finally:
        for name, value in env_snapshot.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        cleanup_pending = False
        if client_creation_attempted:
            client_inspect = _docker_run([
                "container", "inspect", "--format",
                '{{ index .Config.Labels "organizationai.auth-live.run-id" }}|'
                '{{ index .Config.Labels "organizationai.auth-live.kind" }}',
                client_name,
            ], timeout=10, env=os.environ.copy())
            if client_inspect.returncode == 0:
                if client_inspect.stdout.strip() == f"{run_id}|synthetic-test-client":
                    removed = _docker_run(["container", "rm", "--force", client_name], timeout=30)
                    cleanup_pending = removed.returncode != 0
                else:
                    cleanup_pending = True
        if container_creation_attempted:
            listed = _docker_run([
                "container", "ls", "--all", "--format", "{{.Names}}",
            ], timeout=10, env=os.environ.copy())
            if listed.returncode != 0:
                cleanup_pending = True
            elif container_name in {line.strip() for line in listed.stdout.splitlines()}:
                inspect_result = _docker_run([
                    "container", "inspect", "--format",
                    '{{ index .Config.Labels "organizationai.auth-live.run-id" }}|'
                    '{{ index .Config.Labels "organizationai.auth-live.kind" }}',
                    container_name,
                ], timeout=10, env=os.environ.copy())
                if (inspect_result.returncode == 0
                        and inspect_result.stdout.strip() == f"{run_id}|synthetic-test"):
                    stopped = _docker_run(["stop", container_name], timeout=30, env=os.environ.copy())
                    cleanup_pending = cleanup_pending or stopped.returncode != 0
                else:
                    cleanup_pending = True
        if network_creation_attempted:
            network_inspect = _docker_run([
                "network", "inspect", "--format",
                '{{ index .Labels "organizationai.auth-live.run-id" }}|'
                '{{ index .Labels "organizationai.auth-live.kind" }}',
                network_name,
            ], timeout=10, env=os.environ.copy())
            if network_inspect.returncode == 0:
                if network_inspect.stdout.strip() == f"{run_id}|synthetic-test":
                    removed = _docker_run(["network", "rm", network_name], timeout=20)
                    cleanup_pending = cleanup_pending or removed.returncode != 0
                else:
                    cleanup_pending = True
        if source_root is not None:
            try:
                shutil.rmtree(source_root)
            except FileNotFoundError:
                pass
            except Exception:
                cleanup_pending = True
        try:
            if env_file is not None:
                env_file.unlink(missing_ok=True)
            if run_root.exists():
                shutil.rmtree(run_root)
        except Exception:
            cleanup_pending = True
        if cleanup_pending:
            print("SYNTHETIC_CLEANUP=pending")
        else:
            print("SYNTHETIC_CLEANUP=complete")


def _run_alembic_to_revision(source_root: Path, url: URL, revision: str) -> None:
    # The synthetic-only base setup invokes the same pinned Alembic environment;
    # target is deliberately restricted to the validated start revision.
    old_sys_path = list(sys.path)
    snapshot = {name: os.environ.get(name) for name in PROCESS_ENVIRONMENT_NAMES}
    try:
        for name in PROCESS_ENVIRONMENT_NAMES:
            if name not in {"DATABASE_URL", "PYTHONPATH"}:
                os.environ.pop(name, None)
        os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
        os.environ["PYTHONPATH"] = str(source_root)
        sys.path.insert(0, str(source_root))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from alembic import command
            command.upgrade(_alembic_config(source_root), revision)
    except Exception as exc:
        raise _failure_from_exception("SYNTHETIC_BASE_MIGRATION_FAILED", "synthetic_base_migration", exc)
    finally:
        sys.path[:] = old_sys_path
        for name, value in snapshot.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", PINNED_SHA):
        print("RESULT=FAILED; CODE=PINNED_SHA_INVALID")
        return 2
    if os.name != "nt" and not args.synthetic_only:
        print("RESULT=FAILED; CODE=LIVE_RUNNER_REQUIRES_WINDOWS_ENTRYPOINT")
        return 2
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:20]
    root = Path(args.repository_root).resolve()
    if args.synthetic_only:
        return _synthetic_run(root, run_id)
    return _live_run(root, run_id)


if __name__ == "__main__":
    raise SystemExit(main())
