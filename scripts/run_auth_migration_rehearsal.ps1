[CmdletBinding()]
param(
    [string]$ReuseBackupDirectory,
    [string]$ExpectedBackupSha256,
    [int]$ReusePostgresMajor = 0,
    [string]$PythonExe
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$PinnedSha = '0d17887cf1d6a6571fc8b02b74706343e2555e19'
$ExpectedDatabase = 'organizationai_db'
$ExpectedStartRevision = '20261003_07'
$TargetRevision = '20261011_12'
$script:FailureCode = $null
$script:CurrentPhase = 'INITIALIZATION'
$script:FailurePhase = $null
$script:FailureExceptionType = $null
$script:FailureCodeLocation = $null
$script:FailureSqlState = $null
$script:SchemaDiffKinds = @()
$script:PinnedMigrationIndexGapCandidate = $false
$script:IndexGapVerificationPassed = $false
$script:ContainerCleanupDiagnostic = 'NOT_STARTED'
$script:UseExistingBackup = -not [string]::IsNullOrWhiteSpace($ReuseBackupDirectory)
$script:DiagnosticDirectory = $null
$script:DiagnosticPath = $null
$script:BackupComplete = $false
$script:WritersPaused = $false
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

function Set-RunnerPhase {
    param([string]$Name)
    $script:CurrentPhase = $Name
}

function Stop-Safely {
    param([string]$Code)
    $script:FailureCode = $Code
    if ([string]::IsNullOrWhiteSpace($script:FailurePhase)) {
        $script:FailurePhase = $script:CurrentPhase
    }
    if ([string]::IsNullOrWhiteSpace($script:FailureExceptionType)) {
        $script:FailureExceptionType = 'ControlledRunnerStop'
    }
    if ([string]::IsNullOrWhiteSpace($script:FailureCodeLocation)) {
        $frames = @(Get-PSCallStack)
        $caller = if ($frames.Count -gt 1) { $frames[1] } else { $frames[0] }
        $fileName = [IO.Path]::GetFileName([string]$caller.ScriptName)
        if ($fileName -notmatch '^[A-Za-z0-9_.-]+$') { $fileName = 'run_auth_migration_rehearsal.ps1' }
        $script:FailureCodeLocation = '{0}:{1}' -f $fileName, [int]$caller.ScriptLineNumber
    }
    throw [System.InvalidOperationException]::new('Safe runner stop')
}

function New-VerifiedRetainedBackup {
    param(
        [string]$ExpectedRoot,
        [string]$Directory,
        [string]$ExpectedDatabase,
        [string]$ExpectedSha256
    )

    if ($ExpectedSha256 -notmatch '^[A-Fa-f0-9]{64}$') {
        return [pscustomobject]@{ Valid = $false; Code = 'EXPECTED_BACKUP_HASH_INVALID' }
    }
    if (-not (Test-Path -LiteralPath $ExpectedRoot -PathType Container) -or
        -not (Test-Path -LiteralPath $Directory -PathType Container)) {
        return [pscustomobject]@{ Valid = $false; Code = 'BACKUP_DIRECTORY_NOT_FOUND' }
    }

    try {
        $rootFull = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $ExpectedRoot).Path).TrimEnd('\') + '\'
        $directoryFull = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Directory).Path)
        if (-not $directoryFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
            return [pscustomobject]@{ Valid = $false; Code = 'BACKUP_DIRECTORY_OUTSIDE_PRIVATE_ROOT' }
        }
        $archives = @(Get-ChildItem -LiteralPath $directoryFull -File -Filter ($ExpectedDatabase + '-*.dump'))
        if ($archives.Count -ne 1 -or ($archives[0].Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            return [pscustomobject]@{ Valid = $false; Code = 'BACKUP_ARCHIVE_COUNT_INVALID' }
        }
        $archive = $archives[0]
        $sidecarPath = $archive.FullName + '.sha256'
        if (-not (Test-Path -LiteralPath $sidecarPath -PathType Leaf)) {
            return [pscustomobject]@{ Valid = $false; Code = 'BACKUP_HASH_SIDECAR_MISSING' }
        }
        $sidecar = [IO.File]::ReadAllText($sidecarPath)
        $sidecarMatch = [regex]::Match($sidecar, '^([A-Fa-f0-9]{64})\s{2}([^\r\n]+)\s*$')
        if (-not $sidecarMatch.Success -or
            $sidecarMatch.Groups[1].Value -cne $ExpectedSha256 -or
            $sidecarMatch.Groups[2].Value -cne $archive.Name) {
            return [pscustomobject]@{ Valid = $false; Code = 'BACKUP_HASH_SIDECAR_MISMATCH' }
        }
        $actualHash = (Get-FileHash -LiteralPath $archive.FullName -Algorithm SHA256).Hash
        if ($actualHash -cne $ExpectedSha256) {
            return [pscustomobject]@{ Valid = $false; Code = 'BACKUP_HASH_MISMATCH' }
        }
        return [pscustomobject]@{
            Valid = $true
            Code = 'BACKUP_SHA256_VERIFIED'
            Directory = $directoryFull
            ArchivePath = $archive.FullName
            ArchiveFileName = $archive.Name
            Hash = $actualHash
        }
    }
    catch {
        return [pscustomobject]@{ Valid = $false; Code = 'BACKUP_HASH_READ_FAILED' }
    }
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

