import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.run_auth_live_migration import (
    SafeRunnerFailure,
    PINNED_SHA,
    REQUIRED_START_TABLES,
    TARGET_REVISION,
    _human_confirmation,
    _run_alembic_upgrade,
    _prepare_pinned_source,
    build_secure_url,
    safe_exception_fields,
    validate_final_backup_freshness,
    verify_rehearsal_receipt,
)
from datetime import datetime, timedelta, timezone


def test_build_secure_url_overrides_unsafe_tls_and_timeout_options():
    url = build_secure_url(
        "postgresql://runner@example.invalid/organizationai_db"
        "?sslmode=disable&connect_timeout=0&options=-c%20statement_timeout%3D0"
    )

    assert url.drivername == "postgresql+psycopg"
    assert url.query["sslmode"] == "require"
    assert url.query["connect_timeout"] == "10"
    assert "statement_timeout=60000" in url.query["options"]
    assert "sslmode=disable" not in url.render_as_string(hide_password=False)


def test_read_only_preflight_only_requires_tables_present_at_start_revision():
    assert REQUIRED_START_TABLES == ("alembic_version", "users", "roles", "user_roles")
    assert "role_permissions" not in REQUIRED_START_TABLES


def test_safe_exception_fields_never_include_exception_message_or_password():
    error = RuntimeError("password=synthetic-secret token=synthetic-token")
    error.sqlstate = "42703"

    fields = safe_exception_fields(error)

    assert fields["exception_type"] == "RuntimeError"
    assert fields["sqlstate"] == "42703"
    assert "synthetic-secret" not in json.dumps(fields)


def test_live_write_confirmation_requires_the_full_displayed_target(monkeypatch):
    identity = {
        "database": "organizationai_db",
        "schema": "public",
        "baseline_table_count": 4,
        "baseline_row_count": 7,
    }
    expected = f"MIGRATE organizationai_db public 20261003_07 {TARGET_REVISION} {PINNED_SHA}"
    monkeypatch.setattr("builtins.input", lambda _prompt: expected)
    assert _human_confirmation(identity, "A" * 64, synthetic=False)

    monkeypatch.setattr("builtins.input", lambda _prompt: "MIGRATE organizationai_db public")
    assert not _human_confirmation(identity, "A" * 64, synthetic=False)


def test_rehearsal_receipt_must_match_backup_hash_and_pinned_cutover(tmp_path: Path):
    archive = tmp_path / "organizationai_db-final.dump"
    archive.write_bytes(b"synthetic archive bytes")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest().upper()
    archive.with_name(archive.name + ".sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="ascii",
    )
    receipt = tmp_path / "auth-migration-rehearsal.json"
    receipt.write_text(json.dumps({
        "receipt_version": 1,
        "run_id": "20261012T120000Z-0123456789abcdefabcd",
        "result": "PASS",
        "cleanup_complete": True,
        "writers_paused": True,
        "source_sha": "0d17887cf1d6a6571fc8b02b74706343e2555e19",
        "database": "organizationai_db",
        "schema": "public",
        "start_revision": "20261003_07",
        "target_revision": "20261011_12",
        "postgres_major": 16,
        "backup_filename": archive.name,
        "backup_sha256": digest,
        "data_preservation_verified": True,
        "created_utc": "2026-10-12T12:00:00+00:00",
    }), encoding="utf-8")

    result = verify_rehearsal_receipt(
        receipt,
        archive,
        digest,
        expected_database="organizationai_db",
        expected_pg_major=16,
        source_sha="0d17887cf1d6a6571fc8b02b74706343e2555e19",
        start_revision="20261003_07",
        target_revision="20261011_12",
    )

    assert result["backup_sha256"] == digest


def test_rehearsal_receipt_rejects_different_archive_hash(tmp_path: Path):
    archive = tmp_path / "organizationai_db-final.dump"
    archive.write_bytes(b"synthetic archive bytes")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest().upper()
    archive.with_name(archive.name + ".sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="ascii",
    )
    receipt = tmp_path / "auth-migration-rehearsal.json"
    receipt.write_text("{}", encoding="utf-8")

    with pytest.raises(SafeRunnerFailure, match="REHEARSAL_RECEIPT_INVALID"):
        verify_rehearsal_receipt(
            receipt,
            archive,
            "0" * 64,
            expected_database="organizationai_db",
            expected_pg_major=16,
            source_sha="0d17887cf1d6a6571fc8b02b74706343e2555e19",
            start_revision="20261003_07",
            target_revision="20261011_12",
        )


def test_rehearsal_receipt_requires_explicit_paused_writer_confirmation(tmp_path: Path):
    archive = tmp_path / "organizationai_db-final.dump"
    archive.write_bytes(b"synthetic archive bytes")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest().upper()
    archive.with_name(archive.name + ".sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="ascii",
    )
    receipt = tmp_path / "auth-migration-rehearsal.json"
    receipt.write_text(json.dumps({
        "receipt_version": 1,
        "run_id": "20261012T120000Z-0123456789abcdefabcd",
        "result": "PASS",
        "cleanup_complete": True,
        "writers_paused": False,
        "source_sha": "0d17887cf1d6a6571fc8b02b74706343e2555e19",
        "database": "organizationai_db",
        "schema": "public",
        "start_revision": "20261003_07",
        "target_revision": "20261011_12",
        "postgres_major": 16,
        "backup_filename": archive.name,
        "backup_sha256": digest,
        "data_preservation_verified": True,
        "created_utc": "2026-10-12T12:00:00+00:00",
    }), encoding="utf-8")

    with pytest.raises(SafeRunnerFailure, match="REHEARSAL_RECEIPT_INVALID"):
        verify_rehearsal_receipt(
            receipt,
            archive,
            digest,
            expected_database="organizationai_db",
            expected_pg_major=16,
            source_sha="0d17887cf1d6a6571fc8b02b74706343e2555e19",
            start_revision="20261003_07",
            target_revision="20261011_12",
        )


