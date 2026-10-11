from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = ROOT / "scripts" / "classify_alembic_diagnostic.py"


def _load_classifier():
    spec = importlib.util.spec_from_file_location("alembic_diagnostic", CLASSIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_database_sql_errors_return_only_allowlisted_type_state_and_location():
    classifier = _load_classifier()
    raw = (
        'Traceback (most recent call last):\n'
        '  File "C:\\private\\verify_rehearsal.py", line 81, in fingerprint_table\n'
        'psycopg.errors.UndefinedColumn: SQLSTATE=42703 password=never-print-this'
    )
    result = classifier.diagnose(raw, exit_code=1)
    assert result == {
        "code": "DATABASE_MIGRATION_FAILED",
        "exception_type": "UndefinedColumn",
        "sqlstate": "42703",
        "location": "verify_rehearsal.py:81:fingerprint_table",
        "schema_diff_kinds": [],
    }
    assert "never-print-this" not in str(result)
    assert "C:\\private" not in str(result)


def test_database_privilege_errors_are_not_classified_as_output_path_failures():
    classifier = _load_classifier()
    result = classifier.diagnose(
        "permission denied for sequence users_id_seq; password=redacted-input",
        exit_code=1,
    )
    assert result["code"] == "DATABASE_PRIVILEGE_FAILED"
    assert result["exception_type"] is None
    assert "redacted-input" not in str(result)


def test_missing_pinned_revision_and_dependencies_are_distinguished():
    classifier = _load_classifier()
    assert classifier.diagnose(
        "alembic.util.exc.CommandError: Can't locate revision identified by 'secret-ish-value'",
        exit_code=1,
    )["code"] == "ALEMBIC_REVISION_NOT_FOUND"
    assert classifier.diagnose(
        "ModuleNotFoundError: No module named 'private_package'",
        exit_code=1,
    )["code"] == "DEPENDENCY_IMPORT_FAILED"


def test_nonzero_unknown_error_is_redacted_and_success_stderr_is_nonfatal():
    classifier = _load_classifier()
    raw = "opaque error password=must-not-escape"
    assert classifier.diagnose(raw, exit_code=1) == {
        "code": "ALEMBIC_ERROR_REDACTED",
        "exception_type": None,
        "sqlstate": None,
        "location": None,
        "schema_diff_kinds": [],
    }
    assert classifier.diagnose(
        "warning: nonfatal database notice", exit_code=0
    )["code"] == "PROCESS_OUTPUT_NONFATAL"


def test_alembic_schema_drift_reports_only_operation_categories():
    classifier = _load_classifier()
    raw = (
        "FAILED: New upgrade operations detected: "
        "[('modify_type', None, 'private_table', 'private_column')] "
        "password=must-not-escape"
    )
    result = classifier.diagnose(raw, exit_code=-1)
    assert result["code"] == "ALEMBIC_SCHEMA_DRIFT"
    assert result["exception_type"] == "CommandError"
    assert result["schema_diff_kinds"] == ["modify_type"]
    assert "private_table" not in str(result)
    assert "private_column" not in str(result)
    assert "must-not-escape" not in str(result)


def test_exact_pinned_migration_index_metadata_gap_is_classified_safely():
    classifier = _load_classifier()
    raw = (
        "FAILED: New upgrade operations detected: "
        "[('remove_index', Index('ix_auth_management_tokens_user_purpose', "
        "Column('user_id'), Column('purpose'), Column('consumed_at'))), "
        "('remove_index', Index('ix_admin_audit_events_created_at', Column('created_at')))] "
        "[('remove_index', Index('ix_auth_management_tokens_user_purpose', "
        "Column('user_id'), Column('purpose'), Column('consumed_at'))), "
        "('remove_index', Index('ix_admin_audit_events_created_at', Column('created_at')))] "
        "password=must-not-escape"
    )
    result = classifier.diagnose(
        raw, exit_code=1, source_sha="0d17887cf1d6a6571fc8b02b74706343e2555e19"
    )
    assert result["code"] == "PINNED_MIGRATION_INDEX_METADATA_GAP"
    other_source = classifier.diagnose(
        raw, exit_code=1, source_sha="1" * 40
    )
    assert other_source["code"] == "ALEMBIC_SCHEMA_DRIFT"
    assert result["schema_diff_kinds"] == ["remove_index"]
    assert "ix_auth_management_tokens_user_purpose" not in str(result)
    assert "ix_admin_audit_events_created_at" not in str(result)
    assert "must-not-escape" not in str(result)


def test_pinned_index_metadata_gap_rejects_extra_or_unknown_schema_changes():
    classifier = _load_classifier()
    expected_indexes = (
        "('remove_index', Index('ix_auth_management_tokens_user_purpose')) "
        "('remove_index', Index('ix_admin_audit_events_created_at')) "
        "('remove_index', Index('ix_auth_management_tokens_user_purpose')) "
        "('remove_index', Index('ix_admin_audit_events_created_at')) "
    )
    extra_change = classifier.diagnose(
        "New upgrade operations detected: " + expected_indexes + "('add_column', None)",
        exit_code=1,
    )
    assert extra_change["code"] == "ALEMBIC_SCHEMA_DRIFT"

    unknown_index = classifier.diagnose(
        "New upgrade operations detected: "
        "[('remove_index', Index('ix_unexpected_private_index'))]",
        exit_code=1,
    )
    assert unknown_index["code"] == "ALEMBIC_SCHEMA_DRIFT"
