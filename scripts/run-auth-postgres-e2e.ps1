[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$notificationRunner = Join-Path $PSScriptRoot 'run-auth-postgres-notifications-e2e.ps1'
if (-not (Test-Path -LiteralPath $notificationRunner -PathType Leaf)) {
    throw "Notification PostgreSQL runner is missing: $notificationRunner"
}

# Keep the established Auth E2E entry point while delegating to the isolated,
# notification-aware PostgreSQL runner. It provisions only its own temporary DB.
$argumentList = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', ('"' + $notificationRunner + '"')
)
$child = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') `
    -ArgumentList $argumentList -PassThru -Wait -NoNewWindow
exit $child.ExitCode