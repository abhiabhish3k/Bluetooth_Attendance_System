#!/usr/bin/env bash
# =============================================================================
# run_all.sh – Start backend + frontend (+ scanner optional) in one command
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

VENV_DIR="${VENV_DIR:-$REPO_ROOT/.venv}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
SCANNER_ENABLED="${SCANNER_ENABLED:-1}"

if [[ -f "$VENV_DIR/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  echo "==> Activated virtual environment: $VENV_DIR"
else
  echo "==> No virtual environment found at $VENV_DIR (continuing with system Python)"
fi

PIDS=()

cleanup() {
  echo ""
  echo "==> Stopping started services..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

echo "==> Starting backend on http://localhost:$BACKEND_PORT ..."
(
  cd "$REPO_ROOT/backend"
  exec uvicorn app.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
) &
PIDS+=($!)

echo "==> Starting frontend (Vite) ..."
(
  cd "$REPO_ROOT/dashboard/frontend"
  exec npm run dev -- --host 0.0.0.0
) &
PIDS+=($!)

if [[ "$SCANNER_ENABLED" == "1" ]]; then
  echo "==> Starting scanner bridge ..."
  (
    cd "$REPO_ROOT"
    exec bash scripts/run_scanner.sh
  ) &
  PIDS+=($!)
else
  echo "==> Scanner disabled (SCANNER_ENABLED=0)"
fi

echo ""
echo "All services started."
echo "Frontend: http://localhost:5173"
echo "Backend : http://localhost:$BACKEND_PORT (docs: /docs)"
echo "Press Ctrl+C to stop everything."
echo ""

wait
