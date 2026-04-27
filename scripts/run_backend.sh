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

# Resolve candidate venv locations: repo-local first, then two levels up (user root)
_PARENT_DIR="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd 2>/dev/null)"
VENV_CANDIDATES=(
  "${VENV_DIR:-$REPO_ROOT/.venv}"
)
# Only add the parent candidate if it resolves to a real non-root directory
if [[ -n "$_PARENT_DIR" && ! "$_PARENT_DIR" =~ ^/+$ ]]; then
  VENV_CANDIDATES+=("$_PARENT_DIR/.venv")
fi
unset _PARENT_DIR

PYTHON="python3"
for _candidate in "${VENV_CANDIDATES[@]}"; do
  if [[ -f "$_candidate/bin/activate" && -f "$_candidate/bin/python" ]]; then
    # shellcheck source=/dev/null
    source "$_candidate/bin/activate"
    PYTHON="$_candidate/bin/python"
    echo "==> Activated virtual environment: $_candidate"
    break
  fi
done
if [[ "$PYTHON" == "python3" ]]; then
  echo "==> No virtual environment found; using system Python"
fi
unset _candidate

echo "==> Installing Python dependencies..."
cd "$BACKEND_DIR"
"$PYTHON" -m pip install -r requirements.txt --quiet

echo "==> Initialising database..."
"$PYTHON" "$REPO_ROOT/database/init_db.py"

echo "==> Starting FastAPI backend..."
echo "    URL:  http://$HOST:$PORT"
echo "    Docs: http://localhost:$PORT/docs"
echo ""

exec "$PYTHON" -m uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL"
