[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonExe = Join-Path $repoRoot '.venv-test-20261009\Scripts\python.exe'
$frontendRoot = Join-Path $repoRoot 'frontend'
$viteCli = Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'
$npmCommand = Get-Command npm.cmd -ErrorAction Stop
$nodeCommand = Get-Command node.exe -ErrorAction Stop
$dockerCommand = Get-Command docker.exe -ErrorAction Stop

$savedEnvironmentNames = @(
    'APP_ENV',
    'AUTH_ALLOW_SQLITE_MIGRATION_TESTS',
    'AUTH_COOKIE_SECURE',
    'AUTH_COOKIE_SAMESITE',
    'AUTH_E2E_BASE_URL',
    'AUTH_E2E_CHECKER_USERNAME',
    'AUTH_E2E_MAKER_USERNAME',
    'AUTH_REMEMBER_TOKEN_DAYS',
    'AUTH_SEED_ENABLED',
    'AUTH_SEED_PASSWORD',
    'AUTH_WORKFLOW_AI_PROVIDER',
    'AUTH_WORKFLOW_MOCK_SCENARIO',
    'CORS_ORIGINS',
    'DATABASE_URL',
    'DEMO_DATABASE',
    'DEMO_MOCK_MODE',
    'JWT_SECRET',
    'JWT_ACCESS_TOKEN_MINUTES',
    'PLAYWRIGHT_JSON_OUTPUT_FILE',
    'VITE_API_BASE_URL',
    'VITE_DEMO_ENABLED'
)
$currentEnvironment = [Environment]::GetEnvironmentVariables([EnvironmentVariableTarget]::Process)
$savedEnvironment = @{}
foreach ($name in $savedEnvironmentNames) {
    $savedEnvironment[$name] = [pscustomobject]@{
        Exists = $currentEnvironment.Contains($name)
        Value  = [Environment]::GetEnvironmentVariable($name, [EnvironmentVariableTarget]::Process)
    }
}

$runId = [guid]::NewGuid().ToString('N')
$runRoot = Join-Path ([IO.Path]::GetTempPath()) "organizationai-auth-e2e-$runId"
$containerName = "organizationai-auth-e2e-$runId"
$containerCreated = $false
$apiProcess = $null
$frontendProcess = $null
$completed = $false
$artifactArchiveSucceeded = $false
$artifactSecrets = @()
$apiLog = $null
$apiErrorLog = $null
$frontendLog = $null
$frontendErrorLog = $null
$playwrightReport = $null

function Assert-PortFree([int] $Port) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    $started = $false
    try {
        $listener.Start()
        $started = $true
    }
    catch {
        throw "Required local port $Port is not free. Stop the process using that port, then rerun this script."
    }
    finally {
        if ($started) { $listener.Stop() }
    }
}

function Stop-OwnedProcess($Process, [string] $Label) {
    if ($null -eq $Process) { return }
    try {
        $Process.Refresh()
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction Stop
            [void]$Process.WaitForExit(10000)
        }
    }
    catch {
        Write-Warning "Could not stop this run's $Label process (PID $($Process.Id)): $($_.Exception.Message)"
    }
}

function Redact-ArtifactText([string] $Text) {
    foreach ($secret in $artifactSecrets) {
        if (-not [string]::IsNullOrEmpty($secret)) {
            $Text = $Text.Replace($secret, '[REDACTED]')
        }
    }

    $Text = [regex]::Replace(
        $Text,
        '(?i)("?[\w.-]*(?:password|passwd|secret|token|authorization|cookie|api[_-]?key|database[_-]?url)[\w.-]*"?\s*[:=]\s*)("[^"]*"|(?:(?:Bearer|Basic)\s+)?[^\s,;]+)',
        '$1"[REDACTED]"'
    )
    $Text = [regex]::Replace($Text, '(?i)(postgres(?:ql)?(?:\+\w+)?://)[^\s"''<>]+', '$1[REDACTED]')
    $Text = [regex]::Replace($Text, '(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer [REDACTED]')
    $Text = [regex]::Replace($Text, '(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])', '[REDACTED_JWT]')
    return $Text
}

