#!/usr/bin/env bash
# MiroFish One-Click Setup & Run (macOS / Linux)
# Usage: chmod +x start.sh && ./start.sh

set -euo pipefail

BACKEND_PYTHON_VERSION="3.12"

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

have_cmd() {
    command -v "$1" &>/dev/null
}

refresh_brew_shellenv() {
    if [ -x /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -x /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
}

ensure_curl() {
    if have_cmd curl; then
        return 0
    fi

    case "$PKG" in
        apt)
            warn "curl not found - installing via apt..."
            sudo apt-get update
            sudo apt-get install -y curl ca-certificates
            ;;
        dnf)
            warn "curl not found - installing via dnf..."
            sudo dnf install -y curl ca-certificates
            ;;
        pacman)
            warn "curl not found - installing via pacman..."
            sudo pacman -S --noconfirm curl ca-certificates
            ;;
        *)
            err "curl is required and could not be installed automatically."
            exit 1
            ;;
    esac
}

install_homebrew() {
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    refresh_brew_shellenv
}

DOCKER_NEEDS_SUDO=false
COMPOSE_STYLE=""

docker_info_any() {
    if docker info >/dev/null 2>&1; then
        DOCKER_NEEDS_SUDO=false
        return 0
    fi

    if [ "$OS" = "Linux" ] && sudo docker info >/dev/null 2>&1; then
        DOCKER_NEEDS_SUDO=true
        return 0
    fi

    return 1
}

wait_for_docker() {
    local timeout="${1:-180}"
    local elapsed=0

    while [ "$elapsed" -lt "$timeout" ]; do
        if docker_info_any; then
            return 0
        fi

        sleep 2
        elapsed=$((elapsed + 2))
    done

    return 1
}

start_docker_runtime() {
    case "$OS" in
        Darwin)
            open -a Docker
            ;;
        Linux)
            if have_cmd systemctl; then
                sudo systemctl enable --now docker
            else
                return 1
            fi
            ;;
        *)
            return 1
            ;;
    esac
}

docker_cli() {
    if $DOCKER_NEEDS_SUDO; then
        sudo docker "$@"
    else
        docker "$@"
    fi
}

detect_compose() {
    if docker_cli compose version >/dev/null 2>&1; then
        COMPOSE_STYLE="plugin"
        return 0
    fi

    if have_cmd docker-compose; then
        if $DOCKER_NEEDS_SUDO; then
            sudo docker-compose version >/dev/null 2>&1
        else
            docker-compose version >/dev/null 2>&1
        fi

        COMPOSE_STYLE="legacy"
        return 0
    fi

    return 1
}

docker_compose_cli() {
    if [ "$COMPOSE_STYLE" = "plugin" ]; then
        docker_cli compose "$@"
    else
        if $DOCKER_NEEDS_SUDO; then
            sudo docker-compose "$@"
        else
            docker-compose "$@"
        fi
    fi
}

# Helper: extract major.minor from python version string (portable, no grep -P)
python_version() {
    "$1" --version 2>&1 | sed -n 's/.*Python \([0-9]*\.[0-9]*\).*/\1/p'
}

if [ "$OS" = "Darwin" ] && [ -z "$PKG" ]; then
    warn "Homebrew not found - installing it so dependencies can be installed automatically..."
    ensure_curl
    install_homebrew
    PKG="brew"
fi

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
            brew install python@3.12
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
            ensure_curl
            curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
            sudo apt-get install -y nodejs
            ;;
        dnf)
            warn "Node.js 18+ not found - installing via NodeSource..."
            ensure_curl
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
            ;;
        apt)
            warn "Docker not found - installing via apt..."
            sudo apt-get update
            sudo apt-get install -y docker.io docker-compose-plugin
            ;;
        dnf)
            warn "Docker not found - installing via dnf..."
            sudo dnf install -y docker docker-compose-plugin
            ;;
        pacman)
            warn "Docker not found - installing via pacman..."
            sudo pacman -S --noconfirm docker docker-compose
            ;;
        *)
            err "Docker is required and could not be installed automatically."
            echo "    Install from: https://docs.docker.com/get-docker/"
            exit 1
            ;;
    esac
fi

if ! have_cmd docker; then
    err "Docker was installed but is not yet available in this terminal."
    echo "    Restart your terminal and re-run this script."
    exit 1
fi

if ! wait_for_docker 5; then
    warn "Docker is installed but not running - attempting to start it..."
    if ! start_docker_runtime; then
        err "Docker could not be started automatically."
        echo "    Start Docker manually, wait for it to finish booting, then re-run this script."
        exit 1
    fi

    echo "    Waiting for Docker to become ready..."
    if ! wait_for_docker 180; then
        err "Docker did not become ready in time."
        echo "    Open Docker and wait until it is fully running, then re-run this script."
        exit 1
    fi
fi

if ! detect_compose; then
    case "$PKG" in
        apt)
            warn "Docker Compose not found - installing via apt..."
            sudo apt-get update
            sudo apt-get install -y docker-compose-plugin
            ;;
        dnf)
            warn "Docker Compose not found - installing via dnf..."
            sudo dnf install -y docker-compose-plugin
            ;;
        pacman)
            warn "Docker Compose not found - installing via pacman..."
            sudo pacman -S --noconfirm docker-compose
            ;;
        *)
            err "Docker Compose is required and could not be installed automatically."
            exit 1
            ;;
    esac

    if ! detect_compose; then
        err "Docker Compose is required and is still not available."
        exit 1
    fi
fi

ok "Docker is ready"
ok "Docker Compose found"

# --- uv ---
if command -v uv &>/dev/null; then
    ok "uv found"
else
    warn "uv not found - installing..."
    ensure_curl
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    ok "uv installed"
fi

# -----------------------------------------------------------
# 2. Start Neo4j via Docker Compose
# -----------------------------------------------------------
step "Starting Neo4j..."
if ! docker_cli image inspect neo4j:5.26 >/dev/null 2>&1; then
    warn "Neo4j image not found - pulling neo4j:5.26..."
    docker_cli pull neo4j:5.26
fi

ok "Neo4j image ready (neo4j:5.26)"
docker_compose_cli up neo4j -d

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
(
    cd backend
    echo "    Installing backend Python $BACKEND_PYTHON_VERSION via uv..."
    uv python install "$BACKEND_PYTHON_VERSION"
    echo "    Syncing backend environment with Python $BACKEND_PYTHON_VERSION..."
    uv sync --python "$BACKEND_PYTHON_VERSION"
    if [ ! -x ".venv/bin/python" ]; then
        err "Backend virtual environment was not created correctly."
        exit 1
    fi
    uv pip install --python ".venv/bin/python" "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"
)

ok "All dependencies installed"

# -----------------------------------------------------------
# 5. Launch
# -----------------------------------------------------------
step "Launching MiroFish (frontend + backend)..."
echo "    Press Ctrl+C to stop."
echo
npm run dev
