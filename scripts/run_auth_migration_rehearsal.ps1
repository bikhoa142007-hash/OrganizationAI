[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$PinnedSha = '0d17887cf1d6a6571fc8b02b74706343e2555e19'
$ExpectedDatabase = 'organizationai_db'
$ExpectedStartRevision = '20261003_07'
$TargetRevision = '20261011_12'
$script:FailureCode = $null
$script:BackupComplete = $false
$script:ContainerCreated = $false
$script:ContainerCreationAttempted = $false
$script:BackupDirectoryCreated = $false
$script:WorkingDirectoryCreated = $false
$script:ClientContainerNames = [System.Collections.Generic.List[string]]::new()
$script:CleanupPending = $false
$script:CleanupPendingResource = $null
$script:DockerPath = $null
$script:PsqlPath = $null
$script:PythonPath = $null
$sourcePassword = $null
$sourceUri = $null
$sourceUrlText = $null
$secureUrl = $null
$bstr = [IntPtr]::Zero
$tempPassword = $null
$tempDatabaseUrl = $null
$containerName = $null
$backupDirectory = $null
$workingDirectory = $null
$archivePath = $null
$archiveHash = $null

$runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 20)
$containerName = 'oa-auth-rehearsal-' + $runId.Replace('-', '')
$tempUser = 'oa_rehearsal'
$tempDatabase = ('oa_rehearsal_' + $runId.Replace('-', '')).ToLowerInvariant()
$containerArchive = '/tmp/' + $tempDatabase + '.dump'