try {
    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
        throw "Expected Python interpreter is missing: $pythonExe"
    }
    if (-not (Test-Path -LiteralPath $viteCli -PathType Leaf)) {
        throw "Frontend dependencies are missing. Run npm ci in $frontendRoot before retrying."
    }

    # These are the only fixed application ports used by this run. The existing
    # 8010, 5173 and 5433 services are intentionally not queried or modified.
    Assert-PortFree 18010
    Assert-PortFree 15173

    $testSource = Get-Content -LiteralPath (Join-Path $frontendRoot 'e2e\auth-live.spec.ts') -Raw
    $playwrightConfigSource = Get-Content -LiteralPath (Join-Path $frontendRoot 'playwright.auth-live.config.ts') -Raw
    if (-not $testSource.Contains('process.env.AUTH_E2E_MAKER_USERNAME') -or
        -not $testSource.Contains('process.env.AUTH_E2E_CHECKER_USERNAME') -or
        -not $testSource.Contains('process.env.VITE_API_BASE_URL') -or
        -not $playwrightConfigSource.Contains('process.env.AUTH_E2E_BASE_URL')) {
        throw 'Auth E2E must consume its explicit seeded usernames and isolated API/frontend URL environment variables.'
    }

    New-Item -ItemType Directory -Path $runRoot | Out-Null
    $apiLog = Join-Path $runRoot 'api.log'
    $apiErrorLog = Join-Path $runRoot 'api-error.log'
    $frontendLog = Join-Path $runRoot 'frontend.log'
    $frontendErrorLog = Join-Path $runRoot 'frontend-error.log'
    $playwrightReport = Join-Path $runRoot 'auth-e2e-report.json'
    $demoDatabase = Join-Path $runRoot 'isolated-demo.sqlite3'

    $dbUser = 'organizationai_test'
    $dbName = 'organizationai_auth_e2e'
    $makerUsername = 'maker'
    $checkerUsername = 'checker'
    if ([string]::IsNullOrWhiteSpace($makerUsername) -or [string]::IsNullOrWhiteSpace($checkerUsername) -or
        $makerUsername -eq $checkerUsername) {
        throw 'Temporary Maker and Checker usernames must be non-empty and distinct.'
    }
    $dbPassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    $seedPassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    $jwtSecret = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    $artifactSecrets = @($dbPassword, $seedPassword, $jwtSecret)

    [Environment]::SetEnvironmentVariable('APP_ENV', 'demo', 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_ALLOW_SQLITE_MIGRATION_TESTS', 'false', 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_COOKIE_SECURE', 'false', 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_COOKIE_SAMESITE', 'lax', 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_E2E_BASE_URL', 'http://127.0.0.1:15173', 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_E2E_MAKER_USERNAME', $makerUsername, 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_E2E_CHECKER_USERNAME', $checkerUsername, 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_REMEMBER_TOKEN_DAYS', '14', 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_SEED_ENABLED', 'true', 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_SEED_PASSWORD', $seedPassword, 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_WORKFLOW_AI_PROVIDER', 'MOCK_VLM', 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_WORKFLOW_MOCK_SCENARIO', 'review', 'Process')
    # CORS_ORIGINS is also the API's browser trusted-origin allowlist.
    [Environment]::SetEnvironmentVariable('CORS_ORIGINS', 'http://127.0.0.1:15173', 'Process')
    [Environment]::SetEnvironmentVariable('DEMO_DATABASE', $demoDatabase, 'Process')
    [Environment]::SetEnvironmentVariable('DEMO_MOCK_MODE', 'review', 'Process')
    [Environment]::SetEnvironmentVariable('JWT_SECRET', $jwtSecret, 'Process')
    [Environment]::SetEnvironmentVariable('JWT_ACCESS_TOKEN_MINUTES', '30', 'Process')
    [Environment]::SetEnvironmentVariable('PLAYWRIGHT_JSON_OUTPUT_FILE', $playwrightReport, 'Process')
    [Environment]::SetEnvironmentVariable('VITE_API_BASE_URL', 'http://127.0.0.1:18010/api', 'Process')
    [Environment]::SetEnvironmentVariable('VITE_DEMO_ENABLED', 'true', 'Process')

    Write-Host 'Starting a disposable PostgreSQL 16 container on a random loopback port...'
    $dockerRunOutput = & $dockerCommand.Source run --detach --rm --name $containerName `
        --tmpfs '/var/lib/postgresql/data:rw,size=1g' `
        --env "POSTGRES_USER=$dbUser" `
        --env "POSTGRES_PASSWORD=$dbPassword" `
        --env "POSTGRES_DB=$dbName" `
        --publish '127.0.0.1::5432' postgres:16 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker could not start the disposable PostgreSQL container. Existing containers and volumes were not changed.'
    }
    $containerCreated = $true

    $publishedPortOutput = & $dockerCommand.Source port $containerName '5432/tcp' 2>&1
    if ($LASTEXITCODE -ne 0 -or $publishedPortOutput -notmatch '^127\.0\.0\.1:(\d+)$') {
        throw 'Could not determine the disposable PostgreSQL loopback port.'
    }
    $postgresPort = [int]$Matches[1]
    if ($postgresPort -in @(8010, 5173, 5433, 18010, 15173)) {
        throw "Docker selected reserved port $postgresPort; cleanup will remove only this run's container. Rerun to allocate another port."
    }
    Write-Host "Temporary PostgreSQL is bound to 127.0.0.1:$postgresPort."

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $null = & $dockerCommand.Source exec $containerName pg_isready -U $dbUser -d $dbName 2>$null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw 'Disposable PostgreSQL did not become ready within 120 seconds.' }

    $databaseUrl = "postgresql+psycopg://${dbUser}:${dbPassword}@127.0.0.1:${postgresPort}/${dbName}"
    $artifactSecrets += $databaseUrl
    [Environment]::SetEnvironmentVariable('DATABASE_URL', $databaseUrl, 'Process')
    Write-Host 'Applying Alembic migrations to the disposable PostgreSQL database...'
    & $pythonExe -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Alembic migration failed against the disposable PostgreSQL database.' }

    $verifyPostgres = @'
import os
from sqlalchemy import create_engine, inspect, text

engine = create_engine(os.environ["DATABASE_URL"])
try:
    inspector = inspect(engine)
    with engine.connect() as connection:
        revisions = connection.scalars(text("SELECT version_num FROM alembic_version")).all()
    assert revisions == ["20261009_08"], revisions
    assert "auth_workflow_plans" in inspector.get_table_names()
    assert any(
        item["name"] == "uq_auth_workflow_plans_maker_creation_key" and item["unique"]
        for item in inspector.get_indexes("auth_workflow_plans")
    )
    print("PostgreSQL migration verified: head 20261009_08 and unique draft idempotency index.")
finally:
    engine.dispose()
'@
    $verifyScriptPath = Join-Path $runRoot 'verify_postgres_migration.py'
    [IO.File]::WriteAllText($verifyScriptPath, $verifyPostgres, [Text.UTF8Encoding]::new($false))
    & $pythonExe $verifyScriptPath
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL migration verification failed.' }

    Write-Host 'Seeding temporary Maker and Checker accounts with the same ephemeral password used by Playwright...'
    & $pythonExe -m src.backend.seed_auth
    if ($LASTEXITCODE -ne 0) { throw 'Could not seed Maker and Checker into the disposable PostgreSQL database.' }

    $verifySeed = @'
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, select

repo_root = str(Path(sys.argv[1]).resolve())
sys.path.insert(0, repo_root)

from src.backend.db.models import Role, User, UserRole

maker = os.environ["AUTH_E2E_MAKER_USERNAME"]
checker = os.environ["AUTH_E2E_CHECKER_USERNAME"]
if not maker or not checker or maker == checker:
    raise SystemExit("Auth E2E usernames must be non-empty and distinct.")
expected = {maker: {"MAKER"}, checker: {"CHECKER"}}

def assert_seed_roles(actual):
    if actual != expected:
        raise RuntimeError(f"Temporary Auth seed roles do not match E2E configuration: {actual!r}")

# Exercise the guard itself: the exact expected mapping passes; wrong, missing,
# or extra roles must fail before checking the actual temporary database.
assert_seed_roles(expected)
for invalid in (
    {maker: {"CHECKER"}, checker: {"MAKER"}},
    {maker: {"MAKER"}},
    {maker: {"MAKER"}, "wrong-checker": {"CHECKER"}},
    {maker: {"MAKER", "ADMIN"}, checker: {"CHECKER"}},
):
    try:
        assert_seed_roles(invalid)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Seed-role guard accepted an invalid username/role mapping.")

statement = (
    select(User.username, Role.code)
    .join(UserRole, UserRole.user_id == User.id)
    .join(Role, Role.id == UserRole.role_id)
    .where(User.username.in_((maker, checker)), User.status == "ACTIVE")
)
engine = create_engine(os.environ["DATABASE_URL"])
try:
    actual = {}
    with engine.connect() as connection:
        for username, role in connection.execute(statement):
            actual.setdefault(username, set()).add(role)
    assert_seed_roles(actual)
    print("Temporary Auth seed verified: configured Maker and Checker usernames have the expected roles.")
finally:
    engine.dispose()
'@
    $verifySeedScriptPath = Join-Path $runRoot 'verify_auth_seed.py'
    [IO.File]::WriteAllText($verifySeedScriptPath, $verifySeed, [Text.UTF8Encoding]::new($false))
    & $pythonExe $verifySeedScriptPath $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'Temporary Auth seed verification failed; Auth E2E will not run.' }

    Write-Host 'Starting the API on 127.0.0.1:18010 and frontend on 127.0.0.1:15173...'
    $apiProcess = Start-Process -FilePath $pythonExe `
        -ArgumentList @('-m', 'uvicorn', 'src.backend.api.app:app', '--host', '127.0.0.1', '--port', '18010') `
        -WorkingDirectory $repoRoot -RedirectStandardOutput $apiLog -RedirectStandardError $apiErrorLog `
        -PassThru -WindowStyle Hidden
    $frontendProcess = Start-Process -FilePath $nodeCommand.Source `
        -ArgumentList @('"' + $viteCli + '"', '--host', '127.0.0.1', '--port', '15173', '--strictPort') `
        -WorkingDirectory $frontendRoot -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErrorLog `
        -PassThru -WindowStyle Hidden

    $apiReady = $false
    $frontendReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $apiProcess.Refresh()
        $frontendProcess.Refresh()
        if ($apiProcess.HasExited -or $frontendProcess.HasExited) {
            throw 'The isolated API or frontend process exited during startup. Inspect the run-specific logs in the reported temp folder.'
        }
        try {
            $apiResponse = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18010/api/health/ready' -TimeoutSec 4
            $apiHealth = $apiResponse.Content | ConvertFrom-Json
            $apiReady = ($apiResponse.StatusCode -eq 200 -and $apiHealth.auth_database -eq 'postgresql')
        }
        catch { $apiReady = $false }
        try {
            $frontendResponse = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:15173/' -TimeoutSec 4
            $frontendReady = ($frontendResponse.StatusCode -eq 200)
        }
        catch { $frontendReady = $false }
        if ($apiReady -and $frontendReady) { break }
        Start-Sleep -Seconds 2
    }
    if (-not $apiReady -or -not $frontendReady) {
        throw 'The isolated API did not report PostgreSQL readiness or the frontend did not respond within 120 seconds.'
    }

    if ($env:VITE_API_BASE_URL -ne 'http://127.0.0.1:18010/api' -or
        $env:AUTH_E2E_BASE_URL -ne 'http://127.0.0.1:15173' -or
        $env:CORS_ORIGINS -ne 'http://127.0.0.1:15173') {
        throw 'Auth E2E URL, API URL, and trusted-origin configuration do not match the isolated ports.'
    }

    Write-Host 'Running the three Auth E2E cases against the disposable PostgreSQL-backed API...'
    Push-Location $frontendRoot
    try {
        $playwrightArgs = @(
            'run', 'test:e2e', '--', '--config', 'playwright.auth-live.config.ts',
            '--reporter=list,json', '--output', (Join-Path $runRoot 'playwright-output')
        )
        & $npmCommand.Source @playwrightArgs
        $playwrightExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($playwrightExitCode -ne 0) { throw "Playwright exited with code $playwrightExitCode." }
    if (-not (Test-Path -LiteralPath $playwrightReport -PathType Leaf)) {
        throw 'Playwright did not produce its JSON report; refusing to claim a pass.'
    }

    $report = Get-Content -LiteralPath $playwrightReport -Raw | ConvertFrom-Json
    $stats = $report.stats
    if ($null -eq $stats -or $stats.expected -ne 3 -or $stats.skipped -ne 0 -or
        $stats.unexpected -ne 0 -or $stats.flaky -ne 0) {
        $expected = if ($null -ne $stats) { $stats.expected } else { 'unknown' }
        $skipped = if ($null -ne $stats) { $stats.skipped } else { 'unknown' }
        $unexpected = if ($null -ne $stats) { $stats.unexpected } else { 'unknown' }
        $flaky = if ($null -ne $stats) { $stats.flaky } else { 'unknown' }
        throw "Auth E2E did not meet the pass gate (expected=$expected, skipped=$skipped, unexpected=$unexpected, flaky=$flaky)."
    }

    Write-Host 'AUTH E2E PASS: 3 passed; 0 skipped; 0 unexpected; 0 flaky.'
    $completed = $true
}
catch {
    Write-Error $_
    throw
}
finally {
    Stop-OwnedProcess $frontendProcess 'frontend'
    Stop-OwnedProcess $apiProcess 'API'

    if ($containerCreated) {
        $null = & $dockerCommand.Source stop --time 5 $containerName 2>$null
        if ($LASTEXITCODE -ne 0) {
            # The name is unique to this invocation; this fallback cannot target
            # any of the user's existing organizationai containers.
            $null = & $dockerCommand.Source rm --force $containerName 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Could not remove this run's disposable container $containerName. Existing containers and volumes were not targeted."
            }
        }
    }

    if ($completed) {
        $artifactFiles = @(
            [pscustomobject]@{ Name = 'auth-e2e-report.json'; Source = $playwrightReport },
            [pscustomobject]@{ Name = 'api.log'; Source = $apiLog },
            [pscustomobject]@{ Name = 'api-error.log'; Source = $apiErrorLog },
            [pscustomobject]@{ Name = 'frontend.log'; Source = $frontendLog },
            [pscustomobject]@{ Name = 'frontend-error.log'; Source = $frontendErrorLog }
        )
        $availableArtifacts = @($artifactFiles | Where-Object {
            $null -ne $_.Source -and (Test-Path -LiteralPath $_.Source -PathType Leaf)
        })
        if ($availableArtifacts.Count -gt 0) {
            $artifactArchiveRoot = Join-Path $repoRoot "docs\integration\evidence\auth-postgres-e2e\$runId"
            try {
                New-Item -ItemType Directory -Path $artifactArchiveRoot -Force | Out-Null
                foreach ($artifact in $availableArtifacts) {
                    $contents = [IO.File]::ReadAllText($artifact.Source)
                    $contents = Redact-ArtifactText $contents
                    $destination = Join-Path $artifactArchiveRoot $artifact.Name
                    [IO.File]::WriteAllText($destination, $contents, [Text.UTF8Encoding]::new($false))
                }
                $artifactArchiveSucceeded = $true
                Write-Host "Secret-redacted Auth E2E JSON/log artifacts saved under: $artifactArchiveRoot"
            }
            catch {
                Write-Warning "Could not archive redacted Auth E2E artifacts; retaining the run temp folder. $($_.Exception.Message)"
            }
        }
        else {
            Write-Warning 'No Auth E2E JSON/log artifacts were available to archive; retaining the run temp folder.'
        }
    }

    foreach ($name in $savedEnvironmentNames) {
        $saved = $savedEnvironment[$name]
        if ($saved.Exists) {
            [Environment]::SetEnvironmentVariable($name, $saved.Value, [EnvironmentVariableTarget]::Process)
        }
        else {
            [Environment]::SetEnvironmentVariable($name, $null, [EnvironmentVariableTarget]::Process)
        }
    }

    if ($completed -and $artifactArchiveSucceeded) {
        Remove-Item -LiteralPath $runRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    elseif (Test-Path -LiteralPath $runRoot) {
        Write-Host "Run-specific diagnostic files retained at: $runRoot"
    }
}
