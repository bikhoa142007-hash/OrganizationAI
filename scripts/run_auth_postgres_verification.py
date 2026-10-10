#!/usr/bin/env python3
"""Run isolated PostgreSQL migration, Admin-directory, and Auth browser checks.

Run with the repository test interpreter from CMD, Git Bash, or another shell:
  .venv-test-20261009/Scripts/python.exe scripts/run_auth_postgres_verification.py
For the focused employee/account PostgreSQL gate (it creates its own isolated DB):
  .venv-test-20261009/Scripts/python.exe scripts/run_auth_postgres_verification.py --only employee-admin

The script never pulls an image, mounts a volume, or stops/removes a container
that it did not create. The Auth browser cases use the explicitly configured
MOCK_VLM demo provider; they are workflow E2E evidence, not Local AI evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import Request as FastAPIRequest


ROOT = Path(__file__).resolve().parents[1]
HEAD_REVISION = "20261010_10"
PRE_EMPLOYEE_REVISION = "20261009_08"
RESERVED_PORTS = {8010, 5173, 5433, 18010, 15173}
EVIDENCE_ROOT = ROOT / "docs" / "integration" / "evidence"
EXPECTED_BUILTIN_PERMISSIONS = {
    "ADMIN": {
        "MARKETING_PLAN_READ", "MARKETING_PLAN_VIEW_ALL", "MARKETING_HISTORY_READ",
        "ADMIN_EMPLOYEE_MANAGE", "ADMIN_ROLE_MANAGE", "ADMIN_APPROVER_MANAGE",
        "ADMIN_SLA_MANAGE", "ADMIN_AUDIT_READ",
    },
    "CHECKER": {
        "MARKETING_PLAN_READ", "MARKETING_REVIEW_ASSIGNED", "MARKETING_APPROVE",
        "MARKETING_REJECT", "MARKETING_HISTORY_READ",
    },
    "MAKER": {
        "MARKETING_PLAN_READ", "MARKETING_PLAN_CREATE", "MARKETING_PLAN_EDIT_OWN",
        "MARKETING_ATTACHMENT_MANAGE", "MARKETING_PLAN_SUBMIT", "MARKETING_HISTORY_READ",
    },
}


def _make_employee_admin_database_dependency(
    factory, concurrent_request_sessions, concurrent_transactions, evidence_lock,
):
    """Build the employee-admin DB override with a globally resolvable Request type."""
    from sqlalchemy import event

    def database_dependency(request: FastAPIRequest):
        with factory() as session:
            request_id = request.headers.get("x-verification-request")
            if request_id in {"token-use-1", "token-use-2"}:
                with evidence_lock:
                    concurrent_request_sessions[request_id] = session

                def capture_transaction(db_session, transaction, connection):
                    with evidence_lock:
                        if request_id not in concurrent_transactions:
                            concurrent_transactions[request_id] = {
                                "session": db_session,
                                "transaction": transaction,
                                "connection": connection,
                            }

                event.listen(session, "after_begin", capture_transaction)
            yield session

    return database_dependency


def _install_employee_admin_diagnostic_handlers(
    app, concurrent_backend_exceptions, concurrency_evidence_lock,
    login_validation_sensitive_values, login_validation_diagnostics,
):
    """Install the helper's safe concurrency and login-validation diagnostics."""
    from fastapi.exceptions import RequestValidationError
    from src.backend.api.errors import error_response

    async def capture_unexpected_error(request: FastAPIRequest, exc: Exception):
        request_id = request.headers.get("x-verification-request")
        if request_id in {"token-use-1", "token-use-2"}:
            with concurrency_evidence_lock:
                concurrent_backend_exceptions[request_id] = exc
        return error_response(
            "UNAVAILABLE", "Request could not be completed.",
            getattr(request.state, "correlation_id", "auth-request"),
        )

    # Preserve the production HTTP contract while retaining safe exception metadata
    # from the catch-all handler for the two instrumented requests.
    app.add_exception_handler(Exception, capture_unexpected_error)
    original_validation_handler = app.exception_handlers[RequestValidationError]

    async def capture_login_validation(request: FastAPIRequest, exc: RequestValidationError):
        request_id = request.headers.get("x-verification-request")
        if request_id in login_validation_sensitive_values:
            login_validation_diagnostics[request_id] = _safe_validation_details(
                exc.errors(),
                sensitive_values=login_validation_sensitive_values[request_id],
            )
        return await original_validation_handler(request, exc)

    app.add_exception_handler(RequestValidationError, capture_login_validation)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _redact(value: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(
        r"(?i)(\b(?:password|passwd|secret|token|authorization|cookie|api[_-]?key|database[_-]?url)\b\s*[:=]\s*)(\"[^\"]*\"|[^\s,;]+)",
        r'\1"[REDACTED]"', value,
    )
    value = re.sub(r"(?i)(postgres(?:ql)?(?:\+\w+)?://)[^\s\"'<>]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", value)
    value = re.sub(
        r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])",
        "[REDACTED_JWT]", value,
    )
    return _sanitize_postgres_diagnostics(value)


def _sanitize_postgres_diagnostics(value: str) -> str:
    """Remove database row contents and bound SQL values from shareable output."""
    sanitized = []
    suppress_block = None
    for line in value.splitlines():
        stripped = line.lstrip()
        if suppress_block:
            if "]" in line:
                sanitized.append(f"{line[:len(line) - len(stripped)]}{suppress_block}: [REDACTED]")
                suppress_block = None
            continue
        if stripped.startswith("DETAIL: Failing row contains"):
            indentation = line[:len(line) - len(stripped)]
            sanitized.append(f"{indentation}DETAIL: Failing row contents redacted.")
        elif stripped.startswith("[parameters:") or stripped.startswith("[SQL:"):
            label = "[parameters" if stripped.startswith("[parameters:") else "[SQL"
            indentation = line[:len(line) - len(stripped)]
            sanitized.append(f"{indentation}{label}: [REDACTED]")
            if "]" not in stripped:
                suppress_block = label
        elif stripped.startswith("CONTEXT:"):
            indentation = line[:len(line) - len(stripped)]
            sanitized.append(f"{indentation}CONTEXT: [REDACTED]")
        else:
            sanitized.append(line)
    return "\n".join(sanitized)


def _verify_management_token_purpose_constraint(session, token_model, token_id) -> dict:
    """Prove PostgreSQL rejects an out-of-catalog purpose and rolls back its savepoint."""
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError

    expected_constraint = "ck_auth_management_tokens_purpose"
    try:
        with session.begin_nested():
            session.execute(
                update(token_model).where(token_model.id == token_id).values(purpose="UNKNOWN")
            )
    except IntegrityError as exc:
        original = exc.orig
        sqlstate = getattr(original, "sqlstate", None)
        diagnostic = getattr(original, "diag", None)
        constraint_name = getattr(diagnostic, "constraint_name", None)
        database_error_type = type(original).__name__
        if (database_error_type != "CheckViolation" or sqlstate != "23514"
                or constraint_name != expected_constraint):
            raise AssertionError(
                "Out-of-catalog token purpose failed for an unexpected database constraint "
                f"(database_error_type={database_error_type}, sqlstate={sqlstate}, "
                f"constraint_name={constraint_name})."
            ) from None
    else:
        raise AssertionError(
            f"PostgreSQL accepted an out-of-catalog purpose; expected {expected_constraint}."
        )

    session.expire_all()
    persisted = session.get(token_model, token_id)
    if persisted is None or persisted.purpose != "RESET" or persisted.consumed_at is not None:
        raise AssertionError(
            "Purpose constraint savepoint rollback did not preserve the valid, unconsumed RESET fixture."
        )
    return {
        "status": "PASS",
        "invalid_catalog_value_rejected": True,
        "database_error_type": "CheckViolation",
        "sqlstate": "23514",
        "constraint_name": expected_constraint,
        "savepoint_rollback_preserved_purpose": "RESET",
        "savepoint_rollback_preserved_unconsumed_state": True,
        "verification_point": "_verify_employee_account_lifecycle purpose-constraint savepoint",
    }


def _concurrent_token_evidence(request_id: str, *, response=None, exception=None,
                               sensitive_values=()) -> dict:
    """Keep the concurrent token diagnostic to HTTP metadata and sanitized exceptions."""
    result = {
        "request_id": request_id,
        "http_status": None,
        "error_code": None,
        "exception": None,
    }
    if exception is not None:
        message = _redact(str(exception), list(sensitive_values))
        message = re.sub(r"(?i)https?://[^\s\"'<>]+", "[REDACTED_URL]", message)
        result["exception"] = {"type": type(exception).__name__, "message": message[:500]}
    if response is None:
        if exception is None:
            result["exception"] = {"type": "MissingResponse", "message": "No HTTP response was captured."}
        return result

    result["http_status"] = int(response.status_code)
    if result["http_status"] < 400:
        return result
    try:
        payload = response.json()
    except Exception as exc:
        message = _redact(str(exc), list(sensitive_values))
        message = re.sub(r"(?i)https?://[^\s\"'<>]+", "[REDACTED_URL]", message)
        safe_decode_exception = {"type": type(exc).__name__, "message": message[:500]}
        if result["exception"] is None:
            result["exception"] = safe_decode_exception
        else:
            result["response_decode_exception"] = safe_decode_exception
        return result
    error_code = payload.get("code") if isinstance(payload, dict) else None
    if isinstance(error_code, str) and error_code in {
        "VALIDATION_ERROR", "UNAUTHENTICATED", "FORBIDDEN", "NOT_FOUND", "CONFLICT", "UNAVAILABLE",
    }:
        result["error_code"] = error_code
    return result


def _safe_validation_details(errors, *, sensitive_values=()) -> list[dict]:
    """Extract only validation location/type/message, never Pydantic input values."""
    safe_errors = []
    secrets = list(sensitive_values)
    for error in errors:
        raw_loc = error.get("loc", ()) if isinstance(error, dict) else ()
        if not isinstance(raw_loc, (tuple, list)):
            raw_loc = ()
        safe_loc = []
        for part in raw_loc:
            if isinstance(part, int) and not isinstance(part, bool):
                safe_loc.append(part)
            elif isinstance(part, str):
                safe_loc.append(_redact(part, secrets)[:100])
            else:
                safe_loc.append(type(part).__name__)
        raw_type = error.get("type", "unknown") if isinstance(error, dict) else "unknown"
        safe_type = str(raw_type)
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", safe_type):
            safe_type = "unknown"
        raw_message = error.get("msg", "") if isinstance(error, dict) else ""
        safe_message = _redact(str(raw_message), secrets)
        safe_message = re.sub(r"(?i)https?://[^\s\"'<>]+", "[REDACTED_URL]", safe_message)
        safe_errors.append({"loc": safe_loc, "type": safe_type, "message": safe_message[:240]})
    return safe_errors


def _safe_response_error_code(response) -> str | None:
    try:
        payload = response.json()
    except Exception:
        return None
    code = payload.get("code") if isinstance(payload, dict) else None
    if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code):
        return code
    return None


def _auth_login_payload(identifier: str, password: str) -> dict[str, str]:
    """Build the JSON body used by the Auth login endpoint."""
    return {"identifier": identifier, "password": password}


def _employee_admin_login_payload(run_marker: str, suffix: str, password: str) -> dict[str, str]:
    """Build the JSON body for a seeded employee-admin identity."""
    return _auth_login_payload(f"pgemp_{run_marker}_{suffix}", password)


def _require_synthetic_login(response, label: str, *, validation_details=()) -> None:
    if response.status_code == 200:
        return
    safe_diagnostic = {
        "http_status": response.status_code,
        "error_code": _safe_response_error_code(response),
        "validation_errors": list(validation_details),
    }
    raise AssertionError(
        f"{label} returned HTTP {response.status_code}; expected HTTP 200; "
        f"safe_diagnostic={json.dumps(safe_diagnostic, sort_keys=True)}"
    )


def _employee_account_ids(employee_payload: object, account_payload: object) -> tuple[str, str]:
    """Read the distinct EmployeeProfile and User IDs from the create API contracts."""
    try:
        employee_id = str(UUID(employee_payload["id"]))
        if employee_payload.get("account_id") is not None:
            raise AssertionError("New employee profile unexpectedly already has an account ID.")
        linked_employee = account_payload["employee"]
        linked_employee_id = str(UUID(linked_employee["id"]))
        account_id = str(UUID(linked_employee["account_id"]))
    except (AttributeError, KeyError, TypeError, ValueError):
        raise AssertionError(
            "Employee/account create responses did not contain valid synthetic profile and account IDs."
        ) from None
    if linked_employee_id != employee_id:
        raise AssertionError(
            "Account create response linked a different synthetic employee profile "
            f"(employee_id={employee_id}, response_employee_id={linked_employee_id})."
        )
    if account_id == employee_id:
        raise AssertionError(
            "Synthetic employee fixture must keep profile and account IDs distinct "
            f"(employee_id={employee_id}, account_id={account_id})."
        )
    if account_payload.get("purpose") != "ACTIVATE":
        raise AssertionError("New employee account response did not issue an ACTIVATE handover token.")
    if (linked_employee.get("employment_status") != "ACTIVE"
            or linked_employee.get("status") != "DISABLED"
            or linked_employee.get("account_status") != "PENDING_ACTIVATION"):
        raise AssertionError(
            "New employee/account response statuses did not match the pending activation contract "
            f"(employee_id={employee_id}, account_id={account_id})."
        )
    return employee_id, account_id


