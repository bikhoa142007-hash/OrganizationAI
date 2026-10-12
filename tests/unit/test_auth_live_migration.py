import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

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


def _git(cwd: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=cwd, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _create_pinned_source_fixture(repository_root: Path) -> str:
    repository_root.mkdir(parents=True)
    _git(repository_root, "init", "--quiet")
    _git(repository_root, "config", "user.name", "Render test fixture")
    _git(repository_root, "config", "user.email", "render-fixture@example.invalid")
    (repository_root / "alembic/versions").mkdir(parents=True)
    (repository_root / "src/backend/db").mkdir(parents=True)
    (repository_root / "alembic.ini").write_text(
        "[alembic]\nscript_location = alembic\n", encoding="utf-8",
    )
    (repository_root / "alembic/env.py").write_text("# fixture env\n", encoding="utf-8")
    (repository_root / "alembic/versions/20261003_07_fixture.py").write_text(
        "revision = '20261003_07'\ndown_revision = None\n",
        encoding="utf-8",
    )
    (repository_root / "alembic/versions/20261011_12_approval_round_sla.py").write_text(
        "revision = '20261011_12'\ndown_revision = '20261003_07'\n",
        encoding="utf-8",
    )
    (repository_root / "src/backend/db/__init__.py").write_text(
        "FIXTURE_SOURCE = 'fixture-v1'\n", encoding="utf-8",
    )
    (repository_root / "requirements.txt").write_text(
        "fixture-dependency==1\n", encoding="utf-8",
    )
    _git(repository_root, "add", "alembic.ini", "alembic", "src/backend/db", "requirements.txt")
    _git(repository_root, "commit", "--quiet", "-m", "Create pinned source fixture")
    return _git(repository_root, "rev-parse", "HEAD")


def _create_shallow_source_clone(tmp_path: Path) -> tuple[Path, str]:
    source_repository = tmp_path / "source-repository"
    pinned_sha = _create_pinned_source_fixture(source_repository)
    (source_repository / "requirements.txt").write_text(
        "fixture-dependency==2\n", encoding="utf-8",
    )
    _git(source_repository, "add", "requirements.txt")
    _git(source_repository, "commit", "--quiet", "-m", "Advance fixture branch")
    bare_remote = tmp_path / "fixture-origin.git"
    _git(tmp_path, "clone", "--bare", str(source_repository), str(bare_remote))
    shallow_clone = tmp_path / "shallow-checkout"
    _git(tmp_path, "clone", "--depth=1", bare_remote.as_uri(), str(shallow_clone))
    return shallow_clone, pinned_sha


def _git_state(repository_root: Path) -> tuple[str, str, str]:
    return (
        _git(repository_root, "rev-parse", "HEAD"),
        _git(repository_root, "symbolic-ref", "--short", "HEAD"),
        _git(repository_root, "status", "--porcelain"),
    )


def test_pinned_migration_source_is_archived_without_checkout(tmp_path: Path):
    import scripts.run_auth_live_migration as runner

    repository_root = tmp_path / "fixture-repository"
    fixture_sha = _create_pinned_source_fixture(repository_root)
    run_root = tmp_path / "private-run"
    run_root.mkdir()
    before = _git_state(repository_root)

    source_root = runner._prepare_source_archive(repository_root, run_root, fixture_sha)

    assert PINNED_SHA == "0d17887cf1d6a6571fc8b02b74706343e2555e19"
    assert (source_root / "alembic.ini").read_text(encoding="utf-8") == (
        "[alembic]\nscript_location = alembic\n"
    )
    assert (source_root / "src/backend/db/__init__.py").read_text(encoding="utf-8") == (
        "FIXTURE_SOURCE = 'fixture-v1'\n"
    )
    assert _git_state(repository_root) == before
    assert not (run_root / "pinned-source.tar").exists()


def test_production_pinned_source_uses_only_the_reviewed_sha(tmp_path, monkeypatch):
    import scripts.run_auth_live_migration as runner

    observed = {}
    expected_path = tmp_path / "extracted-source"
    monkeypatch.setattr(
        runner,
        "_prepare_source_archive",
        lambda repository_root, run_root, source_sha: observed.update(
            repository_root=repository_root, run_root=run_root, source_sha=source_sha,
        ) or expected_path,
    )

    result = _prepare_pinned_source(tmp_path / "checkout", tmp_path / "run")

    assert result == expected_path
    assert observed["source_sha"] == PINNED_SHA


def test_alembic_uses_extracted_archive_and_restores_process_environment(tmp_path, monkeypatch):
    import scripts.run_auth_live_migration as runner

    repository_root = tmp_path / "fixture-repository"
    fixture_sha = _create_pinned_source_fixture(repository_root)
    run_root = tmp_path / "alembic-run"
    run_root.mkdir()
    source_root = runner._prepare_source_archive(repository_root, run_root, fixture_sha)
    url = build_secure_url("postgresql://runner@example.invalid/organizationai_db")
    monkeypatch.setenv("DATABASE_URL", "before-migration-value")
    monkeypatch.setenv("PGPASSWORD", "synthetic-before-value")
    monkeypatch.delenv("PGSERVICE", raising=False)
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
    assert "PGSERVICE" not in os.environ


def test_alembic_failure_restores_process_environment(tmp_path, monkeypatch):
    import scripts.run_auth_live_migration as runner

    repository_root = tmp_path / "fixture-repository"
    fixture_sha = _create_pinned_source_fixture(repository_root)
    run_root = tmp_path / "alembic-failure-run"
    run_root.mkdir()
    source_root = runner._prepare_source_archive(repository_root, run_root, fixture_sha)
    url = build_secure_url("postgresql://runner@example.invalid/organizationai_db")
    monkeypatch.setenv("DATABASE_URL", "before-failure-value")
    monkeypatch.setenv("PGPASSWORD", "synthetic-before-failure")
    monkeypatch.delenv("PGSERVICE", raising=False)

    from alembic import command

    def failing_upgrade(config, revision):
        assert config.get_main_option("script_location") == str(source_root / "alembic")
        assert revision == TARGET_REVISION
        raise subprocess.CalledProcessError(1, ["alembic", "upgrade"])

    monkeypatch.setattr(command, "upgrade", failing_upgrade)

    with pytest.raises(SafeRunnerFailure, match="PINNED_ALEMBIC_UPGRADE_FAILED"):
        _run_alembic_upgrade(source_root, url)

    assert os.environ["DATABASE_URL"] == "before-failure-value"
    assert os.environ["PGPASSWORD"] == "synthetic-before-failure"
    assert "PGSERVICE" not in os.environ


def test_pinned_source_fetches_exact_sha_from_local_shallow_clone(tmp_path):
    import scripts.run_auth_live_migration as runner

    repository_root, fixture_sha = _create_shallow_source_clone(tmp_path)
    git = shutil.which("git.exe") or shutil.which("git")
    assert git
    missing = subprocess.run(
        [git, "cat-file", "-e", f"{fixture_sha}^{{commit}}"],
        cwd=repository_root, capture_output=True, check=False,
    )
    assert missing.returncode != 0
    run_root = tmp_path / "pinned-source-run"
    run_root.mkdir()
    before = _git_state(repository_root)
    calls = []

    def real_git(command, **kwargs):
        calls.append(command)
        return subprocess.run(command, **kwargs)

    source_root = runner._prepare_source_archive(
        repository_root, run_root, fixture_sha, git_executable=git, run_process=real_git,
    )

    assert [call[1] for call in calls] == ["rev-parse", "fetch", "rev-parse", "archive"]
    assert calls[1][1:] == [
        "fetch", "--no-tags", "--depth=1", "--no-write-fetch-head", "origin", fixture_sha,
    ]
    assert (source_root / "src/backend/db/__init__.py").read_text(encoding="utf-8") == (
        "FIXTURE_SOURCE = 'fixture-v1'\n"
    )
    assert _git_state(repository_root) == before


@pytest.mark.parametrize(
    ("fetch_result", "expected_code"),
    (("failure", "PINNED_SOURCE_FETCH_FAILED"), ("timeout", "PINNED_SOURCE_FETCH_TIMEOUT"),
     ("sha_mismatch", "PINNED_SOURCE_SHA_UNAVAILABLE")),
)
def test_pinned_source_fetch_errors_are_classified_offline(
    tmp_path, fetch_result, expected_code,
):
    import scripts.run_auth_live_migration as runner

    repository_root, fixture_sha = _create_shallow_source_clone(tmp_path)
    run_root = tmp_path / "pinned-source-failure-run"
    run_root.mkdir()
    git = shutil.which("git.exe") or shutil.which("git")
    assert git
    resolve_count = 0

    def controlled_git(command, **kwargs):
        nonlocal resolve_count
        if command[1] == "fetch" and fetch_result == "failure":
            return subprocess.CompletedProcess(command, 128, stdout="", stderr="local fixture failure")
        if command[1] == "fetch" and fetch_result == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))
        if command[1:3] == ["rev-parse", "--verify"]:
            resolve_count += 1
            if fetch_result == "sha_mismatch" and resolve_count == 2:
                return subprocess.CompletedProcess(command, 0, stdout=f"{'f' * 40}\n", stderr="")
        return subprocess.run(command, **kwargs)

    with pytest.raises(SafeRunnerFailure, match=expected_code):
        runner._prepare_source_archive(
            repository_root, run_root, fixture_sha,
            git_executable=git, run_process=controlled_git,
        )