function Get-ExactContainerPresence {
    param([string]$Name)
    try {
        $listResult = Invoke-NativeWithDiagnostic $script:DockerPath @('container', 'ls', '--all', '--format', '{{.Names}}')
        if ($listResult.InvocationStatus -cne 'NATIVE_PROCESS_EXITED' -or [int]$listResult.ExitCode -ne 0) {
            $listResult.DiagnosticText = $null
            return 'UNKNOWN'
        }
        $normalizedNames = @(([string]$listResult.DiagnosticText -split "`r?`n") | ForEach-Object { $_.Trim() })
        $listResult.DiagnosticText = $null
        if ($normalizedNames -ccontains $Name) { return 'PRESENT' }
        return 'ABSENT'
    }
    catch {
        return 'UNKNOWN'
    }
}

function Remove-RunOwnedContainer {
    param([string]$Name, [string]$RunId)
    for ($attempt = 0; $attempt -lt 2; $attempt++) {
        $presence = Get-ExactContainerPresence $Name
        if ($presence -ceq 'ABSENT') {
            $script:ContainerCleanupDiagnostic = 'EXACT_NAME_ALREADY_ABSENT'
            return $true
        }
        if ($presence -cne 'PRESENT') {
            $script:ContainerCleanupDiagnostic = 'PRESENCE_QUERY_FAILED'
            return $false
        }

        try {
            $inspectResult = Invoke-NativeWithDiagnostic $script:DockerPath @(
                'container', 'inspect', '--format', '{{json .Config.Labels}}', $Name
            )
            if ($inspectResult.InvocationStatus -cne 'NATIVE_PROCESS_EXITED') {
                $script:ContainerCleanupDiagnostic = 'LABEL_INSPECT_PROCESS_START_FAILED'
                $inspectResult.DiagnosticText = $null
                return $false
            }
            if ([int]$inspectResult.ExitCode -ne 0) {
                $script:ContainerCleanupDiagnostic = 'LABEL_INSPECT_CLI_EXIT_NONZERO'
                $inspectResult.DiagnosticText = $null
                return $false
            }
            try {
                $labelLines = @(([string]$inspectResult.DiagnosticText -split "`r?`n") |
                    ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^\{.*\}$' })
                if ($labelLines.Count -ne 1) {
                    $script:ContainerCleanupDiagnostic = 'LABEL_INSPECT_JSON_INVALID'
                    $inspectResult.DiagnosticText = $null
                    return $false
                }
                $labelObject = $labelLines[0] | ConvertFrom-Json
                $labelProperty = $labelObject.PSObject.Properties['organizationai.auth-rehearsal.run']
                $observedLabel = if ($null -eq $labelProperty) { $null } else { [string]$labelProperty.Value }
            }
            catch {
                $script:ContainerCleanupDiagnostic = 'LABEL_INSPECT_JSON_INVALID'
                $inspectResult.DiagnosticText = $null
                return $false
            }
            $inspectResult.DiagnosticText = $null
        }
        catch {
            $script:ContainerCleanupDiagnostic = 'LABEL_INSPECT_EXCEPTION'
            return $false
        }
        if ($observedLabel -cne $RunId) {
            $script:ContainerCleanupDiagnostic = 'RUN_LABEL_MISMATCH'
            return $false
        }

        $removeResult = Invoke-NativeWithDiagnostic $script:DockerPath @('container', 'rm', '--force', $Name)
        $removeExitCode = if ($removeResult.InvocationStatus -ceq 'NATIVE_PROCESS_EXITED') {
            [int]$removeResult.ExitCode
        }
        else {
            9009
        }
        $removeResult.DiagnosticText = $null
        if ($removeResult.InvocationStatus -cne 'NATIVE_PROCESS_EXITED') {
            $script:ContainerCleanupDiagnostic = 'REMOVE_PROCESS_START_FAILED'
        }
        elseif ($removeExitCode -ne 0) {
            $script:ContainerCleanupDiagnostic = 'REMOVE_EXIT_NONZERO'
        }
        else {
            $script:ContainerCleanupDiagnostic = 'REMOVE_EXIT_ZERO'
        }
        $presence = Get-ExactContainerPresence $Name
        if ($presence -ceq 'ABSENT') {
            $script:ContainerCleanupDiagnostic = 'REMOVAL_CONFIRMED_BY_EXACT_NAME'
            return $true
        }
        if ($presence -cne 'PRESENT') {
            $script:ContainerCleanupDiagnostic = 'POST_REMOVE_PRESENCE_QUERY_FAILED'
            return $false
        }
    }
    $script:ContainerCleanupDiagnostic = 'RESOURCE_PRESENT_AFTER_RETRY'
    return $false
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

function Invoke-NativeWithDiagnostic {
    param([string]$FilePath, [string[]]$Arguments)
    $previousErrorActionPreference = $ErrorActionPreference
    $hasNativePreferenceVariable = Test-Path variable:PSNativeCommandUseErrorActionPreference
    if ($hasNativePreferenceVariable) { $previousNativePreference = $PSNativeCommandUseErrorActionPreference }
    try {
        $ErrorActionPreference = 'Continue'
        if ($hasNativePreferenceVariable) {
            Set-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Local -Value $false
        }
        $capturedOutput = @(& $FilePath @Arguments 2>&1)
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
        return [pscustomobject]@{
            InvocationStatus = 'POWERSHELL_EXCEPTION'
            ExitCode = $null
            PowerShellFailure = $_.Exception.GetType().Name
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

function Get-SafeAlembicDiagnostic {
    param([string]$DiagnosticText, [int]$ExitCode)
    $classifierPath = Join-Path $repoRoot 'scripts\classify_alembic_diagnostic.py'
    if (-not (Test-Path -LiteralPath $classifierPath)) { return 'DIAGNOSTIC_CLASSIFIER_UNAVAILABLE' }
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $classifierOutput = @($DiagnosticText | & $script:PythonPath $classifierPath '--exit-code' ([string]$ExitCode) '--pinned-sha' $PinnedSha 2>$null)
        $classifierExitCode = [int]$LASTEXITCODE
        $safeCode = $null
        foreach ($line in $classifierOutput) {
            $safeLine = ([string]$line).Trim()
            if ($safeLine -match '^CODE=(NONE|PROCESS_OUTPUT_NONFATAL|DATABASE_PRIVILEGE_FAILED|DATABASE_AUTHENTICATION_FAILED|DATABASE_CONNECTION_FAILED|DEPENDENCY_IMPORT_FAILED|ALEMBIC_REVISION_NOT_FOUND|ALEMBIC_SCHEMA_DRIFT|PINNED_MIGRATION_INDEX_METADATA_GAP|DATABASE_MIGRATION_FAILED|ALEMBIC_ERROR_REDACTED)$') {
                $safeCode = $Matches[1]
            }
            elseif ($safeLine -match '^EXCEPTION_TYPE=(CommandError|ModuleNotFoundError|ImportError|OperationalError|ProgrammingError|IntegrityError|UndefinedColumn|UndefinedTable|InsufficientPrivilege|UniqueViolation|ForeignKeyViolation|CheckViolation)$') {
                $script:FailureExceptionType = $Matches[1]
            }
            elseif ($safeLine -match '^SQLSTATE=([0-9A-Z]{5})$') {
                $script:FailureSqlState = $Matches[1]
            }
            elseif ($safeLine -match '^LOCATION=([A-Za-z0-9_.-]+:[0-9]+:[A-Za-z0-9_<>]+)$') {
                $script:FailureCodeLocation = $Matches[1]
            }
            elseif ($safeLine -match '^SCHEMA_DIFF_KIND=(add_column|remove_column|modify_type|modify_default|add_index|remove_index|add_constraint|remove_constraint|add_table|remove_table)$') {
                $script:SchemaDiffKinds += $Matches[1]
            }
        }
        if ($classifierExitCode -eq 0 -and $safeCode) {
            if ($safeCode -ceq 'PINNED_MIGRATION_INDEX_METADATA_GAP') {
                $script:PinnedMigrationIndexGapCandidate = $true
            }
            return $safeCode
        }
    }
    catch {
        return 'DIAGNOSTIC_CLASSIFIER_UNAVAILABLE'
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return 'DIAGNOSTIC_CLASSIFIER_UNAVAILABLE'
}

function Run-VerificationHelper {
    param([string[]]$Arguments)
    try {
        $helperOutput = @(& $script:PythonPath @Arguments 2>$null)
        $helperExitCode = [int]$LASTEXITCODE
        foreach ($line in $helperOutput) {
            $safeLine = ([string]$line).Trim()
            if ($safeLine -ceq 'VERIFY_PINNED_INDEX_DEFINITIONS=true') {
                $script:IndexGapVerificationPassed = $true
            }
            elseif ($safeLine -match '^VERIFY_EXCEPTION_TYPE=([A-Za-z][A-Za-z0-9_]*)$') {
                $script:FailureExceptionType = $Matches[1]
            }
            elseif ($safeLine -match '^VERIFY_EXCEPTION_LOCATION=([A-Za-z0-9_.<>-]+:[0-9]+:[A-Za-z0-9_<>]+)$') {
                $script:FailureCodeLocation = $Matches[1]
            }
        }
        return $helperExitCode
    }
    catch {
        return 9009
    }
}

try {
    Set-RunnerPhase 'PREFLIGHT'
    $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
    $privateRoot = Join-Path $env:LOCALAPPDATA 'OrganizationAI\AuthSchemaRehearsal'
    if ($script:UseExistingBackup) {
        $backupDirectory = $ReuseBackupDirectory
        $workingDirectory = Join-Path $privateRoot ('work-' + $runId)
        $archiveFileName = $null
        $archivePath = $null
        $hashPath = $null
    }
    else {
        $backupDirectory = Join-Path $privateRoot $runId
        $workingDirectory = Join-Path $privateRoot ('work-' + $runId)
        $archiveFileName = $ExpectedDatabase + '-' + $runId + '.dump'
        $archivePath = Join-Path $backupDirectory $archiveFileName
        $hashPath = Join-Path $backupDirectory ($archiveFileName + '.sha256')
    }
    $script:DiagnosticDirectory = Join-Path $privateRoot ('diagnostic-' + $runId)
    $script:DiagnosticPath = Join-Path $script:DiagnosticDirectory 'safe-summary.txt'

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

    $pythonCandidates = if (-not [string]::IsNullOrWhiteSpace($PythonExe)) {
        @($PythonExe)
    }
    else {
        @(
            (Join-Path $repoRoot '.venv-test-20261009\Scripts\python.exe'),
            'C:\Users\Khoa Bi\VS Studio\repos\OrganizationAI\.venv-test-20261009\Scripts\python.exe'
        )
    }
    $script:PythonPath = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($script:PythonPath)) {
        Stop-Safely 'PINNED_PYTHON_NOT_FOUND'
    }
    $script:PythonPath = (Resolve-Path -LiteralPath $script:PythonPath -ErrorAction Stop).Path
    $runtimeProbe = 'import sys,alembic,sqlalchemy,psycopg; print(chr(9).join([sys.executable,str(sys.version_info[0])+chr(46)+str(sys.version_info[1])+chr(46)+str(sys.version_info[2]),alembic.__version__,sqlalchemy.__version__,psycopg.__version__]))'
    $probeLines = @(& $script:PythonPath '-B' '-c' $runtimeProbe 2>$null)
    $probeExit = [int]$LASTEXITCODE
    $probeFields = if ($probeLines.Count -eq 1) { ([string]$probeLines[0]) -split "`t" } else { @() }
    if ($probeExit -ne 0 -or $probeFields.Count -ne 5 -or
        -not [IO.Path]::GetFullPath([string]$probeFields[0]).Equals(
            [IO.Path]::GetFullPath($script:PythonPath), [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Safely 'PINNED_PYTHON_DEPENDENCIES_MISSING'
    }
    $probeVersion = ([string]$probeFields[1]) -split '\.'
    if ($probeVersion.Count -ne 3 -or [int]$probeVersion[0] -ne 3 -or
        [int]$probeVersion[1] -lt 12 -or [int]$probeVersion[1] -ge 14) {
        Stop-Safely 'PINNED_PYTHON_VERSION_UNSUPPORTED'
    }
    Write-Host ('PYTHON_ACTUAL_EXECUTABLE={0}' -f $script:PythonPath)
    Write-Host ('PYTHON_VERSION={0}; ALEMBIC_VERSION={1}; SQLALCHEMY_VERSION={2}; PSYCOPG_VERSION={3}' -f `
        $probeFields[1], $probeFields[2], $probeFields[3], $probeFields[4])

    $dockerVersion = & $script:DockerPath 'info' '--format' '{{.ServerVersion}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$dockerVersion)) {
        Stop-Safely 'DOCKER_ENGINE_UNAVAILABLE'
    }
    $psqlVersion = & $script:PsqlPath '--version' 2>$null
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely 'PSQL_UNAVAILABLE'
    }

if ($script:UseExistingBackup) {
    Set-RunnerPhase 'RETAINED_BACKUP_VALIDATION'
    if ([string]::IsNullOrWhiteSpace($ExpectedBackupSha256) -or $ReusePostgresMajor -lt 12 -or $ReusePostgresMajor -gt 99) {
        Stop-Safely 'RETAINED_BACKUP_ARGUMENTS_INVALID'
    }
    $verifiedBackup = New-VerifiedRetainedBackup $privateRoot $backupDirectory $ExpectedDatabase $ExpectedBackupSha256
    if (-not $verifiedBackup.Valid) {
        Stop-Safely $verifiedBackup.Code
    }
    $backupDirectory = $verifiedBackup.Directory
    $archivePath = $verifiedBackup.ArchivePath
    $archiveFileName = $verifiedBackup.ArchiveFileName
    $archiveHash = $verifiedBackup.Hash
    $hashPath = $archivePath + '.sha256'
    if (Test-Path -LiteralPath $workingDirectory) {
        Stop-Safely 'RUN_DIRECTORY_COLLISION'
    }
    New-Item -ItemType Directory -Path $workingDirectory | Out-Null
    $script:WorkingDirectoryCreated = $true
    Protect-Directory $workingDirectory
    $sourceDatabase = $ExpectedDatabase
    $sourceSchema = 'public'
    $sourceSearchPath = 'public'
    $sourceRevision = $ExpectedStartRevision
    $sourceRevisionCount = '1'
    $serverMajor = $ReusePostgresMajor
    Clear-SourcePostgresEnvironment
    Write-Host 'SOURCE_CONNECTION=SKIPPED_RETAINED_BACKUP'
    Write-Host 'BACKUP_SHA256_VERIFIED=true'
    Write-Host ('RETAINED_SOURCE_REVISION_EXPECTED={0}' -f $ExpectedStartRevision)
    Write-Host ('RETAINED_SOURCE_POSTGRES_MAJOR_EXPECTED={0}' -f $serverMajor)
}
else {
        Write-Host 'Before creating a cutover backup, verify the Auth API service and every background/database writer are paused in Render Dashboard.'
        Write-Host 'Maintenance Mode alone does not stop private-network or scheduled writers. Do not suspend PostgreSQL.'
        $writersPausedConfirmation = Read-Host 'After confirming all writers are paused, type AUTH_WRITERS_PAUSED'
        if ($writersPausedConfirmation -cne 'AUTH_WRITERS_PAUSED') {
            Stop-Safely 'WRITERS_NOT_PAUSED'
        }
        $script:WritersPaused = $true

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
    }
    Set-RunnerPhase 'PINNED_SOURCE_PREPARATION'

    Set-RunnerPhase 'PINNED_SOURCE_PREPARATION'
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

    Set-RunnerPhase 'VERIFICATION_HELPER_PREPARATION'
    $helperPath = Join-Path $workingDirectory 'verify_rehearsal.py'
    $baselinePath = Join-Path $workingDirectory 'baseline_counts.json'
    $helperSource = @'
from __future__ import annotations
import json
import hashlib
import os
import sys
import traceback
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

def verify_pinned_index_metadata_gap(connection) -> bool:
    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
    try:
        identity = connection.execute(text(
            "SELECT current_database(), COALESCE(current_schema(), ''), "
            "current_setting('server_version_num')"
        )).one()
        database, schema, version_number = identity
        revision, revision_count = read_revision(connection)
        expected_major = int(os.environ["OA_EXPECTED_PG_MAJOR"])
        if (database != os.environ["OA_EXPECTED_TEMP_DB"] or schema != "public"
                or int(version_number) // 10000 != expected_major
                or revision_count != 1 or revision != TARGET_REVISION):
            return False

        expected = (
            ("auth_management_tokens", "ix_auth_management_tokens_user_purpose",
             ["user_id", "purpose", "consumed_at"]),
            ("admin_audit_events", "ix_admin_audit_events_created_at", ["created_at"]),
        )
        index_query = text("""
            SELECT idx.indisvalid, idx.indisready, idx.indisunique,
                   idx.indpred IS NULL, idx.indexprs IS NULL,
                   idx.indnatts = idx.indnkeyatts, idx.indisprimary,
                   ARRAY(
                       SELECT attr.attname
                       FROM unnest(idx.indkey) WITH ORDINALITY AS key(attnum, ordinality)
                       JOIN pg_attribute AS attr
                         ON attr.attrelid = tbl.oid AND attr.attnum = key.attnum
                       WHERE key.ordinality <= idx.indnkeyatts
                       ORDER BY key.ordinality
                   )
            FROM pg_class AS idx_relation
            JOIN pg_namespace AS index_schema ON index_schema.oid = idx_relation.relnamespace
            JOIN pg_index AS idx ON idx.indexrelid = idx_relation.oid
            JOIN pg_class AS tbl ON tbl.oid = idx.indrelid
            WHERE index_schema.nspname = :schema_name
              AND tbl.relname = :table_name
              AND idx_relation.relname = :index_name
              AND idx_relation.relkind = 'i'
        """)
        for table_name, index_name, expected_columns in expected:
            row = connection.execute(index_query, {
                "schema_name": "public",
                "table_name": table_name,
                "index_name": index_name,
            }).one_or_none()
            if row is None:
                return False
            valid, ready, unique, unfiltered, no_expressions, no_include_columns, primary, columns = row
            if (not valid or not ready or unique or not unfiltered or not no_expressions
                    or not no_include_columns or primary or list(columns) != expected_columns):
                return False
        return True
    finally:
        connection.rollback()

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
            if mode == "verify-index-gap":
                if verify_pinned_index_metadata_gap(connection):
                    print("VERIFY_PINNED_INDEX_DEFINITIONS=true")
                    return 0
                print("VERIFY_PINNED_INDEX_DEFINITIONS=false")
                return 21

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
    except Exception as exc:
        frames = traceback.extract_tb(exc.__traceback__)
        frame = frames[-1] if frames else None
        print("VERIFY_EXCEPTION_TYPE=" + type(exc).__name__)
        if frame is not None:
            print("VERIFY_EXCEPTION_LOCATION=" + f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}")
        print("VERIFY_FAILED_WITH_REDACTED_DIAGNOSTIC")
        raise SystemExit(20)
'@
    [IO.File]::WriteAllText($helperPath, $helperSource, [Text.UTF8Encoding]::new($false))

    Set-RunnerPhase 'POSTGRES_IMAGE_PREPARATION'
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

if ($script:UseExistingBackup) {
    Set-RunnerPhase 'RETAINED_ARCHIVE_VALIDATION'
    $mountSpec = 'type=bind,source=' + $backupDirectory + ',target=/backup,readonly'
    $archiveCheckClientName = Register-ClientContainer 'archive-check'
    $archiveListExit = Invoke-DockerClient @(
        'run', '--rm', '--name', $archiveCheckClientName,
        '--label', ('organizationai.auth-rehearsal.run=' + $runId),
        '--mount', $mountSpec, $image, 'pg_restore', '--list', ('/backup/' + $archiveFileName)
    )
    if ($archiveListExit -ne 0) {
        Stop-Safely 'BACKUP_ARCHIVE_READ_FAILED'
    }
    $verifiedAgain = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    if ($verifiedAgain -cne $archiveHash) {
        Stop-Safely 'RETAINED_BACKUP_HASH_CHANGED'
    }
    $script:BackupComplete = $true
    Write-Host 'PG_RESTORE_LIST=PASS'
    Write-Host ('Backup archive reused read-only; SHA-256={0}.' -f $archiveHash)
}
else {
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
    }


    $tempPassword = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
    Set-ProcessEnvironment 'POSTGRES_USER' $tempUser
    Set-ProcessEnvironment 'POSTGRES_DB' $tempDatabase
    Set-ProcessEnvironment 'POSTGRES_PASSWORD' $tempPassword

    Set-RunnerPhase 'TEMP_POSTGRES_START'
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

    Set-RunnerPhase 'TEMP_ARCHIVE_RESTORE'
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

    Set-RunnerPhase 'BASELINE_FINGERPRINT'
    $baselineExit = Run-VerificationHelper @($helperPath, 'before', $baselinePath)
    if ($baselineExit -ne 0) {
        Stop-Safely 'TEMP_BASELINE_VERIFICATION_FAILED'
    }
    Write-Host ('Restored copy is at revision {0}; existing table data fingerprints are recorded privately for comparison.' -f $ExpectedStartRevision)

    Set-RunnerPhase 'ALEMBIC_UPGRADE'
    $locationPushed = $false
    $migrationProcess = $null
    try {
        Push-Location -LiteralPath $sourceRoot
        $locationPushed = $true
        $migrationProcess = Invoke-NativeWithDiagnostic $script:PythonPath @('-m', 'alembic', '-c', 'alembic.ini', 'upgrade', $TargetRevision)
    }
    finally {
        if ($locationPushed) { Pop-Location }
    }
    if ($migrationProcess.InvocationStatus -cne 'NATIVE_PROCESS_EXITED') {
        $script:FailureExceptionType = $migrationProcess.PowerShellFailure
        Stop-Safely 'ALEMBIC_UPGRADE_PROCESS_START_FAILED'
    }
    $migrationExit = [int]$migrationProcess.ExitCode
    $migrationDiagnostic = Get-SafeAlembicDiagnostic $migrationProcess.DiagnosticText $migrationExit
    $migrationProcess.DiagnosticText = $null
    Write-Host ('ALEMBIC_UPGRADE_EXIT_CODE={0}' -f $migrationExit)
    Write-Host ('ALEMBIC_UPGRADE_DIAGNOSTIC={0}' -f $migrationDiagnostic)
    if ($script:FailureSqlState) { Write-Host ('ALEMBIC_UPGRADE_SQLSTATE={0}' -f $script:FailureSqlState) }
    if ($migrationExit -ne 0) {
        Stop-Safely 'PINNED_ALEMBIC_UPGRADE_FAILED'
    }
    Write-Host ('Pinned Alembic source advanced only the temporary copy to {0}.' -f $TargetRevision)

    Set-RunnerPhase 'ALEMBIC_SCHEMA_CHECK'
    $locationPushed = $false
    $schemaCheckProcess = $null
    try {
        Push-Location -LiteralPath $sourceRoot
        $locationPushed = $true
        $schemaCheckProcess = Invoke-NativeWithDiagnostic $script:PythonPath @('-m', 'alembic', '-c', 'alembic.ini', 'check')
    }
    finally {
        if ($locationPushed) { Pop-Location }
    }
    if ($schemaCheckProcess.InvocationStatus -cne 'NATIVE_PROCESS_EXITED') {
        $script:FailureExceptionType = $schemaCheckProcess.PowerShellFailure
        Stop-Safely 'ALEMBIC_SCHEMA_CHECK_PROCESS_START_FAILED'
    }
    $schemaCheckExit = [int]$schemaCheckProcess.ExitCode
    $schemaCheckDiagnostic = Get-SafeAlembicDiagnostic $schemaCheckProcess.DiagnosticText $schemaCheckExit
    $schemaCheckProcess.DiagnosticText = $null
    Write-Host ('ALEMBIC_SCHEMA_CHECK_EXIT_CODE={0}' -f $schemaCheckExit)
    Write-Host ('ALEMBIC_SCHEMA_CHECK_DIAGNOSTIC={0}' -f $schemaCheckDiagnostic)
    if ($script:FailureSqlState) { Write-Host ('ALEMBIC_SCHEMA_CHECK_SQLSTATE={0}' -f $script:FailureSqlState) }
    if ($script:SchemaDiffKinds.Count -gt 0) { Write-Host ('ALEMBIC_SCHEMA_DIFF_KINDS={0}' -f (($script:SchemaDiffKinds | Sort-Object -Unique) -join ',')) }
    $knownIndexGapVerified = $false
    if ($schemaCheckExit -ne 0 -and
        $schemaCheckDiagnostic -ceq 'PINNED_MIGRATION_INDEX_METADATA_GAP' -and
        $script:PinnedMigrationIndexGapCandidate -and
        (@($script:SchemaDiffKinds | Sort-Object -Unique) -join ',') -ceq 'remove_index') {
        Set-RunnerPhase 'PINNED_INDEX_METADATA_GAP_VERIFICATION'
        $script:IndexGapVerificationPassed = $false
        $indexGapExit = Run-VerificationHelper @($helperPath, 'verify-index-gap', $baselinePath)
        if ($indexGapExit -eq 0 -and $script:IndexGapVerificationPassed) {
            $knownIndexGapVerified = $true
            Write-Host 'PINNED_MIGRATION_INDEX_METADATA_GAP_VERIFIED=true'
        }
        else {
            Stop-Safely 'PINNED_MIGRATION_INDEX_METADATA_GAP_VERIFICATION_FAILED'
        }
    }
    if ($schemaCheckExit -ne 0 -and -not $knownIndexGapVerified) {
        Stop-Safely 'PINNED_ALEMBIC_SCHEMA_CHECK_FAILED'
    }
    if ($knownIndexGapVerified) {
        $script:FailureExceptionType = $null
        $script:FailureCodeLocation = $null
        $script:FailureSqlState = $null
        Write-Host 'ALEMBIC_SCHEMA_CHECK=PINNED_INDEX_METADATA_GAP_VERIFIED'
    }
    else {
        Write-Host 'ALEMBIC_SCHEMA_CHECK=true'
    }

    Set-RunnerPhase 'POST_MIGRATION_VERIFICATION'
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
    $failureRecord = $_
    if ([string]::IsNullOrWhiteSpace($script:FailureCode)) {
        $script:FailureCode = 'UNEXPECTED_REDACTED_FAILURE'
        $script:FailurePhase = $script:CurrentPhase
        $script:FailureExceptionType = $failureRecord.Exception.GetType().Name
        $failureLine = [int]$failureRecord.InvocationInfo.ScriptLineNumber
        $failureFile = [IO.Path]::GetFileName([string]$failureRecord.InvocationInfo.ScriptName)
        if ($failureFile -notmatch '^[A-Za-z0-9_.-]+$') { $failureFile = 'run_auth_migration_rehearsal.ps1' }
        $script:FailureCodeLocation = '{0}:{1}' -f $failureFile, $failureLine
    }
}
finally {
    Set-RunnerPhase 'CLEANUP'
    try {
        if ($script:ContainerCreationAttempted -and -not [string]::IsNullOrWhiteSpace($containerName)) {
            try {
                $removed = Remove-RunOwnedContainer $containerName $runId
                if (-not $removed) {
                    $script:CleanupPending = $true
                    $script:CleanupPendingResource = $containerName
                }
                else {
                    $script:ContainerCreated = $false
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
                            $removed = Remove-RunOwnedContainer $clientName $runId
                            if (-not $removed) {
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
        $script:FailurePhase = 'CLEANUP'
        $script:FailureExceptionType = $null
        $script:FailureCodeLocation = $null
        $script:FailureSqlState = $null
    }
    Write-Host ('CLEANUP_PENDING_RESOURCE={0}' -f $script:CleanupPendingResource)
    Write-Host ('CONTAINER_CLEANUP_DIAGNOSTIC={0}' -f $script:ContainerCleanupDiagnostic)
}
if (-not $script:CleanupPending -and [string]::IsNullOrWhiteSpace($script:FailureCode) -and -not $script:UseExistingBackup) {
    try {
        $receipt = [ordered]@{
            receipt_version = 1
            run_id = $runId
            result = 'PASS'
            cleanup_complete = $true
            writers_paused = $script:WritersPaused
            source_sha = $PinnedSha
            database = $sourceDatabase
            schema = $sourceSchema
            start_revision = $ExpectedStartRevision
            target_revision = $TargetRevision
            postgres_major = [int]$serverMajor
            backup_filename = [IO.Path]::GetFileName($archivePath)
            backup_sha256 = $archiveHash.ToUpperInvariant()
            data_preservation_verified = $true
            created_utc = [DateTime]::UtcNow.ToString('o')
        }
        $receiptPath = Join-Path $backupDirectory 'auth-migration-rehearsal.json'
        $temporaryReceiptPath = $receiptPath + '.tmp-' + $runId.Replace('-', '')
        [IO.File]::WriteAllText(
            $temporaryReceiptPath,
            ($receipt | ConvertTo-Json -Depth 4),
            [Text.UTF8Encoding]::new($false)
        )
        Move-Item -LiteralPath $temporaryReceiptPath -Destination $receiptPath -Force
        Write-Host 'REHEARSAL_RECEIPT=PASS'
    }
    catch {
        $script:FailureCode = 'REHEARSAL_RECEIPT_WRITE_FAILED'
        $script:FailurePhase = 'REHEARSAL_RECEIPT_WRITE'
        $script:FailureExceptionType = $_.Exception.GetType().Name
        if ($script:FailureExceptionType -notmatch '^[A-Za-z][A-Za-z0-9_]{0,79}$') {
            $script:FailureExceptionType = 'PowerShellFailure'
        }
    }
}
elseif (-not $script:CleanupPending -and [string]::IsNullOrWhiteSpace($script:FailureCode) -and $script:UseExistingBackup) {
    Write-Host 'REHEARSAL_RECEIPT=NOT_ISSUED_REUSED_BACKUP'
}
elseif (-not [string]::IsNullOrWhiteSpace($script:FailureCode)) {
    Write-Host 'TEMPORARY_RESOURCE_CLEANUP=complete'
}
if (-not [string]::IsNullOrWhiteSpace($script:FailureCode)) {
    Write-Host ('FAILURE_PHASE={0}' -f $(if ($script:FailurePhase) { $script:FailurePhase } else { $script:CurrentPhase }))
    if ($script:FailureExceptionType) {
        Write-Host ('FAILURE_EXCEPTION_TYPE={0}' -f $script:FailureExceptionType)
    }
    if ($script:FailureCodeLocation) {
        Write-Host ('FAILURE_CODE_LOCATION={0}' -f $script:FailureCodeLocation)
    }
    if ($script:FailureSqlState) {
        Write-Host ('FAILURE_SQLSTATE={0}' -f $script:FailureSqlState)
    }
    Write-Host ('RESULT=FAILED; CODE={0}' -f $script:FailureCode)
    if ($script:BackupComplete -or $script:UseExistingBackup) {
        Write-Host ('BACKUP_RETAINED={0}' -f $backupDirectory)
        Write-Host ('BACKUP_SHA256={0}' -f $archiveHash)
    }
    try {
        New-Item -ItemType Directory -Path $script:DiagnosticDirectory -ErrorAction Stop | Out-Null
        Protect-Directory $script:DiagnosticDirectory
        $safeLines = @(
            ('RUN_ID=' + $runId),
            ('FAILURE_PHASE=' + $(if ($script:FailurePhase) { $script:FailurePhase } else { $script:CurrentPhase })),
            ('FAILURE_CODE=' + $script:FailureCode),
            ('FAILURE_EXCEPTION_TYPE=' + $(if ($script:FailureExceptionType) { $script:FailureExceptionType } else { 'unavailable' })),
            ('FAILURE_CODE_LOCATION=' + $(if ($script:FailureCodeLocation) { $script:FailureCodeLocation } else { 'unavailable' })),
            ('CLEANUP=' + $(if ($script:CleanupPending) { 'pending' } else { 'complete' }))
        )
        [IO.File]::WriteAllLines($script:DiagnosticPath, $safeLines, [Text.UTF8Encoding]::new($false))
        Write-Host ('SAFE_DIAGNOSTIC_FILE={0}' -f $script:DiagnosticPath)
    }
    catch {
        Write-Host 'SAFE_DIAGNOSTIC_FILE=not_written'
    }
    exit 1
}
Write-Host 'TEMP_CONTAINER_CLEANUP=complete'
Write-Host 'RESULT=PASS'
exit 0
