# MiroFish One-Click Setup & Run (Windows PowerShell)
# Usage: .\start.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step { param([string]$msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$msg) Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Err  { param([string]$msg) Write-Host "    [ERROR] $msg" -ForegroundColor Red }
function Write-Warn { param([string]$msg) Write-Host "    [WARN] $msg" -ForegroundColor Yellow }

$root = $PSScriptRoot
if (-not $root) { $root = Get-Location }
Set-Location $root

# Helper: check if winget is available
function Test-Winget {
    try { $null = & winget --version 2>&1; return $true } catch { return $false }
}

# Helper: refresh PATH from registry so newly-installed tools are visible
function Update-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

# -----------------------------------------------------------
# 1. Dependency checks & auto-install
# -----------------------------------------------------------
Write-Step "Checking dependencies..."

$hasWinget = Test-Winget

# --- Python 3.11+ ---
$pythonCmd = $null
foreach ($cmd in @("python", "python3")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "(\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 11) { $pythonCmd = $cmd; break }
        }
    } catch {}
}
if (-not $pythonCmd) {
    if ($hasWinget) {
        Write-Warn "Python 3.11+ not found - installing via winget..."
        winget install Python.Python.3.13 --accept-package-agreements --accept-source-agreements
        Update-Path
        # Re-check
        foreach ($cmd in @("python", "python3")) {
            try {
                $ver = & $cmd --version 2>&1
                if ($ver -match "(\d+)\.(\d+)") {
                    $major = [int]$Matches[1]; $minor = [int]$Matches[2]
                    if ($major -ge 3 -and $minor -ge 11) { $pythonCmd = $cmd; break }
                }
            } catch {}
        }
    }
    if (-not $pythonCmd) {
        Write-Err "Python 3.11+ is required and could not be installed automatically."
        Write-Host "    Install from: https://www.python.org/downloads/"
        exit 1
    }
}
Write-Ok "Python found ($pythonCmd)"

# --- Node 18+ ---
$nodeOk = $false
try {
    $nodeVer = & node --version 2>&1
    if ($nodeVer -match "v(\d+)") {
        if ([int]$Matches[1] -ge 18) { $nodeOk = $true }
    }
} catch {}
if (-not $nodeOk) {
    if ($hasWinget) {
        Write-Warn "Node.js 18+ not found - installing via winget..."
        winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
        Update-Path
        try {
            $nodeVer = & node --version 2>&1
            if ($nodeVer -match "v(\d+)") {
                if ([int]$Matches[1] -ge 18) { $nodeOk = $true }
            }
        } catch {}
    }
    if (-not $nodeOk) {
        Write-Err "Node.js 18+ is required and could not be installed automatically."
        Write-Host "    Install from: https://nodejs.org/"
        exit 1
    }
}
Write-Ok "Node.js found ($(node --version))"

# --- Docker ---
$dockerOk = $false
try { $null = & docker --version 2>&1; $dockerOk = $true } catch {}
if (-not $dockerOk) {
    if ($hasWinget) {
        Write-Warn "Docker not found - installing Docker Desktop via winget..."
        winget install Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        Update-Path
        Write-Warn "Docker Desktop was installed. You may need to restart your PC and launch Docker Desktop before continuing."
        Write-Warn "After Docker is running, re-run this script."
        exit 1
    } else {
        Write-Err "Docker is required and could not be installed automatically."
        Write-Host "    Install from: https://docs.docker.com/get-docker/"
        exit 1
    }
}
Write-Ok "Docker found"

# --- uv ---
$uvFound = $false
try { $null = & uv --version 2>&1; $uvFound = $true } catch {}
if (-not $uvFound) {
    Write-Warn "uv not found - installing..."
    # Try the official installer first, fall back to pip
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        Update-Path
    } catch {
        & $pythonCmd -m pip install uv --quiet
    }
    Write-Ok "uv installed"
} else {
    Write-Ok "uv found"
}

# -----------------------------------------------------------
# 2. Start Neo4j via Docker Compose
# -----------------------------------------------------------
Write-Step "Starting Neo4j..."
docker compose up neo4j -d

Write-Host "    Waiting for Neo4j to become ready..."
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("localhost", 7687)
        $tcp.Close()
        $ready = $true
        break
    } catch {}
}
if ($ready) { Write-Ok "Neo4j is reachable on port 7687" }
else { Write-Warn "Neo4j may not be ready yet - continuing anyway" }

# -----------------------------------------------------------
# 3. Environment file
# -----------------------------------------------------------
Write-Step "Checking environment file..."
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Write-Ok ".env already exists - skipping copy"
} else {
    Copy-Item (Join-Path $root ".env.openai.example") $envFile
    Write-Ok "Copied .env.openai.example -> .env"
    Write-Warn "Edit .env with your API keys before using the app!"
}

# -----------------------------------------------------------
# 4. Install dependencies
# -----------------------------------------------------------
Write-Step "Installing dependencies..."

Write-Host "    Installing root packages..."
npm install --prefix $root

Write-Host "    Installing frontend packages..."
npm install --prefix (Join-Path $root "frontend")

Write-Host "    Installing backend packages..."
Push-Location (Join-Path $root "backend")
uv sync
uv pip install "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"
Pop-Location

Write-Ok "All dependencies installed"

# -----------------------------------------------------------
# 5. Launch
# -----------------------------------------------------------
Write-Step "Launching MiroFish (frontend + backend)..."
Write-Host "    Press Ctrl+C to stop.`n"
npm run dev --prefix $root
