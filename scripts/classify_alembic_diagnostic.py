from __future__ import annotations

import argparse
from collections import Counter
import re
import sys
from pathlib import Path


_PINNED_SOURCE_SHA = "0d17887cf1d6a6571fc8b02b74706343e2555e19"
_PINNED_MIGRATION_INDEXES = {
    "ix_auth_management_tokens_user_purpose",
    "ix_admin_audit_events_created_at",
}

_EXCEPTION_TYPES = {
    "CommandError", "ModuleNotFoundError", "ImportError",
    "OperationalError", "ProgrammingError", "IntegrityError",
    "UndefinedColumn", "UndefinedTable", "InsufficientPrivilege",
    "UniqueViolation", "ForeignKeyViolation", "CheckViolation",
    "RuntimeError", "TypeError", "ValueError", "KeyError",
    "NameError", "AttributeError", "NoSuchModuleError",
    "NotImplementedError", "AssertionError",
}


def _is_exact_pinned_migration_index_gap(text: str) -> bool:
    marker = re.search(r"new upgrade operations detected\s*:\s*", text, re.IGNORECASE)
    if marker is None:
        return False
    operations_text = text[marker.end():]
    operation_names = re.findall(
        r"\(\s*['\"](add_column|remove_column|modify_type|modify_default|add_index|"
        r"remove_index|add_constraint|remove_constraint|add_table|remove_table)['\"]\s*,",
        operations_text,
        flags=re.IGNORECASE,
    )
    if [name.casefold() for name in operation_names] != ["remove_index"] * 4:
        return False
    index_names = re.findall(r"\bIndex\(\s*['\"]([^'\"]+)['\"]", operations_text)
    expected_counts = Counter({name: 2 for name in _PINNED_MIGRATION_INDEXES})
    return Counter(index_names) == expected_counts


def diagnose(
    text: str, exit_code: int, source_sha: str | None = None
) -> dict[str, object]:
    if exit_code == 0:
        return {
            "code": "PROCESS_OUTPUT_NONFATAL" if text.strip() else "NONE",
            "exception_type": None,
            "sqlstate": None,
            "location": None,
            "schema_diff_kinds": [],
        }

    lower = text.casefold()
    exception_match = re.search(
        r"\b(" + "|".join(sorted(_EXCEPTION_TYPES)) + r")\b", text
    )
    exception_type = exception_match.group(1) if exception_match else None

    state_match = re.search(
        r"(?:sqlstate|sql state)(?:\s*[=:]\s*|\s*\[)([0-9A-Z]{5})",
        text,
        flags=re.IGNORECASE,
    )
    sqlstate = state_match.group(1).upper() if state_match else None

    location = None
    trace_frames = list(
        re.finditer(
            r'File\s+"([^"]+)",\s*line\s+(\d+),\s*in\s+([A-Za-z0-9_<>]+)',
            text,
        )
    )
    if trace_frames:
        frame = trace_frames[-1]
        basename = Path(frame.group(1).replace("\\", "/")).name
        if re.fullmatch(r"[A-Za-z0-9_.-]+", basename):
            location = f"{basename}:{frame.group(2)}:{frame.group(3)}"

    schema_diff_kinds: list[str] = []
    schema_drift = (
        "new upgrade operations detected" in lower
        or "new autogenerate operations detected" in lower
    )
    if schema_drift:
        code = (
            "PINNED_MIGRATION_INDEX_METADATA_GAP"
            if source_sha == _PINNED_SOURCE_SHA and _is_exact_pinned_migration_index_gap(text)
            else "ALEMBIC_SCHEMA_DRIFT"
        )
        if exception_type is None:
            exception_type = "CommandError"
        known_kinds = (
            "add_column", "remove_column", "modify_type", "modify_default",
            "add_index", "remove_index", "add_constraint", "remove_constraint",
            "add_table", "remove_table",
        )
        schema_diff_kinds = [kind for kind in known_kinds if kind in lower]
    elif re.search(r"(?:permission denied for|must be owner of)", lower):
        code = "DATABASE_PRIVILEGE_FAILED"
    elif re.search(r"password authentication failed|no password supplied", lower):
        code = "DATABASE_AUTHENTICATION_FAILED"
    elif re.search(r"could not connect|connection refused|server closed the connection|no pg_hba\.conf entry", lower):
        code = "DATABASE_CONNECTION_FAILED"
    elif re.search(r"module not found|no module named|modulenotfounderror|importerror|nosuchmoduleerror", lower):
        code = "DEPENDENCY_IMPORT_FAILED"
    elif re.search(r"can't locate revision|cannot locate revision|revision .* not found", lower):
        code = "ALEMBIC_REVISION_NOT_FOUND"
    elif sqlstate or exception_type is not None or re.search(
        r"sqlalchemy\.exc|psycopg(?:2)?(?:\.errors)?|traceback \(most recent call last\)",
        lower,
    ):
        code = "DATABASE_MIGRATION_FAILED"
    else:
        code = "ALEMBIC_ERROR_REDACTED"

    return {
        "code": code,
        "exception_type": exception_type,
        "sqlstate": sqlstate,
        "location": location,
        "schema_diff_kinds": schema_diff_kinds,
    }


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--pinned-sha")
    args = parser.parse_args()
    result = diagnose(sys.stdin.read(), args.exit_code, source_sha=args.pinned_sha)
    print("CODE=" + str(result["code"]))
    if result["exception_type"]:
        print("EXCEPTION_TYPE=" + str(result["exception_type"]))
    if result["sqlstate"]:
        print("SQLSTATE=" + str(result["sqlstate"]))
    if result["location"]:
        print("LOCATION=" + str(result["location"]))
    for kind in result["schema_diff_kinds"]:
        print("SCHEMA_DIFF_KIND=" + kind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