def test_final_backup_receipt_must_be_fresh_and_timezone_aware():
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    validate_final_backup_freshness({"created_utc": (now - timedelta(hours=1)).isoformat()}, now=now)

    with pytest.raises(SafeRunnerFailure, match="FINAL_BACKUP_RECEIPT_STALE"):
        validate_final_backup_freshness({"created_utc": (now - timedelta(hours=13)).isoformat()}, now=now)

    with pytest.raises(SafeRunnerFailure, match="FINAL_BACKUP_RECEIPT_TIMESTAMP_INVALID"):
        validate_final_backup_freshness({"created_utc": "2026-10-12T12:00:00"}, now=now)


def test_final_backup_archive_must_be_recent_and_not_older_than_its_receipt(tmp_path: Path):
    now = datetime.now(timezone.utc)
    archive = tmp_path / "organizationai_db-final.dump"
    archive.write_bytes(b"synthetic backup bytes")
    validate_final_backup_freshness(
        {"created_utc": (now - timedelta(minutes=1)).isoformat()},
        archive_path=archive,
        now=now,
    )

    archive.write_bytes(b"reused older backup bytes")
    old = (now - timedelta(hours=13)).timestamp()
    os.utime(archive, (old, old))
    with pytest.raises(SafeRunnerFailure, match="FINAL_BACKUP_ARCHIVE_STALE"):
        validate_final_backup_freshness(
            {"created_utc": (now - timedelta(minutes=1)).isoformat()},
            archive_path=archive,
            now=now,
        )


def test_pinned_migration_source_is_archived_without_checkout(tmp_path: Path):
    repository_root = Path(__file__).resolve().parents[2]
    run_root = tmp_path / "private-run"
    run_root.mkdir()

    source_root = _prepare_pinned_source(repository_root, run_root)

    assert PINNED_SHA == "0d17887cf1d6a6571fc8b02b74706343e2555e19"
    assert (source_root / "alembic.ini").is_file()
    assert (source_root / "alembic/versions/20261011_12_approval_round_sla.py").is_file()


def test_alembic_uses_extracted_archive_and_restores_process_environment(tmp_path, monkeypatch):
    repository_root = Path(__file__).resolve().parents[2]
    run_root = tmp_path / "alembic-run"
    run_root.mkdir()
    source_root = _prepare_pinned_source(repository_root, run_root)
    url = build_secure_url("postgresql://runner@example.invalid/organizationai_db")
    monkeypatch.setenv("DATABASE_URL", "before-migration-value")
    monkeypatch.setenv("PGPASSWORD", "synthetic-before-value")
    seen = {}

    from alembic import command

    def fake_upgrade(config, revision):
        seen["script_location"] = config.get_main_option("script_location")
        seen["revision"] = revision
        seen["database_url"] = os.environ["DATABASE_URL"]

    monkeypatch.setattr(command, "upgrade", fake_upgrade)

    _run_alembic_upgrade(source_root, url)

    assert seen["script_location"] == str(source_root / "alembic")
    assert seen["revision"] == TARGET_REVISION
    assert "sslmode=require" in seen["database_url"]
    assert os.environ["DATABASE_URL"] == "before-migration-value"
    assert os.environ["PGPASSWORD"] == "synthetic-before-value"


def test_pinned_source_fetches_exact_sha_for_shallow_clone(tmp_path, monkeypatch):
    import io
    import subprocess
    import tarfile

    import scripts.run_auth_live_migration as runner

    run_root = tmp_path / "pinned-source-run"
    run_root.mkdir()
    repository_root = tmp_path / "shallow-checkout"
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w") as archive:
        for name, content in (
            ("alembic.ini", b"[alembic]\n"),
            ("alembic/versions/20261011_12_approval_round_sla.py", b"revision = '20261011_12'\n"),
        ):
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
    pinned_archive = archive_bytes.getvalue()
    calls = []
    fetched = False

    def fake_run(command, **kwargs):
        nonlocal fetched
        calls.append(command)
        if command[1:3] == ["rev-parse", "--verify"]:
            if not fetched:
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
            return subprocess.CompletedProcess(
                command, 0, stdout=f"{runner.PINNED_SHA}\n", stderr="",
            )
        if command[1] == "fetch":
            fetched = True
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[1] == "archive":
            kwargs["stdout"].write(pinned_archive)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError("unexpected Git command")

    monkeypatch.setattr(runner.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "_validate_pinned_migration_chain", lambda _root: None)

    source_root = runner._prepare_pinned_source(repository_root, run_root)

    fetch_calls = [call for call in calls if call[1] == "fetch"]
    assert fetch_calls == [[
        "git",
        "fetch",
        "--no-tags",
        "--depth=1",
        "--no-write-fetch-head",
        "origin",
        runner.PINNED_SHA,
    ]]
    assert [call[1] for call in calls] == ["rev-parse", "fetch", "rev-parse", "archive"]
    assert (source_root / "alembic.ini").is_file()
    assert (source_root / "alembic/versions/20261011_12_approval_round_sla.py").is_file()
    assert not (run_root / "pinned-source.tar").exists()
