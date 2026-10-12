from pathlib import Path

def test_rehearsal_can_resume_a_verified_archive_without_source_credentials():
    source = Path("scripts/run_auth_migration_rehearsal.ps1").read_text(encoding="utf-8")
    assert "ReuseBackupDirectory" in source
    assert "ExpectedBackupSha256" in source
    assert "SOURCE_CONNECTION=SKIPPED_RETAINED_BACKUP" in source
    assert "BACKUP_SHA256_VERIFIED=true" in source
    assert "target=/backup,readonly" in source
    assert "New-VerifiedRetainedBackup" in source
    assert "Invoke-NativeWithDiagnostic" in source
    assert "Get-SafeAlembicDiagnostic" in source

def test_runner_reports_sanitized_phase_exception_and_code_location():
    source = Path("scripts/run_auth_migration_rehearsal.ps1").read_text(encoding="utf-8")
    assert "FAILURE_PHASE=" in source
    assert "FAILURE_EXCEPTION_TYPE=" in source
    assert "FAILURE_CODE_LOCATION=" in source
    assert "$script:FailureSqlState = $null" in source
    assert "VERIFY_EXCEPTION_TYPE=" in source
    assert "VERIFY_EXCEPTION_LOCATION=" in source
    assert "ALEMBIC_UPGRADE_DIAGNOSTIC=" in source
    assert "Alembic stderr will remain available only to the allowlisted classifier." not in source
    assert "Exception.Message" not in source
    assert "Write-Host $_" not in source

def test_retained_backup_validation_helper_rejects_hash_mismatch_on_windows_powershell():
    import os
    import shutil
    import subprocess
    import pytest
    if os.name != "nt":
        pytest.skip("PowerShell file-system behavior is Windows-specific")
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell 5.1 is not installed")
    command = r"""
$ErrorActionPreference = 'Stop'
$runnerPath = Join-Path (Get-Location) 'scripts\run_auth_migration_rehearsal.ps1'
$tokens=$null; $parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($runnerPath,[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count -ne 0){exit 71}
$fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'New-VerifiedRetainedBackup'},$true)
if($null -eq $fn){exit 72}
. ([scriptblock]::Create($fn.Extent.Text))
$root=Join-Path $env:TEMP ('oa-archive-verify-'+[Guid]::NewGuid().ToString('N'))
$dir=Join-Path $root 'run with spaces'
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$outside=$null
try {
  $archive=Join-Path $dir 'organizationai_db-test.dump'
  [IO.File]::WriteAllBytes($archive,[byte[]](1,2,3,4))
  $hash=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
  [IO.File]::WriteAllText(($archive+'.sha256'),($hash+'  organizationai_db-test.dump'),[Text.Encoding]::ASCII)
  $ok=New-VerifiedRetainedBackup $root $dir 'organizationai_db' $hash
  if(-not $ok.Valid -or $ok.Hash -cne $hash){exit 73}
  $bad=New-VerifiedRetainedBackup $root $dir 'organizationai_db' ('0'*64)
  if($bad.Valid -or $bad.Code -cne 'BACKUP_HASH_MISMATCH'){exit 74}
  $outside=Join-Path $env:TEMP ('oa-archive-outside-'+[Guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $outside -Force | Out-Null
  $escape=New-VerifiedRetainedBackup $root $outside 'organizationai_db' $hash
  if($escape.Valid -or $escape.Code -cne 'BACKUP_DIRECTORY_OUTSIDE_PRIVATE_ROOT'){exit 75}
  Write-Output 'RETAINED_BACKUP_HASH_GUARD=PASS'
} finally {
  Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
  if($null -ne $outside -and (Test-Path -LiteralPath $outside)){Remove-Item -LiteralPath $outside -Recurse -Force -ErrorAction SilentlyContinue}
}
"""


def test_handled_pinned_index_difference_clears_stale_failure_diagnostics():
    source = Path("scripts/run_auth_migration_rehearsal.ps1").read_text(encoding="utf-8")
    handled_gap = source.split("if ($knownIndexGapVerified) {", 1)[1].split(
        "Set-RunnerPhase 'POST_MIGRATION_VERIFICATION'", 1
    )[0]
    assert "$script:FailureExceptionType = $null" in handled_gap
    assert "$script:FailureCodeLocation = $null" in handled_gap
    assert "$script:FailureSqlState = $null" in handled_gap


def test_cleanup_rechecks_exact_container_presence_and_retries_only_run_owned_resources():
    source = Path("scripts/run_auth_migration_rehearsal.ps1").read_text(encoding="utf-8")
    assert "function Get-ExactContainerPresence" in source
    assert "function Remove-RunOwnedContainer" in source
    assert "Invoke-NativeWithDiagnostic $script:DockerPath @('container', 'rm', '--force', $Name)" in source
    assert "Invoke-NativeWithDiagnostic $script:DockerPath @('container', 'ls', '--all', '--format', '{{.Names}}')" in source
    assert "'container', 'inspect', '--format', '{{json .Config.Labels}}', $Name" in source
    assert "organizationai.auth-rehearsal.run=" in source
    assert "$removed = Remove-RunOwnedContainer $containerName $runId" in source
    assert "$removed = Remove-RunOwnedContainer $clientName $runId" in source
    assert "TEMPORARY_RESOURCE_CLEANUP_FAILED" in source
    assert "CONTAINER_CLEANUP_DIAGNOSTIC=" in source
