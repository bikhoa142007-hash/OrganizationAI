[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$PythonExe,

    [switch]$SyntheticOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$helperPath = Join-Path $PSScriptRoot 'run_auth_live_migration.py'
$environmentNames = @(
    'DATABASE_URL', 'AUTH_ALLOW_SQLITE_MIGRATION_TESTS', 'PYTHONPATH',
    'PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGUSER', 'PGDATABASE', 'PGPASSWORD',
    'PGPASSFILE', 'PGSSLMODE', 'PGSSLCERT', 'PGSSLKEY', 'PGSSLROOTCERT',
    'PGSSLCRL', 'PGSSLCRLDIR', 'PGSSLNEGOTIATION', 'PGGSSENCMODE',
    'PGREQUIRESSL', 'PGCHANNELBINDING', 'PGAPPNAME', 'PGCONNECT_TIMEOUT',
    'PGOPTIONS', 'PGSERVICE', 'PGSERVICEFILE', 'PGTARGETSESSIONATTRS',
    'POSTGRES_USER', 'POSTGRES_DB', 'POSTGRES_PASSWORD'
)
$environmentSnapshot = @{}
$pythonExitCode = 1
$script:SetupCode = 'INITIALIZATION'
$previousErrorActionPreference = $null

try {
    $script:SetupCode = 'PYTHON_PATH_RESOLUTION'
    $resolvedPython = (Resolve-Path -LiteralPath $PythonExe -ErrorAction Stop).Path
    if (-not (Test-Path -LiteralPath $resolvedPython -PathType Leaf)) {
        $script:SetupCode = 'PYTHON_EXECUTABLE_NOT_FOUND'
        throw 'PYTHON_EXECUTABLE_NOT_FOUND'
    }
    if (-not (Test-Path -LiteralPath $helperPath -PathType Leaf)) {
        $script:SetupCode = 'PYTHON_RUNNER_MISSING'
        throw 'PYTHON_RUNNER_MISSING'
    }

    $script:SetupCode = 'PYTHON_RUNTIME_PROBE'
    $probeCode = 'import sys,alembic,sqlalchemy,psycopg; print(chr(9).join([sys.executable,str(sys.version_info[0])+chr(46)+str(sys.version_info[1])+chr(46)+str(sys.version_info[2]),alembic.__version__,sqlalchemy.__version__,psycopg.__version__]))'
    $probeErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $probeLines = @(& $resolvedPython -B -c $probeCode)
    $probeExit = [int]$LASTEXITCODE
    $ErrorActionPreference = $probeErrorActionPreference
    if ($probeExit -ne 0 -or $probeLines.Count -ne 1) {
        $script:SetupCode = 'PYTHON_DEPENDENCIES_UNAVAILABLE'
        throw 'PYTHON_DEPENDENCIES_UNAVAILABLE'
    }
    $probeFields = ([string]$probeLines[0]) -split "`t"
    if ($probeFields.Count -ne 5) {
        $script:SetupCode = 'PYTHON_PROBE_INVALID'
        throw 'PYTHON_PROBE_INVALID'
    }
    $versionFields = $probeFields[1] -split '\.'
    if ($versionFields.Count -ne 3) {
        $script:SetupCode = 'PYTHON_PROBE_INVALID'
        throw 'PYTHON_PROBE_INVALID'
    }
    $actualPython = [IO.Path]::GetFullPath([string]$probeFields[0])
    $requestedPython = [IO.Path]::GetFullPath($resolvedPython)
    if (-not $actualPython.Equals($requestedPython, [StringComparison]::OrdinalIgnoreCase)) {
        $script:SetupCode = 'PYTHON_EXECUTABLE_PATH_MISMATCH'
        throw 'PYTHON_EXECUTABLE_PATH_MISMATCH'
    }
    $pythonMajor = [int]$versionFields[0]
    $pythonMinor = [int]$versionFields[1]
    if ($pythonMajor -ne 3 -or $pythonMinor -lt 12 -or $pythonMinor -ge 14) {
        $script:SetupCode = 'PYTHON_VERSION_UNSUPPORTED'
        throw 'PYTHON_VERSION_UNSUPPORTED'
    }
    Write-Host ('PYTHON_ACTUAL_EXECUTABLE={0}' -f $actualPython)
    Write-Host ('PYTHON_VERSION={0}' -f $probeFields[1])
    Write-Host ('ALEMBIC_VERSION={0}; SQLALCHEMY_VERSION={1}; PSYCOPG_VERSION={2}' -f $probeFields[2], $probeFields[3], $probeFields[4])

    $script:SetupCode = 'PROCESS_ENVIRONMENT_ISOLATION'
    foreach ($name in $environmentNames) {
        $environmentSnapshot[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }

    $pythonArguments = @('-B', $helperPath, '--repository-root', $repoRoot)
    if ($SyntheticOnly) {
        $pythonArguments += '--synthetic-only'
    }
    $script:SetupCode = if ($SyntheticOnly) { 'SYNTHETIC_RUN' } else { 'LIVE_RUN' }
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $actualPython @pythonArguments
    $pythonExitCode = [int]$LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
}
catch {
    $safeType = $_.Exception.GetType().Name
    if ($safeType -notmatch '^[A-Za-z][A-Za-z0-9_]{0,79}$') { $safeType = 'PowerShellFailure' }
    Write-Host ('RUNNER_SETUP_PHASE={0}' -f $script:SetupCode)
    if ($script:SetupCode -ceq 'PYTHON_DEPENDENCIES_UNAVAILABLE') {
        Write-Host ('PYTHON_PROBE_EXIT_CODE={0}; OUTPUT_LINE_COUNT={1}' -f $probeExit, $probeLines.Count)
    }
    Write-Host ('RUNNER_SETUP_FAILURE_EXCEPTION_TYPE={0}' -f $safeType)
    Write-Host 'RESULT=FAILED; CODE=RUNNER_SETUP_FAILED'
    $pythonExitCode = 2
}
finally {
    if ($null -ne $previousErrorActionPreference) {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    foreach ($name in $environmentNames) {
        if ($environmentSnapshot.ContainsKey($name)) {
            [Environment]::SetEnvironmentVariable($name, $environmentSnapshot[$name], 'Process')
        }
    }
}

exit $pythonExitCode