def _require_account_visible_from_session(
    session, account_model, *, employee_id: str, account_id: str, label: str,
):
    """Read a linked User by account ID and fail with safe synthetic identity context."""
    employee_uuid = UUID(employee_id)
    account_uuid = UUID(account_id)
    if employee_uuid == account_uuid:
        raise AssertionError(
            f"{label} requires distinct synthetic employee and account IDs "
            f"(employee_id={employee_uuid}, account_id={account_uuid})."
        )
    account = session.get(account_model, account_uuid)
    if account is None:
        raise AssertionError(
            f"{label} account was not visible from an independent PostgreSQL session "
            f"(employee_id={employee_uuid}, account_id={account_uuid})."
        )
    return account


def _run(args: list[str], *, env=None, cwd=ROOT, timeout=120, secrets=None, check=True):
    completed = subprocess.run(
        args, cwd=cwd, env=env, capture_output=True, text=True,
        timeout=timeout, errors="replace",
    )
    stdout = _redact(completed.stdout or "", secrets or [])
    stderr = _redact(completed.stderr or "", secrets or [])
    if check and completed.returncode:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {_redact(repr(args), secrets or [])}\n"
            f"{stderr[-3000:]}\n{stdout[-3000:]}"
        )
    return completed.returncode, stdout, stderr


def _port_is_free(port: int) -> bool:
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    if port in RESERVED_PORTS:
        return _free_port()
    return port


def _container_inventory(docker: str) -> dict[str, dict[str, str]]:
    code, output, error = _run(
        [docker, "ps", "-a", "--no-trunc", "--format", "{{.ID}}\t{{.Names}}\t{{.State}}"],
        check=False,
    )
    if code:
        raise RuntimeError(f"Could not inspect existing container inventory: {error[-1000:]}")
    inventory = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0]:
            inventory[parts[0]] = {"name": parts[1], "state": parts[2]}
    return inventory


def _engine_info(docker: str) -> dict:
    code, output, error = _run([docker, "info", "--format", "{{json .}}"], check=False)
    if code:
        raise RuntimeError(f"Docker Engine is not reachable from this process: {error.strip()[-1000:]}")
    try:
        info = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Docker info did not return parseable JSON.") from exc
    return {
        key: info.get(key)
        for key in ("ServerVersion", "OSType", "OperatingSystem", "Architecture", "NCPU")
    }


def _is_docker_access_blocked(message: str) -> bool:
    normalized = message.lower()
    return any(marker in normalized for marker in (
        "docker engine is not reachable",
        "permission denied while trying to connect to the docker api",
        "cannot connect to the docker daemon",
        "error during connect: in the default daemon configuration on windows",
    ))


def _revision_info() -> dict:
    _, head, _ = _run(["git", "rev-parse", "HEAD"])
    _, branch, _ = _run(["git", "branch", "--show-current"])
    code, origin_main, _ = _run(["git", "rev-parse", "origin/main"], check=False)
    _, status, _ = _run(["git", "status", "--short", "--untracked-files=all"])
    _, paths_output, _ = _run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    digest = hashlib.sha256()
    paths = sorted(path for path in paths_output.split("\0") if path)
    for relative in paths:
        path = ROOT / relative
        digest.update(relative.encode("utf-8", errors="surrogatepass"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"[MISSING]")
        digest.update(b"\0")
    changed_paths = [line[3:].strip() for line in status.splitlines() if len(line) >= 4]
    return {
        "branch": branch.strip(),
        "head": head.strip(),
        "origin_main_local_ref": origin_main.strip() if code == 0 else None,
        "working_tree": {
            "dirty": bool(status.strip()),
            "changed_paths": changed_paths,
            "content_sha256": digest.hexdigest(),
            "fingerprint_scope": "tracked and non-ignored untracked file contents at runner start",
        },
    }


def _assert_migration_head(python: str) -> str:
    _, heads, _ = _run([python, "-m", "alembic", "heads"])
    matches = re.findall(r"(?m)^([0-9A-Za-z_]+) \(head\)$", heads)
    if matches != [HEAD_REVISION]:
        raise RuntimeError(f"Expected exactly one Alembic head {HEAD_REVISION}; got {matches!r}.")
    return heads.strip()


def _helper(python: str, mode: str, *, env, extra=(), secrets=None, timeout=120):
    helper_env = os.environ.copy()
    helper_env.update(env or {})
    command = [
        python,
        str(Path(__file__).resolve()),
        "--repo-root",
        str(ROOT.resolve()),
        "--helper-mode",
        mode,
        *extra,
    ]
    code, stdout, stderr = _run(
        command, env=helper_env, timeout=timeout, secrets=secrets, check=False,
    )
    if code:
        raise RuntimeError(
            f"PostgreSQL helper {mode!r} failed ({code}); command={_redact(repr(command), secrets or [])}\n"
            f"{stderr}\n{stdout}"
        )
    unexpected_stderr = _strip_known_helper_warnings(stderr)
    if unexpected_stderr.strip():
        raise RuntimeError(f"PostgreSQL helper emitted unexpected stderr: {unexpected_stderr}")
    try:
        return json.loads(stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise RuntimeError(f"PostgreSQL helper returned no JSON evidence: {stdout[-1500:]}") from exc


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _strip_known_helper_warnings(stderr: str) -> str:
    return re.sub(
        r"(?m)^.*StarletteDeprecationWarning: Using `httpx` with `starlette\.testclient` "
        r"is deprecated; install `httpx2` instead\.\r?\n"
        r"[ \t]+from starlette\.testclient import TestClient as TestClient\s+# noqa\r?\n?",
        "",
        stderr,
    )


def _require_status(response, label: str, *, expected_status: int = 200) -> None:
    status = getattr(response, "status_code", None)
    if status != expected_status:
        raise AssertionError(f"{label} returned HTTP {status}; expected HTTP {expected_status}.")


def _response_payload(response, label: str, *, expected_status: int = 200):
    _require_status(response, label, expected_status=expected_status)
    try:
        return response.json()
    except Exception as exc:
        raise AssertionError(f"{label} returned invalid JSON after HTTP {expected_status}.") from exc


def _employee_page_payload(response, label: str) -> dict:
    payload = _response_payload(response, label)
    if not isinstance(payload, dict):
        raise AssertionError(f"{label} response must be an object containing the paged employee envelope.")
    required_page_fields = {"items", "offset", "limit", "total"}
    missing_page_fields = required_page_fields - payload.keys()
    if missing_page_fields:
        raise AssertionError(f"{label} response is missing page fields: {sorted(missing_page_fields)}.")
    if not isinstance(payload["items"], list):
        raise AssertionError(f"{label} response field 'items' must be a list.")
    for field in ("offset", "limit", "total"):
        if type(payload[field]) is not int or payload[field] < 0:
            raise AssertionError(f"{label} response field {field!r} must be a non-negative integer.")
    if payload["limit"] == 0:
        raise AssertionError(f"{label} response field 'limit' must be greater than zero.")

    required_item_fields = {
        "id", "account_id", "user_code", "username", "display_name", "email", "phone", "department",
        "job_title", "employment_start_date", "employment_status", "status", "account_status", "roles",
        "effective_permissions",
    }
    string_item_fields = {"id", "user_code", "display_name"}
    nullable_string_item_fields = {
        "email", "phone", "department", "job_title", "employment_start_date",
    }
    for index, item in enumerate(payload["items"]):
        if not isinstance(item, dict):
            raise AssertionError(f"{label} response field 'items[{index}]' must be an object.")
        missing_item_fields = required_item_fields - item.keys()
        if missing_item_fields:
            raise AssertionError(
                f"{label} response item {index} is missing fields: {sorted(missing_item_fields)}."
            )
        for field in string_item_fields:
            if not isinstance(item[field], str):
                raise AssertionError(f"{label} response item {index} field {field!r} must be a string.")
        for field in nullable_string_item_fields:
            if item[field] is not None and not isinstance(item[field], str):
                raise AssertionError(
                    f"{label} response item {index} field {field!r} must be a string or null."
                )
        for field in ("account_id", "username"):
            if item[field] is not None and not isinstance(item[field], str):
                raise AssertionError(f"{label} response item {index} field {field!r} must be a string or null.")
        if (item["account_id"] is None) != (item["username"] is None):
            raise AssertionError(f"{label} response item {index} has inconsistent account_id/username fields.")
        if (not isinstance(item["employment_status"], str)
                or item["employment_status"] not in {"ACTIVE", "INACTIVE"}):
            raise AssertionError(f"{label} response item {index} has an invalid employment_status.")
        if item["status"] is not None and item["status"] not in {"ACTIVE", "DISABLED"}:
            raise AssertionError(f"{label} response item {index} has an invalid legacy account status.")
        if item["account_status"] is not None and item["account_status"] not in {"ACTIVE", "DISABLED", "PENDING_ACTIVATION"}:
            raise AssertionError(f"{label} response item {index} has an invalid account_status.")
        if (item["account_id"] is None) != (item["account_status"] is None):
            raise AssertionError(f"{label} response item {index} has inconsistent account identity/state fields.")
        if not isinstance(item["roles"], list) or any(not isinstance(role, str) for role in item["roles"]):
            raise AssertionError(f"{label} response item {index} field 'roles' must be a list of strings.")
        if not isinstance(item["effective_permissions"], list) or any(
            not isinstance(permission, str) for permission in item["effective_permissions"]
        ):
            raise AssertionError(f"{label} response item {index} field 'effective_permissions' must be a list of strings.")
    return payload


def _checker_list_payload(response, label: str) -> list[dict]:
    payload = _response_payload(response, label)
    if not isinstance(payload, list):
        raise AssertionError(f"{label} response must be a list of checker objects.")
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise AssertionError(f"{label} checker list item {index} must be an object.")
        if not isinstance(item.get("id"), str) or not isinstance(item.get("display_name"), str):
            raise AssertionError(f"{label} checker list item {index} must contain string id and display_name fields.")
    return payload


def _helper_mode(mode: str, args) -> int:
    from sqlalchemy import create_engine, inspect, text

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError("Helper requires an explicit temporary PostgreSQL DATABASE_URL.")
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        if mode == "verify-empty":
            inspector = inspect(engine)
            with engine.connect() as connection:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
                user_count = connection.scalar(text("SELECT count(*) FROM users"))
                user_role_count = connection.scalar(text("SELECT count(*) FROM user_roles"))
                workflow_count = connection.scalar(text("SELECT count(*) FROM auth_workflow_plans"))
                employee_count = connection.scalar(text("SELECT count(*) FROM employee_profiles"))
                role_rows = connection.execute(text(
                    "SELECT code, is_builtin, status FROM roles ORDER BY code"
                )).mappings().all()
                role_permissions = connection.execute(text(
                    "SELECT roles.code, role_permissions.permission_code "
                    "FROM role_permissions JOIN roles ON roles.id = role_permissions.role_id "
                    "ORDER BY roles.code, role_permissions.permission_code"
                )).all()
                management_tokens = connection.scalar(text("SELECT count(*) FROM auth_management_tokens"))
                admin_audit_events = connection.scalar(text("SELECT count(*) FROM admin_audit_events"))
                server_version = connection.scalar(text("SHOW server_version"))
            profile_columns = {column["name"] for column in inspector.get_columns("users")}
            employee_profile_columns = {column["name"] for column in inspector.get_columns("employee_profiles")}
            role_columns = {column["name"] for column in inspector.get_columns("roles")}
            required = {"department", "job_title", "employment_start_date", "employment_status"}
            expected_permissions = {
                (role, permission)
                for role, permissions in EXPECTED_BUILTIN_PERMISSIONS.items()
                for permission in permissions
            }
            actual_permissions = set(role_permissions)
            if (revision != HEAD_REVISION or user_count != 0 or user_role_count != 0
                    or workflow_count != 0 or employee_count != 0 or not required <= profile_columns
                    or not {"activation_pending", "session_version"} <= profile_columns
                    or not {"user_code", "display_name", "user_id", "employment_status"} <= employee_profile_columns
                    or not {"is_builtin", "status"} <= role_columns
                    or not {"role_permissions", "auth_management_tokens", "admin_audit_events"} <= set(inspector.get_table_names())
                    or management_tokens != 0 or admin_audit_events != 0
                    or actual_permissions != expected_permissions):
                raise AssertionError("Empty PostgreSQL upgrade did not reach the expected head/schema.")
            if [(row["code"], row["is_builtin"], row["status"]) for row in role_rows] != [
                ("ADMIN", True, "ACTIVE"), ("CHECKER", True, "ACTIVE"), ("MAKER", True, "ACTIVE"),
            ]:
                raise AssertionError(f"Unexpected built-in role catalog after empty upgrade: {role_rows!r}")
            print(json.dumps({
                "status": "PASS", "revision": revision, "users": user_count,
                "user_roles": user_role_count, "workflow_plans": workflow_count,
                "employee_profiles": employee_count,
                "role_codes": [row["code"] for row in role_rows],
                "profile_columns": sorted(required | {"activation_pending", "session_version"}),
                "role_permission_rows": len(actual_permissions),
                "management_tokens": management_tokens, "admin_audit_events": admin_audit_events,
                "postgres_version": server_version,
            }))
            return 0

        if mode == "seed-legacy":
            run_id = args.run_id
            maker_id, checker_id, plan_id, version_id, event_id = [str(uuid4()) for _ in range(5)]
            marker = run_id[:10].upper()
            with engine.begin() as connection:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
                if revision != PRE_EMPLOYEE_REVISION:
                    raise AssertionError(
                        f"Expected the pre-employee revision {PRE_EMPLOYEE_REVISION}; got {revision!r}."
                    )
                roles = dict(connection.execute(text(
                    "SELECT code, id::text FROM roles WHERE code IN ('MAKER','CHECKER','ADMIN')"
                )).all())
                if set(roles) != {"MAKER", "CHECKER", "ADMIN"}:
                    raise AssertionError("Pre-profile migration did not seed the built-in role catalog.")
                for user_id, suffix, role_code in (
                    (maker_id, "maker", "MAKER"), (checker_id, "checker", "CHECKER"),
                ):
                    connection.execute(text("""
                        INSERT INTO users
                            (id, user_code, username, email, phone, password_hash, display_name, status)
                        VALUES (CAST(:id AS uuid), :code, :username, :email, NULL,
                                :password_hash, :display_name, 'ACTIVE')
                    """), {
                        "id": user_id, "code": f"PG{marker}{suffix[:1].upper()}",
                        "username": f"pg_{marker.lower()}_{suffix}",
                        "email": f"pg_{marker.lower()}_{suffix}@example.invalid",
                        "password_hash": "synthetic-not-authenticated",
                        "display_name": f"Synthetic legacy {suffix}",
                    })
                    connection.execute(text("""
                        INSERT INTO user_roles (user_id, role_id)
                        VALUES (CAST(:user_id AS uuid), CAST(:role_id AS uuid))
                    """), {"user_id": user_id, "role_id": roles[role_code]})
                payload = json.dumps({
                    "title": f"Synthetic preserved workflow {marker}",
                    "objective": "Migration preservation fixture.",
                    "summary": "Synthetic data only.",
                }, separators=(",", ":"))
                connection.execute(text("""
                    INSERT INTO auth_workflow_plans
                        (id, code, maker_id, checker_id, payload, creation_idempotency_key,
                         creation_request_hash, status, processing_stage, current_version,
                         current_round, revision, decision_reason)
                    VALUES (CAST(:id AS uuid), :code, CAST(:maker AS uuid), CAST(:checker AS uuid),
                            CAST(:payload AS json), :intent, :request_hash, 'PENDING_APPROVAL',
                            'HUMAN_REVIEW_REQUIRED', 1, 1, 1, NULL)
                """), {
                    "id": plan_id, "code": f"LEGACY-{marker}", "maker": maker_id,
                    "checker": checker_id, "payload": payload,
                    "intent": f"synthetic:{run_id}", "request_hash": hashlib.sha256(run_id.encode()).hexdigest(),
                })
                connection.execute(text("""
                    INSERT INTO auth_workflow_versions
                        (id, plan_id, version_number, round_number, payload_snapshot,
                         attachment_snapshot, snapshot_hash, submitted_by)
                    VALUES (CAST(:id AS uuid), CAST(:plan AS uuid), 1, 1,
                            CAST(:payload AS json), CAST(:attachments AS json), :snapshot_hash,
                            CAST(:maker AS uuid))
                """), {
                    "id": version_id, "plan": plan_id, "payload": payload,
                    "attachments": "[]", "snapshot_hash": hashlib.sha256(payload.encode()).hexdigest(),
                    "maker": maker_id,
                })
                connection.execute(text("""
                    INSERT INTO auth_workflow_events
                        (id, plan_id, actor_id, actor_type, sequence_number, action,
                         status_before, status_after, details)
                    VALUES (CAST(:id AS uuid), CAST(:plan AS uuid), CAST(:maker AS uuid),
                            'HUMAN', 1, 'SUBMITTED', 'DRAFT', 'PENDING_APPROVAL',
                            CAST(:details AS json))
                """), {
                    "id": event_id, "plan": plan_id, "maker": maker_id,
                    "details": json.dumps({"version": 1, "round": 1, "synthetic": True}),
                })
            snapshot = _legacy_snapshot(engine, [maker_id, checker_id], plan_id)
            snapshot.update({
                "status": "SEEDED_PRE_PROFILE_HEAD", "revision": revision,
                "ids": {"maker": maker_id, "checker": checker_id, "plan": plan_id},
                "marker": marker,
            })
            snapshot_path = Path(args.snapshot)
            _write_text(snapshot_path, json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"status": "PASS", "snapshot_file": str(snapshot_path),
                              "user_count": len(snapshot["users"]), "workflow_plan_count": len(snapshot["plans"])}))
            return 0

        if mode == "verify-legacy":
            before = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
            after = _legacy_snapshot(engine, [before["ids"]["maker"], before["ids"]["checker"]], before["ids"]["plan"])
            if after != {key: before[key] for key in after}:
                raise AssertionError("Synthetic user, role assignment, plan, version, or event changed during migration.")
            inspector = inspect(engine)
            columns = {column["name"] for column in inspector.get_columns("users")}
            role_columns = {column["name"] for column in inspector.get_columns("roles")}
            required = {"department", "job_title", "employment_start_date", "employment_status"}
            if (not required <= columns or not {"activation_pending", "session_version"} <= columns
                    or not {"is_builtin", "status"} <= role_columns):
                raise AssertionError("Employee profile columns are missing after upgrade.")
            with engine.connect() as connection:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
                profiles = connection.execute(text("""
                    SELECT user_code, user_id::text AS user_id, department, job_title,
                           employment_start_date, employment_status
                    FROM employee_profiles WHERE user_id IN (CAST(:maker AS uuid), CAST(:checker AS uuid))
                    ORDER BY user_code
                """), {"maker": before["ids"]["maker"], "checker": before["ids"]["checker"]}).mappings().all()
                account_defaults = connection.execute(text("""
                    SELECT activation_pending, session_version FROM users
                    WHERE id IN (CAST(:maker AS uuid), CAST(:checker AS uuid))
                """), {"maker": before["ids"]["maker"], "checker": before["ids"]["checker"]}).all()
                builtin_roles = connection.execute(text(
                    "SELECT code, is_builtin, status FROM roles ORDER BY code"
                )).all()
                permission_rows = connection.execute(text(
                    "SELECT roles.code, role_permissions.permission_code "
                    "FROM role_permissions JOIN roles ON roles.id = role_permissions.role_id"
                )).all()
                tokens_count = connection.scalar(text("SELECT count(*) FROM auth_management_tokens"))
                audit_count = connection.scalar(text("SELECT count(*) FROM admin_audit_events"))
                server_version = connection.scalar(text("SHOW server_version"))
            if (revision != HEAD_REVISION or len(profiles) != 2 or len(account_defaults) != 2
                    or any(pending or version != 0 for pending, version in account_defaults)
                    or builtin_roles != [("ADMIN", True, "ACTIVE"), ("CHECKER", True, "ACTIVE"),
                                         ("MAKER", True, "ACTIVE")]
                    or tokens_count != 0 or audit_count != 0):
                raise AssertionError(f"Legacy upgrade did not reach {HEAD_REVISION}: {revision!r}.")
            if any(row["user_id"] not in {before["ids"]["maker"], before["ids"]["checker"]}
                   or row["department"] is not None or row["job_title"] is not None
                   or row["employment_start_date"] is not None or row["employment_status"] != "ACTIVE"
                   for row in profiles):
                raise AssertionError("Unknown employee fields were not kept null/defaulted.")
            actual_permissions = set(permission_rows)
            expected_permissions = {
                (role, permission)
                for role, permissions in EXPECTED_BUILTIN_PERMISSIONS.items()
                for permission in permissions
            }
            if actual_permissions != expected_permissions:
                raise AssertionError("Built-in role permissions were not migrated as expected.")
            print(json.dumps({
                "status": "PASS", "revision": revision,
                "preserved": ["users", "roles", "user_roles", "auth_workflow_plans",
                              "auth_workflow_versions", "auth_workflow_events", "employee_profiles"],
                "employee_profiles_backfilled": len(profiles),
                "unknown_profile_fields_null": True,
                "employment_status_default": "ACTIVE",
                "account_defaults_preserved": True,
                "builtin_roles_marked_and_active": True,
                "role_permission_rows": len(actual_permissions),
                "management_tokens": tokens_count, "admin_audit_events": audit_count,
                "postgres_version": server_version,
            }))
            return 0

        if mode == "directory":
            result = _verify_directory(engine, os.environ["AUTH_SEED_PASSWORD"])
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if mode == "employee-admin":
            result = _verify_employee_account_lifecycle(engine, os.environ["AUTH_SEED_PASSWORD"])
            print(json.dumps(result, ensure_ascii=False))
            return 0
        raise RuntimeError(f"Unsupported helper mode: {mode}")
    finally:
        engine.dispose()


