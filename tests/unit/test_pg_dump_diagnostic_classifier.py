from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run_auth_migration_rehearsal.ps1"
CLASSIFIER = ROOT / "scripts" / "classify_pg_dump_diagnostic.py"


def _load_classifier():
    spec = importlib.util.spec_from_file_location("pg_dump_diagnostic", CLASSIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_successful_pg_dump_with_stderr_warning_is_not_a_failure() -> None:
    classifier = _load_classifier()
    assert classifier.classify_diagnostic(
        "pg_dump: warning: could not read some noncritical metadata",
        exit_code=0,
        archive_ready=True,
    ) == "STDERR_PRESENT_NONFATAL"


def test_failed_dump_reports_only_allowlisted_category_not_raw_secrets() -> None:
    classifier = _load_classifier()
    raw = (
        "pg_dump: error: password authentication failed for user private-user; "
        "password=super-secret host=db.example.invalid"
    )
    result = classifier.classify_diagnostic(raw, exit_code=1, archive_ready=False)
    assert result == "DATABASE_AUTHENTICATION_FAILED"
    assert "super-secret" not in result
    assert "db.example.invalid" not in result
    assert raw not in result


def test_docker_bind_mount_and_local_backup_permissions_are_distinguished() -> None:
    classifier = _load_classifier()
    assert classifier.classify_diagnostic(
        "docker: invalid mount config for type bind: source path not found",
        exit_code=125,
        archive_ready=False,
    ) == "DOCKER_BIND_MOUNT_FAILED"
    assert classifier.classify_diagnostic(
        "pg_dump: error: could not open output file: Permission denied",
        exit_code=1,
        archive_ready=False,
    ) == "BACKUP_PATH_PERMISSION_FAILED"


def test_zero_exit_without_nonempty_archive_does_not_pass() -> None:
    classifier = _load_classifier()
    assert classifier.classify_diagnostic(
        "", exit_code=0, archive_ready=False
    ) == "ARCHIVE_MISSING_OR_EMPTY"


def test_database_privilege_and_docker_daemon_failures_are_categorized() -> None:
    classifier = _load_classifier()
    assert classifier.classify_diagnostic(
        "pg_dump: error: permission denied for table users; output file target was /backup/run.dump",
        exit_code=1,
        archive_ready=False,
    ) == "DATABASE_PRIVILEGE_FAILED"
    assert classifier.classify_diagnostic(
        "pg_dump: error: permission denied for sequence users_id_seq; output file target was /backup/run.dump",
        exit_code=1,
        archive_ready=False,
    ) == "DATABASE_PRIVILEGE_FAILED"
    assert classifier.classify_diagnostic(
        "docker: error during connect: daemon unavailable",
        exit_code=1,
        archive_ready=False,
    ) == "DOCKER_ENGINE_FAILED"


def test_permission_denied_requires_output_file_context_for_path_classification() -> None:
    classifier = _load_classifier()
    assert classifier.classify_diagnostic(
        'pg_dump: error: could not open output file "/backup/run.dump": Permission denied',
        exit_code=1,
        archive_ready=False,
    ) == "BACKUP_PATH_PERMISSION_FAILED"
    assert classifier.classify_diagnostic(
        'pg_dump: error: could not open output file "/backup/": Is a directory',
        exit_code=1,
        archive_ready=False,
    ) == "BACKUP_PATH_OPEN_FAILED_REDACTED"
    assert classifier.classify_diagnostic(
        "permission denied while reading an unspecified resource",
        exit_code=1,
        archive_ready=False,
    ) == "PERMISSION_DENIED_UNCLASSIFIED"


def test_docker_cli_and_pg_dump_option_errors_are_distinguished() -> None:
    classifier = _load_classifier()
    assert classifier.classify_diagnostic(
        "Error response from daemon: synthetic failure",
        exit_code=1,
        archive_ready=False,
    ) == "DOCKER_CLI_ERROR_REDACTED"
    assert classifier.classify_diagnostic(
        "pg_dump: error: unrecognized option '--synthetic-invalid'",
        exit_code=1,
        archive_ready=False,
    ) == "PG_DUMP_OPTION_ERROR"
    assert classifier.classify_diagnostic(
        "pg_dump: error: could not connect to server: Connection refused",
        exit_code=2,
        archive_ready=False,
    ) == "DATABASE_CONNECTION_FAILED"


def test_runner_captures_exit_code_and_never_prints_raw_dump_diagnostics() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    dump_flow = source[source.index("$dumpExecution = Invoke-PgDumpBackup") :]
    assert "@Arguments 2>&1" in source
    assert "$nativeExitCode = [int]$LASTEXITCODE" in source
    assert "InvocationStatus = 'NATIVE_PROCESS_EXITED'" in source
    assert "InvocationStatus = 'POWERSHELL_EXCEPTION'" in source
    assert "ExitCode = $null" in source
    assert "ExitCode = 9009" not in source
    assert "function New-PgDumpBackupArguments" in source
    assert "function Invoke-PgDumpBackup" in source
    assert "$dumpExecution = Invoke-PgDumpBackup" in source
    assert "PG_DUMP_PROCESS_STATUS={0}" in source
    assert "PG_DUMP_DIAGNOSTIC=" in source
    assert "Write-Host $dumpDiagnosticText" not in source
    assert "Write-Host $dumpResult.DiagnosticText" not in source
    assert dump_flow.index("Clear-SourcePostgresEnvironment") < dump_flow.index(
        "Get-SafePgDumpDiagnosticCode"
    )
    assert "'--mount', $MountSpec" in source
    assert "'--env', 'PGPASSWORD', '--env', 'PGSSLMODE'" in source
    assert "$script:BackupComplete = $true" in source
    assert source.index("'pg_restore', '--list'") < source.index("$script:BackupComplete = $true")


def test_windows_powershell_keeps_pg_dump_output_path_in_one_argument() -> None:
    import os
    import shutil
    import subprocess

    import pytest

    if os.name != "nt":
        pytest.skip("Windows PowerShell argument parsing is Windows-specific")
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell 5.1 is not installed")

    command = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$runnerPath = Join-Path (Get-Location) 'scripts\run_auth_migration_rehearsal.ps1'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($runnerPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { exit 31 }
$functionAst = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'New-PgDumpBackupArguments' }, $true)
if ($null -eq $functionAst) { exit 32 }
. ([scriptblock]::Create($functionAst.Extent.Text))
$archiveName = 'synthetic backup with spaces.dump'
$arguments = @(New-PgDumpBackupArguments 'synthetic-client' 'synthetic-run' 'postgres:16.15' 'type=bind,source=C:\Users\Synthetic User\backup,target=/backup' $archiveName)
$fileArguments = @($arguments | Where-Object { $_ -like '--file=*' })
if ($fileArguments.Count -ne 1) { exit 33 }
if ($fileArguments[0] -cne ('--file=/backup/' + $archiveName)) { exit 34 }
if ($arguments -ccontains $archiveName) { exit 35 }
$mountIndex = [Array]::IndexOf($arguments, '--mount')
if ($mountIndex -lt 0 -or $arguments[$mountIndex + 1] -cne 'type=bind,source=C:\Users\Synthetic User\backup,target=/backup') { exit 36 }
Write-Output 'REGRESSION_PG_DUMP_FILE_ARGUMENT=ONE'
Write-Output 'REGRESSION_MOUNT_ARGUMENT=ONE'
"""
    result = subprocess.run(
        [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=RUNNER.parents[1],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, "PowerShell pg_dump argument regression probe failed"
    assert "REGRESSION_PG_DUMP_FILE_ARGUMENT=ONE" in result.stdout
    assert "REGRESSION_MOUNT_ARGUMENT=ONE" in result.stdout


def test_safe_diagnostic_allowlist_includes_unclassified_permissions() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "PERMISSION_DENIED_UNCLASSIFIED" in source
    assert "BACKUP_PATH_OPEN_FAILED_REDACTED" in source

def test_windows_powershell_preserves_native_exit_after_stderr() -> None:
    import os
    import shutil
    import subprocess

    import pytest

    if os.name != "nt":
        pytest.skip("Windows PowerShell native stderr behavior is Windows-specific")
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell 5.1 is not installed")

    command = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$runnerPath = Join-Path (Get-Location) 'scripts\run_auth_migration_rehearsal.ps1'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($runnerPath, [ref]$tokens, [ref]$parseErrors)
$functionAst = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-DockerClientWithDiagnostic' }, $true)
. ([scriptblock]::Create($functionAst.Extent.Text))
$script:DockerPath = $env:ComSpec
$result = Invoke-DockerClientWithDiagnostic @('/d', '/c', 'echo synthetic-marker 1>&2 & exit /b 37')
if ($result.InvocationStatus -cne 'NATIVE_PROCESS_EXITED') { exit 41 }
if ($result.ExitCode -ne 37) { exit 42 }
if ($result.DiagnosticText -notmatch 'synthetic-marker') { exit 43 }
Write-Output 'REGRESSION_POWERSHELL_NATIVE_STDERR=CAPTURED'
Write-Output 'REGRESSION_NATIVE_EXIT_CODE=37'
"""
    result = subprocess.run(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        cwd=RUNNER.parents[1],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, "PowerShell regression probe failed"
    assert "REGRESSION_POWERSHELL_NATIVE_STDERR=CAPTURED" in result.stdout
    assert "REGRESSION_NATIVE_EXIT_CODE=37" in result.stdout