$environmentNames = @(
    'DATABASE_URL', 'AUTH_ALLOW_SQLITE_MIGRATION_TESTS',
    'PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGUSER', 'PGDATABASE', 'PGPASSWORD', 'PGPASSFILE',
    'PGSSLMODE', 'PGSSLCERT', 'PGSSLKEY', 'PGSSLROOTCERT', 'PGSSLCRL', 'PGSSLCRLDIR',
    'PGSSLNEGOTIATION', 'PGGSSENCMODE', 'PGREQUIRESSL', 'PGCHANNELBINDING', 'PGAPPNAME',
    'PGCONNECT_TIMEOUT', 'PGOPTIONS', 'PGSERVICE', 'PGSERVICEFILE',
    'PGTARGETSESSIONATTRS', 'POSTGRES_USER', 'POSTGRES_DB', 'POSTGRES_PASSWORD',
    'OA_EXPECTED_PG_MAJOR', 'OA_EXPECTED_TEMP_DB', 'PYTHONPATH'
)
$environmentSnapshot = @{}
foreach ($name in $environmentNames) {
    $environmentSnapshot[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

function Set-ProcessEnvironment {
    param([string]$Name, [AllowNull()][string]$Value)
    [Environment]::SetEnvironmentVariable($Name, $Value, 'Process')
}

function Stop-Safely {
    param([string]$Code)
    $script:FailureCode = $Code
    throw [System.InvalidOperationException]::new('Safe runner stop')
}

function Invoke-NativeQuiet {
    param([string]$FilePath, [string[]]$Arguments)
    try {
        $null = & $FilePath @Arguments 2>$null
        return [int]$LASTEXITCODE
    }
    catch {
        return 9009
    }
}

function Protect-Directory {
    param([string]$Path)
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $userGrant = $identity + ':(OI)(CI)F'
    $null = & icacls.exe $Path '/inheritance:r' '/grant:r' $userGrant 'SYSTEM:(OI)(CI)F' '/c' 2>$null
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely 'PRIVATE_DIRECTORY_ACL_FAILED'
    }
}

function Set-PostgresEnvironment {
    param(
        [string]$HostName,
        [int]$Port,
        [string]$UserName,
        [string]$Database,
        [string]$Password,
        [string]$SslMode,
        [string]$Options
    )
    Set-ProcessEnvironment 'PGHOST' $HostName
    Set-ProcessEnvironment 'PGHOSTADDR' $null
    Set-ProcessEnvironment 'PGPORT' ([string]$Port)
    Set-ProcessEnvironment 'PGUSER' $UserName
    Set-ProcessEnvironment 'PGDATABASE' $Database
    Set-ProcessEnvironment 'PGPASSWORD' $Password
    Set-ProcessEnvironment 'PGPASSFILE' $null
    Set-ProcessEnvironment 'PGSSLMODE' $SslMode
    Set-ProcessEnvironment 'PGSSLCERT' $null
    Set-ProcessEnvironment 'PGSSLKEY' $null
    Set-ProcessEnvironment 'PGSSLROOTCERT' $null
    Set-ProcessEnvironment 'PGSSLCRL' $null
    Set-ProcessEnvironment 'PGSSLCRLDIR' $null
    Set-ProcessEnvironment 'PGSSLNEGOTIATION' $null
    Set-ProcessEnvironment 'PGGSSENCMODE' 'disable'
    Set-ProcessEnvironment 'PGREQUIRESSL' $null
    Set-ProcessEnvironment 'PGCHANNELBINDING' $null
    Set-ProcessEnvironment 'PGAPPNAME' $null
    Set-ProcessEnvironment 'PGCONNECT_TIMEOUT' '10'
    Set-ProcessEnvironment 'PGOPTIONS' $Options
    Set-ProcessEnvironment 'PGSERVICE' $null
    Set-ProcessEnvironment 'PGSERVICEFILE' $null
    Set-ProcessEnvironment 'PGTARGETSESSIONATTRS' $null
}

function Invoke-DockerClient {
    param([string[]]$Arguments)
    try {
        $null = & $script:DockerPath @Arguments 2>$null
        return [int]$LASTEXITCODE
    }
    catch {
        return 9009
    }
}

function Invoke-DockerClientWithDiagnostic {
    param([string[]]$Arguments)

    $previousErrorActionPreference = $ErrorActionPreference
    $nativePreferenceVariable = Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue
    $hasNativePreferenceVariable = $null -ne $nativePreferenceVariable
    if ($hasNativePreferenceVariable) {
        $previousNativePreference = $nativePreferenceVariable.Value
    }

    try {
        # Windows PowerShell 5.1 turns redirected native stderr into a terminating
        # NativeCommandError when ErrorActionPreference is Stop. Capture it as data
        # so the process exit code and redacted diagnostic remain distinguishable.
        $ErrorActionPreference = 'Continue'
        if ($hasNativePreferenceVariable) {
            Set-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Local -Value $false
        }

        $capturedOutput = @(& $script:DockerPath @Arguments 2>&1)
        # Read this before any other command so it is the native docker.exe result.
        $nativeExitCode = [int]$LASTEXITCODE
        $diagnosticLines = @($capturedOutput | ForEach-Object { [string]$_ })
        return [pscustomobject]@{
            InvocationStatus = 'NATIVE_PROCESS_EXITED'
            ExitCode = $nativeExitCode
            PowerShellFailure = $null
            DiagnosticText = [string]::Join([Environment]::NewLine, $diagnosticLines)
        }
    }
    catch {
        $exceptionName = $_.Exception.GetType().Name
        $failureCode = switch ($exceptionName) {
            'CommandNotFoundException' { 'EXECUTABLE_NOT_FOUND'; break }
            'Win32Exception' { 'PROCESS_START_FAILED'; break }
            'UnauthorizedAccessException' { 'PROCESS_ACCESS_DENIED'; break }
            'NativeCommandError' { 'POWERSHELL_NATIVE_STDERR_EXCEPTION'; break }
            'RemoteException' { 'POWERSHELL_NATIVE_STDERR_EXCEPTION'; break }
            default { 'POWERSHELL_INVOCATION_EXCEPTION' }
        }
        return [pscustomobject]@{
            InvocationStatus = 'POWERSHELL_EXCEPTION'
            ExitCode = $null
            PowerShellFailure = $failureCode
            DiagnosticText = ''
        }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        if ($hasNativePreferenceVariable) {
            Set-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Local -Value $previousNativePreference
        }
    }
}

function New-PgDumpBackupArguments {
    param(
        [string]$ContainerName,
        [string]$RunId,
        [string]$Image,
        [string]$MountSpec,
        [string]$ArchiveFileName
    )

    return @(
        'run', '--rm', '--name', $ContainerName,
        '--label', ('organizationai.auth-rehearsal.run=' + $RunId),
        '--mount', $MountSpec,
        '--env', 'PGHOST', '--env', 'PGPORT', '--env', 'PGUSER',
        '--env', 'PGDATABASE', '--env', 'PGPASSWORD', '--env', 'PGSSLMODE',
        '--env', 'PGCONNECT_TIMEOUT', '--env', 'PGOPTIONS', '--env', 'PGGSSENCMODE',
        $Image, 'pg_dump', '--no-password', '--format=custom',
        '--lock-wait-timeout=10s', ('--file=/backup/' + $ArchiveFileName)
    )
}

function Invoke-PgDumpBackup {
    param(
        [string]$ContainerName,
        [string]$RunId,
        [string]$Image,
        [string]$MountSpec,
        [string]$BackupDirectory,
        [string]$ArchiveFileName
    )

    $archivePath = Join-Path $BackupDirectory $ArchiveFileName
    if (Test-Path -LiteralPath $archivePath) {
        Stop-Safely 'BACKUP_ARCHIVE_PATH_COLLISION'
    }

    $dumpArguments = New-PgDumpBackupArguments `
        $ContainerName $RunId $Image $MountSpec $ArchiveFileName
    $processResult = Invoke-DockerClientWithDiagnostic $dumpArguments
    $archiveReady = $false
    if (Test-Path -LiteralPath $archivePath) {
        $archiveReady = (Get-Item -LiteralPath $archivePath).Length -gt 0
    }
    return [pscustomobject]@{
        ProcessResult = $processResult
        ArchiveReady = $archiveReady
    }
}

function Clear-SourcePostgresEnvironment {
    foreach ($name in @('DATABASE_URL', 'POSTGRES_USER', 'POSTGRES_DB', 'POSTGRES_PASSWORD')) {
        Set-ProcessEnvironment $name $null
    }
    foreach ($name in @(
        'PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGUSER', 'PGDATABASE', 'PGPASSWORD', 'PGPASSFILE',
        'PGSSLMODE', 'PGSSLCERT', 'PGSSLKEY', 'PGSSLROOTCERT', 'PGSSLCRL', 'PGSSLCRLDIR',
        'PGSSLNEGOTIATION', 'PGGSSENCMODE', 'PGREQUIRESSL', 'PGCHANNELBINDING', 'PGAPPNAME',
        'PGCONNECT_TIMEOUT', 'PGOPTIONS', 'PGSERVICE', 'PGSERVICEFILE', 'PGTARGETSESSIONATTRS'
    )) {
        Set-ProcessEnvironment $name $null
    }
}

function Get-SafePgDumpDiagnosticCode {
    param(
        [string]$DiagnosticText,
        [int]$ExitCode,
        [bool]$ArchiveReady
    )
    $classifierPath = Join-Path $repoRoot 'scripts\classify_pg_dump_diagnostic.py'
    if (-not (Test-Path -LiteralPath $classifierPath)) {
        return 'DIAGNOSTIC_CLASSIFIER_UNAVAILABLE'
    }
    $classifierArguments = @($classifierPath, '--exit-code', [string]$ExitCode)
    if ($ArchiveReady) {
        $classifierArguments += '--archive-ready'
    }
    try {
        $classifierOutput = @($DiagnosticText | & $script:PythonPath @classifierArguments 2>$null)
        $classifierExitCode = [int]$LASTEXITCODE
        $safeCode = ([string](@($classifierOutput | Select-Object -Last 1))).Trim()
        if ($classifierExitCode -eq 0 -and $safeCode -cmatch '^(NONE|STDERR_PRESENT_NONFATAL|ARCHIVE_MISSING_OR_EMPTY|DOCKER_BIND_MOUNT_FAILED|DOCKER_ENGINE_FAILED|DOCKER_CLI_ERROR_REDACTED|DOCKER_RUN_START_OR_COMMAND_FAILED|DOCKER_RUN_OR_CONTAINER_ERROR_REDACTED|BACKUP_PATH_PERMISSION_FAILED|BACKUP_PATH_OPEN_FAILED_REDACTED|DATABASE_AUTHENTICATION_FAILED|DATABASE_PRIVILEGE_FAILED|BACKUP_STORAGE_FAILED|PG_DUMP_VERSION_MISMATCH|PG_DUMP_OPTION_ERROR|DATABASE_CONNECTION_FAILED|PERMISSION_DENIED_UNCLASSIFIED|ERROR_OUTPUT_UNAVAILABLE|PG_DUMP_ERROR_REDACTED)$') {
            return $safeCode
        }
    }
    catch {
        return 'DIAGNOSTIC_CLASSIFIER_UNAVAILABLE'
    }
    return 'DIAGNOSTIC_CLASSIFIER_UNAVAILABLE'
}

function Register-ClientContainer {
    param([string]$Suffix)
    $name = 'oa-client-' + $Suffix + '-' + $runId.Replace('-', '')
    $script:ClientContainerNames.Add($name)
    return $name
}

function Run-VerificationHelper {
    param([string[]]$Arguments)
    try {
        $null = & $script:PythonPath @Arguments 2>$null
        return [int]$LASTEXITCODE
    }
    catch {
        return 9009
    }
}

try {
    $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
    $privateRoot = Join-Path $env:LOCALAPPDATA 'OrganizationAI\AuthSchemaRehearsal'
    $backupDirectory = Join-Path $privateRoot $runId
    $workingDirectory = Join-Path $privateRoot ('work-' + $runId)
    $archiveFileName = $ExpectedDatabase + '-' + $runId + '.dump'
    $archivePath = Join-Path $backupDirectory $archiveFileName
    $hashPath = Join-Path $backupDirectory ($archiveFileName + '.sha256')

    $backupRootFull = [IO.Path]::GetFullPath($privateRoot).TrimEnd('\')
    $repoPrefix = [IO.Path]::GetFullPath($repoRoot).TrimEnd('\') + '\'
    if ($backupRootFull.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Safely 'BACKUP_PATH_INSIDE_WORKTREE'
    }
    $ancestor = [IO.Path]::GetFullPath($env:LOCALAPPDATA)
    while (-not [string]::IsNullOrWhiteSpace($ancestor)) {
        if (Test-Path -LiteralPath (Join-Path $ancestor '.git')) {
            Stop-Safely 'BACKUP_PATH_INSIDE_GIT'
        }
        $parent = [IO.Directory]::GetParent($ancestor)
        if ($null -eq $parent) { break }
        $ancestor = $parent.FullName
    }

    $gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($null -eq $gitCommand) {
        Stop-Safely 'GIT_NOT_FOUND'
    }
    $dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($null -eq $dockerCommand) {
        $dockerFallback = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
        if (Test-Path -LiteralPath $dockerFallback) {
            $script:DockerPath = $dockerFallback
        }
        else {
            Stop-Safely 'DOCKER_CLI_NOT_FOUND'
        }
    }
    else {
        $script:DockerPath = $dockerCommand.Source
    }
    Write-Host ('DOCKER_EXECUTABLE={0}' -f $script:DockerPath)
    $psqlCommand = Get-Command psql.exe -ErrorAction SilentlyContinue
    if ($null -eq $psqlCommand) {
        $psqlFallback = 'C:\Program Files\PostgreSQL\18\bin\psql.exe'
        if (Test-Path -LiteralPath $psqlFallback) {
            $script:PsqlPath = $psqlFallback
        }
        else {
            Stop-Safely 'PSQL_NOT_FOUND'
        }
    }
    else {
        $script:PsqlPath = $psqlCommand.Source
    }

    $pythonCandidates = @(
        (Join-Path $repoRoot '.venv-test-20261009\Scripts\python.exe'),
        'C:\Users\Khoa Bi\VS Studio\repos\OrganizationAI\.venv-test-20261009\Scripts\python.exe'
    )
    $script:PythonPath = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($script:PythonPath)) {
        Stop-Safely 'PINNED_PYTHON_NOT_FOUND'
    }
    if ((Invoke-NativeQuiet $script:PythonPath @('-c', 'import alembic, sqlalchemy, psycopg')) -ne 0) {
        Stop-Safely 'PINNED_PYTHON_DEPENDENCIES_MISSING'
    }

    $dockerVersion = & $script:DockerPath 'info' '--format' '{{.ServerVersion}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$dockerVersion)) {
        Stop-Safely 'DOCKER_ENGINE_UNAVAILABLE'
    }
    $psqlVersion = & $script:PsqlPath '--version' 2>$null
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely 'PSQL_UNAVAILABLE'
    }

    Write-Host 'Before continuing, open Render Dashboard locally:'
    Write-Host '1. In the Auth API environment, confirm DATABASE_URL references the intended PostgreSQL service.'
    Write-Host '2. Open that PostgreSQL service and use its External Database URL. Internal URLs may not be reachable from Windows.'
    Write-Host '3. Do not paste the URL, password, or screenshots containing secrets into chat. This runner does not use pg_control_system() or require extra database grants.'
    $dashboardConfirmed = Read-Host 'After confirming the API-to-PostgreSQL service link, type YES'
    if ($dashboardConfirmed -cne 'YES') {
        Stop-Safely 'DASHBOARD_LINK_NOT_CONFIRMED'
    }

    $secureUrl = Read-Host -AsSecureString 'Enter the External Database URL (input hidden)'
    if ($null -eq $secureUrl -or $secureUrl.Length -eq 0) {
        Stop-Safely 'EXTERNAL_URL_EMPTY'
    }
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureUrl)
    $sourceUrlText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    $bstr = [IntPtr]::Zero
    $secureUrl.Dispose()
    $secureUrl = $null

    try {
        $sourceUri = [Uri]::new($sourceUrlText, [UriKind]::Absolute)
    }
    catch {
        Stop-Safely 'EXTERNAL_URL_FORMAT_INVALID'
    }
    if ($sourceUri.Scheme -notin @('postgres', 'postgresql') -or
        [string]::IsNullOrWhiteSpace($sourceUri.Host) -or
        [string]::IsNullOrWhiteSpace($sourceUri.UserInfo) -or
        [string]::IsNullOrWhiteSpace($sourceUri.AbsolutePath.Trim('/'))) {
        Stop-Safely 'EXTERNAL_URL_FORMAT_INVALID'
    }
    $userInfo = $sourceUri.UserInfo
    $separator = $userInfo.IndexOf(':')
    if ($separator -le 0 -or $separator -ge ($userInfo.Length - 1)) {
        Stop-Safely 'EXTERNAL_URL_CREDENTIALS_INVALID'
    }
    $sourceUser = [Uri]::UnescapeDataString($userInfo.Substring(0, $separator))
    $sourcePassword = [Uri]::UnescapeDataString($userInfo.Substring($separator + 1))
    $sourceHost = $sourceUri.DnsSafeHost
    $sourcePort = if ($sourceUri.IsDefaultPort) { 5432 } else { $sourceUri.Port }
    $sourceDatabase = [Uri]::UnescapeDataString($sourceUri.AbsolutePath.Trim('/'))
    $sourceUri = $null
    $userInfo = $null
    $sourceUrlText = $null

    if ($sourceDatabase -cne $ExpectedDatabase) {
        Stop-Safely 'SOURCE_DATABASE_NAME_MISMATCH'
    }
    if ([string]::IsNullOrWhiteSpace($sourcePassword)) {
        Stop-Safely 'EXTERNAL_URL_PASSWORD_MISSING'
    }

    New-Item -ItemType Directory -Path $privateRoot -Force | Out-Null
    $resolvedPrivateRoot = (Resolve-Path -LiteralPath $privateRoot).Path
    if ([IO.Path]::GetFullPath($resolvedPrivateRoot).StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Safely 'BACKUP_PATH_RESOLVES_INSIDE_WORKTREE'
    }
    $resolvedAncestor = [IO.Path]::GetFullPath($resolvedPrivateRoot)
    while (-not [string]::IsNullOrWhiteSpace($resolvedAncestor)) {
        if (Test-Path -LiteralPath (Join-Path $resolvedAncestor '.git')) {
            Stop-Safely 'BACKUP_PATH_RESOLVES_INSIDE_GIT'
        }
        $resolvedParent = [IO.Directory]::GetParent($resolvedAncestor)
        if ($null -eq $resolvedParent) { break }
        $resolvedAncestor = $resolvedParent.FullName
    }
    if ((Test-Path -LiteralPath $backupDirectory) -or (Test-Path -LiteralPath $workingDirectory)) {
        Stop-Safely 'RUN_DIRECTORY_COLLISION'
    }
    New-Item -ItemType Directory -Path $backupDirectory | Out-Null
    $script:BackupDirectoryCreated = $true
    Protect-Directory $backupDirectory
    New-Item -ItemType Directory -Path $workingDirectory | Out-Null
    $script:WorkingDirectoryCreated = $true
    Protect-Directory $workingDirectory

    Set-PostgresEnvironment $sourceHost $sourcePort $sourceUser $sourceDatabase $sourcePassword 'require' '-c default_transaction_read_only=on -c statement_timeout=1800000 -c lock_timeout=10000'
    Set-ProcessEnvironment 'DATABASE_URL' $null
    Set-ProcessEnvironment 'AUTH_ALLOW_SQLITE_MIGRATION_TESTS' $null

    $sourceProbeSql = @'
BEGIN TRANSACTION READ ONLY;
SELECT current_database(),
       current_setting('server_version_num'),
       COALESCE(current_schema(), ''),
       current_setting('search_path'),
       COALESCE((SELECT string_agg(version_num, ',' ORDER BY version_num) FROM public.alembic_version), 'NONE'),
       (SELECT count(*)::text FROM public.alembic_version),
       to_regclass('users') = to_regclass('public.users'),
       to_regclass('roles') = to_regclass('public.roles'),
       to_regclass('user_roles') = to_regclass('public.user_roles'),
       array_position(current_schemas(false), 'public') IS NOT NULL,
       COALESCE((SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()), false);
ROLLBACK;
'@
    $probeArguments = @(
        '-X', '-q', '-t', '-A', '-F', '|', '-w',
        '--set=ON_ERROR_STOP=1',
        '--host', $sourceHost, '--port', [string]$sourcePort,
        '--username', $sourceUser, '--dbname', $sourceDatabase,
        '--command', $sourceProbeSql
    )
    $probeOutput = & $script:PsqlPath @probeArguments 2>$null
    $probeExit = $LASTEXITCODE
    if ($probeExit -ne 0) {
        Stop-Safely 'SOURCE_READONLY_PROBE_FAILED'
    }
    $probeLine = [string](@($probeOutput | Where-Object { ([string]$_).Contains('|') } | Select-Object -Last 1))
    $probeFields = $probeLine.Split('|')
    if ($probeFields.Length -ne 11) {
        Stop-Safely 'SOURCE_READONLY_PROBE_INVALID'
    }
    $sourceDatabase = $probeFields[0]
    $serverVersionNumber = 0
    if (-not [int]::TryParse($probeFields[1], [ref]$serverVersionNumber)) {
        Stop-Safely 'SOURCE_VERSION_INVALID'
    }
    $sourceSchema = $probeFields[2]
    $sourceSearchPath = $probeFields[3]
    $sourceRevision = $probeFields[4]
    $sourceRevisionCount = $probeFields[5]
    $authResolution = @($probeFields[6], $probeFields[7], $probeFields[8])
    $publicInSearchPath = $probeFields[9]
    $tlsActive = $probeFields[10]
    $serverMajor = [int][Math]::Floor($serverVersionNumber / 10000)

    if ($sourceDatabase -cne $ExpectedDatabase) {
        Stop-Safely 'SOURCE_DATABASE_NAME_MISMATCH'
    }
    if ($sourceSchema -cne 'public' -or [string]::IsNullOrWhiteSpace($sourceSearchPath) -or $publicInSearchPath -cne 't') {
        Stop-Safely 'SOURCE_SCHEMA_OR_SEARCH_PATH_MISMATCH'
    }
    if (@($authResolution | Where-Object { $_ -cne 't' }).Count -ne 0) {
        Stop-Safely 'SOURCE_AUTH_TABLE_RESOLUTION_MISMATCH'
    }
    if ($tlsActive -cne 't') {
        Stop-Safely 'SOURCE_TLS_NOT_ACTIVE'
    }
    if ($sourceRevisionCount -cne '1' -or $sourceRevision -cne $ExpectedStartRevision) {
        Stop-Safely 'SOURCE_ALEMBIC_REVISION_MISMATCH'
    }
    if ($serverMajor -lt 12 -or $serverMajor -gt 99) {
        Stop-Safely 'SOURCE_POSTGRES_MAJOR_UNSUPPORTED'
    }
    Write-Host ('Verified source identity: database={0}, schema={1}, revision={2}, PostgreSQL major={3}, TLS=active.' -f $sourceDatabase, $sourceSchema, $sourceRevision, $serverMajor)

    $resolvedSha = & $gitCommand.Source '-C' $repoRoot 'rev-parse' ($PinnedSha + '^{commit}') 2>$null
    if ($LASTEXITCODE -ne 0 -or ([string]$resolvedSha).Trim() -cne $PinnedSha) {
        Stop-Safely 'PINNED_SOURCE_SHA_UNAVAILABLE'
    }
    $sourceZip = Join-Path $workingDirectory 'pinned-source.zip'
    $sourceRoot = Join-Path $workingDirectory 'pinned-source'
    $null = & $gitCommand.Source '-C' $repoRoot 'archive' '--format=zip' ('--output=' + $sourceZip) $PinnedSha 2>$null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $sourceZip)) {
        Stop-Safely 'PINNED_SOURCE_ARCHIVE_FAILED'
    }
    Expand-Archive -LiteralPath $sourceZip -DestinationPath $sourceRoot
    Remove-Item -LiteralPath $sourceZip -Force
    $expectedMigration = Join-Path $sourceRoot 'alembic\versions\20261011_12_approval_round_sla.py'
    $expectedEnv = Join-Path $sourceRoot 'alembic\env.py'
    if (-not (Test-Path -LiteralPath $expectedMigration) -or -not (Test-Path -LiteralPath $expectedEnv)) {
        Stop-Safely 'PINNED_MIGRATION_FILES_MISSING'
    }
    Set-ProcessEnvironment 'PYTHONPATH' $sourceRoot

    $helperPath = Join-Path $workingDirectory 'verify_rehearsal.py'
    $baselinePath = Join-Path $workingDirectory 'baseline_counts.json'
    $helperSource = @'
from __future__ import annotations
import json
import hashlib
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

START_REVISION = "20261003_07"
TARGET_REVISION = "20261011_12"

def read_revision(connection):
    value, count = connection.execute(text(
        "SELECT COALESCE(string_agg(version_num, ',' ORDER BY version_num), ''), count(*) "
        "FROM public.alembic_version"
    )).one()
    return value, int(count)

def fingerprint_table(connection, table_name, columns, primary_key):
    if not primary_key:
        raise RuntimeError("baseline table has no primary key")
    preparer = connection.dialect.identifier_preparer
    qualified = preparer.quote_schema("public") + "." + preparer.quote(table_name)
    selected = ", ".join(preparer.quote(name) for name in columns)
    ordering = ", ".join(preparer.quote(name) for name in primary_key)
    result = connection.execution_options(stream_results=True).execute(
        text(f"SELECT {selected} FROM {qualified} ORDER BY {ordering}")
    )
    digest = hashlib.sha256()
    row_count = 0
    for row in result:
        payload = json.dumps(
            list(row), sort_keys=True, default=str,
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        digest.update(payload)
        digest.update(b"\\n")
        row_count += 1
    return row_count, digest.hexdigest()

def main() -> int:
    mode = sys.argv[1]
    counts_path = Path(sys.argv[2])
    raw_url = os.environ.get("DATABASE_URL", "")
    try:
        url = make_url(raw_url)
    except Exception:
        print("VERIFY_DATABASE_TARGET_INVALID")
        return 10
    if url.drivername != "postgresql+psycopg" or url.host != "127.0.0.1":
        print("VERIFY_DATABASE_TARGET_INVALID")
        return 10
    engine = create_engine(
        url,
        connect_args={
            "connect_timeout": 10,
            "options": "-c default_transaction_read_only=on -c statement_timeout=1800000",
        },
        pool_pre_ping=False,
    )
    try:
        with engine.connect() as connection:
            identity = connection.execute(text(
                "SELECT current_database(), current_setting('server_version_num'), "
                "COALESCE(current_schema(), '')"
            )).one()
            database, version_number, schema = identity
            revision, revision_count = read_revision(connection)
            major = int(version_number) // 10000
            expected_major = int(os.environ["OA_EXPECTED_PG_MAJOR"])
            if database != os.environ["OA_EXPECTED_TEMP_DB"] or schema != "public" or major != expected_major:
                print("VERIFY_DATABASE_IDENTITY_MISMATCH")
                return 11
            if mode == "before":
                if revision_count != 1 or revision != START_REVISION:
                    print("VERIFY_BASE_REVISION_MISMATCH")
                    return 12
                inspector = inspect(connection)
                tables = inspector.get_table_names(schema="public")
                if "users" not in tables:
                    print("VERIFY_BASE_AUTH_TABLES_MISSING")
                    return 13
                snapshots = {}
                for table in sorted(tables):
                    if table == "alembic_version":
                        continue
                    columns = [column["name"] for column in inspector.get_columns(table, schema="public")]
                    primary_key = inspector.get_pk_constraint(table, schema="public").get("constrained_columns") or []
                    count, digest = fingerprint_table(connection, table, columns, primary_key)
                    snapshots[table] = {
                        "columns": columns,
                        "primary_key": primary_key,
                        "row_count": count,
                        "sha256": digest,
                    }
                counts_path.write_text(json.dumps(snapshots, sort_keys=True), encoding="utf-8")
                print("BASELINE_OK")
                return 0

            if mode != "after" or revision_count != 1 or revision != TARGET_REVISION:
                print("VERIFY_TARGET_REVISION_MISMATCH")
                return 14
            from src.backend.db.base import Base
            from src.backend.db import models  # noqa: F401

            inspector = inspect(connection)
            actual_tables = set(inspector.get_table_names(schema="public"))
            missing_table_count = 0
            missing_column_count = 0
            for table in Base.metadata.sorted_tables:
                schema_name = table.schema or "public"
                if schema_name != "public" or table.name not in actual_tables:
                    missing_table_count += 1
                    continue
                actual_columns = {column["name"] for column in inspector.get_columns(table.name, schema="public")}
                missing_column_count += len({column.name for column in table.columns} - actual_columns)
            if missing_table_count or missing_column_count:
                print("VERIFY_ORM_SCHEMA_MISMATCH")
                return 15

            previous_snapshots = json.loads(counts_path.read_text(encoding="utf-8"))
            for table, previous in previous_snapshots.items():
                if table not in actual_tables:
                    print("VERIFY_PREEXISTING_TABLE_MISSING")
                    return 16
                actual_columns = {column["name"] for column in inspector.get_columns(table, schema="public")}
                if not set(previous["columns"]).issubset(actual_columns):
                    print("VERIFY_PREEXISTING_COLUMN_MISSING")
                    return 17
                current_count, current_digest = fingerprint_table(
                    connection, table, previous["columns"], previous["primary_key"]
                )
                if current_count != int(previous["row_count"]) or current_digest != previous["sha256"]:
                    print("VERIFY_PREEXISTING_TABLE_DATA_CHANGED")
                    return 17

            user_count = int(connection.execute(text('SELECT count(*) FROM "public"."users"')).scalar_one())
            profile_count = int(connection.execute(text('SELECT count(*) FROM "public"."employee_profiles"')).scalar_one())
            missing_profile_count = int(connection.execute(text("""
                SELECT count(*) FROM public.users AS u
                WHERE NOT EXISTS (SELECT 1 FROM public.employee_profiles AS p WHERE p.user_id = u.id)
            """)).scalar_one())
            orphan_profile_count = int(connection.execute(text("""
                SELECT count(*) FROM public.employee_profiles AS p
                WHERE p.user_id IS NULL
                   OR NOT EXISTS (SELECT 1 FROM public.users AS u WHERE u.id = p.user_id)
            """)).scalar_one())
            duplicate_profile_user_count = int(connection.execute(text("""
                SELECT count(*) FROM (
                    SELECT user_id FROM public.employee_profiles
                    WHERE user_id IS NOT NULL GROUP BY user_id HAVING count(*) <> 1
                ) AS duplicate_profiles
            """)).scalar_one())
            profile_mismatch_count = int(connection.execute(text("""
                SELECT count(*)
                FROM public.users AS u
                JOIN public.employee_profiles AS p ON p.user_id = u.id
                WHERE p.user_code IS DISTINCT FROM u.user_code
                   OR p.display_name IS DISTINCT FROM u.display_name
                   OR p.email IS DISTINCT FROM u.email
                   OR p.phone IS DISTINCT FROM u.phone
                   OR p.department IS DISTINCT FROM u.department
                   OR p.job_title IS DISTINCT FROM u.job_title
                   OR p.employment_start_date IS DISTINCT FROM u.employment_start_date
                   OR p.employment_status IS DISTINCT FROM u.employment_status
            """)).scalar_one())
            if (profile_count != user_count or missing_profile_count != 0 or orphan_profile_count != 0
                    or duplicate_profile_user_count != 0 or profile_mismatch_count != 0):
                print("VERIFY_COPIED_PROFILE_OR_REVISION_COUNT_MISMATCH")
                return 18

            new_history_tables = (
                "auth_management_tokens", "admin_audit_events",
                "auth_workflow_notifications", "auth_workflow_sla_configurations",
                "auth_workflow_sla_rounds",
            )
            for table in new_history_tables:
                if int(connection.execute(text(f'SELECT count(*) FROM public."{table}"')).scalar_one()) != 0:
                    print("VERIFY_UNEXPECTED_NEW_HISTORY_ROWS")
                    return 19
            trigger_state = connection.execute(text("""
                SELECT
                    to_regprocedure('public.reject_auth_workflow_sla_configuration_mutation()') IS NOT NULL,
                    to_regprocedure('public.guard_auth_workflow_sla_round_snapshot()') IS NOT NULL,
                    EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = to_regclass('public.auth_workflow_sla_configurations')
                           AND tgname = 'trg_auth_workflow_sla_configurations_immutable' AND NOT tgisinternal),
                    EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = to_regclass('public.auth_workflow_sla_rounds')
                           AND tgname = 'trg_auth_workflow_sla_rounds_immutable' AND NOT tgisinternal)
            """)).one()
            if not all(trigger_state):
                print("VERIFY_SLA_TRIGGER_SCHEMA_MISMATCH")
                return 20
            print("MIGRATION_VERIFICATION_OK")
            print("ORM_TABLE_COLUMN_MATCH=true")
            print("PREEXISTING_TABLE_DATA_SHA256_MATCH=true")
            print("EMPLOYEE_PROFILES_MATCH_USERS=true")
            print("EMPLOYEE_PROFILE_FIELDS_MATCH_USERS=true")
            print("MIGRATION_CREATED_NO_TOKEN_AUDIT_NOTIFICATION_OR_SLA_HISTORY=true")
            print("SLA_TRIGGER_SCHEMA_MATCH=true")
            return 0
    finally:
        engine.dispose()

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("VERIFY_FAILED_WITH_REDACTED_DIAGNOSTIC")
        raise SystemExit(20)
'@
    [IO.File]::WriteAllText($helperPath, $helperSource, [Text.UTF8Encoding]::new($false))

    $image = 'postgres:' + [string]$serverMajor
    $imageCheck = Invoke-DockerClient @('image', 'inspect', $image)
    if ($imageCheck -ne 0) {
        Write-Host ('Fetching PostgreSQL major-version image {0}.' -f $serverMajor)
        if ((Invoke-DockerClient @('pull', $image)) -ne 0) {
            Stop-Safely 'POSTGRES_IMAGE_UNAVAILABLE'
        }
    }
    $clientVersionName = Register-ClientContainer 'version'
    $clientVersionOutput = @(& $script:DockerPath 'run' '--rm' '--name' $clientVersionName '--label' ('organizationai.auth-rehearsal.run=' + $runId) '--entrypoint' 'sh' $image '-c' 'command -v pg_dump && pg_dump --version' 2>$null)
    $clientVersionExitCode = [int]$LASTEXITCODE
    $clientVersionLines = @($clientVersionOutput | ForEach-Object { ([string]$_).Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($clientVersionExitCode -ne 0 -or $clientVersionLines.Count -ne 2 -or $clientVersionLines[1] -notmatch ('PostgreSQL\) ' + [regex]::Escape([string]$serverMajor) + '\.')) {
        Stop-Safely 'MATCHING_POSTGRES_CLIENT_UNAVAILABLE'
    }
    $script:PgDumpExecutable = $clientVersionLines[0]
    $script:PgDumpVersion = $clientVersionLines[1]
    Write-Host ('PG_DUMP_EXECUTABLE_IN_IMAGE={0}' -f $script:PgDumpExecutable)
    Write-Host ('PG_DUMP_VERSION={0}' -f $script:PgDumpVersion)
    $restoreVersionName = Register-ClientContainer 'restore-version'
    $restoreVersionOutput = @(& $script:DockerPath 'run' '--rm' '--name' $restoreVersionName '--label' ('organizationai.auth-rehearsal.run=' + $runId) '--entrypoint' 'sh' $image '-c' 'command -v pg_restore && pg_restore --version' 2>$null)
    $restoreVersionExitCode = [int]$LASTEXITCODE
    $restoreVersionLines = @($restoreVersionOutput | ForEach-Object { ([string]$_).Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($restoreVersionExitCode -ne 0 -or $restoreVersionLines.Count -ne 2 -or $restoreVersionLines[1] -notmatch ('PostgreSQL\) ' + [regex]::Escape([string]$serverMajor) + '\.')) {
        Stop-Safely 'MATCHING_POSTGRES_RESTORE_UNAVAILABLE'
    }
    Write-Host ('PG_RESTORE_EXECUTABLE_IN_IMAGE={0}' -f $restoreVersionLines[0])
    Write-Host ('PG_RESTORE_VERSION={0}' -f $restoreVersionLines[1])
    if ((Invoke-DockerClient @('container', 'inspect', $containerName)) -eq 0) {
        Stop-Safely 'TEMP_CONTAINER_NAME_COLLISION'
    }

    $mountSpec = 'type=bind,source=' + $backupDirectory + ',target=/backup'
    $hostWriteProbe = Join-Path $backupDirectory ('.host-write-probe-' + $runId)
    try {
        [IO.File]::WriteAllText($hostWriteProbe, 'probe', [Text.UTF8Encoding]::new($false))
    }
    catch {
        Stop-Safely 'BACKUP_PATH_WRITE_PROBE_FAILED'
    }
    if (-not (Test-Path -LiteralPath $hostWriteProbe) -or (Get-Item -LiteralPath $hostWriteProbe).Length -le 0) {
        Stop-Safely 'BACKUP_PATH_WRITE_PROBE_FAILED'
    }
    Remove-Item -LiteralPath $hostWriteProbe -Force
    if (Test-Path -LiteralPath $hostWriteProbe) {
        Stop-Safely 'BACKUP_PATH_WRITE_PROBE_CLEANUP_FAILED'
    }
    Write-Host 'BACKUP_HOST_DIRECTORY_WRITE=verified'

    $mountProbeName = Register-ClientContainer 'backup-mount-probe'
    $mountProbePath = '/backup/.docker-write-probe-' + $runId.Replace('-', '')
    $mountProbeCommand = 'set -eu; : > ' + $mountProbePath + '; test -f ' + $mountProbePath + '; rm -f ' + $mountProbePath
    $mountProbeArguments = @(
        'run', '--rm', '--name', $mountProbeName,
        '--label', ('organizationai.auth-rehearsal.run=' + $runId),
        '--mount', $mountSpec, '--entrypoint', 'sh', $image, '-c', $mountProbeCommand
    )
    $mountProbeResult = Invoke-DockerClientWithDiagnostic $mountProbeArguments
    if ($mountProbeResult.InvocationStatus -cne 'NATIVE_PROCESS_EXITED' -or $mountProbeResult.ExitCode -ne 0) {
        $hostProbePath = Join-Path $backupDirectory $mountProbePath.Split('/')[-1]
        if (Test-Path -LiteralPath $hostProbePath) {
            Remove-Item -LiteralPath $hostProbePath -Force -ErrorAction SilentlyContinue
        }
        Clear-SourcePostgresEnvironment
        $sourcePassword = $null
        if ($mountProbeResult.InvocationStatus -ceq 'NATIVE_PROCESS_EXITED') {
            $safeMountDiagnostic = Get-SafePgDumpDiagnosticCode $mountProbeResult.DiagnosticText $mountProbeResult.ExitCode $false
            Write-Host ('BACKUP_MOUNT_PROBE_DOCKER_RUN_EXIT_CODE={0}' -f $mountProbeResult.ExitCode)
        }
        else {
            $safeMountDiagnostic = [string]$mountProbeResult.PowerShellFailure
            Write-Host ('BACKUP_MOUNT_PROBE_PROCESS_STATUS={0}' -f $mountProbeResult.InvocationStatus)
        }
        $mountProbeResult.DiagnosticText = $null
        Write-Host ('BACKUP_MOUNT_PROBE_DIAGNOSTIC={0}' -f $safeMountDiagnostic)
        Stop-Safely 'BACKUP_MOUNT_ACCESS_FAILED'
    }
    Write-Host 'BACKUP_DOCKER_MOUNT_WRITE=verified'

    $dumpClientName = Register-ClientContainer 'dump'
    Write-Host 'Creating a logical backup of the verified source database. URL and password remain hidden.'
    $dumpExecution = Invoke-PgDumpBackup $dumpClientName $runId $image $mountSpec $backupDirectory $archiveFileName
    $dumpResult = $dumpExecution.ProcessResult
    $archiveReady = [bool]$dumpExecution.ArchiveReady
    Clear-SourcePostgresEnvironment
    $sourcePassword = $null
    $dumpFailed = $true
    if ($dumpResult.InvocationStatus -ceq 'NATIVE_PROCESS_EXITED') {
        $safeDumpDiagnostic = Get-SafePgDumpDiagnosticCode $dumpResult.DiagnosticText $dumpResult.ExitCode $archiveReady
        Write-Host ('PG_DUMP_DOCKER_RUN_EXIT_CODE={0}' -f $dumpResult.ExitCode)
        $dumpFailed = $dumpResult.ExitCode -ne 0 -or -not $archiveReady
    }
    else {
        $safeDumpDiagnostic = [string]$dumpResult.PowerShellFailure
        Write-Host ('PG_DUMP_PROCESS_STATUS={0}' -f $dumpResult.InvocationStatus)
        Write-Host ('PG_DUMP_DOCKER_RUN_EXIT_CODE=not-returned')
    }
    $dumpResult.DiagnosticText = $null
    Write-Host ('PG_DUMP_DIAGNOSTIC={0}' -f $safeDumpDiagnostic)
    if ($dumpFailed) {
        if (Test-Path -LiteralPath $archivePath) {
            Remove-Item -LiteralPath $archivePath -Force
        }
        if (Test-Path -LiteralPath $archivePath) {
            Write-Host 'BACKUP_PARTIAL_FILE_CLEANUP=failed'
            Stop-Safely 'PARTIAL_BACKUP_CLEANUP_FAILED'
        }
        Write-Host 'BACKUP_PARTIAL_FILE_CLEANUP=complete'
        Stop-Safely 'SOURCE_BACKUP_FAILED'
    }
    Write-Host 'PG_DUMP_ARCHIVE=nonempty'
    $archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    Set-Content -LiteralPath $hashPath -Value ($archiveHash + '  ' + $archiveFileName) -Encoding Ascii

    $archiveCheckClientName = Register-ClientContainer 'archive-check'
    if ((Invoke-DockerClient @(
        'run', '--rm', '--name', $archiveCheckClientName,
        '--label', ('organizationai.auth-rehearsal.run=' + $runId),
        '--mount', $mountSpec, $image, 'pg_restore', '--list', ('/backup/' + $archiveFileName)
    )) -ne 0) {
        Stop-Safely 'BACKUP_ARCHIVE_READ_FAILED'
    }
    $script:BackupComplete = $true
    Write-Host ('Backup archive readable; SHA-256={0}.' -f $archiveHash)

    $tempPassword = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
    Set-ProcessEnvironment 'POSTGRES_USER' $tempUser
    Set-ProcessEnvironment 'POSTGRES_DB' $tempDatabase
    Set-ProcessEnvironment 'POSTGRES_PASSWORD' $tempPassword

    $script:ContainerCreationAttempted = $true
    $containerArguments = @(
        'run', '--detach', '--name', $containerName,
        '--label', ('organizationai.auth-rehearsal.run=' + $runId),
        '--publish', '127.0.0.1::5432',
        '--env', 'POSTGRES_USER', '--env', 'POSTGRES_DB', '--env', 'POSTGRES_PASSWORD',
        $image
    )
    $containerOutput = & $script:DockerPath @containerArguments 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$containerOutput)) {
        Stop-Safely 'TEMP_POSTGRES_START_FAILED'
    }
    $script:ContainerCreated = $true

    $ready = $false
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        $null = & $script:DockerPath 'exec' $containerName 'pg_isready' '--host=127.0.0.1' '--port=5432' '--username' $tempUser '--dbname' $tempDatabase 2>$null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        Stop-Safely 'TEMP_POSTGRES_START_TIMEOUT'
    }

    $portOutput = & $script:DockerPath 'port' $containerName '5432/tcp' 2>$null
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely 'TEMP_POSTGRES_PORT_LOOKUP_FAILED'
    }
    $portLine = [string](@($portOutput | Select-Object -First 1))
    if ($portLine -notmatch '^127\.0\.0\.1:(\d+)$') {
        Stop-Safely 'TEMP_POSTGRES_PORT_INVALID'
    }
    $hostPort = [int]$Matches[1]
    Write-Host ('Temporary PostgreSQL is listening on Docker-assigned localhost port {0}; Docker bound the port atomically.' -f $hostPort)

    $containerArchivePath = $containerName + ':' + $containerArchive
    $null = & $script:DockerPath 'cp' $archivePath $containerArchivePath 2>$null
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely 'BACKUP_COPY_TO_TEMP_FAILED'
    }

    Set-ProcessEnvironment 'PGPASSWORD' $tempPassword
    $restoreArguments = @(
        'exec', '--env', 'PGPASSWORD', $containerName,
        'pg_restore', '--host=127.0.0.1', '--port=5432', '--username', $tempUser,
        '--dbname', $tempDatabase, '--no-password', '--no-owner', '--no-acl',
        '--single-transaction', '--exit-on-error', $containerArchive
    )
    Write-Host 'Restoring the archive into the isolated temporary database.'
    if ((Invoke-DockerClient $restoreArguments) -ne 0) {
        Stop-Safely 'TEMP_RESTORE_FAILED'
    }

    $escapedUser = [Uri]::EscapeDataString($tempUser)
    $tempDatabaseUrl = 'postgresql+psycopg://' + $escapedUser + ':' + $tempPassword +
        '@127.0.0.1:' + [string]$hostPort + '/' + $tempDatabase +
        '?sslmode=disable&connect_timeout=10'
    Set-ProcessEnvironment 'DATABASE_URL' $tempDatabaseUrl
    Set-PostgresEnvironment '127.0.0.1' $hostPort $tempUser $tempDatabase $tempPassword 'disable' '-c statement_timeout=1800000'
    Set-ProcessEnvironment 'OA_EXPECTED_PG_MAJOR' ([string]$serverMajor)
    Set-ProcessEnvironment 'OA_EXPECTED_TEMP_DB' $tempDatabase
    Set-ProcessEnvironment 'AUTH_ALLOW_SQLITE_MIGRATION_TESTS' $null

    $baselineExit = Run-VerificationHelper @($helperPath, 'before', $baselinePath)
    if ($baselineExit -ne 0) {
        Stop-Safely 'TEMP_BASELINE_VERIFICATION_FAILED'
    }
    Write-Host ('Restored copy is at revision {0}; existing table data fingerprints are recorded privately for comparison.' -f $ExpectedStartRevision)

    $locationPushed = $false
    try {
        Push-Location -LiteralPath $sourceRoot
        $locationPushed = $true
        $null = & $script:PythonPath '-m' 'alembic' '-c' 'alembic.ini' 'upgrade' $TargetRevision 2>$null
        $migrationExit = $LASTEXITCODE
    }
    finally {
        if ($locationPushed) {
            Pop-Location
        }
    }
    if ($migrationExit -ne 0) {
        Stop-Safely 'PINNED_ALEMBIC_UPGRADE_FAILED'
    }
    Write-Host ('Pinned Alembic source advanced only the temporary copy to {0}.' -f $TargetRevision)

    $schemaCheckExit = 9009
    $locationPushed = $false
    try {
        Push-Location -LiteralPath $sourceRoot
        $locationPushed = $true
        $null = & $script:PythonPath '-m' 'alembic' '-c' 'alembic.ini' 'check' 2>$null
        $schemaCheckExit = $LASTEXITCODE
    }
    finally {
        if ($locationPushed) {
            Pop-Location
        }
    }
    if ($schemaCheckExit -ne 0) {
        Stop-Safely 'PINNED_ALEMBIC_SCHEMA_CHECK_FAILED'
    }
    Write-Host 'ALEMBIC_SCHEMA_CHECK=true'

    $verificationExit = Run-VerificationHelper @($helperPath, 'after', $baselinePath)
    if ($verificationExit -ne 0) {
        Stop-Safely 'TEMP_POST_MIGRATION_VERIFICATION_FAILED'
    }
    $finalArchiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    if ($finalArchiveHash -cne $archiveHash) {
        Stop-Safely 'RETAINED_BACKUP_HASH_CHANGED'
    }
    Write-Host ('POST_REVISION={0}' -f $TargetRevision)
    Write-Host 'ORM_TABLE_COLUMN_MATCH=true'
    Write-Host 'PREEXISTING_TABLE_DATA_SHA256_MATCH=true'
    Write-Host 'EMPLOYEE_PROFILES_MATCH_USERS=true'
    Write-Host 'EMPLOYEE_PROFILE_FIELDS_MATCH_USERS=true'
    Write-Host 'MIGRATION_CREATED_NO_TOKEN_AUDIT_NOTIFICATION_OR_SLA_HISTORY=true'
    Write-Host 'SLA_TRIGGER_SCHEMA_MATCH=true'
    Write-Host ('BACKUP_DIRECTORY={0}' -f $backupDirectory)
    Write-Host ('BACKUP_SHA256={0}' -f $archiveHash)
}
catch {
    if ([string]::IsNullOrWhiteSpace($script:FailureCode)) {
        $script:FailureCode = 'UNEXPECTED_REDACTED_FAILURE'
    }
}
finally {
    try {
        if ($script:ContainerCreationAttempted -and -not [string]::IsNullOrWhiteSpace($containerName)) {
            try {
                $runLabel = & $script:DockerPath 'container' 'inspect' '--format' '{{ index .Config.Labels "organizationai.auth-rehearsal.run" }}' $containerName 2>$null
                if ($LASTEXITCODE -eq 0 -and ([string]$runLabel).Trim() -ceq $runId) {
                    $removed = Invoke-DockerClient @('rm', '--force', $containerName)
                    if ($removed -ne 0) {
                        $script:CleanupPending = $true
                        $script:CleanupPendingResource = $containerName
                    }
                    else {
                        $script:ContainerCreated = $false
                    }
                }
                elseif ($script:ContainerCreated) {
                    $script:CleanupPending = $true
                    $script:CleanupPendingResource = $containerName
                }
            }
            catch {
                $script:CleanupPending = $true
                $script:CleanupPendingResource = $containerName
            }
        }

        if ($script:ClientContainerNames.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace($script:DockerPath)) {
            try {
                $labeledContainers = & $script:DockerPath 'container' 'ls' '--all' '--filter' ('label=organizationai.auth-rehearsal.run=' + $runId) '--format' '{{.Names}}' 2>$null
                if ($LASTEXITCODE -ne 0) {
                    $script:CleanupPending = $true
                    $script:CleanupPendingResource = 'run-labeled-client-containers'
                }
                else {
                    $presentNames = @($labeledContainers | ForEach-Object { ([string]$_).Trim() })
                    foreach ($clientName in $script:ClientContainerNames) {
                        if ($presentNames -ccontains $clientName) {
                            $removed = Invoke-DockerClient @('rm', '--force', $clientName)
                            if ($removed -ne 0) {
                                $script:CleanupPending = $true
                                $script:CleanupPendingResource = $clientName
                            }
                        }
                    }
                }
            }
            catch {
                $script:CleanupPending = $true
                $script:CleanupPendingResource = 'run-labeled-client-containers'
            }
        }

        if (-not $script:BackupComplete -and $script:BackupDirectoryCreated -and
            -not [string]::IsNullOrWhiteSpace($backupDirectory) -and (Test-Path -LiteralPath $backupDirectory)) {
            Remove-Item -LiteralPath $backupDirectory -Recurse -Force -ErrorAction SilentlyContinue
            if (Test-Path -LiteralPath $backupDirectory) {
                $script:CleanupPending = $true
                $script:CleanupPendingResource = $backupDirectory
            }
        }
        if ($script:WorkingDirectoryCreated -and -not [string]::IsNullOrWhiteSpace($workingDirectory) -and
            (Test-Path -LiteralPath $workingDirectory)) {
            Remove-Item -LiteralPath $workingDirectory -Recurse -Force -ErrorAction SilentlyContinue
            if (Test-Path -LiteralPath $workingDirectory) {
                $script:CleanupPending = $true
                $script:CleanupPendingResource = $workingDirectory
            }
        }
    }
    catch {
        $script:CleanupPending = $true
        if ([string]::IsNullOrWhiteSpace($script:CleanupPendingResource)) {
            $script:CleanupPendingResource = 'run-owned-temporary-resources'
        }
    }
    finally {
        try {
            if ($null -ne $secureUrl) { $secureUrl.Dispose() }
            if ($bstr -ne [IntPtr]::Zero) {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
                $bstr = [IntPtr]::Zero
            }
            $sourceUrlText = $null
            $sourcePassword = $null
            $tempPassword = $null
            $tempDatabaseUrl = $null
            $sourceUri = $null
        }
        catch {
            if ([string]::IsNullOrWhiteSpace($script:FailureCode)) {
                $script:FailureCode = 'LOCAL_SECRET_CLEAR_FAILED'
            }
        }
        foreach ($name in $environmentNames) {
            try {
                [Environment]::SetEnvironmentVariable($name, $environmentSnapshot[$name], 'Process')
            }
            catch {
                if ([string]::IsNullOrWhiteSpace($script:FailureCode)) {
                    $script:FailureCode = 'ENVIRONMENT_RESTORE_FAILED'
                }
            }
        }
    }
}

if ($script:CleanupPending) {
    if ([string]::IsNullOrWhiteSpace($script:FailureCode)) {
        $script:FailureCode = 'TEMPORARY_RESOURCE_CLEANUP_FAILED'
    }
    Write-Host ('CLEANUP_PENDING_RESOURCE={0}' -f $script:CleanupPendingResource)
}
elseif (-not [string]::IsNullOrWhiteSpace($script:FailureCode)) {
    Write-Host 'TEMPORARY_RESOURCE_CLEANUP=complete'
}
if (-not [string]::IsNullOrWhiteSpace($script:FailureCode)) {
    Write-Host ('RESULT=FAILED; CODE={0}' -f $script:FailureCode)
    if ($script:BackupComplete) {
        Write-Host ('BACKUP_RETAINED={0}' -f $backupDirectory)
        Write-Host ('BACKUP_SHA256={0}' -f $archiveHash)
    }
    exit 1
}
Write-Host 'TEMP_CONTAINER_CLEANUP=complete'
Write-Host 'RESULT=PASS'
exit 0
