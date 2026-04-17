#!/usr/bin/env bash
# =============================================================================
# run_backend.sh – Install dependencies and start the FastAPI backend
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-1}"
LOG_LEVEL="${LOG_LEVEL:-info}"

echo "==> Installing Python dependencies..."
cd "$BACKEND_DIR"
pip install -r requirements.txt --quiet

echo "==> Initialising database..."
python "$REPO_ROOT/database/init_db.py"

echo "==> Starting FastAPI backend..."
echo "    URL:  http://$HOST:$PORT"
echo "    Docs: http://localhost:$PORT/docs"
echo ""

exec uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL"