def _legacy_snapshot(engine, user_ids: list[str], plan_id: str) -> dict:
    from sqlalchemy import text

    with engine.connect() as connection:
        users = connection.execute(text("""
            SELECT id::text AS id, user_code, username, email, phone, display_name, status
            FROM users WHERE id IN (CAST(:maker AS uuid), CAST(:checker AS uuid)) ORDER BY username
        """), {"maker": user_ids[0], "checker": user_ids[1]}).mappings().all()
        assignments = connection.execute(text("""
            SELECT ur.user_id::text AS user_id, r.code AS role_code, ur.assigned_by::text AS assigned_by
            FROM user_roles ur JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id IN (CAST(:maker AS uuid), CAST(:checker AS uuid))
            ORDER BY ur.user_id::text, r.code
        """), {"maker": user_ids[0], "checker": user_ids[1]}).mappings().all()
        role_codes = connection.scalars(text("SELECT code FROM roles ORDER BY code")).all()
        plans = connection.execute(text("""
            SELECT id::text AS id, code, maker_id::text AS maker_id, checker_id::text AS checker_id,
                   payload, creation_idempotency_key, creation_request_hash, status,
                   processing_stage, current_version, current_round, revision, decision_reason
            FROM auth_workflow_plans WHERE id = CAST(:plan AS uuid)
        """), {"plan": plan_id}).mappings().all()
        versions = connection.execute(text("""
            SELECT id::text AS id, plan_id::text AS plan_id, version_number, round_number,
                   payload_snapshot, attachment_snapshot, snapshot_hash, submitted_by::text AS submitted_by
            FROM auth_workflow_versions WHERE plan_id = CAST(:plan AS uuid)
        """), {"plan": plan_id}).mappings().all()
        events = connection.execute(text("""
            SELECT id::text AS id, plan_id::text AS plan_id, actor_id::text AS actor_id,
                   actor_type, sequence_number, action, status_before, status_after, details
            FROM auth_workflow_events WHERE plan_id = CAST(:plan AS uuid)
        """), {"plan": plan_id}).mappings().all()
    normalize = lambda rows: [
        {key: (dict(value) if hasattr(value, "items") else list(value) if isinstance(value, tuple) else value)
         for key, value in row.items()}
        for row in rows
    ]
    return {
        "users": normalize(users), "role_codes": list(role_codes),
        "role_assignments": normalize(assignments), "plans": normalize(plans),
        "versions": normalize(versions), "events": normalize(events),
    }


