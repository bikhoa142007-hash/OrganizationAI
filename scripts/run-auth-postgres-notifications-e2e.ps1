[CmdletBinding()]
param(
    [string] $ExpectedBranch = 'codex/scope1-phase1-judge-continuation-20261011',
    [switch] $SkipOtherCheckoutVerification
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$expectedBranch = $ExpectedBranch
$oldCheckout = 'C:\Users\Khoa Bi\VS Studio\repos\OrganizationAI'
$backendImage = 'organizationai-backend:latest'
$postgresImage = 'postgres:16'
$docker = (Get-Command docker.exe -ErrorAction Stop).Source
$node = (Get-Command node.exe -ErrorAction Stop).Source
$frontendRoot = Join-Path $repoRoot 'frontend'
$viteCli = Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'
$playwrightCli = Join-Path $frontendRoot 'node_modules\@playwright\test\cli.js'
$runnerFile = Join-Path $PSScriptRoot 'run-auth-postgres-notifications-e2e.ps1'
$helperFile = Join-Path $PSScriptRoot 'verify_auth_postgres_notifications.py'
$runId = [guid]::NewGuid().ToString('N')
$runRoot = Join-Path ([IO.Path]::GetTempPath()) "organizationai-notification-postgres-$runId"
$artifactRoot = Join-Path $repoRoot "docs\integration\evidence\auth-postgres-notifications\$runId"
$networkName = "oa-notify-$runId"
$postgresContainer = "oa-notify-pg-$runId"
$apiContainer = "oa-notify-api-$runId"
$databaseUser = 'oa_test'
$emptyDatabase = "organizationai_test_empty_$runId"
$legacyDatabase = "organizationai_test_legacy_$runId"
$databasePassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$seedPassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$jwtSecret = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$artifactSecrets = @($databasePassword, $seedPassword, $jwtSecret)
$ownedNetworkCreated = $false
$ownedPostgresCreated = $false
$ownedApiCreated = $false
$frontendProcess = $null
$apiPortReservation = $null
$frontendPortReservation = $null
$apiPort = $null
$frontendPort = $null
$portAllocationMutex = [Threading.Mutex]::new($false, 'OrganizationAI.NotificationVerification.RenderPorts')
$portAllocationMutexHeld = $false
$status = 'RUNNING'
$errorMessage = $null
$evidence = $null
$migrationHead = $null
$emptyMigration = $null
$legacySeed = $null
$legacyUpgrade = $null
$postgresTestOutput = ''
$browserStats = $null
$provider = 'MOCK_VLM deterministic fixture; no live inference'
$beforeContainerIds = @()
$containerSnapshotAvailable = $false
$oldCheckoutBefore = [ordered]@{ branch = $null; head = $null; status = $null }
$oldCheckoutAfter = $null
$branch = $null
$head = $null
$oldCheckoutUnchanged = $false
$pythonRuntime = $null
$imageId = @()
$postgresImageId = @()
$afterContainerIds = @()
$startedAtUtc = [DateTimeOffset]::UtcNow.ToString('o')
$postgresLogPath = $null
$workingTreeBefore = @()
$fingerprintFiles = @(
    'alembic/versions/20261011_11_in_app_notifications.py',
    'scripts/verify_auth_postgres_notifications.py',
    'scripts/run-auth-postgres-notifications-e2e.ps1',
    'scripts/run-auth-postgres-e2e.ps1',
    'src/backend/application/auth_workflow.py',
    'src/backend/db/models/auth_workflow.py',
    'src/backend/api/auth_workflow.py',
    'src/backend/api/auth_workflow_schemas.py',
    'tests/integration/test_auth_workflow_postgres_notifications.py',
    'frontend/e2e/auth-live.spec.ts',
    'frontend/src/pages/AuthenticatedNotificationsPage.tsx',
    'frontend/src/services/authWorkflow.ts',
    'frontend/src/types/authWorkflow.ts'
)

$savedEnvironmentNames = @(
    'APP_ENV', 'AUTH_ALLOW_SQLITE_MIGRATION_TESTS', 'AUTH_COOKIE_SECURE',
    'AUTH_COOKIE_SAMESITE', 'AUTH_E2E_BASE_URL', 'AUTH_E2E_CHECKER_USERNAME',
    'AUTH_E2E_MAKER_USERNAME', 'AUTH_REMEMBER_TOKEN_DAYS', 'AUTH_SEED_ENABLED',
    'AUTH_SEED_PASSWORD', 'AUTH_WORKFLOW_AI_PROVIDER', 'AUTH_WORKFLOW_MOCK_SCENARIO',
    'CORS_ORIGINS', 'DATABASE_URL', 'DEMO_DATABASE', 'DEMO_MOCK_MODE', 'JWT_SECRET',
    'JWT_ACCESS_TOKEN_MINUTES', 'NOTIFICATION_VERIFICATION_RUN_ID',
    'POSTGRES_TEST_DATABASE', 'POSTGRES_TEST_USER', 'POSTGRES_TEST_RUN_ID',
    'PLAYWRIGHT_JSON_OUTPUT_FILE', 'VITE_API_BASE_URL', 'VITE_DEMO_ENABLED'
)
$processEnvironment = [Environment]::GetEnvironmentVariables([EnvironmentVariableTarget]::Process)
$savedEnvironment = @{}
foreach ($name in $savedEnvironmentNames) {
    $savedEnvironment[$name] = [pscustomobject]@{
        Exists = $processEnvironment.Contains($name)
        Value = [Environment]::GetEnvironmentVariable($name, [EnvironmentVariableTarget]::Process)
    }
}

function Get-GitText([string] $Path, [string[]] $Arguments) {
    $result = & git -C $Path @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "git $($Arguments -join ' ') failed for ${Path}: $($result -join "`n")" }
    return ($result -join "`n").Trim()
}

function Set-RunEnvironment([hashtable] $Values) {
    foreach ($entry in $Values.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable([string]$entry.Key, [string]$entry.Value, [EnvironmentVariableTarget]::Process)
    }
}

function Set-TestPostgresTarget([string] $Database, [string] $Url) {
    Set-RunEnvironment @{
        DATABASE_URL = $Url
        POSTGRES_TEST_DATABASE = $Database
        POSTGRES_TEST_USER = $databaseUser
        POSTGRES_TEST_RUN_ID = $runId
    }
    $null = Invoke-BackendPython @('scripts/verify_postgres_test_target.py')
}

function Redact-Text([string] $Text) {
    foreach ($secret in $artifactSecrets) {
        if (-not [string]::IsNullOrEmpty($secret)) { $Text = $Text.Replace($secret, '[REDACTED]') }
    }
    $Text = [regex]::Replace($Text, '(?i)(postgres(?:ql)?(?:\+\w+)?://)[^\s"''<>]+', '$1[REDACTED]')
    $Text = [regex]::Replace(
        $Text,
        '(?i)("?[\w.-]*(?:password|passwd|secret|token|authorization|cookie|api[_-]?key|database[_-]?url)[\w.-]*"?\s*[:=]\s*)("[^"]*"|(?:(?:Bearer|Basic)\s+)?[^\s,;]+)',
        '$1"[REDACTED]"'
    )
    $Text = [regex]::Replace($Text, '(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer [REDACTED]')
    return $Text
}

function Invoke-BackendPython([string[]] $PythonArguments, [switch] $AllowFailure) {
    $dockerArguments = @(
        'run', '--rm', '--pull=never', '--network', $networkName,
        '--label', "com.organizationai.notification-verification.run-id=$runId",
        '--volume', "${repoRoot}:/app", '--workdir', '/app'
    )
    foreach ($name in @(
        'APP_ENV', 'AUTH_ALLOW_SQLITE_MIGRATION_TESTS', 'AUTH_COOKIE_SECURE',
        'AUTH_COOKIE_SAMESITE', 'AUTH_E2E_BASE_URL', 'AUTH_E2E_CHECKER_USERNAME',
        'AUTH_E2E_MAKER_USERNAME', 'AUTH_REMEMBER_TOKEN_DAYS', 'AUTH_SEED_ENABLED',
        'AUTH_SEED_PASSWORD', 'AUTH_WORKFLOW_AI_PROVIDER', 'AUTH_WORKFLOW_MOCK_SCENARIO',
        'CORS_ORIGINS', 'DATABASE_URL', 'DEMO_DATABASE', 'DEMO_MOCK_MODE', 'JWT_SECRET',
        'JWT_ACCESS_TOKEN_MINUTES', 'NOTIFICATION_VERIFICATION_RUN_ID', 'POSTGRES_TEST_DATABASE', 'POSTGRES_TEST_USER', 'POSTGRES_TEST_RUN_ID'
    )) {
        if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, [EnvironmentVariableTarget]::Process))) {
            $dockerArguments += @('--env', $name)
        }
    }
    $dockerArguments += @($backendImage, 'python')
    $dockerArguments += $PythonArguments
    $savedErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = @(& $docker @dockerArguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedErrorActionPreference }
    $text = $output -join "`n"
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "Backend container command failed ($exitCode): $($PythonArguments -join ' ')`n$(Redact-Text $text)"
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = $text }
}

