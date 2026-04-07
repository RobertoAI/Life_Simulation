#!/bin/bash
# ┌─────────────────────────────────────────────────────────────────┐
# │  AI Life Simulator — Quick Start Script                         │
# │  Usage: ./start.sh [OPTIONS]                                    │
# └─────────────────────────────────────────────────────────────────┘

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# ── Defaults ───────────────────────────────────────────────────
PORT=8000
GPU_ENABLED=true
RELOAD=false
WORKERS=1

# ── Functions ───────────────────────────────────────────────────

usage() {
    echo -e "${WHITE}AI Life Simulator${NC}"
    echo ""
    echo -e "${CYAN}Usage:${NC} $0 [OPTIONS]"
    echo ""
    echo -e "${CYAN}Options:${NC}"
    echo -e "  ${GREEN}--gpu${NC}        Enable GPU monitoring (default)"
    echo -e "  ${GREEN}--no-gpu${NC}     Disable GPU monitoring (use fallback)"
    echo -e "  ${GREEN}--port PORT${NC}  Set the HTTP port (default: 8000)"
    echo -e "  ${GREEN}--dev${NC}        Development mode with auto-reload"
    echo -e "  ${GREEN}--help -h${NC}    Show this help message"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo -e "  $0                    # Start on port 8000 with GPU"
    echo -e "  $0 --port 9000        # Start on port 9000"
    echo -e "  $0 --no-gpu --dev     # Dev mode, no GPU"
    echo ""
    exit 0
}

log_info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Parse Arguments ─────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --gpu)
            GPU_ENABLED=true
            shift
            ;;
        --no-gpu)
            GPU_ENABLED=false
            shift
            ;;
        --port)
            if [[ -z "${2:-}" ]]; then
                log_error "Missing port number"
                exit 1
            fi
            PORT="$2"
            shift 2
            ;;
        --dev)
            RELOAD=true
            WORKERS=1
            shift
            ;;
        --help|-h)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            echo ""
            usage
            ;;
    esac
done

# ── Pre-flight Checks ──────────────────────────────────────────

cd "$(dirname "$0")"

log_info "AI Life Simulator — Starting up..."

# Check Python
if ! command -v python3 &>/dev/null; then
    log_error "Python 3 is not installed or not in PATH"
    exit 1
fi
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
log_ok "Python ${PYTHON_VERSION} found"

# Check requirements
if [ ! -f "requirements.txt" ]; then
    log_error "requirements.txt not found — are you in the right directory?"
    exit 1
fi

# Install dependencies if needed
if [ ! -d "venv" ] && ! python3 -c "import fastapi" &>/dev/null 2>&1; then
    log_info "Installing Python dependencies..."
    pip install -r requirements.txt -q 2>/dev/null || pip install -r requirements.txt
    log_ok "Dependencies installed"
else
    log_ok "Dependencies satisfied"
fi

# Check port availability
if command -v lsof &>/dev/null; then
    if lsof -i ":${PORT}" &>/dev/null; then
        log_error "Port ${PORT} is already in use"
        log_info "Try: ./start.sh --port 8001"
        exit 1
    fi
elif command -v ss &>/dev/null; then
    if ss -tlnp | grep -q ":${PORT} "; then
        log_error "Port ${PORT} is already in use"
        log_info "Try: ./start.sh --port 8001"
        exit 1
    fi
fi

# Create data directory
mkdir -p data
log_ok "Data directory ready"

# ── GPU Setup ───────────────────────────────────────────────────

if [ "$GPU_ENABLED" = true ]; then
    if python3 -c "import pynvml; pynvml.nvmlInit(); pynvml.nvmlShutdown()" &>/dev/null 2>&1; then
        log_ok "NVIDIA GPU detected"
        export GPU_ENABLED_ENV=true
    else
        log_warn "No NVIDIA GPU found — using fallback monitor"
        export GPU_ENABLED_ENV=false
    fi
else
    log_warn "GPU monitoring disabled"
    export GPU_ENABLED_ENV=false
fi

# ── Launch ──────────────────────────────────────────────────────

if [ "$RELOAD" = true ]; then
    log_info "Starting in ${YELLOW}development mode${NC} with auto-reload on port ${CYAN}${PORT}${NC}"
    LOG_LEVEL="${LOG_LEVEL:-debug}"
    exec uvicorn backend.main:app \
        --host 0.0.0.0 \
        --port "${PORT}" \
        --reload \
        --log-level "${LOG_LEVEL}"
else
    log_info "Starting ${GREEN}production server${NC} on port ${CYAN}${PORT}${NC}"
    exec uvicorn backend.main:app \
        --host 0.0.0.0 \
        --port "${PORT}" \
        --workers "${WORKERS}" \
        --log-level info
fi
