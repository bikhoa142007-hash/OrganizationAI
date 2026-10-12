"""Docker-network-only client for the pinned Auth migration rehearsal.

This helper intentionally accepts no command-line arguments and no arbitrary
database URL. The Windows parent provides only generated credentials for a
run-labelled PostgreSQL container on a private Docker network.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import importlib.util


PINNED_SHA = "0d17887cf1d6a6571fc8b02b74706343e2555e19"
REQUIREMENT_NAMES = ("alembic", "sqlalchemy", "psycopg")


def _fail(phase: str, code: str, exc: BaseException | None = None) -> int:
    if exc is not None:
        original_phase = getattr(exc, "phase", None)
        original_code = getattr(exc, "code", None)
        if isinstance(original_phase, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", original_phase):
            phase = original_phase
        if isinstance(original_code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", original_code):
            code = original_code
    print(f"SYNTHETIC_CLIENT_FAILURE_PHASE={phase}")
    print(f"SYNTHETIC_CLIENT_FAILURE_CODE={code}")
    if exc is not None:
        try:
            from run_auth_live_migration import safe_exception_fields, _safe_reason_code

            fields = safe_exception_fields(exc)
            exception_type = getattr(exc, "exception_type", fields["exception_type"])
            sqlstate = getattr(exc, "sqlstate", fields["sqlstate"])
            reason = getattr(exc, "reason_code", _safe_reason_code(exc))
            if not isinstance(exception_type, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", exception_type):
                exception_type = fields["exception_type"]
            if not isinstance(sqlstate, str) or not re.fullmatch(r"[0-9A-Z]{5}|unavailable", sqlstate):
                sqlstate = fields["sqlstate"]
            if not isinstance(reason, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}|unclassified", reason):
                reason = _safe_reason_code(exc)
            print(f"SYNTHETIC_CLIENT_FAILURE_EXCEPTION_TYPE={exception_type}")
            print(f"SYNTHETIC_CLIENT_FAILURE_SQLSTATE={sqlstate}")
            print(f"SYNTHETIC_CLIENT_FAILURE_REASON={reason}")
        except Exception:
            print("SYNTHETIC_CLIENT_FAILURE_EXCEPTION_TYPE=unavailable")
            print("SYNTHETIC_CLIENT_FAILURE_SQLSTATE=unavailable")
            print("SYNTHETIC_CLIENT_FAILURE_REASON=unclassified")
    return 1


def _requirements(source_root: Path, versions: dict[str, str]) -> list[str]:
    matches: dict[str, str] = {}
    requirement_file = source_root / "requirements.txt"
    for raw_line in requirement_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.partition("#")[0].strip()
        match = re.match(r"^([A-Za-z0-9_.-]+)(\[[^]]+\])?(\s*[^;]+)?$", line)
        if not match:
            continue
        name = match.group(1).lower().replace("_", "-").replace(".", "-")
        if name in REQUIREMENT_NAMES:
            extra = match.group(2) or ""
            specifier = (match.group(3) or "").strip()
            if not specifier.startswith(("<", ">", "=", "~", "!")):
                continue
            matches[name] = f"{match.group(1)}{extra}{specifier}"
    if set(matches) != set(REQUIREMENT_NAMES):
        raise ValueError("pinned requirements do not declare cutover packages")
    result = []
    for name in REQUIREMENT_NAMES:
        version = versions.get(name, "")
        if not re.fullmatch(r"[0-9A-Za-z.+!-]{1,80}", version):
            raise ValueError("host dependency version is invalid")
        result.append(f"{matches[name]},=={version}")
    return result


def _install_requirements(source_root: Path, versions: dict[str, str]) -> bool:
    try:
        command = [
            sys.executable, "-B", "-m", "pip", "install", "--quiet",
            "--disable-pip-version-check", "--no-warn-script-location",
            *_requirements(source_root, versions),
        ]
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=240, check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def main() -> int:
    if len(sys.argv) != 1:
        return _fail("input_validation", "SYNTHETIC_CLIENT_ARGUMENTS_REJECTED")
    try:
        if sys.version_info[:2] != (3, 12):
            return _fail("runtime_validation", "SYNTHETIC_CLIENT_PYTHON_VERSION_MISMATCH")
        run_id = os.environ.get("OA_TEST_RUN_ID", "")
        if not re.fullmatch(r"[0-9a-f]{8}T[0-9]{6}Z-[0-9a-f]{20}", run_id):
            return _fail("input_validation", "SYNTHETIC_CLIENT_RUN_ID_INVALID")
        if (os.environ.get("OA_TEST_SOURCE_SHA") != PINNED_SHA
                or os.environ.get("OA_TEST_PG_HOST") != "postgres"
                or os.environ.get("OA_TEST_PG_DATABASE") != "organizationai_db"
                or os.environ.get("OA_TEST_PG_USER") != "oa_cutover_test"
                or not re.fullmatch(r"[a-f0-9]{64}", os.environ.get("OA_TEST_PG_PASSWORD", ""))):
            return _fail("input_validation", "SYNTHETIC_CLIENT_TARGET_REJECTED")
        dependency_versions = {
            "alembic": os.environ.get("OA_TEST_ALEMBIC_VERSION", ""),
            "sqlalchemy": os.environ.get("OA_TEST_SQLALCHEMY_VERSION", ""),
            "psycopg": os.environ.get("OA_TEST_PSYCOPG_VERSION", ""),
        }
        source_root = Path("/pinned")
        if not (source_root / "alembic.ini").is_file():
            return _fail("pinned_source", "PINNED_SOURCE_MISSING")
        if not _install_requirements(source_root, dependency_versions):
            return _fail("dependencies", "SYNTHETIC_CLIENT_DEPENDENCY_INSTALL_FAILED")

        runner_spec = importlib.util.spec_from_file_location(
            "run_auth_live_migration", "/run_auth_live_migration.py",
        )
        if runner_spec is None or runner_spec.loader is None:
            return _fail("runner_import", "SYNTHETIC_RUNNER_MODULE_UNAVAILABLE")
        runner_module = importlib.util.module_from_spec(runner_spec)
        sys.modules["run_auth_live_migration"] = runner_module
        runner_spec.loader.exec_module(runner_module)
        from run_auth_live_migration import (
            DATABASE_NAME,
            PINNED_SHA as RUNNER_SHA,
            START_REVISION,
            TARGET_REVISION,
            _insert_synthetic_user,
            _preflight_and_snapshot,
            _run_alembic_to_revision,
            _run_alembic_upgrade,
            _validate_pinned_migration_chain,
            _verify_post_migration,
            build_secure_url,
        )
        from sqlalchemy.engine import URL

        if RUNNER_SHA != PINNED_SHA or DATABASE_NAME != "organizationai_db":
            return _fail("pinned_source", "RUNNER_SOURCE_IDENTITY_MISMATCH")
        _validate_pinned_migration_chain(source_root)

        url_text = URL.create(
            "postgresql+psycopg",
            username="oa_cutover_test",
            password=os.environ["OA_TEST_PG_PASSWORD"],
            host="postgres",
            port=5432,
            database="organizationai_db",
        ).render_as_string(hide_password=False)
        url = build_secure_url(url_text)
        url_text = ""

        try:
            _run_alembic_to_revision(source_root, url, START_REVISION)
        except Exception as exc:
            return _fail("synthetic_base_migration", "SYNTHETIC_BASE_MIGRATION_FAILED", exc)
        try:
            _insert_synthetic_user(url, source_root, run_id)
            identity, snapshots = _preflight_and_snapshot(url)
            if identity["revision"] != START_REVISION or not identity["tls"]:
                return _fail("synthetic_preflight", "SYNTHETIC_PREFLIGHT_MISMATCH")
        except Exception as exc:
            return _fail("synthetic_preflight", "SYNTHETIC_PREFLIGHT_FAILED", exc)

        print("SYNTHETIC_CLIENT_BASE_REVISION=20261003_07")
        print("SYNTHETIC_CLIENT_TLS=verified")
        try:
            _run_alembic_upgrade(source_root, url)
        except Exception as exc:
            return _fail("synthetic_migration", "SYNTHETIC_TARGET_MIGRATION_FAILED", exc)
        try:
            checks = _verify_post_migration(url, source_root, snapshots)
            if checks["users"] != 1 or checks["employee_profiles"] != 1:
                return _fail("synthetic_postcheck", "SYNTHETIC_DATA_PRESERVATION_FAILED")
        except Exception as exc:
            return _fail("synthetic_postcheck", "SYNTHETIC_POST_MIGRATION_CHECK_FAILED", exc)
        print("SYNTHETIC_CLIENT_TARGET_REVISION=20261011_12")
        print("SYNTHETIC_CLIENT_SCHEMA=PASS")
        print("SYNTHETIC_CLIENT_EXISTING_DATA_FINGERPRINT=PASS")
        print("SYNTHETIC_CLIENT_EMPLOYEE_PROFILE_BACKFILL=PASS")
        print("SYNTHETIC_CLIENT_RESULT=PASS")
        return 0
    except Exception as exc:
        return _fail("synthetic_client", "SYNTHETIC_CLIENT_UNEXPECTED_FAILURE", exc)


if __name__ == "__main__":
    raise SystemExit(main())
