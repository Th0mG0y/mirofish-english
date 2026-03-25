# MiroFish One-Click Setup & Run (Windows PowerShell)
# Usage: .\start.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$backendPythonVersion = "3.12"

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

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-LastExitCode {
    param([string]$Context)
    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE."
    }
}

function Wait-ForDocker {
    param([int]$TimeoutSeconds = 180)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            & docker info *> $null
            return $true
        } catch {
            Start-Sleep -Seconds 2
        }
    }

    return $false
}

function Start-DockerDesktop {
    $candidates = @()

    if ($Env:ProgramFiles) {
        $candidates += (Join-Path $Env:ProgramFiles "Docker\Docker\Docker Desktop.exe")
    }

    if ($Env:LocalAppData) {
        $candidates += (Join-Path $Env:LocalAppData "Programs\Docker\Docker\Docker Desktop.exe")
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            Start-Process -FilePath $candidate | Out-Null
            return $true
        }
    }

    return $false
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
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        Assert-LastExitCode "Python installation"
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
        Assert-LastExitCode "Node.js installation"
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
        Assert-LastExitCode "Docker installation"
        Update-Path
    } else {
        Write-Err "Docker is required and could not be installed automatically."
        Write-Host "    Install from: https://docs.docker.com/get-docker/"
        exit 1
    }
}

if (-not (Test-Command "docker")) {
    Write-Err "Docker was installed but is not yet available in this terminal."
    Write-Host "    Restart PowerShell and re-run this script."
    exit 1
}

if (-not (Wait-ForDocker -TimeoutSeconds 5)) {
    Write-Warn "Docker is installed but not running - attempting to start Docker Desktop..."
    if (-not (Start-DockerDesktop)) {
        Write-Err "Docker Desktop could not be started automatically."
        Write-Host "    Launch Docker Desktop once, wait for it to finish starting, then re-run this script."
        exit 1
    }

    Write-Host "    Waiting for Docker to become ready..."
    if (-not (Wait-ForDocker)) {
        Write-Err "Docker Desktop did not become ready in time."
        Write-Host "    Open Docker Desktop, wait until it says it is running, then re-run this script."
        exit 1
    }
}

$composeOk = $false
try { $null = & docker compose version 2>&1; $composeOk = $true } catch {}
if (-not $composeOk) {
    Write-Err "Docker Compose is required and is not available."
    Write-Host "    Ensure Docker Desktop finished installing correctly, then re-run this script."
    exit 1
}

Write-Ok "Docker found and ready"
Write-Ok "Docker Compose found"

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
        Assert-LastExitCode "uv installation"
    }
    Write-Ok "uv installed"
} else {
    Write-Ok "uv found"
}

# -----------------------------------------------------------
# 2. Start Neo4j via Docker Compose
# -----------------------------------------------------------
Write-Step "Starting Neo4j..."
$neo4jImage = "neo4j:5.26"
$neo4jImageReady = $false

try {
    & docker image inspect $neo4jImage *> $null
    $neo4jImageReady = $true
} catch {}

if (-not $neo4jImageReady) {
    Write-Warn "Neo4j image not found - pulling $neo4jImage..."
    docker pull $neo4jImage
    Assert-LastExitCode "Neo4j image pull"
}

Write-Ok "Neo4j image ready ($neo4jImage)"
docker compose up neo4j -d
Assert-LastExitCode "Neo4j startup"

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
Assert-LastExitCode "Root npm install"

Write-Host "    Installing frontend packages..."
npm install --prefix (Join-Path $root "frontend")
Assert-LastExitCode "Frontend npm install"

Write-Host "    Installing backend packages..."
Push-Location (Join-Path $root "backend")
$backendPython = Join-Path (Join-Path (Get-Location) ".venv") "Scripts\python.exe"

Write-Host "    Installing backend Python $backendPythonVersion via uv..."
uv python install $backendPythonVersion
Assert-LastExitCode "Backend Python installation"

Write-Host "    Syncing backend environment with Python $backendPythonVersion..."
uv sync --python $backendPythonVersion
Assert-LastExitCode "Backend dependency sync"

if (-not (Test-Path $backendPython)) {
    throw "Backend virtual environment was not created at $backendPython."
}

uv pip install --python $backendPython "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"
Assert-LastExitCode "Backend package refresh"
Pop-Location

Write-Ok "All dependencies installed"

# -----------------------------------------------------------
# 5. Launch
# -----------------------------------------------------------
Write-Step "Launching MiroFish (frontend + backend)..."
Write-Host "    Press Ctrl+C to stop.`n"
npm run dev --prefix $root