function Invoke-BackendJson([string[]] $PythonArguments) {
    $result = Invoke-BackendPython $PythonArguments
    try { return ($result.Output.Trim().Split("`n")[-1] | ConvertFrom-Json) }
    catch { throw "Backend helper did not return JSON: $(Redact-Text $result.Output)" }
}

function Reserve-FreeLoopbackPort([int[]] $ExcludedPorts = @()) {
    for ($attempt = 0; $attempt -lt 16; $attempt++) {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
        try {
            $listener.Start()
            $port = [int]$listener.LocalEndpoint.Port
            if ($port -notin $ExcludedPorts) { return $listener }
        } catch {
            $listener.Stop()
            throw
        }
        $listener.Stop()
    }
    throw 'Could not reserve distinct loopback ports for this run.'
}

function Get-UnrelatedContainerIds {
    $containerIds = @(& $docker ps -aq --no-trunc)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect Docker container ownership.' }
    $unrelated = @()
    foreach ($containerId in $containerIds) {
        if ([string]::IsNullOrWhiteSpace($containerId)) { continue }
        $runIdLabel = @(& $docker inspect --format '{{ index .Config.Labels "com.organizationai.notification-verification.run-id" }}' $containerId 2>$null)
        if ($LASTEXITCODE -ne 0) { throw 'Could not inspect a Docker container ownership label.' }
        $labelValue = ($runIdLabel -join '').Trim()
        if ([string]::IsNullOrWhiteSpace($labelValue) -or $labelValue -eq '<no value>') { $unrelated += $containerId }
    }
    return $unrelated
}

