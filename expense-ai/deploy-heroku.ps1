[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[a-z][a-z0-9-]{2,29}$")]
    [string]$AppName,

    [string]$PostgresPlan = "essential-0",

    [string]$Stack = "heroku-26"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Heroku {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & heroku @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "Heroku command failed: heroku $($Arguments -join ' ')"
    }
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & git @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($Arguments -join ' ')"
    }
}

Write-Host "Validating deployment prerequisites..." -ForegroundColor Cyan

foreach ($command in @("heroku", "git")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command '$command' was not found in PATH."
    }
}

foreach ($file in @("Procfile", "requirements.txt", ".python-version")) {
    if (-not (Test-Path $file -PathType Leaf)) {
        throw "Run this script from the repository root. Missing file: $file"
    }
}

& git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
    throw "The current directory is not a Git repository."
}

$uncommittedChanges = & git status --porcelain
if ($uncommittedChanges) {
    throw "Commit or stash local changes before deploying. Heroku deploys committed Git content."
}

if ([string]::IsNullOrWhiteSpace($env:OPENROUTER_API_KEY)) {
    throw "Set OPENROUTER_API_KEY in the current PowerShell session before running this script."
}

if ([string]::IsNullOrWhiteSpace($env:LANGSMITH_API_KEY)) {
    throw "Set LANGSMITH_API_KEY in the current PowerShell session before running this script."
}

& heroku auth:whoami *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Heroku authentication is required. Run 'heroku login' and retry."
}

Write-Host "Creating or selecting Heroku app '$AppName'..." -ForegroundColor Cyan

& heroku apps:info -a $AppName *> $null
if ($LASTEXITCODE -eq 0) {
    Invoke-Heroku -Arguments @("git:remote", "-a", $AppName)
}
else {
    Invoke-Heroku -Arguments @(
        "create",
        $AppName,
        "--stack",
        $Stack
    )
}

Write-Host "Provisioning PostgreSQL with the nested configuration alias..." -ForegroundColor Cyan

$nestedDatabaseUrl = & heroku config:get DATA__DATABASE_URL -a $AppName 2>$null
$nestedDatabaseUrl = ($nestedDatabaseUrl -join "").Trim()

if ([string]::IsNullOrWhiteSpace($nestedDatabaseUrl)) {
    $defaultDatabaseUrl = & heroku config:get DATABASE_URL -a $AppName 2>$null
    $defaultDatabaseUrl = ($defaultDatabaseUrl -join "").Trim()

    if (-not [string]::IsNullOrWhiteSpace($defaultDatabaseUrl)) {
        throw @"
The app already has a default DATABASE_URL but no DATA__DATABASE_URL.
This project intentionally does not support the flat DATABASE_URL variable.
To avoid provisioning and charging for a second database, attach the existing
database using the DATA__DATABASE alias, or deploy to a fresh Heroku app.
"@
    }

    # Heroku appends _URL to the attachment alias. The DATA__DATABASE alias
    # therefore creates and maintains DATA__DATABASE_URL automatically.
    Invoke-Heroku -Arguments @(
        "addons:create",
        "heroku-postgresql:$PostgresPlan",
        "--as",
        "DATA__DATABASE",
        "-a",
        $AppName
    )

    Invoke-Heroku -Arguments @(
        "pg:wait",
        "DATA__DATABASE_URL",
        "-a",
        $AppName
    )
}
else {
    Write-Host "DATA__DATABASE_URL already exists; reusing its PostgreSQL add-on."
}

Write-Host "Setting application configuration..." -ForegroundColor Cyan

Invoke-Heroku -Arguments @(
    "config:set",
    "AGENTIC_EXPENSE=true",
    "DATA__DATABASE_SSLMODE=require",
    "RUNTIME_TIMEOUT_SECONDS=10",
    "RUNTIME_MAX_RETRIES=1",
    "RAG_PERSIST_DIRECTORY=/tmp/chroma",
    "OTEL_CONSOLE_TRACE_ENABLED=true",
    "OBSERVABILITY__TRACING_ENABLED=true",
    "OBSERVABILITY__METRICS_ENABLED=true",
    "OBSERVABILITY__CONSOLE_METRIC_EXPORTER_ENABLED=true",
    "LANGSMITH_TRACING=true",
    "LANGSMITH_PROJECT=expense-ai-heroku-demo",
    "CONFIG_DEBUG=false",
    "OPENROUTER_API_KEY=$env:OPENROUTER_API_KEY",
    "LANGSMITH_API_KEY=$env:LANGSMITH_API_KEY",
    "-a",
    $AppName
)

# Remove obsolete configuration left by earlier deployment attempts.
$obsoleteSslMode = & heroku config:get DATABASE_SSLMODE -a $AppName 2>$null
if (-not [string]::IsNullOrWhiteSpace(($obsoleteSslMode -join "").Trim())) {
    Invoke-Heroku -Arguments @(
        "config:unset",
        "DATABASE_SSLMODE",
        "-a",
        $AppName
    )
}

Write-Host "Deploying the current committed revision..." -ForegroundColor Cyan
Invoke-Git -Arguments @("push", "heroku", "HEAD:main")

Write-Host "Starting one web dyno..." -ForegroundColor Cyan
Invoke-Heroku -Arguments @(
    "ps:scale",
    "web=1",
    "-a",
    $AppName
)

Write-Host "Verifying PostgreSQL attachment..." -ForegroundColor Cyan
Invoke-Heroku -Arguments @(
    "pg:info",
    "DATA__DATABASE_URL",
    "-a",
    $AppName
)

$appInfoJson = & heroku apps:info -a $AppName --json
if ($LASTEXITCODE -ne 0) {
    throw "Unable to resolve the deployed application URL."
}

$appInfo = $appInfoJson | ConvertFrom-Json
$baseUrl = $appInfo.web_url.TrimEnd("/")
$healthUrl = "$baseUrl/health"
$healthResponse = $null

Write-Host "Waiting for health check: $healthUrl" -ForegroundColor Cyan

for ($attempt = 1; $attempt -le 6; $attempt++) {
    try {
        $healthRequest = @{
            Uri = $healthUrl
            Method = "Get"
            TimeoutSec = 20
        }

        $healthResponse = Invoke-RestMethod @healthRequest
        break
    }
    catch {
        if ($attempt -eq 6) {
            throw "Deployment completed, but the health check failed: $($_.Exception.Message)"
        }

        Start-Sleep -Seconds 5
    }
}

if ($healthResponse.status -ne "UP") {
    throw "Unexpected health response: $($healthResponse | ConvertTo-Json -Compress)"
}

Write-Host "Deployment succeeded." -ForegroundColor Green
Write-Host "Application: $baseUrl"
Write-Host "API docs:    $baseUrl/docs"
Write-Host "Health:      $healthUrl"
Write-Host "Logs:        heroku logs --tail -a $AppName"