def _verify_directory(engine, password: str) -> dict:
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session, sessionmaker
    from src.backend.api.app import create_app
    from src.backend.api.auth import get_auth_db
    from src.backend.api.dependencies import Settings
    from src.backend.api.errors import error_response
    from src.backend.db.models import AuthWorkflowEvent, EmployeeProfile, Role, User, UserRole
    from src.backend.db.security import hash_password

    if not password:
        raise RuntimeError("Directory API verification requires the run's synthetic password.")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    run_marker = uuid4().hex[:8]
    ids = {}
    profiles = (
        ("maker-a", "MAKER", "ACTIVE", "ACTIVE", "Operations Synthetic", "Campaign Planner"),
        ("maker-b", "MAKER", "ACTIVE", "ACTIVE", "Operations Synthetic", "Campaign Planner"),
        ("inactive-checker", "CHECKER", "ACTIVE", "INACTIVE", "Sales Synthetic", "Team Lead"),
        ("locked-checker", "CHECKER", "DISABLED", "ACTIVE", "Sales Synthetic", "Reviewer"),
    )
    with factory.begin() as session:
        roles = {item.code: item for item in session.scalars(select(Role)).all()}
        if not {"MAKER", "CHECKER", "ADMIN"} <= set(roles):
            raise AssertionError("Required role catalog is missing in PostgreSQL.")
        for suffix, role_code, account_status, employee_status, department, title in profiles:
            user_id = uuid4()
            employee_id = uuid4()
            ids[suffix] = str(employee_id)
            user = User(
                id=user_id,
                user_code=f"PG{run_marker.upper()}{suffix[:1].upper()}{len(ids)}",
                username=f"pgverify_{run_marker}_{suffix.replace('-', '_')}",
                email=f"pgverify_{run_marker}_{suffix.replace('-', '_')}@example.invalid",
                phone=None,
                password_hash=hash_password(password),
                display_name=f"Synthetic {suffix}",
                department=department,
                job_title=title,
                employment_status=employee_status,
                status=account_status,
            )
            session.add(user)
            session.flush()
            session.add(EmployeeProfile(
                id=employee_id, user_code=user.user_code, display_name=user.display_name,
                email=user.email, phone=user.phone, department=department, job_title=title,
                employment_status=employee_status, user_id=user.id,
            ))
            session.add(UserRole(user_id=user.id, role_id=roles[role_code].id))

    app = create_app(Settings(app_env="demo", cors_origins=("http://127.0.0.1:5173",)))

    def database_dependency():
        with factory() as session:
            yield session

    app.dependency_overrides[get_auth_db] = database_dependency
    with factory() as session:
        events_before = session.scalar(select(func.count(AuthWorkflowEvent.id))) or 0
    try:
        with TestClient(app) as anonymous:
            anonymous_status = anonymous.get("/api/workflow/employees").status_code
        with TestClient(app) as maker, TestClient(app) as checker, TestClient(app) as admin:
            maker_login = maker.post("/api/auth/login", json={"identifier": "maker", "password": password})
            checker_login = checker.post("/api/auth/login", json={"identifier": "checker", "password": password})
            admin_login = admin.post("/api/auth/login", json={"identifier": "admin", "password": password})
            if (maker_login.status_code != 200 or checker_login.status_code != 200
                    or admin_login.status_code != 200):
                raise AssertionError("Could not authenticate the synthetic E2E Maker/Checker/Admin accounts.")
            maker_status = maker.get("/api/workflow/employees").status_code
            checker_status = checker.get("/api/workflow/employees").status_code
            admin_page = admin.get("/api/workflow/employees", params={"limit": 1})
            admin_status = admin_page.status_code
            filters = {
                "query": run_marker.upper(), "role": "MAKER", "status": "ACTIVE",
                "department": "operations synthetic", "job_title": "campaign planner",
                "employment_status": "ACTIVE", "limit": 1,
            }
            first_response = admin.get("/api/workflow/employees", params={**filters, "offset": 0})
            second_response = admin.get("/api/workflow/employees", params={**filters, "offset": 1})
            inactive_response = admin.get("/api/workflow/employees", params={
                "query": run_marker.upper(), "role": "CHECKER", "status": "ACTIVE",
                "employment_status": "INACTIVE",
            })
            locked_response = admin.get("/api/workflow/employees", params={
                "query": run_marker.upper(), "role": "CHECKER", "status": "DISABLED",
                "employment_status": "ACTIVE",
            })
            checker_picker_response = maker.get("/api/workflow/checkers")
            if anonymous_status != 401 or maker_status != 403 or checker_status != 403:
                raise AssertionError("Employee directory did not enforce anonymous/Admin authorization.")
            if admin_status != 200 or admin_page.status_code != 200:
                raise AssertionError("Admin could not access the employee directory.")
            for label, response in (
                ("Admin employee page", admin_page),
                ("Admin employee search page 1", first_response),
                ("Admin employee search page 2", second_response),
                ("Admin inactive employee filter", inactive_response),
                ("Admin disabled account filter", locked_response),
                ("Maker checker picker", checker_picker_response),
            ):
                _require_status(response, label)
            admin_page_payload = _employee_page_payload(admin_page, "Admin employee page")
            first = _employee_page_payload(first_response, "Admin employee search page 1")
            second = _employee_page_payload(second_response, "Admin employee search page 2")
            inactive = _employee_page_payload(inactive_response, "Admin inactive employee filter")
            locked = _employee_page_payload(locked_response, "Admin disabled account filter")
            selectable = _checker_list_payload(checker_picker_response, "Maker checker picker")
            if admin_page_payload["offset"] != 0 or admin_page_payload["limit"] != 1:
                raise AssertionError("Admin employee page did not honor the requested offset/limit.")
            if (first["offset"] != 0 or second["offset"] != 1
                    or first["limit"] != 1 or second["limit"] != 1):
                raise AssertionError("Employee directory did not preserve the requested pagination metadata.")
            if first.get("total") != 2 or second.get("total") != 2 or len(first.get("items", [])) != 1:
                raise AssertionError("Employee directory search/filter/pagination returned unexpected results.")
            if len(second.get("items", [])) != 1 or first["items"][0]["id"] == second["items"][0]["id"]:
                raise AssertionError("Employee directory offset pagination repeated or omitted a row.")
            if inactive.get("total") != 1 or locked.get("total") != 1:
                raise AssertionError("Employee and account status filters did not remain distinct.")
            selected_ids = {item["id"] for item in selectable}
            if ids["inactive-checker"] in selected_ids or ids["locked-checker"] in selected_ids:
                raise AssertionError("Inactive employee or disabled account remained a selectable Checker.")
            if any("password_hash" in item for item in first["items"]):
                raise AssertionError("Employee directory exposed an authentication secret field.")
        with factory() as session:
            events_after = session.scalar(select(func.count(AuthWorkflowEvent.id))) or 0
        if events_after != events_before:
            raise AssertionError("Read-only directory requests wrote workflow audit events.")
    finally:
        app.dependency_overrides.clear()
    return {
        "status": "PASS", "authorization": {
            "anonymous": anonymous_status, "maker": maker_status,
            "checker": checker_status, "admin": admin_status,
        },
        "filters": ["search", "role", "account_status", "department", "job_title", "employment_status"],
        "pagination": "offset/limit returned distinct rows with total=2",
        "inactive_and_locked_checkers_excluded": True,
        "safe_response_fields": True,
        "workflow_event_count_unchanged": True,
        "synthetic_records": 4,
    }