function Stop-ProcessOwned($Process, [string] $Label) {
    if ($null -eq $Process) { return }
    try {
        $Process.Refresh()
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction Stop
            [void]$Process.WaitForExit(10000)
        }
    }
    catch { Write-Warning "Could not stop this run's $Label process: $($_.Exception.Message)" }
}

function Save-RedactedFile([string] $Source, [string] $Destination) {
    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        $contents = Redact-Text ([IO.File]::ReadAllText($Source))
        [IO.File]::WriteAllText($Destination, $contents, [Text.UTF8Encoding]::new($false))
    }
}

try {
    [Environment]::SetEnvironmentVariable('DATABASE_URL', $null, [EnvironmentVariableTarget]::Process)
    [Environment]::SetEnvironmentVariable('DEMO_DATABASE', $null, [EnvironmentVariableTarget]::Process)
    [Environment]::SetEnvironmentVariable('POSTGRES_TEST_DATABASE', $null, [EnvironmentVariableTarget]::Process)
    [Environment]::SetEnvironmentVariable('POSTGRES_TEST_USER', $null, [EnvironmentVariableTarget]::Process)
    [Environment]::SetEnvironmentVariable('POSTGRES_TEST_RUN_ID', $null, [EnvironmentVariableTarget]::Process)
    [Environment]::SetEnvironmentVariable('CORS_ORIGINS', $null, [EnvironmentVariableTarget]::Process)
    [Environment]::SetEnvironmentVariable('AUTH_E2E_BASE_URL', $null, [EnvironmentVariableTarget]::Process)
    [Environment]::SetEnvironmentVariable('VITE_API_BASE_URL', $null, [EnvironmentVariableTarget]::Process)
    $resolvedRoot = (Get-GitText $repoRoot @('rev-parse', '--show-toplevel')).Replace('/', '\').TrimEnd('\')
    $normalizedRepoRoot = $repoRoot.TrimEnd('\')
    if (-not [string]::Equals($resolvedRoot, $normalizedRepoRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Runner root mismatch. Resolved repository is $resolvedRoot."
    }
    $branch = Get-GitText $repoRoot @('branch', '--show-current')
    $head = Get-GitText $repoRoot @('rev-parse', 'HEAD')
    if ($branch -ne $expectedBranch) { throw "Expected branch $expectedBranch; found $branch. Runner refuses to use another checkout." }
    $workingTreeBefore = @(Get-GitText $repoRoot @('status', '--porcelain=v1', '--untracked-files=all') -split "`n" | Where-Object { $_ })

    if (-not $SkipOtherCheckoutVerification) {
        if (-not (Test-Path -LiteralPath $oldCheckout -PathType Container)) { throw "Expected preserved checkout is missing: $oldCheckout" }
        $oldCheckoutBefore = [ordered]@{
            branch = Get-GitText $oldCheckout @('branch', '--show-current')
            head = Get-GitText $oldCheckout @('rev-parse', 'HEAD')
            status = Get-GitText $oldCheckout @('status', '--porcelain=v1', '--untracked-files=all')
        }
    }
    if (-not (Test-Path -LiteralPath $viteCli -PathType Leaf) -or -not (Test-Path -LiteralPath $playwrightCli -PathType Leaf)) {
        throw 'Frontend Vite/Playwright dependencies are unavailable in this worktree.'
    }

    $imageId = @(& $docker image inspect $backendImage --format '{{.Id}}' 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $imageId) { throw "The local $backendImage image is required; this runner never pulls images." }
    $postgresImageId = @(& $docker image inspect $postgresImage --format '{{.Id}}' 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $postgresImageId) { throw "The local $postgresImage image is required; this runner never pulls images." }
    $beforeContainerIds = @(Get-UnrelatedContainerIds | Sort-Object -Unique)
    $containerSnapshotAvailable = $true
    New-Item -ItemType Directory -Path $runRoot | Out-Null
    $apiLogPath = Join-Path $runRoot 'api.log'
    $frontendLogPath = Join-Path $runRoot 'frontend.log'
    $browserReportPath = Join-Path $runRoot 'auth-e2e-report.json'
    $postgresLogPath = Join-Path $runRoot 'postgres.log'

    $networkOutput = @(& $docker network create $networkName 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Could not create this run's private Docker network: $(Redact-Text ($networkOutput -join "`n"))" }
    $ownedNetworkCreated = $true

    $backendCheck = Invoke-BackendPython @('-c', 'import sys,pytest,sqlalchemy,fastapi,psycopg; print(sys.executable); print(sys.version.split()[0]); print(pytest.__version__); print(sqlalchemy.__version__); print(fastapi.__version__); print(psycopg.__version__)')
    $pythonValues = @($backendCheck.Output -split "`r?`n" | Where-Object { $_ })
    if ($pythonValues.Count -ne 6) { throw 'Could not resolve the backend Python interpreter and test-library versions.' }
    $pythonRuntime = [ordered]@{
        executable = $pythonValues[0]
        version = $pythonValues[1]
        pytest = $pythonValues[2]
        sqlalchemy = $pythonValues[3]
        fastapi = $pythonValues[4]
        psycopg = $pythonValues[5]
    }
    $headOutput = Invoke-BackendPython @('-m', 'alembic', 'heads')
    $headMatch = [regex]::Matches($headOutput.Output, '(?m)^([0-9A-Za-z_]+) \(head\)$')
    if ($headMatch.Count -ne 1 -or $headMatch[0].Groups[1].Value -ne '20261011_11') {
        throw "Expected exactly migration head 20261011_11 in this worktree; got $($headOutput.Output.Trim())."
    }
    $migrationHead = $headMatch[0].Groups[1].Value

    $environment = @{
        APP_ENV = 'demo'
        AUTH_ALLOW_SQLITE_MIGRATION_TESTS = 'false'
        AUTH_COOKIE_SECURE = 'false'
        AUTH_COOKIE_SAMESITE = 'lax'
        AUTH_E2E_CHECKER_USERNAME = 'checker'
        AUTH_E2E_MAKER_USERNAME = 'maker'
        AUTH_REMEMBER_TOKEN_DAYS = '14'
        AUTH_SEED_ENABLED = 'true'
        AUTH_SEED_PASSWORD = $seedPassword
        AUTH_WORKFLOW_AI_PROVIDER = 'MOCK_VLM'
        AUTH_WORKFLOW_MOCK_SCENARIO = 'review'
        DEMO_DATABASE = '/tmp/organizationai-notification-demo.sqlite3'
        DEMO_MOCK_MODE = 'review'
        JWT_SECRET = $jwtSecret
        JWT_ACCESS_TOKEN_MINUTES = '30'
        NOTIFICATION_VERIFICATION_RUN_ID = $runId
        PLAYWRIGHT_JSON_OUTPUT_FILE = $browserReportPath
        VITE_DEMO_ENABLED = 'true'
    }
    Set-RunEnvironment $environment

    $postgresArgs = @(
        'run', '--pull=never', '--detach', '--rm', '--name', $postgresContainer,
        '--label', "com.organizationai.notification-verification.run-id=$runId",
        '--network', $networkName, '--network-alias', 'postgres',
        '--tmpfs', '/var/lib/postgresql/data:rw,size=1g',
        '--env', "POSTGRES_USER=$databaseUser", '--env', "POSTGRES_PASSWORD=$databasePassword",
        '--env', "POSTGRES_DB=$emptyDatabase", $postgresImage
    )
    $null = @(& $docker @postgresArgs 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'Could not start the runner-owned temporary PostgreSQL 16 container.' }
    $ownedPostgresCreated = $true
    $postgresReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $null = @(& $docker exec $postgresContainer pg_isready -U $databaseUser -d $emptyDatabase 2>$null)
        if ($LASTEXITCODE -eq 0) { $postgresReady = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $postgresReady) { throw 'Temporary PostgreSQL did not become ready within 120 seconds.' }

    $emptyUrl = "postgresql+psycopg://${databaseUser}:${databasePassword}@postgres:5432/${emptyDatabase}"
    Set-TestPostgresTarget $emptyDatabase $emptyUrl
    $null = Invoke-BackendPython @('-m', 'alembic', 'upgrade', 'head')
    $emptyMigration = Invoke-BackendJson @('scripts/verify_auth_postgres_notifications.py', 'verify-empty')

    $createdb = @(& $docker exec $postgresContainer createdb -U $databaseUser $legacyDatabase 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Could not create the runner-owned revision 10 database: $(Redact-Text ($createdb -join "`n"))" }
    $legacyUrl = "postgresql+psycopg://${databaseUser}:${databasePassword}@postgres:5432/${legacyDatabase}"
    Set-TestPostgresTarget $legacyDatabase $legacyUrl
    $null = Invoke-BackendPython @('-m', 'alembic', 'upgrade', '20261010_10')
    $legacySeed = Invoke-BackendJson @('scripts/verify_auth_postgres_notifications.py', 'seed-revision-10')
    if ($legacySeed.status -ne 'PASS' -or $legacySeed.revision -ne '20261010_10') {
        throw 'Synthetic revision 10 data was not seeded at the requested migration revision.'
    }
    $null = Invoke-BackendPython @('-m', 'alembic', 'upgrade', 'head')
    $legacyUpgrade = Invoke-BackendJson @('scripts/verify_auth_postgres_notifications.py', 'verify-revision-11')
    $beforeJson = ConvertTo-Json -InputObject $legacySeed.preserved_state -Depth 60 -Compress
    $afterJson = ConvertTo-Json -InputObject $legacyUpgrade.preserved_state -Depth 60 -Compress
    if ($beforeJson -cne $afterJson) { throw 'Revision 10 synthetic user, role, plan, version, or event data changed after migration.' }
    if ($legacyUpgrade.revision -ne '20261011_11' -or $legacyUpgrade.notifications -ne 0) {
        throw 'Legacy database did not reach the notification head without adding notification rows.'
    }

    Set-TestPostgresTarget $emptyDatabase $emptyUrl
    $seedOutput = Invoke-BackendPython @('-m', 'src.backend.seed_auth')
    $integrationOutput = Invoke-BackendPython @('-m', 'pytest', '-q', '-m', 'postgres')
    $postgresTestOutput = $integrationOutput.Output

    # Serialize port handoff between concurrent copies of this runner. Hold the
    # reservations until each listener is started and ready, then release the lock.
    try { $mutexAcquired = $portAllocationMutex.WaitOne([TimeSpan]::FromMinutes(2)) }
    catch [Threading.AbandonedMutexException] { $mutexAcquired = $true }
    if (-not $mutexAcquired) { throw 'Timed out waiting for the Auth E2E loopback port allocator.' }
    $portAllocationMutexHeld = $true
    $apiPortReservation = Reserve-FreeLoopbackPort
    $apiPort = [int]$apiPortReservation.LocalEndpoint.Port
    $frontendPortReservation = Reserve-FreeLoopbackPort -ExcludedPorts @($apiPort)
    $frontendPort = [int]$frontendPortReservation.LocalEndpoint.Port
    $frontendOrigin = "http://127.0.0.1:$frontendPort"
    $apiOrigin = "http://127.0.0.1:$apiPort"
    $listenerEnvironment = @{
        AUTH_E2E_BASE_URL = $frontendOrigin
        CORS_ORIGINS = $frontendOrigin
        VITE_API_BASE_URL = "$apiOrigin/api"
    }
    Set-RunEnvironment $listenerEnvironment

    $apiArguments = @(
        'run', '--pull=never', '--detach', '--rm', '--name', $apiContainer,
        '--label', "com.organizationai.notification-verification.run-id=$runId",
        '--network', $networkName, '--publish', "127.0.0.1:${apiPort}:8000", '--workdir', '/app',
        '--volume', "${repoRoot}:/app"
    )
    foreach ($name in @(
        'APP_ENV', 'AUTH_ALLOW_SQLITE_MIGRATION_TESTS', 'AUTH_COOKIE_SECURE', 'AUTH_COOKIE_SAMESITE',
        'AUTH_REMEMBER_TOKEN_DAYS', 'AUTH_SEED_ENABLED', 'AUTH_SEED_PASSWORD',
        'AUTH_WORKFLOW_AI_PROVIDER', 'AUTH_WORKFLOW_MOCK_SCENARIO', 'CORS_ORIGINS',
        'DATABASE_URL', 'DEMO_DATABASE', 'DEMO_MOCK_MODE', 'JWT_SECRET', 'JWT_ACCESS_TOKEN_MINUTES'
    )) { $apiArguments += @('--env', $name) }
    $apiArguments += @($backendImage, 'python', '-m', 'uvicorn', 'src.backend.api.app:app', '--host', '0.0.0.0', '--port', '8000')
    $apiPortReservation.Stop()
    $apiPortReservation = $null
    $apiStartOutput = @(& $docker @apiArguments 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Could not start this run's API container: $(Redact-Text ($apiStartOutput -join "`n"))" }
    $ownedApiCreated = $true

    $frontendLog = Join-Path $runRoot 'frontend.log'
    $frontendErrorLog = Join-Path $runRoot 'frontend-error.log'
    $viteArgs = @('"' + $viteCli + '"', '--host', '127.0.0.1', '--port', [string]$frontendPort, '--strictPort')
    $frontendPortReservation.Stop()
    $frontendPortReservation = $null
    $frontendProcess = Start-Process -FilePath $node `
        -ArgumentList $viteArgs -WorkingDirectory $frontendRoot `
        -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErrorLog `
        -PassThru -WindowStyle Hidden

    $apiReady = $false
    $frontendReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $frontendProcess.Refresh()
        if ($frontendProcess.HasExited) { throw 'The temporary Vite frontend exited during startup.' }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$apiPort/api/health/ready" -TimeoutSec 4
            $health = $response.Content | ConvertFrom-Json
            $apiReady = $response.StatusCode -eq 200 -and $health.auth_database -eq 'postgresql'
        } catch { $apiReady = $false }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$frontendPort/" -TimeoutSec 4
            $frontendReady = $response.StatusCode -eq 200
        } catch { $frontendReady = $false }
        if ($apiReady -and $frontendReady) { break }
        Start-Sleep -Seconds 2
    }
    if (-not $apiReady -or -not $frontendReady) { throw 'The runner-owned PostgreSQL API or Vite frontend did not become ready.' }

    $corsPreflight = Invoke-WebRequest -UseBasicParsing -Method Options `
        -Uri "$apiOrigin/api/health/ready" `
        -Headers @{
            Origin = $frontendOrigin
            'Access-Control-Request-Method' = 'GET'
        } -TimeoutSec 8
    $allowedOrigin = $corsPreflight.Headers['Access-Control-Allow-Origin']
    if ($allowedOrigin -cne $frontendOrigin) {
        throw 'Auth E2E CORS preflight did not allow the configured frontend origin and port.'
    }
    if ($listenerEnvironment.AUTH_E2E_BASE_URL -cne $frontendOrigin -or
        $listenerEnvironment.VITE_API_BASE_URL -cne "$apiOrigin/api") {
        throw 'Auth E2E trusted origin or frontend API URL differs from the active listener ports.'
    }
    $processFrontendOrigin = [Environment]::GetEnvironmentVariable('AUTH_E2E_BASE_URL', [EnvironmentVariableTarget]::Process)
    $processApiUrl = [Environment]::GetEnvironmentVariable('VITE_API_BASE_URL', [EnvironmentVariableTarget]::Process)
    if ($processFrontendOrigin -cne $frontendOrigin -or $processApiUrl -cne "$apiOrigin/api") {
        throw 'Auth E2E process URLs differ from the active frontend or API listener ports.'
    }
    $portAllocationMutex.ReleaseMutex()
    $portAllocationMutexHeld = $false

    Push-Location $frontendRoot
    try {
        $playwrightArgs = @(
            $playwrightCli, 'test', '--config', 'playwright.auth-live.config.ts',
            '--reporter=list,json', '--output', (Join-Path $runRoot 'playwright-output')
        )
        $savedErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $playwrightOutput = @(& $node @playwrightArgs 2>&1)
            $playwrightExit = $LASTEXITCODE
        } finally { $ErrorActionPreference = $savedErrorActionPreference }
    }
    finally { Pop-Location }
    [IO.File]::WriteAllText((Join-Path $runRoot 'playwright.log'), ($playwrightOutput -join "`n"), [Text.UTF8Encoding]::new($false))
    if ($playwrightExit -ne 0 -or -not (Test-Path -LiteralPath $browserReportPath -PathType Leaf)) {
        throw "Auth browser E2E failed (exit $playwrightExit) or did not produce its JSON report."
    }
    $browserReport = Get-Content -LiteralPath $browserReportPath -Raw | ConvertFrom-Json
    $browserStats = $browserReport.stats
    $reportText = [IO.File]::ReadAllText($browserReportPath)
    if ($browserStats.expected -ne 3 -or $browserStats.skipped -ne 0 -or $browserStats.unexpected -ne 0 -or $browserStats.flaky -ne 0) {
        throw "Auth browser E2E must pass all 3 cases with no skipped tests; got $($browserStats | ConvertTo-Json -Compress)."
    }
    if (-not $reportText.Contains('live Auth Maker-to-Checker browser workflow preserves a rejected version through resubmission')) {
        throw 'Maker/Checker notification browser workflow is absent from the Playwright report.'
    }

    $status = 'PASS'
}
catch {
    $status = 'FAILED'
    $errorMessage = Redact-Text $_.Exception.Message
}
finally {
    if ($null -ne $apiPortReservation) { $apiPortReservation.Stop() }
    if ($null -ne $frontendPortReservation) { $frontendPortReservation.Stop() }
    if ($portAllocationMutexHeld) {
        $portAllocationMutex.ReleaseMutex()
        $portAllocationMutexHeld = $false
    }
    $portAllocationMutex.Dispose()

    Stop-ProcessOwned $frontendProcess 'Vite frontend'

    if ($ownedApiCreated) {
        $savedErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $apiLog = @(& $docker logs $apiContainer 2>&1)
            [IO.File]::WriteAllText((Join-Path $runRoot 'api.log'), (Redact-Text ($apiLog -join "`n")), [Text.UTF8Encoding]::new($false))
            $null = @(& $docker stop --timeout 5 $apiContainer 2>&1)
            if ($LASTEXITCODE -ne 0) { $null = @(& $docker rm --force $apiContainer 2>&1) }
        } finally { $ErrorActionPreference = $savedErrorActionPreference }
        $ownedApiCreated = $false
    }
    if ($ownedPostgresCreated) {
        $savedErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $postgresLog = @(& $docker logs $postgresContainer 2>&1)
            [IO.File]::WriteAllText($postgresLogPath, (Redact-Text ($postgresLog -join "`n")), [Text.UTF8Encoding]::new($false))
            $null = @(& $docker stop --timeout 5 $postgresContainer 2>&1)
            if ($LASTEXITCODE -ne 0) { $null = @(& $docker rm --force $postgresContainer 2>&1) }
        } finally { $ErrorActionPreference = $savedErrorActionPreference }
        $ownedPostgresCreated = $false
    }
    if ($ownedNetworkCreated) {
        $networkRemoved = $false
        $networkRemovalOutput = ''
        for ($attempt = 0; $attempt -lt 10; $attempt++) {
            $savedErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $networkRemovalOutput = (@(& $docker network rm $networkName 2>&1) -join "`n")
                $networkRemoved = ($LASTEXITCODE -eq 0)
            } catch {
                $networkRemovalOutput = $_.Exception.Message
                $networkRemoved = $false
            } finally { $ErrorActionPreference = $savedErrorActionPreference }
            if ($networkRemoved) { break }

            $attached = @(& $docker ps -aq --filter "network=$networkName")
            foreach ($containerId in $attached) {
                $labelOutput = @(& $docker inspect --format '{{json .Config.Labels}}' $containerId 2>$null)
                $labels = $null
                try { $labels = ($labelOutput -join '' | ConvertFrom-Json) } catch { $labels = $null }
                $runLabel = if ($labels) { $labels.PSObject.Properties['com.organizationai.notification-verification.run-id'].Value } else { $null }
                if ($runLabel -eq $runId) {
                    $savedErrorActionPreference = $ErrorActionPreference
                    $ErrorActionPreference = 'Continue'
                    try {
                        $null = @(& $docker stop --time 5 $containerId 2>&1)
                        if ($LASTEXITCODE -ne 0) { $null = @(& $docker rm --force $containerId 2>&1) }
                    } finally { $ErrorActionPreference = $savedErrorActionPreference }
                }
            }
            Start-Sleep -Seconds 1
        }
        if (-not $networkRemoved) {
            $ownedNetworkCreated = $true
            if ($status -eq 'PASS') {
                $status = 'FAILED'
                $errorMessage = "The runner-owned Docker network could not be removed: $(Redact-Text $networkRemovalOutput)"
            } elseif ($errorMessage) {
                $errorMessage += " Cleanup also could not remove the runner-owned network: $(Redact-Text $networkRemovalOutput)"
            }
        } else {
            $ownedNetworkCreated = $false
        }
    }

    foreach ($name in $savedEnvironmentNames) {
        $saved = $savedEnvironment[$name]
        if ($saved.Exists) {
            [Environment]::SetEnvironmentVariable($name, $saved.Value, [EnvironmentVariableTarget]::Process)
        } else {
            [Environment]::SetEnvironmentVariable($name, $null, [EnvironmentVariableTarget]::Process)
        }
    }

    if (-not $SkipOtherCheckoutVerification) {
        try {
            $oldCheckoutAfter = [ordered]@{
                branch = Get-GitText $oldCheckout @('branch', '--show-current')
                head = Get-GitText $oldCheckout @('rev-parse', 'HEAD')
                status = Get-GitText $oldCheckout @('status', '--porcelain=v1', '--untracked-files=all')
            }
            $oldCheckoutUnchanged = ($oldCheckoutBefore.branch -ceq $oldCheckoutAfter.branch -and
                $oldCheckoutBefore.head -ceq $oldCheckoutAfter.head -and $oldCheckoutBefore.status -ceq $oldCheckoutAfter.status)
        } catch {
            $oldCheckoutUnchanged = $false
            if ($status -eq 'PASS') { $status = 'FAILED'; $errorMessage = "Could not reverify the old checkout: $($_.Exception.Message)" }
        }
    }

    $missingContainerIds = @()
    if ($containerSnapshotAvailable) {
        try {
            $afterContainerIds = @(Get-UnrelatedContainerIds | Sort-Object -Unique)
            $missingContainerIds = @($beforeContainerIds | Where-Object { $_ -and $_ -notin $afterContainerIds })
            if ($missingContainerIds.Count -gt 0 -and $status -eq 'PASS') {
                $status = 'FAILED'
                $errorMessage = 'A container that existed before the runner is missing after cleanup.'
            }
        } catch {
            if ($status -eq 'PASS') {
                $status = 'FAILED'
                $errorMessage = 'Could not verify unrelated Docker containers after cleanup.'
            }
        }
    }

    $fileHashes = [ordered]@{}
    foreach ($relativePath in $fingerprintFiles) {
        $absolutePath = Join-Path $repoRoot ($relativePath -replace '/', '\')
        if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
            $fileHashes[$relativePath] = 'MISSING'
        } else {
            $fileHashes[$relativePath] = (Get-FileHash -LiteralPath $absolutePath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    $fingerprintMaterial = ($fileHashes.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "`n"
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $fingerprintBytes = $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($fingerprintMaterial))
        $fingerprintDigest = [BitConverter]::ToString($fingerprintBytes).Replace('-', '').ToLowerInvariant()
    } finally { $sha256.Dispose() }

    $evidence = [ordered]@{
        schema_version = 1
        run_id = $runId
        started_at_utc = $startedAtUtc
        completed_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
        status = $status
        source = 'Runner-owned Docker network, PostgreSQL 16 tmpfs databases, no live application database/container.'
        repository = [ordered]@{
            worktree = $repoRoot
            branch = $branch
            head = $head
            migration_head = $migrationHead
            working_tree_dirty_before_run = ($workingTreeBefore.Count -gt 0)
            changed_paths_before_run = $workingTreeBefore
            other_checkout_verification = if ($SkipOtherCheckoutVerification) { 'SKIPPED_BY_WORKTREE_ISOLATION' } else { 'VERIFIED' }
            old_checkout = if ($SkipOtherCheckoutVerification) { $null } else { $oldCheckout }
            old_checkout_branch_before = $oldCheckoutBefore.branch
            old_checkout_head_before = $oldCheckoutBefore.head
            old_checkout_status_unchanged = $oldCheckoutUnchanged
        }
        code_fingerprint = [ordered]@{
            algorithm = 'SHA-256'
            digest = $fingerprintDigest
            files = $fileHashes
        }
        runtime = [ordered]@{
            auth_e2e = [ordered]@{
                frontend_url = if ($frontendPort) { "http://127.0.0.1:$frontendPort" } else { $null }
                api_url = if ($apiPort) { "http://127.0.0.1:$apiPort/api" } else { $null }
                cors_allowed_origin = if ($frontendPort) { "http://127.0.0.1:$frontendPort" } else { $null }
                trusted_origin = if ($frontendPort) { "http://127.0.0.1:$frontendPort" } else { $null }
            }
            docker_backend_image = $backendImage
            backend_image_id = ($imageId -join '').Trim()
            python = $pythonRuntime
            postgres_image = $postgresImage
            postgres_image_id = ($postgresImageId -join '').Trim()
            browser_provider = $provider
        }
        migrations = [ordered]@{
            empty_database = $emptyMigration
            revision_20261010_10_seed = $legacySeed
            revision_20261010_10_upgrade = $legacyUpgrade
            legacy_data_unchanged = ($null -ne $legacySeed -and $null -ne $legacyUpgrade -and
                (ConvertTo-Json -InputObject $legacySeed.preserved_state -Depth 60 -Compress) -ceq
                (ConvertTo-Json -InputObject $legacyUpgrade.preserved_state -Depth 60 -Compress))
        }
        postgres_notification_test_output = $postgresTestOutput
        browser_e2e = [ordered]@{
            expected = if ($browserStats) { $browserStats.expected } else { $null }
            skipped = if ($browserStats) { $browserStats.skipped } else { $null }
            unexpected = if ($browserStats) { $browserStats.unexpected } else { $null }
            flaky = if ($browserStats) { $browserStats.flaky } else { $null }
            notification_flow = 'Assigned Checker opens submission notice, marks it read, opens the plan; Maker opens rejection notice, marks it read, opens the same plan.'
            provider = $provider
        }
        cleanup = [ordered]@{
            owned_network_removed = -not $ownedNetworkCreated
            owned_postgres_container_stopped = -not $ownedPostgresCreated
            owned_api_container_stopped = -not $ownedApiCreated
            preexisting_containers_preserved = ($missingContainerIds.Count -eq 0)
            missing_preexisting_container_ids = $missingContainerIds
            temporary_files_archived_or_retained = $true
        }
        error = $errorMessage
        artifacts = [ordered]@{}
    }

    if ($runRoot -and (Test-Path -LiteralPath $runRoot)) {
        try {
            New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
            foreach ($name in @('auth-e2e-report.json', 'playwright.log', 'api.log', 'frontend.log', 'frontend-error.log', 'postgres.log')) {
                $source = Join-Path $runRoot $name
                if (Test-Path -LiteralPath $source -PathType Leaf) {
                    Save-RedactedFile $source (Join-Path $artifactRoot $name)
                }
            }
            if ($evidence) {
                $evidence.artifacts = [ordered]@{
                    directory = $artifactRoot
                    files = @(Get-ChildItem -LiteralPath $artifactRoot -File | Select-Object -ExpandProperty Name)
                }
                [IO.File]::WriteAllText((Join-Path $artifactRoot 'notification-postgres-evidence.json'),
                    (ConvertTo-Json -InputObject $evidence -Depth 80) + "`n", [Text.UTF8Encoding]::new($false))
            }
            if ($status -eq 'PASS') { Remove-Item -LiteralPath $runRoot -Recurse -Force }
            else { Write-Host "Run-specific diagnostics retained at: $runRoot" }
        } catch {
            Write-Warning "Could not archive all redacted runner artifacts: $($_.Exception.Message)"
            if ($status -eq 'PASS') { $status = 'FAILED'; $evidence.status = $status; $evidence.error = 'Evidence archive failed.' }
        }
    }

    if ($evidence) {
        $evidence.status = $status
        if (-not (Test-Path -LiteralPath $artifactRoot)) { New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null }
        [IO.File]::WriteAllText((Join-Path $artifactRoot 'notification-postgres-evidence.json'),
            (ConvertTo-Json -InputObject $evidence -Depth 80) + "`n", [Text.UTF8Encoding]::new($false))
        Write-Host "Evidence: $(Join-Path $artifactRoot 'notification-postgres-evidence.json')"
    }
}

if ($status -ne 'PASS') {
    if ($errorMessage) { Write-Error $errorMessage }
    exit 2
}
Write-Host 'PostgreSQL notification migration checks, API checks, and Auth browser E2E passed with zero skipped tests.'
exit 0
