#!/usr/bin/env bash
# MiroFish One-Click Setup & Run (macOS / Linux)
# Usage: chmod +x start.sh && ./start.sh

set -euo pipefail

step()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
ok()    { printf '    \033[1;32m[OK]\033[0m %s\n' "$1"; }
err()   { printf '    \033[1;31m[ERROR]\033[0m %s\n' "$1"; }
warn()  { printf '    \033[1;33m[WARN]\033[0m %s\n' "$1"; }

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Detect OS and package manager
OS="$(uname -s)"
PKG=""
if [ "$OS" = "Darwin" ]; then
    if command -v brew &>/dev/null; then PKG="brew"; fi
elif [ "$OS" = "Linux" ]; then
    if command -v apt-get &>/dev/null; then PKG="apt"
    elif command -v dnf &>/dev/null; then PKG="dnf"
    elif command -v pacman &>/dev/null; then PKG="pacman"
    fi
fi

# Helper: extract major.minor from python version string (portable, no grep -P)
python_version() {
    "$1" --version 2>&1 | sed -n 's/.*Python \([0-9]*\.[0-9]*\).*/\1/p'
}

# -----------------------------------------------------------
# 1. Dependency checks & auto-install
# -----------------------------------------------------------
step "Checking dependencies..."

# --- Python 3.11+ ---
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$(python_version "$cmd")
        major=${ver%%.*}
        minor=${ver#*.}
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done
if [ -z "$PYTHON_CMD" ]; then
    case "$PKG" in
        brew)
            warn "Python 3.11+ not found - installing via Homebrew..."
            brew install python@3.13
            ;;
        apt)
            warn "Python 3.11+ not found - installing via apt..."
            sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
            ;;
        dnf)
            warn "Python 3.11+ not found - installing via dnf..."
            sudo dnf install -y python3 python3-pip
            ;;
        pacman)
            warn "Python 3.11+ not found - installing via pacman..."
            sudo pacman -S --noconfirm python python-pip
            ;;
    esac
    # Re-check
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            ver=$(python_version "$cmd")
            major=${ver%%.*}
            minor=${ver#*.}
            if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
                PYTHON_CMD="$cmd"
                break
            fi
        fi
    done
    if [ -z "$PYTHON_CMD" ]; then
        err "Python 3.11+ is required and could not be installed automatically."
        echo "    Install from: https://www.python.org/downloads/"
        exit 1
    fi
fi
ok "Python found ($PYTHON_CMD $($PYTHON_CMD --version 2>&1 | sed 's/Python //'))"

# --- Node 18+ ---
node_ok=false
if command -v node &>/dev/null; then
    node_major=$(node --version | sed 's/v\([0-9]*\).*/\1/')
    if [ "$node_major" -ge 18 ]; then node_ok=true; fi
fi
if ! $node_ok; then
    case "$PKG" in
        brew)
            warn "Node.js 18+ not found - installing via Homebrew..."
            brew install node@22
            brew link --overwrite node@22 2>/dev/null || true
            ;;
        apt)
            warn "Node.js 18+ not found - installing via NodeSource..."
            curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
            sudo apt-get install -y nodejs
            ;;
        dnf)
            warn "Node.js 18+ not found - installing via NodeSource..."
            curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
            sudo dnf install -y nodejs
            ;;
        pacman)
            warn "Node.js 18+ not found - installing via pacman..."
            sudo pacman -S --noconfirm nodejs npm
            ;;
    esac
    # Re-check
    if command -v node &>/dev/null; then
        node_major=$(node --version | sed 's/v\([0-9]*\).*/\1/')
        if [ "$node_major" -ge 18 ]; then node_ok=true; fi
    fi
    if ! $node_ok; then
        err "Node.js 18+ is required and could not be installed automatically."
        echo "    Install from: https://nodejs.org/"
        exit 1
    fi
fi
ok "Node.js found ($(node --version))"

# --- Docker ---
if command -v docker &>/dev/null; then
    ok "Docker found"
else
    case "$PKG" in
        brew)
            warn "Docker not found - installing Docker via Homebrew..."
            brew install --cask docker
            warn "Docker Desktop was installed. Please launch it from Applications, then re-run this script."
            exit 1
            ;;
        apt)
            warn "Docker not found - installing via apt..."
            sudo apt-get update
            sudo apt-get install -y docker.io docker-compose-plugin
            sudo systemctl start docker
            sudo usermod -aG docker "$USER"
            warn "You were added to the docker group. You may need to log out and back in, then re-run this script."
            ;;
        dnf)
            warn "Docker not found - installing via dnf..."
            sudo dnf install -y docker docker-compose-plugin
            sudo systemctl start docker
            sudo usermod -aG docker "$USER"
            warn "You were added to the docker group. You may need to log out and back in, then re-run this script."
            ;;
        pacman)
            warn "Docker not found - installing via pacman..."
            sudo pacman -S --noconfirm docker docker-compose
            sudo systemctl start docker
            sudo usermod -aG docker "$USER"
            warn "You were added to the docker group. You may need to log out and back in, then re-run this script."
            ;;
        *)
            err "Docker is required and could not be installed automatically."
            echo "    Install from: https://docs.docker.com/get-docker/"
            exit 1
            ;;
    esac
    # Verify docker works now
    if ! command -v docker &>/dev/null; then
        err "Docker was installed but is not yet available. Please restart your terminal and re-run this script."
        exit 1
    fi
    ok "Docker installed"
fi

# --- uv ---
if command -v uv &>/dev/null; then
    ok "uv found"
else
    warn "uv not found - installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    ok "uv installed"
fi

# -----------------------------------------------------------
# 2. Start Neo4j via Docker Compose
# -----------------------------------------------------------
step "Starting Neo4j..."
docker compose up neo4j -d

echo "    Waiting for Neo4j to become ready..."
ready=false
for i in $(seq 1 15); do
    sleep 2
    if (echo > /dev/tcp/localhost/7687) 2>/dev/null; then
        ready=true
        break
    fi
done
if $ready; then ok "Neo4j is reachable on port 7687"
else warn "Neo4j may not be ready yet - continuing anyway"; fi

# -----------------------------------------------------------
# 3. Environment file
# -----------------------------------------------------------
step "Checking environment file..."
if [ -f "$ROOT/.env" ]; then
    ok ".env already exists - skipping copy"
else
    cp "$ROOT/.env.openai.example" "$ROOT/.env"
    ok "Copied .env.openai.example -> .env"
    warn "Edit .env with your API keys before using the app!"
fi

# -----------------------------------------------------------
# 4. Install dependencies
# -----------------------------------------------------------
step "Installing dependencies..."

echo "    Installing root packages..."
npm install

echo "    Installing frontend packages..."
(cd frontend && npm install)

echo "    Installing backend packages..."
(cd backend && uv sync && uv pip install "graphiti-core==0.28.2" "neo4j==5.26.0")

ok "All dependencies installed"

# -----------------------------------------------------------
# 5. Launch
# -----------------------------------------------------------
step "Launching MiroFish (frontend + backend)..."
echo "    Press Ctrl+C to stop."
echo
npm run dev