def _verify_employee_account_lifecycle(engine, password: str) -> dict:
    """Exercise new employee/account/token/reassignment behavior against PostgreSQL."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Barrier, Lock

    from fastapi.testclient import TestClient
    from sqlalchemy import func, select
    from sqlalchemy.orm import sessionmaker

    from src.backend.api.app import create_app
    from src.backend.api.auth import get_auth_db
    from src.backend.api.auth_workflow_schemas import (
        AccountHandoverResponse, EmployeeAccountCreateResponse, WorkflowEmployeeResponse,
    )
    from src.backend.api.dependencies import Settings
    from src.backend.db.models import (
        AdminAuditEvent, AuthManagementToken, AuthWorkflowEvent, AuthWorkflowPlan,
        EmployeeProfile, Role, User, UserRole,
    )
    from src.backend.db.security import hash_password, verify_password

    if not password:
        raise RuntimeError("Employee/account PostgreSQL verification requires the run's synthetic password.")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    run_marker = uuid4().hex[:8]
    seeded_employee_ids: dict[str, UUID] = {}
    seeded_account_ids: dict[str, UUID] = {}
    seeded_usernames: dict[str, str] = {}
    role_codes = {"admin": "ADMIN", "departing_checker": "CHECKER", "maker": "MAKER",
                  "replacement_checker": "CHECKER", "locked_checker": "CHECKER",
                  "locked_maker": "MAKER"}
    with factory.begin() as session:
        roles = {role.code: role for role in session.scalars(select(Role)).all()}
        for suffix, role_code in role_codes.items():
            account_id = uuid4()
            employee_id = uuid4()
            seeded_account_ids[suffix] = account_id
            seeded_employee_ids[suffix] = employee_id
            code = f"EMP{run_marker.upper()}{len(seeded_employee_ids):02d}"
            username = _employee_admin_login_payload(run_marker, suffix, password)["identifier"]
            seeded_usernames[suffix] = username
            user = User(
                id=account_id, user_code=code, username=username,
                email=f"pgemp_{run_marker}_{suffix}@example.invalid", phone=None,
                password_hash=hash_password(password), display_name=f"Synthetic {suffix}", status="ACTIVE",
                employment_status="ACTIVE", activation_pending=False, session_version=0,
            )
            session.add(user)
            session.flush()
            session.add(EmployeeProfile(
                id=employee_id, user_code=code, display_name=user.display_name, email=user.email,
                employment_status="ACTIVE", user_id=account_id,
            ))
            session.add(UserRole(user_id=account_id, role_id=roles[role_code].id))
    with factory.begin() as session:
        for suffix, checker_suffix, maker_suffix in (
            ("deactivation", "departing_checker", "maker"),
            ("lock", "locked_checker", "locked_maker"),
        ):
            session.add(AuthWorkflowPlan(
                code=f"PG-EMP-{run_marker}-{suffix}", maker_id=seeded_account_ids[maker_suffix],
                checker_id=seeded_account_ids[checker_suffix], payload={}, status="PENDING_APPROVAL",
                processing_stage="HUMAN_REVIEW_REQUIRED",
            ))

    app = create_app(Settings(app_env="demo", cors_origins=("http://127.0.0.1:5173",)))

    concurrent_request_sessions = {}
    concurrent_transactions = {}
    concurrent_backend_exceptions = {}
    concurrency_evidence_lock = Lock()
    login_validation_sensitive_values = {}
    login_validation_diagnostics = {}

    database_dependency = _make_employee_admin_database_dependency(
        factory, concurrent_request_sessions, concurrent_transactions, concurrency_evidence_lock,
    )
    app.dependency_overrides[get_auth_db] = database_dependency

    _install_employee_admin_diagnostic_handlers(
        app, concurrent_backend_exceptions, concurrency_evidence_lock,
        login_validation_sensitive_values, login_validation_diagnostics,
    )

    def login_with_safe_diagnostics(client, identifier: str, login_password: str,
                                    request_id: str, label: str):
        login_validation_sensitive_values[request_id] = (login_password, identifier)
        response = client.post(
            "/api/auth/login", json=_auth_login_payload(identifier, login_password),
            headers={"X-Verification-Request": request_id},
        )
        _require_synthetic_login(
            response, label,
            validation_details=login_validation_diagnostics.get(request_id, ()),
        )
        return response

    checkers = []
    try:
        with (TestClient(app) as admin,
              TestClient(app) as departing_checker,
              TestClient(app) as recipient,
              TestClient(app) as replacement_checker,
              TestClient(app, raise_server_exceptions=False) as concurrent_client_one,
              TestClient(app, raise_server_exceptions=False) as concurrent_client_two):
            for client, suffix in ((admin, "admin"), (departing_checker, "departing_checker"),
                                   (replacement_checker, "replacement_checker")):
                request_id = f"synthetic-login-{suffix}"
                login_with_safe_diagnostics(
                    client, seeded_usernames[suffix], password,
                    request_id, f"synthetic {suffix} login",
                )

            # Account activation is Admin-issued, single use, recipient-password chosen, and hash-only at rest.
            created = admin.post("/api/workflow/employees", json={
                "user_code": f"NEW{run_marker.upper()}", "display_name": "Synthetic New Employee",
                "email": f"new_{run_marker}@example.invalid", "phone": None,
                "department": None, "job_title": None, "employment_start_date": None,
            })
            created_payload = _response_payload(
                created, "Admin employee profile create", expected_status=201,
            )
            try:
                created_profile = WorkflowEmployeeResponse.model_validate(created_payload)
                new_employee_id = str(UUID(created_profile.id))
            except (TypeError, ValueError):
                raise AssertionError(
                    "Employee profile create returned an invalid synthetic employee response schema."
                ) from None
            if created_profile.account_id is not None:
                raise AssertionError(
                    "New employee profile unexpectedly had an account before account creation "
                    f"(employee_id={new_employee_id})."
                )
            with factory() as session:
                created_profile_row = session.get(EmployeeProfile, UUID(new_employee_id))
                if created_profile_row is None or created_profile_row.user_id is not None:
                    raise AssertionError(
                        "Employee profile create was not visible from an independent PostgreSQL session "
                        f"(employee_id={new_employee_id}, profile_found={created_profile_row is not None}, "
                        f"account_linked={created_profile_row.user_id is not None if created_profile_row else False})."
                    )
            account = admin.post(f"/api/workflow/employees/{new_employee_id}/account", json={
                "username": f"new_{run_marker}",
            })
            account_payload = _response_payload(
                account, "Admin issue activation link", expected_status=201,
            )
            try:
                created_account = EmployeeAccountCreateResponse.model_validate(account_payload)
            except (TypeError, ValueError):
                raise AssertionError(
                    "Employee account create returned an invalid synthetic account response schema."
                ) from None
            response_employee_id, new_account_id = _employee_account_ids(
                created_profile.model_dump(mode="json"), created_account.model_dump(mode="json"),
            )
            if response_employee_id != new_employee_id:
                raise AssertionError(
                    "Account create response did not preserve the synthetic employee profile ID "
                    f"(employee_id={new_employee_id}, response_employee_id={response_employee_id})."
                )
            activation_token = created_account.handover_token
            activation_token_hash = hashlib.sha256(activation_token.encode("utf-8")).hexdigest()
            with factory() as session:
                linked_profile = session.get(EmployeeProfile, UUID(new_employee_id))
                linked_account = _require_account_visible_from_session(
                    session, User, employee_id=new_employee_id, account_id=new_account_id,
                    label="Account create independent-session check",
                )
                activation_row = session.scalar(select(AuthManagementToken).where(
                    AuthManagementToken.token_hash == activation_token_hash,
                ))
                if linked_profile is None:
                    raise AssertionError(
                        "Employee profile disappeared after account creation "
                        f"(employee_id={new_employee_id}, account_id={new_account_id})."
                    )
                if linked_profile.user_id != UUID(new_account_id):
                    linked_account_id = str(linked_profile.user_id) if linked_profile.user_id else None
                    raise AssertionError(
                        "Account create did not persist the API-reported profile/account link "
                        f"(employee_id={new_employee_id}, response_account_id={new_account_id}, "
                        f"linked_account_id={linked_account_id})."
                    )
                if (linked_account.status != "DISABLED" or not linked_account.activation_pending
                        or activation_row is None or activation_row.user_id != UUID(new_account_id)
                        or activation_row.purpose != "ACTIVATE"):
                    raise AssertionError(
                        "Account create state/token did not match the pending activation contract "
                        f"(employee_id={new_employee_id}, account_id={new_account_id}, "
                        f"token_found={activation_row is not None}, "
                        f"token_account_matches={activation_row.user_id == UUID(new_account_id) if activation_row else False}, "
                        f"token_purpose={activation_row.purpose if activation_row else None})."
                    )

            def require_management_token_owner(
                raw_token: str, purpose: str, label: str, *,
                expected_employee_id: str | UUID | None = None,
                expected_account_id: str | UUID | None = None,
                expected_consumed: bool | None = None,
            ) -> str:
                token_employee_id = UUID(str(expected_employee_id or new_employee_id))
                token_account_id = UUID(str(expected_account_id or new_account_id))
                token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
                with factory() as verification_session:
                    token_row = verification_session.scalar(select(AuthManagementToken).where(
                        AuthManagementToken.token_hash == token_hash,
                    ))
                    if (token_row is None or token_row.user_id != token_account_id
                            or token_row.purpose != purpose):
                        raise AssertionError(
                            f"{label} token is not linked to the expected synthetic account and purpose "
                            f"(employee_id={token_employee_id}, account_id={token_account_id}, "
                            f"token_found={token_row is not None}, "
                            f"token_account_matches={token_row.user_id == token_account_id if token_row else False}, "
                            f"token_purpose={token_row.purpose if token_row else None}, "
                            f"expected_account_id={token_account_id}, expected_purpose={purpose})."
                        )
                    if (expected_consumed is not None
                            and (token_row.consumed_at is not None) != expected_consumed):
                        raise AssertionError(
                            f"{label} token had an unexpected consumed state "
                            f"(employee_id={token_employee_id}, account_id={token_account_id}, "
                            f"expected_consumed={expected_consumed})."
                        )
                return token_hash

            require_management_token_owner(
                activation_token, "ACTIVATE", "Initial activation",
                expected_consumed=False,
            )
            initial_activation_token = activation_token
            activation_renewal = admin.post(
                f"/api/workflow/employees/{new_employee_id}/account/activation",
            )
            activation_renewal_payload = _response_payload(
                activation_renewal, "Admin reissue activation link",
            )
            try:
                activation_renewal_response = AccountHandoverResponse.model_validate(
                    activation_renewal_payload,
                )
            except (TypeError, ValueError):
                raise AssertionError("Activation reissue returned an invalid handover response schema.") from None
            if activation_renewal_response.purpose != "ACTIVATE":
                raise AssertionError("Reissued activation link lost its purpose contract.")
            activation_token = activation_renewal_response.handover_token
            activation_hash = require_management_token_owner(
                activation_token, "ACTIVATE", "Reissued activation", expected_consumed=False,
            )
            initial_activation_hash = hashlib.sha256(
                initial_activation_token.encode("utf-8"),
            ).hexdigest()
            with factory() as session:
                previous_activation_row = session.scalar(select(AuthManagementToken).where(
                    AuthManagementToken.token_hash == initial_activation_hash,
                ))
                if previous_activation_row is None or previous_activation_row.consumed_at is None:
                    raise AssertionError(
                        "Activation reissue did not invalidate the prior synthetic token "
                        f"(employee_id={new_employee_id}, account_id={new_account_id})."
                    )
            stale_activation = recipient.post("/api/auth/activate", json={
                "token": initial_activation_token, "password": "Old-activation-password-123!",
            })
            if stale_activation.status_code < 400:
                raise AssertionError("Reissuing an ACTIVATE link did not invalidate its predecessor.")
            with factory() as session:
                stored_activations = session.scalars(select(AuthManagementToken).where(
                    AuthManagementToken.token_hash.in_({
                        hashlib.sha256(raw.encode("utf-8")).hexdigest()
                        for raw in (initial_activation_token, activation_token)
                    }),
                )).all()
                stored_activation = next((row for row in stored_activations if row.token_hash == activation_hash), None)
                if (len(stored_activations) != 2 or stored_activation is None
                        or any(row.token_hash in (initial_activation_token, activation_token)
                               for row in stored_activations)):
                    raise AssertionError("Activation token was not stored exclusively as its SHA-256 digest.")
                remaining = stored_activation.expires_at - datetime.now(timezone.utc)
                if not timedelta(minutes=29) <= remaining <= timedelta(minutes=30, seconds=2):
                    raise AssertionError("Activation token expiry is not 30 minutes from issuance.")
            recipient_password = "Recipient-chosen-Secure-123!"
            activated = recipient.post("/api/auth/activate", json={
                "token": activation_token, "password": recipient_password,
            })
            _require_status(activated, "recipient activation", expected_status=204)
            activation_hash = require_management_token_owner(
                activation_token, "ACTIVATE", "Consumed activation", expected_consumed=True,
            )
            with factory() as session:
                activated_user = _require_account_visible_from_session(
                    session, User, employee_id=new_employee_id, account_id=new_account_id,
                    label="Activated account independent-session check",
                )
                if (activated_user.status != "ACTIVE"
                        or activated_user.activation_pending):
                    raise AssertionError(
                        "Successful activation did not update the linked synthetic account "
                        f"(employee_id={new_employee_id}, account_id={new_account_id}, "
                        f"activation_pending={activated_user.activation_pending})."
                    )
            replay_activation = recipient.post("/api/auth/activate", json={
                "token": activation_token, "password": "Different-secure-password-456!",
            })
            if replay_activation.status_code < 400:
                raise AssertionError("An activation link was accepted more than once.")
            login_with_safe_diagnostics(
                recipient, f"new_{run_marker}", recipient_password,
                "activated-recipient-login", "activated recipient login",
            )

            # Re-issuing invalidates only the earlier RESET token; successful consumption revokes old sessions.
            first_reset = admin.post(f"/api/workflow/employees/{new_employee_id}/account/password-reset")
            first_reset_payload = _response_payload(
                first_reset, "first password-reset link", expected_status=200,
            )
            try:
                first_reset_response = AccountHandoverResponse.model_validate(first_reset_payload)
            except (TypeError, ValueError):
                raise AssertionError("First password reset returned an invalid handover response schema.") from None
            if first_reset_response.purpose != "RESET":
                raise AssertionError("First password-reset link did not have RESET purpose.")
            first_reset_token = first_reset_response.handover_token
            first_reset_hash = require_management_token_owner(
                first_reset_token, "RESET", "First password reset", expected_consumed=False,
            )
            second_reset = admin.post(f"/api/workflow/employees/{new_employee_id}/account/password-reset")
            second_reset_payload = _response_payload(
                second_reset, "replacement password-reset link", expected_status=200,
            )
            try:
                second_reset_response = AccountHandoverResponse.model_validate(second_reset_payload)
            except (TypeError, ValueError):
                raise AssertionError("Replacement password reset returned an invalid handover response schema.") from None
            if second_reset_response.purpose != "RESET":
                raise AssertionError("Replacement password-reset link did not have RESET purpose.")
            second_reset_token = second_reset_response.handover_token
            second_reset_hash = require_management_token_owner(
                second_reset_token, "RESET", "Replacement password reset", expected_consumed=False,
            )
            with factory() as session:
                previous_reset_row = session.scalar(select(AuthManagementToken).where(
                    AuthManagementToken.token_hash == first_reset_hash,
                ))
                if previous_reset_row is None or previous_reset_row.consumed_at is None:
                    raise AssertionError(
                        "Password-reset reissue did not invalidate the prior synthetic token "
                        f"(employee_id={new_employee_id}, account_id={new_account_id})."
                    )
            stale_reset = recipient.post("/api/auth/activate", json={
                "token": first_reset_token, "password": "Reset-password-should-not-work-123!",
            })
            if stale_reset.status_code < 400:
                raise AssertionError("Reissuing a RESET link did not invalidate its predecessor.")
            if recipient.get("/api/auth/me").status_code != 200:
                raise AssertionError("Issuing a reset link revoked the current session before password reset completed.")
            completed_reset = recipient.post("/api/auth/activate", json={
                "token": second_reset_token, "password": "Reset-password-completed-123!",
            })
            _require_status(completed_reset, "recipient password reset", expected_status=204)
            require_management_token_owner(
                second_reset_token, "RESET", "Consumed password reset", expected_consumed=True,
            )
            if recipient.get("/api/auth/me").status_code != 401:
                raise AssertionError("Successful password reset did not revoke all prior sessions.")
            replay_reset = recipient.post("/api/auth/activate", json={
                "token": second_reset_token, "password": "Reset-password-replay-123!",
            })
            if replay_reset.status_code < 400:
                raise AssertionError("A password-reset link was accepted more than once.")

            purpose_constraint_reset = admin.post(
                f"/api/workflow/employees/{new_employee_id}/account/password-reset",
            )
            purpose_constraint_payload = _response_payload(
                purpose_constraint_reset, "purpose-constraint password-reset fixture", expected_status=200,
            )
            try:
                purpose_constraint_response = AccountHandoverResponse.model_validate(purpose_constraint_payload)
            except (TypeError, ValueError):
                raise AssertionError("Purpose-constraint fixture returned an invalid handover response schema.") from None
            if purpose_constraint_response.purpose != "RESET":
                raise AssertionError("Purpose-constraint fixture did not issue a valid RESET token.")
            purpose_constraint_token = purpose_constraint_response.handover_token
            purpose_constraint_hash = require_management_token_owner(
                purpose_constraint_token, "RESET", "Purpose-constraint fixture before DB check",
                expected_consumed=False,
            )
            with factory() as session:
                before_purpose_constraint_user = _require_account_visible_from_session(
                    session, User, employee_id=new_employee_id, account_id=new_account_id,
                    label="Account before purpose-constraint check",
                )
                before_purpose_constraint_password_hash = before_purpose_constraint_user.password_hash
                before_purpose_constraint_session_version = before_purpose_constraint_user.session_version
                before_purpose_constraint_audit_count = session.scalar(select(func.count(AdminAuditEvent.id)).where(
                    AdminAuditEvent.employee_id == new_employee_id,
                    AdminAuditEvent.action == "PASSWORD_RESET_COMPLETED",
                ))
            with factory() as session:
                purpose_constraint_row = session.scalar(select(AuthManagementToken).where(
                    AuthManagementToken.token_hash == purpose_constraint_hash,
                ).with_for_update())
                if purpose_constraint_row is None or purpose_constraint_row.purpose != "RESET":
                    raise AssertionError("Purpose-constraint fixture was not found with its valid RESET purpose.")
                purpose_constraint_result = _verify_management_token_purpose_constraint(
                    session, AuthManagementToken, purpose_constraint_row.id,
                )
                after_purpose_constraint_user = _require_account_visible_from_session(
                    session, User, employee_id=new_employee_id, account_id=new_account_id,
                    label="Account after purpose-constraint savepoint rollback",
                )
                after_purpose_constraint_token = session.scalar(select(AuthManagementToken).where(
                    AuthManagementToken.token_hash == purpose_constraint_hash,
                ))
                after_purpose_constraint_audit_count = session.scalar(select(func.count(AdminAuditEvent.id)).where(
                    AdminAuditEvent.employee_id == new_employee_id,
                    AdminAuditEvent.action == "PASSWORD_RESET_COMPLETED",
                ))
                purpose_constraint_state_unchanged = (
                    after_purpose_constraint_user.password_hash == before_purpose_constraint_password_hash
                    and after_purpose_constraint_user.session_version == before_purpose_constraint_session_version
                    and after_purpose_constraint_token is not None
                    and after_purpose_constraint_token.purpose == "RESET"
                    and after_purpose_constraint_token.consumed_at is None
                    and after_purpose_constraint_audit_count == before_purpose_constraint_audit_count
                )
            if not purpose_constraint_state_unchanged:
                raise AssertionError(
                    "Purpose-constraint savepoint rollback changed account, token, or audit state "
                    f"(employee_id={new_employee_id}, account_id={new_account_id})."
                )

            expired_reset = admin.post(f"/api/workflow/employees/{new_employee_id}/account/password-reset")
            expired_reset_payload = _response_payload(
                expired_reset, "expired password-reset fixture", expected_status=200,
            )
            try:
                expired_reset_response = AccountHandoverResponse.model_validate(expired_reset_payload)
            except (TypeError, ValueError):
                raise AssertionError("Expired reset fixture returned an invalid handover response schema.") from None
            if expired_reset_response.purpose != "RESET":
                raise AssertionError("Expired password-reset fixture did not have RESET purpose.")
            expired_token = expired_reset_response.handover_token
            expired_hash = require_management_token_owner(
                expired_token, "RESET", "Expired password reset", expected_consumed=False,
            )
            with factory.begin() as session:
                token = session.scalar(select(AuthManagementToken).where(AuthManagementToken.token_hash == expired_hash).with_for_update())
                token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            expired_response = recipient.post("/api/auth/activate", json={
                "token": expired_token,
                "password": "Expired-password-should-fail-123!",
            })
            if expired_response.status_code < 400:
                raise AssertionError("An expired password-reset link was accepted.")

            # Start with a live recipient session so reset success must revoke it.
            login_with_safe_diagnostics(
                recipient, f"new_{run_marker}", "Reset-password-completed-123!",
                "pre-race-recipient-login", "pre-race recipient login",
            )
            if recipient.get("/api/auth/me").status_code != 200:
                raise AssertionError("Could not establish a live recipient session before concurrent reset.")
            with factory() as session:
                race_user_before = _require_account_visible_from_session(
                    session, User, employee_id=new_employee_id, account_id=new_account_id,
                    label="Activated account before concurrent reset",
                )
                race_session_version_before = race_user_before.session_version
                race_password_hash_before = race_user_before.password_hash
                race_audit_count_before = session.scalar(select(func.count(AdminAuditEvent.id)).where(
                    AdminAuditEvent.employee_id == new_employee_id,
                    AdminAuditEvent.action == "PASSWORD_RESET_COMPLETED",
                ))

            # Two independent HTTP clients and PostgreSQL transactions race to consume one valid token.
            concurrent_reset = admin.post(f"/api/workflow/employees/{new_employee_id}/account/password-reset")
            concurrent_reset_payload = _response_payload(
                concurrent_reset, "concurrent password-reset fixture", expected_status=200,
            )
            try:
                concurrent_reset_response = AccountHandoverResponse.model_validate(
                    concurrent_reset_payload,
                )
            except (TypeError, ValueError):
                raise AssertionError("Concurrent reset fixture returned an invalid handover response schema.") from None
            if concurrent_reset_response.purpose != "RESET":
                raise AssertionError("Concurrent password-reset fixture did not have RESET purpose.")
            concurrent_token = concurrent_reset_response.handover_token
            concurrent_token_hash = require_management_token_owner(
                concurrent_token, "RESET", "Concurrent password reset", expected_consumed=False,
            )
            concurrent_passwords = {
                "token-use-1": "Concurrent-reset-password-1-123!",
                "token-use-2": "Concurrent-reset-password-2-123!",
            }
            concurrent_clients = {
                "token-use-1": concurrent_client_one,
                "token-use-2": concurrent_client_two,
            }
            request_barrier = Barrier(2)

            def consume_concurrently(request_id: str) -> dict:
                response = None
                exception = None
                try:
                    request_barrier.wait(timeout=15)
                    response = concurrent_clients[request_id].post(
                        "/api/auth/activate",
                        json={"token": concurrent_token, "password": concurrent_passwords[request_id]},
                        headers={"X-Verification-Request": request_id},
                    )
                except Exception as exc:
                    exception = exc
                if exception is None:
                    with concurrency_evidence_lock:
                        exception = concurrent_backend_exceptions.get(request_id)
                return _concurrent_token_evidence(
                    request_id, response=response, exception=exception,
                    sensitive_values=(concurrent_token, *concurrent_passwords.values()),
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                concurrent_results = list(pool.map(
                    consume_concurrently, ("token-use-1", "token-use-2"),
                ))

            clients_independent = concurrent_client_one is not concurrent_client_two
            sessions_independent = (
                set(concurrent_request_sessions) == {"token-use-1", "token-use-2"}
                and concurrent_request_sessions["token-use-1"] is not concurrent_request_sessions["token-use-2"]
            )
            transactions_independent = (
                set(concurrent_transactions) == {"token-use-1", "token-use-2"}
                and concurrent_transactions["token-use-1"]["session"]
                is not concurrent_transactions["token-use-2"]["session"]
                and concurrent_transactions["token-use-1"]["transaction"]
                is not concurrent_transactions["token-use-2"]["transaction"]
                and concurrent_transactions["token-use-1"]["connection"]
                is not concurrent_transactions["token-use-2"]["connection"]
            )
            accepted_requests = [
                item for item in concurrent_results
                if item["http_status"] == 204 and item["error_code"] is None and item["exception"] is None
            ]
            replay_rejections = [
                item for item in concurrent_results
                if item["http_status"] == 422 and item["error_code"] == "VALIDATION_ERROR"
                and item["exception"] is None
            ]

            with factory() as session:
                race_user_after = _require_account_visible_from_session(
                    session, User, employee_id=new_employee_id, account_id=new_account_id,
                    label="Account after concurrent token use",
                )
                race_token_after = session.scalar(select(AuthManagementToken).where(
                    AuthManagementToken.token_hash == concurrent_token_hash,
                ))
                race_audit_count_after = session.scalar(select(func.count(AdminAuditEvent.id)).where(
                    AdminAuditEvent.employee_id == new_employee_id,
                    AdminAuditEvent.action == "PASSWORD_RESET_COMPLETED",
                ))
                password_matches = [
                    request_id for request_id, candidate_password in concurrent_passwords.items()
                    if verify_password(race_user_after.password_hash, candidate_password)
                ]
                password_matches_prior = verify_password(
                    race_user_after.password_hash, "Reset-password-completed-123!",
                )
                race_state = {
                    "token_account_matches": (
                        race_token_after is not None and race_token_after.user_id == UUID(new_account_id)
                    ),
                    "token_purpose_matches": race_token_after is not None and race_token_after.purpose == "RESET",
                    "token_consumed": race_token_after is not None and race_token_after.consumed_at is not None,
                    "session_version_delta": race_user_after.session_version - race_session_version_before,
                    "password_reset_audit_delta": race_audit_count_after - race_audit_count_before,
                    "matching_candidate_request_ids": password_matches,
                    "prior_password_still_matches": password_matches_prior,
                }
            old_session_status = recipient.get("/api/auth/me").status_code
            race_state["prior_session_revoked"] = old_session_status == 401

            race_diagnostic = {
                "requests": concurrent_results,
                "clients_independent": clients_independent,
                "sessions_independent": sessions_independent,
                "transactions_and_connections_independent": transactions_independent,
                "request_barrier_synchronized": not request_barrier.broken,
                "database_state": race_state,
            }
            if not (clients_independent and sessions_independent and transactions_independent
                    and race_diagnostic["request_barrier_synchronized"]):
                raise AssertionError(
                    "Concurrent token gate did not use two independently captured HTTP/DB contexts: "
                    + json.dumps(race_diagnostic, sort_keys=True)
                )
            if len(accepted_requests) != 1 or len(replay_rejections) != 1:
                raise AssertionError(
                    "Concurrent token use did not produce exactly one HTTP 204 success and one "
                    "HTTP 422 VALIDATION_ERROR replay rejection: "
                    + json.dumps(race_diagnostic, sort_keys=True)
                )
            if not (
                race_state["token_account_matches"]
                and race_state["token_purpose_matches"]
                and race_state["token_consumed"]
                and race_state["session_version_delta"] == 1
                and race_state["password_reset_audit_delta"] == 1
                and len(password_matches) == 1
                and not password_matches_prior
                and race_state["prior_session_revoked"]
            ):
                raise AssertionError(
                    "Concurrent token use produced incorrect PostgreSQL account, audit, or session state: "
                    + json.dumps(race_diagnostic, sort_keys=True)
                )

            winning_request_id = password_matches[0]
            login_with_safe_diagnostics(
                recipient, f"new_{run_marker}", concurrent_passwords[winning_request_id],
                "post-race-recipient-login", "login with winning concurrent reset password",
            )
            _require_status(recipient.get("/api/auth/me"), "new recipient session after concurrent reset")
            replay_after_race = concurrent_client_one.post("/api/auth/activate", json={
                "token": concurrent_token, "password": "Concurrent-reset-replay-after-race-123!",
            })
            replay_after_race_evidence = _concurrent_token_evidence(
                "token-post-race-replay", response=replay_after_race,
                sensitive_values=(concurrent_token, "Concurrent-reset-replay-after-race-123!"),
            )
            with factory() as session:
                user_after_replay = _require_account_visible_from_session(
                    session, User, employee_id=new_employee_id, account_id=new_account_id,
                    label="Account after post-race replay",
                )
                token_after_replay = session.scalar(select(AuthManagementToken).where(
                    AuthManagementToken.token_hash == concurrent_token_hash,
                ))
                audit_after_replay = session.scalar(select(func.count(AdminAuditEvent.id)).where(
                    AdminAuditEvent.employee_id == new_employee_id,
                    AdminAuditEvent.action == "PASSWORD_RESET_COMPLETED",
                ))
                replay_state_unchanged = (
                    user_after_replay.session_version == race_session_version_before + 1
                    and verify_password(user_after_replay.password_hash, concurrent_passwords[winning_request_id])
                    and audit_after_replay == race_audit_count_before + 1
                    and token_after_replay is not None
                    and token_after_replay.user_id == UUID(new_account_id)
                    and token_after_replay.purpose == "RESET"
                    and token_after_replay.consumed_at is not None
                )
            replay_session_status = recipient.get("/api/auth/me").status_code
            race_diagnostic["post_race_replay"] = replay_after_race_evidence
            race_diagnostic["post_race_replay_no_side_effects"] = replay_state_unchanged
            race_diagnostic["new_session_survived_replay"] = replay_session_status == 200
            if not (
                replay_after_race_evidence["http_status"] == 422
                and replay_after_race_evidence["error_code"] == "VALIDATION_ERROR"
                and replay_after_race_evidence["exception"] is None
                and replay_state_unchanged and replay_session_status == 200
            ):
                raise AssertionError(
                    "A post-race replay was not rejected without account/session/audit side effects: "
                    + json.dumps(race_diagnostic, sort_keys=True)
                )

            # Locking a Checker with assigned work is blocked; revoking Checker is also blocked.
            pending_lock = admin.post(
                f"/api/workflow/employees/{seeded_employee_ids['locked_checker']}/account/lock",
            )
            if pending_lock.status_code != 409:
                raise AssertionError("Locking a Checker with a pending plan was not blocked with HTTP 409.")
            revoke_pending = admin.put(
                f"/api/workflow/employees/{seeded_employee_ids['locked_checker']}/roles",
                json={"role_codes": []},
            )
            if revoke_pending.status_code != 409:
                raise AssertionError("Revoking Checker access with pending work was not blocked with HTTP 409.")

            locked_replacement = admin.post(
                f"/api/workflow/employees/{seeded_employee_ids['replacement_checker']}/account/lock",
            )
            _require_status(locked_replacement, "lock Checker with no pending work")
            if replacement_checker.get("/api/auth/me").status_code != 401:
                raise AssertionError("Account lock did not revoke the Checker’s existing session.")
            unlocked_replacement = admin.post(
                f"/api/workflow/employees/{seeded_employee_ids['replacement_checker']}/account/unlock",
            )
            _require_status(unlocked_replacement, "unlock active Checker without pending work")
            if unlocked_replacement.json().get("account_status") != "ACTIVE":
                raise AssertionError("An eligible account unlock did not reactivate only account access.")

            with factory() as session:
                target_plan = session.scalar(select(AuthWorkflowPlan).where(
                    AuthWorkflowPlan.code == f"PG-EMP-{run_marker}-deactivation",
                ))
                plan_id = str(target_plan.id)
            missing_reassignment = admin.post(
                f"/api/workflow/employees/{seeded_employee_ids['departing_checker']}/deactivation",
                json={"reassignments": {}},
            )
            if missing_reassignment.status_code != 409:
                raise AssertionError("Deactivation without one replacement per pending plan was not blocked.")
            invalid_reassignment = admin.post(
                f"/api/workflow/employees/{seeded_employee_ids['departing_checker']}/deactivation",
                json={"reassignments": {plan_id: str(seeded_account_ids["maker"])}},
            )
            if invalid_reassignment.status_code < 400:
                raise AssertionError("Deactivation accepted a Maker as a Checker replacement.")
            with factory() as session:
                unchanged_profile = session.get(EmployeeProfile, seeded_employee_ids["departing_checker"])
                unchanged_user = session.get(User, seeded_account_ids["departing_checker"])
                unchanged_plan = session.get(AuthWorkflowPlan, target_plan.id)
                if (unchanged_profile.employment_status != "ACTIVE" or unchanged_user.status != "ACTIVE"
                        or unchanged_user.employment_status != "ACTIVE" or unchanged_user.session_version != 0
                        or unchanged_plan.checker_id != seeded_account_ids["departing_checker"]):
                    raise AssertionError("A failed deactivation partially changed employee/account/workflow state.")

            reset_checker = admin.post(
                f"/api/workflow/employees/{seeded_employee_ids['departing_checker']}/account/password-reset",
            )
            reset_checker_payload = _response_payload(
                reset_checker, "Checker reset-token invalidation fixture", expected_status=200,
            )
            try:
                reset_checker_response = AccountHandoverResponse.model_validate(reset_checker_payload)
            except (TypeError, ValueError):
                raise AssertionError(
                    "Checker reset-token fixture returned an invalid handover response schema."
                ) from None
            if reset_checker_response.purpose != "RESET":
                raise AssertionError("Checker reset-token fixture did not issue a RESET-purpose token.")
            checker_reset_token = reset_checker_response.handover_token
            require_management_token_owner(
                checker_reset_token, "RESET", "Checker reset fixture",
                expected_employee_id=str(seeded_employee_ids["departing_checker"]),
                expected_account_id=str(seeded_account_ids["departing_checker"]),
                expected_consumed=False,
            )
            changed = admin.post(
                f"/api/workflow/employees/{seeded_employee_ids['departing_checker']}/deactivation",
                json={"reassignments": {plan_id: str(seeded_account_ids["replacement_checker"])}},
            )
            _require_status(changed, "atomic Checker reassignment and deactivation")
            _require_status(departing_checker.get("/api/auth/me"), "revoked Checker session", expected_status=401)
            checker_old_token = recipient.post("/api/auth/activate", json={
                "token": checker_reset_token, "password": "Inactive-checker-token-should-fail-123!",
            })
            if checker_old_token.status_code < 400:
                raise AssertionError("Employee deactivation left a usable password-reset token.")
            require_management_token_owner(
                checker_reset_token, "RESET", "Invalidated Checker reset fixture",
                expected_employee_id=str(seeded_employee_ids["departing_checker"]),
                expected_account_id=str(seeded_account_ids["departing_checker"]),
                expected_consumed=True,
            )
            with factory() as session:
                inactive_profile = session.get(EmployeeProfile, seeded_employee_ids["departing_checker"])
                inactive_user = session.get(User, seeded_account_ids["departing_checker"])
                reassigned_plan = session.get(AuthWorkflowPlan, target_plan.id)
                reassignment_event = session.scalar(select(AuthWorkflowEvent).where(
                    AuthWorkflowEvent.plan_id == target_plan.id,
                    AuthWorkflowEvent.action == "CHECKER_REASSIGNED",
                ))
                audit_count = session.scalar(select(func.count(AdminAuditEvent.id)).where(
                    AdminAuditEvent.employee_id == seeded_employee_ids["departing_checker"],
                    AdminAuditEvent.action == "EMPLOYEE_DEACTIVATED",
                ))
                if (inactive_profile.employment_status != "INACTIVE" or inactive_user.employment_status != "INACTIVE"
                        or inactive_user.status != "DISABLED" or inactive_user.session_version != 1
                        or reassigned_plan.checker_id != seeded_account_ids["replacement_checker"]
                        or reassignment_event is None or audit_count != 1):
                    raise AssertionError("Checker deactivation, lock, reassignment, or audit was not atomic/complete.")

            removed_role = admin.put(
                f"/api/workflow/employees/{seeded_employee_ids['departing_checker']}/roles",
                json={"role_codes": []},
            )
            _require_status(removed_role, "role revocation while account is disabled")
            reactivated = admin.post(
                f"/api/workflow/employees/{seeded_employee_ids['departing_checker']}/reactivation",
            )
            _require_status(reactivated, "employee reactivation")
            reactivated_payload = reactivated.json()
            if (reactivated_payload["employment_status"] != "ACTIVE"
                    or reactivated_payload["account_status"] != "DISABLED"
                    or reactivated_payload["roles"]):
                raise AssertionError("Reactivation unlocked the account or restored a revoked role.")

            audit_response = admin.get("/api/workflow/admin-audit", params={"limit": 200})
            _require_status(audit_response, "Admin lifecycle audit page")
            audit_text = json.dumps(audit_response.json(), ensure_ascii=False)
            raw_handover_values = (
                initial_activation_token, activation_token, first_reset_token, second_reset_token,
                purpose_constraint_token, expired_reset.json()["handover_token"],
                concurrent_token, checker_reset_token,
            )
            if any(raw_token in audit_text for raw_token in raw_handover_values):
                raise AssertionError("Admin audit response exposed a handover token.")
            with factory() as session:
                persisted_hashes = {row.token_hash for row in session.scalars(select(AuthManagementToken)).all()}
                for raw_token in raw_handover_values:
                    if hashlib.sha256(raw_token.encode("utf-8")).hexdigest() not in persisted_hashes:
                        raise AssertionError("A management token digest is missing from PostgreSQL.")
            return {
                "status": "PASS", "source": "synthetic PostgreSQL-backed HTTP/service checks",
                "employee_account_identity": {
                    "employee_id": new_employee_id,
                    "account_id": new_account_id,
                    "profile_account_ids_distinct": new_employee_id != new_account_id,
                    "profile_visible_before_account_creation": True,
                    "profile_link_verified": True,
                    "account_visible_from_independent_postgresql_session": True,
                    "api_and_verification_sessions_share_temporary_engine": True,
                    "all_management_token_account_and_purpose_checks_passed": True,
                },
                "activation": {"one_time": True, "expiry_minutes": 30, "stored_as_sha256_only": True,
                               "recipient_selected_password": True, "replay_rejected": True,
                               "reissue_invalidates_old": True},
                "password_reset": {"reissue_invalidates_old": True, "expiry_enforced": True,
                                   "replay_rejected": True, "unknown_purpose_rejected": True,
                                   "old_sessions_revoked_on_success": True,
                                   "concurrent_consumption": race_diagnostic},
                "management_token_purpose_constraint": purpose_constraint_result,
                "management_token_purpose_contract": {
                    "consumer_endpoint": "/api/auth/activate",
                    "valid_purposes": ["ACTIVATE", "RESET"],
                    "operation_selected_by": "stored token purpose",
                    "separate_reset_consumer_endpoint": False,
                    "wrong_operation_endpoint_case": "not_applicable_to_shared_endpoint_contract",
                },
                "checker_lifecycle": {"lock_with_pending_blocked": True,
                                      "role_revoke_with_pending_blocked": True,
                                      "deactivation_requires_each_replacement": True,
                                      "invalid_reassignment_rollback": True,
                                      "reassignment_deactivation_account_lock_audit_atomic": True,
                                      "old_session_revoked": True, "outstanding_tokens_invalidated": True},
                "reactivation": {"account_remains_disabled": True, "revoked_roles_not_restored": True},
                "raw_handover_values_in_audit": False,
            }
    finally:
        app.dependency_overrides.clear()


def _stop_process(process, timeout=10):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def _copy_redacted_log(source: Path | None, destination: Path, secrets: list[str]):
    if source is None or not source.exists():
        return
    _write_text(destination, _redact(source.read_text(encoding="utf-8", errors="replace"), secrets))


class _FocusedPostgresGateComplete(Exception):
    """Stop after a requested focused gate while still running owned-resource cleanup."""


def _run_full() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper-mode", choices=("verify-empty", "seed-legacy", "verify-legacy", "directory", "employee-admin"))
    parser.add_argument("--only", choices=("employee-admin",),
                        help="Run the empty-database migration check and employee-admin PostgreSQL gate only.")
    parser.add_argument("--run-id")
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    if args.helper_mode:
        raise RuntimeError("Helper modes require the isolated DATABASE_URL supplied by the parent run.")

    run_id = uuid4().hex
    container_name = f"organizationai-pgverify-{run_id}"
    database_user = "oa_test"
    database_password = uuid4().hex + uuid4().hex
    auth_password = uuid4().hex + uuid4().hex
    jwt_secret = uuid4().hex + uuid4().hex
    secrets = [database_password, auth_password, jwt_secret]
    empty_database = f"oa_empty_{run_id[:10]}"
    legacy_database = f"oa_legacy_{run_id[:10]}"
    evidence_path = EVIDENCE_ROOT / f"auth-postgres-verification-{run_id[:10]}.json"
    log_root = EVIDENCE_ROOT / f"auth-postgres-run-{run_id[:10]}"
    log_root.mkdir(parents=True, exist_ok=False)
    temporary = Path(tempfile.mkdtemp(prefix=f"oa-pgverify-{run_id[:8]}-"))
    temp_run = temporary / "run"
    temp_run.mkdir()
    processes = []
    container_started = False
    docker = shutil.which("docker.exe") or shutil.which("docker")
    python = sys.executable
    evidence = {
        "run_id": run_id,
        "started_at": _now(),
        "status": "RUNNING",
        "source": "caller-run; synthetic PostgreSQL only; no live database",
        "revision": _revision_info(),
        "migration_head": None,
        "environment": {
            "os": sys.platform,
            "python": sys.version.split()[0],
            "docker_client": None,
            "docker_engine": None,
            "postgres_image": "postgres:16",
        },
        "port_preflight": {str(port): _port_is_free(port) for port in sorted(RESERVED_PORTS)},
        "migration_empty_database": None,
        "migration_legacy_database": None,
        "admin_directory_postgres": None,
        "employee_account_postgres": None,
        "auth_e2e": None,
        "focused_gate": args.only,
        "gates_not_run": [],
        "existing_containers_before": None,
        "existing_containers_after": None,
        "temporary_container_name": container_name,
        "cleanup": {"owned_container_removed": False, "temporary_files_removed": False},
        "errors": [],
    }
    try:
        if not docker:
            raise RuntimeError("Docker CLI was not found on PATH.")
        docker_code, docker_client, docker_error = _run([docker, "version", "--format", "{{.Client.Version}}"], check=False)
        if docker_code:
            raise RuntimeError(f"Docker client check failed: {docker_error.strip()[-1000:]}")
        evidence["environment"]["docker_client"] = docker_client.strip()
        engine = _engine_info(docker)
        evidence["environment"]["docker_engine"] = engine
        evidence["existing_containers_before"] = _container_inventory(docker)
        image_code, image_id, image_error = _run(
            [docker, "image", "inspect", "postgres:16", "--format", "{{.Id}}"], check=False,
        )
        if image_code or not image_id.strip():
            raise RuntimeError("Local postgres:16 image is required; this runner will not pull images.")
        evidence["environment"]["postgres_image_id"] = image_id.strip()

        python = str(ROOT / ".venv-test-20261009" / "Scripts" / "python.exe") if os.name == "nt" else str(ROOT / ".venv-test-20261009" / "bin" / "python")
        if not Path(python).is_file():
            raise RuntimeError(f"Expected project test Python is missing: {python}")
        evidence["environment"]["python"] = _run([python, "--version"])[1].strip().replace("Python ", "")
        evidence["migration_head"] = _assert_migration_head(python)
        node = None
        vite = None
        playwright_cli = None
        if args.only is None:
            node = shutil.which("node.exe") or shutil.which("node")
            if not node:
                raise RuntimeError("Node.js was not found on PATH.")
            evidence["environment"]["node"] = _run([node, "--version"])[1].strip()
            vite = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
            playwright_cli = ROOT / "frontend" / "node_modules" / "@playwright" / "test" / "cli.js"
            if not vite.is_file() or not playwright_cli.is_file():
                raise RuntimeError("Frontend dependencies are missing; install the existing lockfile before rerunning.")
        if not all(_port_is_free(port) for port in RESERVED_PORTS):
            occupied = [port for port in RESERVED_PORTS if not _port_is_free(port)]
            evidence["port_preflight"]["occupied"] = occupied
        api_port, frontend_port = _free_port(), _free_port()
        while frontend_port == api_port:
            frontend_port = _free_port()
        evidence["ports"] = {"temporary_postgres": None, "api": api_port, "frontend": frontend_port}

        docker_args = [
            docker, "run", "--pull=never", "--detach", "--rm", "--name", container_name,
            "--label", f"com.organizationai.verification.run-id={run_id}",
            "--tmpfs", "/var/lib/postgresql/data:rw,size=1g",
            "--env", f"POSTGRES_USER={database_user}",
            "--env", f"POSTGRES_PASSWORD={database_password}",
            "--env", f"POSTGRES_DB={empty_database}",
            "--publish", "127.0.0.1::5432", "postgres:16",
        ]
        _, _, _ = _run(docker_args, secrets=secrets)
        container_started = True
        _, published, _ = _run([docker, "port", container_name, "5432/tcp"])
        match = re.match(r"127\.0\.0\.1:(\d+)", published.strip())
        if not match:
            raise RuntimeError("Docker did not publish PostgreSQL on a loopback-only port.")
        pg_port = int(match.group(1))
        if pg_port in RESERVED_PORTS:
            raise RuntimeError(f"Docker selected reserved application port {pg_port}; refusing to continue.")
        evidence["ports"]["temporary_postgres"] = pg_port
        ready = False
        for _ in range(60):
            code, _, _ = _run([docker, "exec", container_name, "pg_isready", "-U", database_user, "-d", empty_database], check=False)
            if code == 0:
                ready = True
                break
            time.sleep(2)
        if not ready:
            raise RuntimeError("Temporary PostgreSQL did not become ready within 120 seconds.")

        base_url = f"postgresql+psycopg://{database_user}:{quote(database_password, safe='')}@127.0.0.1:{pg_port}"
        base_env = os.environ.copy()
        base_env.update({"AUTH_ALLOW_SQLITE_MIGRATION_TESTS": "false", "APP_ENV": "demo"})
        empty_env = {**base_env, "DATABASE_URL": f"{base_url}/{empty_database}"}
        _, migration_empty_out, migration_empty_err = _run(
            [python, "-m", "alembic", "upgrade", "head"], env=empty_env, secrets=secrets,
        )
        _write_text(log_root / "migration-empty.log", migration_empty_out + migration_empty_err)
        empty_result = _helper(python, "verify-empty", env=empty_env, secrets=secrets)
        evidence["migration_empty_database"] = empty_result

        if args.only == "employee-admin":
            focused_auth_env = {
                **empty_env,
                "APP_ENV": "demo",
                "AUTH_COOKIE_SECURE": "false",
                "AUTH_COOKIE_SAMESITE": "lax",
                "AUTH_REMEMBER_TOKEN_DAYS": "14",
                "AUTH_SEED_ENABLED": "true",
                "AUTH_SEED_PASSWORD": auth_password,
                "AUTH_WORKFLOW_AI_PROVIDER": "MOCK_VLM",
                "AUTH_WORKFLOW_MOCK_SCENARIO": "review",
                "CORS_ORIGINS": f"http://127.0.0.1:{frontend_port}",
                "DEMO_DATABASE": str(temp_run / "isolated-demo.sqlite3"),
                "DEMO_MOCK_MODE": "review",
                "JWT_SECRET": jwt_secret,
                "JWT_ACCESS_TOKEN_MINUTES": "30",
            }
            _, seed_out, seed_err = _run(
                [python, "-m", "src.backend.seed_auth"], env=focused_auth_env, secrets=secrets,
            )
            _write_text(temp_run / "seed-auth.log", seed_out + seed_err)
            evidence["employee_account_postgres"] = _helper(
                python, "employee-admin", env=focused_auth_env, secrets=secrets, timeout=180,
            )
            evidence["gates_not_run"] = [
                "migration_legacy_database", "admin_directory_postgres", "auth_e2e",
            ]
            evidence["status"] = "PASS"
            raise _FocusedPostgresGateComplete()

        _, _, _ = _run([docker, "exec", container_name, "createdb", "-U", database_user, legacy_database], secrets=secrets)
        legacy_env = {**base_env, "DATABASE_URL": f"{base_url}/{legacy_database}"}
        _, migration_legacy_before_out, migration_legacy_before_err = _run(
            [python, "-m", "alembic", "upgrade", PRE_EMPLOYEE_REVISION], env=legacy_env, secrets=secrets,
        )
        _write_text(log_root / "migration-legacy-bootstrap.log",
                    migration_legacy_before_out + migration_legacy_before_err)
        legacy_snapshot = temp_run / "legacy-before.json"
        seeded = _helper(
            python, "seed-legacy", env=legacy_env,
            extra=("--run-id", run_id, "--snapshot", str(legacy_snapshot)), secrets=secrets,
        )
        _copy_redacted_log(legacy_snapshot, log_root / "legacy-before.json", secrets)
        _, migration_legacy_after_out, migration_legacy_after_err = _run(
            [python, "-m", "alembic", "upgrade", "head"], env=legacy_env, secrets=secrets,
        )
        _write_text(log_root / "migration-legacy-upgrade.log",
                    migration_legacy_after_out + migration_legacy_after_err)
        legacy_result = _helper(
            python, "verify-legacy", env=legacy_env,
            extra=("--snapshot", str(legacy_snapshot)), secrets=secrets,
        )
        evidence["migration_legacy_database"] = {"seed": seeded, "upgrade": legacy_result}

        auth_env = {
            **base_env,
            "DATABASE_URL": f"{base_url}/{empty_database}",
            "APP_ENV": "demo",
            "AUTH_COOKIE_SECURE": "false",
            "AUTH_COOKIE_SAMESITE": "lax",
            "AUTH_REMEMBER_TOKEN_DAYS": "14",
            "AUTH_SEED_ENABLED": "true",
            "AUTH_SEED_PASSWORD": auth_password,
            "AUTH_WORKFLOW_AI_PROVIDER": "MOCK_VLM",
            "AUTH_WORKFLOW_MOCK_SCENARIO": "review",
            "CORS_ORIGINS": f"http://127.0.0.1:{frontend_port}",
            "DEMO_DATABASE": str(temp_run / "isolated-demo.sqlite3"),
            "DEMO_MOCK_MODE": "review",
            "JWT_SECRET": jwt_secret,
            "JWT_ACCESS_TOKEN_MINUTES": "30",
            "AUTH_E2E_BASE_URL": f"http://127.0.0.1:{frontend_port}",
            "AUTH_E2E_MAKER_USERNAME": "maker",
            "AUTH_E2E_CHECKER_USERNAME": "checker",
            "VITE_API_BASE_URL": f"http://127.0.0.1:{api_port}/api",
            "VITE_DEMO_ENABLED": "true",
            "PLAYWRIGHT_JSON_OUTPUT_FILE": str(temp_run / "playwright-report.json"),
        }
        _, seed_out, seed_err = _run([python, "-m", "src.backend.seed_auth"], env=auth_env, secrets=secrets)
        _write_text(temp_run / "seed-auth.log", seed_out + seed_err)
        directory = _helper(python, "directory", env=auth_env, secrets=secrets)
        evidence["admin_directory_postgres"] = directory
        evidence["employee_account_postgres"] = _helper(
            python, "employee-admin", env=auth_env, secrets=secrets, timeout=180,
        )

        api_log, frontend_log = temp_run / "api.log", temp_run / "frontend.log"
        api_handle = api_log.open("w", encoding="utf-8")
        api_process = subprocess.Popen(
            [python, "-m", "uvicorn", "src.backend.api.app:app", "--host", "127.0.0.1", "--port", str(api_port)],
            cwd=ROOT, env=auth_env, stdout=api_handle, stderr=subprocess.STDOUT,
        )
        processes.append((api_process, api_handle))
        frontend_handle = frontend_log.open("w", encoding="utf-8")
        frontend_process = subprocess.Popen(
            [node, str(vite), "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"],
            cwd=ROOT / "frontend", env=auth_env, stdout=frontend_handle, stderr=subprocess.STDOUT,
        )
        processes.append((frontend_process, frontend_handle))

        import httpx
        api_ready = frontend_ready = False
        for _ in range(60):
            if api_process.poll() is not None or frontend_process.poll() is not None:
                raise RuntimeError("Temporary API or Vite process exited before readiness.")
            try:
                api_response = httpx.get(f"http://127.0.0.1:{api_port}/api/health/ready", timeout=1)
                api_ready = api_response.status_code == 200 and api_response.json().get("auth_database") == "postgresql"
            except Exception:
                pass
            try:
                front_response = httpx.get(f"http://127.0.0.1:{frontend_port}/", timeout=1)
                frontend_ready = front_response.status_code == 200
            except Exception:
                pass
            if api_ready and frontend_ready:
                break
            time.sleep(1)
        if not api_ready or not frontend_ready:
            raise RuntimeError("Temporary API/Vite did not become ready on their dynamically allocated ports.")

        playwright_report = Path(auth_env["PLAYWRIGHT_JSON_OUTPUT_FILE"])
        code, playwright_out, playwright_err = _run(
            [node, str(playwright_cli), "test", "--config", "playwright.auth-live.config.ts",
             "--reporter=list,json", "--output", str(temp_run / "playwright-output")],
            cwd=ROOT / "frontend", env=auth_env, timeout=900, secrets=secrets, check=False,
        )
        _write_text(temp_run / "playwright.log", playwright_out + playwright_err)
        if code != 0 or not playwright_report.is_file():
            raise RuntimeError(f"Auth Playwright exited {code} or did not produce its JSON report.")
        report = json.loads(playwright_report.read_text(encoding="utf-8"))
        stats = report.get("stats") or {}
        report_text = json.dumps(report, ensure_ascii=False)
        if (stats.get("expected") != 3 or stats.get("skipped") != 0
                or stats.get("unexpected") != 0 or stats.get("flaky") != 0):
            raise RuntimeError(f"Auth E2E gate failed: {stats!r}")
        if "creation intent replays a lost PostgreSQL draft response and rejects changed content" not in report_text:
            raise RuntimeError("The idempotency-across-reload Auth E2E case is absent from the report.")
        evidence["auth_e2e"] = {
            "status": "PASS", "expected": stats["expected"], "skipped": stats["skipped"],
            "unexpected": stats["unexpected"], "flaky": stats["flaky"],
            "idempotency_reload_case_present": True,
            "provider": "MOCK_VLM deterministic workflow fixture; not local model inference",
            "report_file": str(log_root / "playwright-report.json"),
        }
        _write_text(
            log_root / "playwright-report.json",
            _redact(json.dumps(report, ensure_ascii=False, indent=2) + "\n", secrets),
        )
        evidence["status"] = "PASS"
    except _FocusedPostgresGateComplete:
        pass
    except Exception as exc:
        evidence["status"] = "BLOCKED_PRECHECK" if _is_docker_access_blocked(str(exc)) else "FAILED"
        evidence["errors"].append({
            "type": type(exc).__name__,
            "message": _redact(str(exc), secrets)[:3000],
            "traceback": _redact(traceback.format_exc(), secrets),
        })
    finally:
        for process, handle in reversed(processes):
            _stop_process(process)
            handle.close()
        for name in ("api.log", "frontend.log", "seed-auth.log", "playwright.log"):
            source = temp_run / name
            _copy_redacted_log(source if source.exists() else None, log_root / name, secrets)
        if container_started and docker:
            code, postgres_log, postgres_error = _run(
                [docker, "logs", container_name], secrets=secrets, check=False,
            )
            _write_text(log_root / "postgres.log", postgres_log + postgres_error)
            code, _, error = _run([docker, "stop", "--time", "5", container_name], secrets=secrets, check=False)
            evidence["cleanup"]["owned_container_removed"] = code == 0
            if code != 0:
                evidence["errors"].append({"type": "cleanup", "message": _redact(error[-1000:], secrets)})
                evidence["status"] = "FAILED"
        if docker:
            try:
                after = _container_inventory(docker)
                evidence["existing_containers_after"] = after
                before = evidence.get("existing_containers_before") or {}
                missing = sorted(set(before) - set(after))
                changed = sorted(key for key in set(before) & set(after) if before[key] != after[key])
                evidence["cleanup"]["preexisting_container_ids_preserved"] = not missing
                evidence["cleanup"]["missing_preexisting_container_ids"] = missing
                evidence["cleanup"]["changed_preexisting_container_ids"] = changed
                if missing or changed:
                    evidence["status"] = "FAILED"
            except Exception as exc:
                evidence["errors"].append({
                    "type": "container_inventory_after",
                    "message": _redact(str(exc), secrets)[:1000],
                    "traceback": _redact(traceback.format_exc(), secrets),
                })
                evidence["cleanup"]["preexisting_container_ids_preserved"] = None
                if evidence["status"] == "PASS":
                    evidence["status"] = "FAILED"
        try:
            shutil.rmtree(temporary)
            evidence["cleanup"]["temporary_files_removed"] = True
        except OSError as exc:
            evidence["cleanup"]["temporary_files_removed"] = False
            evidence["errors"].append({
                "type": "temporary_cleanup",
                "message": _redact(str(exc), secrets)[:1000],
                "traceback": _redact(traceback.format_exc(), secrets),
            })
            evidence["status"] = "FAILED"
        evidence["completed_at"] = _now()
        evidence["logs"] = str(log_root)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text(evidence_path, json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
        print(f"Evidence: {evidence_path}")
        print(f"Status: {evidence['status']}")
        if evidence["errors"]:
            print(json.dumps(evidence["errors"], ensure_ascii=False))
    return 0 if evidence["status"] == "PASS" else 2


def _dispatch_helper() -> bool:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--helper-mode", choices=("verify-empty", "seed-legacy", "verify-legacy", "directory", "employee-admin"))
    parser.add_argument("--repo-root")
    parser.add_argument("--run-id")
    parser.add_argument("--snapshot")
    parsed, _ = parser.parse_known_args()
    if not parsed.helper_mode:
        return False
    if not parsed.repo_root:
        raise RuntimeError("--repo-root is required for PostgreSQL helper modes.")
    repo_root = Path(parsed.repo_root)
    if not repo_root.is_absolute():
        raise RuntimeError("--repo-root must be an absolute, resolved repository path.")
    global ROOT, EVIDENCE_ROOT
    ROOT = repo_root
    EVIDENCE_ROOT = ROOT / "docs" / "integration" / "evidence"
    repo_path = str(ROOT)
    if repo_path not in sys.path:
        sys.path.insert(0, repo_path)
    if parsed.helper_mode in {"seed-legacy", "verify-legacy"} and not parsed.snapshot:
        raise RuntimeError("--snapshot is required for legacy migration helper modes.")
    if parsed.helper_mode == "seed-legacy" and not parsed.run_id:
        raise RuntimeError("--run-id is required to construct synthetic legacy fixtures.")
    raise SystemExit(_helper_mode(parsed.helper_mode, parsed))


if __name__ == "__main__":
    try:
        if not _dispatch_helper():
            raise SystemExit(_run_full())
    except SystemExit:
        raise
    except Exception as exc:
        child_secrets = [
            os.environ.get("AUTH_SEED_PASSWORD", ""),
            os.environ.get("JWT_SECRET", ""),
            os.environ.get("DATABASE_URL", ""),
        ]
        safe_traceback = _redact(traceback.format_exc(), child_secrets)
        safe_message = _redact(str(exc), child_secrets)
        print(
            f"POSTGRES VERIFICATION FAILED: {type(exc).__name__}: {safe_message}\n{safe_traceback}",
            file=sys.stderr,
        )
        raise SystemExit(2)
