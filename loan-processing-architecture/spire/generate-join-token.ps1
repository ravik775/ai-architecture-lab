
<#
.SYNOPSIS
  Generates a SPIRE agent join token and writes it into .env.sb as JOIN_TOKEN.

.DESCRIPTION
  - Verifies docker CLI is available
  - Verifies the spire-server service/container is running
  - Waits (with retries) for the spire-server admin API socket to respond
  - Generates a join token for the given SPIFFE ID
  - Parses the token out of the CLI output
  - Writes/updates JOIN_TOKEN=<value> in the target env file (creates it if missing)

.NOTES
  Join tokens are single-use and expire quickly (default ~600s).
  Run this immediately before starting spire-agent, not far in advance.
#>

[CmdletBinding()]
param(
    [string]$SpiffeId    = "spiffe://example.org/agent",
    [string]$SocketPath  = "/tmp/spire-server/private/api.sock",
    [string]$EnvFile     = ".env.sb",
    [string]$ServiceName = "spire-server",
    [int]$MaxRetries     = 15,
    [int]$RetryDelaySec  = 2
)

$ErrorActionPreference = "Stop"

function Write-Step  { param($msg) Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-WarnX { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err   { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Fail {
    param([string]$Message, [int]$Code = 1)
    Write-Err $Message
    exit $Code
}

Write-Host "============================================"
Write-Host " SPIRE Join Token Generator"
Write-Host "============================================"

# ---------------------------------------------------------------------------
# 1. docker CLI available?
# ---------------------------------------------------------------------------
Write-Step "Checking docker CLI"
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Fail "docker CLI not found in PATH. Install/start Docker Desktop first."
}
Write-Ok "docker CLI found: $($dockerCmd.Source)"

# ---------------------------------------------------------------------------
# 2. spire-server container exists?
# ---------------------------------------------------------------------------
Write-Step "Checking $ServiceName container"
$containerId = (& docker compose ps -q $ServiceName 2>$null)
if ([string]::IsNullOrWhiteSpace($containerId)) {
    Fail "No container found for service '$ServiceName'. Run: docker compose up -d $ServiceName"
}

$isRunning = (& docker inspect -f "{{.State.Running}}" $containerId 2>$null)
if ($LASTEXITCODE -ne 0) {
    Fail "Could not inspect container '$containerId'. Is Docker daemon healthy?"
}
if ($isRunning.Trim() -ne "true") {
    Fail "'$ServiceName' container exists but is not running (state: $isRunning). Run: docker compose up -d $ServiceName"
}
Write-Ok "$ServiceName is running (container: $containerId)"

# ---------------------------------------------------------------------------
# 3. Wait for admin API socket to respond
# ---------------------------------------------------------------------------
Write-Step "Waiting for $ServiceName admin API to become ready"
$ready = $false
for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
    & docker compose exec $ServiceName /opt/spire/bin/spire-server entry show -socketPath $SocketPath *> $null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        Write-Ok "Admin API responded on attempt $attempt/$MaxRetries"
        break
    }
    Write-Host "  attempt $attempt/$MaxRetries - not ready yet, retrying in ${RetryDelaySec}s..."
    Start-Sleep -Seconds $RetryDelaySec
}
if (-not $ready) {
    Fail "$ServiceName admin API did not respond after $MaxRetries attempts. Check: docker compose logs $ServiceName"
}

# ---------------------------------------------------------------------------
# 4. Generate the token
# ---------------------------------------------------------------------------
Write-Step "Generating join token for SPIFFE ID: $SpiffeId"
$tokenOutput = & docker compose exec $ServiceName `
    /opt/spire/bin/spire-server token generate `
    -spiffeID $SpiffeId `
    -socketPath $SocketPath 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Err "Token generation command failed. Output was:"
    Write-Host ($tokenOutput -join "`n")
    exit 1
}

# ---------------------------------------------------------------------------
# 5. Parse the token out of the CLI output
# ---------------------------------------------------------------------------
$tokenLine = ($tokenOutput -join "`n") -split "`n" | Where-Object { $_ -match "^\s*Token:\s*(\S+)" } | Select-Object -First 1
if (-not $tokenLine) {
    Write-Err "Could not find a 'Token:' line in spire-server output. Full output was:"
    Write-Host ($tokenOutput -join "`n")
    exit 1
}

$match = [regex]::Match($tokenLine, "Token:\s*(\S+)")
if (-not $match.Success -or [string]::IsNullOrWhiteSpace($match.Groups[1].Value)) {
    Fail "Found a Token line but failed to parse the value from it: '$tokenLine'"
}
$joinToken = $match.Groups[1].Value
Write-Ok "Token generated: $joinToken"

# ---------------------------------------------------------------------------
# 6. Write/update JOIN_TOKEN in the env file
# ---------------------------------------------------------------------------
Write-Step "Updating $EnvFile"
try {
    if (-not (Test-Path $EnvFile)) {
        Write-WarnX "$EnvFile not found - creating a new one."
        Set-Content -Path $EnvFile -Value "JOIN_TOKEN=$joinToken" -Encoding ascii -NoNewline:$false
        Write-Ok "Created $EnvFile with JOIN_TOKEN."
    }
    else {
        $lines = Get-Content -Path $EnvFile -ErrorAction Stop
        $found = $false
        $newLines = foreach ($line in $lines) {
            if ($line -match "^\s*JOIN_TOKEN\s*=") {
                $found = $true
                "JOIN_TOKEN=$joinToken"
            } else {
                $line
            }
        }
        if (-not $found) {
            $newLines += "JOIN_TOKEN=$joinToken"
        }
        Set-Content -Path $EnvFile -Value $newLines -Encoding ascii
        if ($found) {
            Write-Ok "Replaced existing JOIN_TOKEN entry in $EnvFile."
        } else {
            Write-Ok "Appended JOIN_TOKEN entry to $EnvFile."
        }
    }
}
catch {
    Fail "Failed to write to '$EnvFile': $($_.Exception.Message)"
}

Write-Host "============================================"
Write-Host " JOIN_TOKEN is ready in $EnvFile" -ForegroundColor Green
Write-Host " Reminder: this token is single-use and" -ForegroundColor Yellow
Write-Host " expires quickly (~600s). Start spire-agent" -ForegroundColor Yellow
Write-Host " now, e.g.: docker compose up -d spire-agent" -ForegroundColor Yellow
Write-Host "============================================"
exit 0