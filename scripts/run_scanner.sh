#!/usr/bin/env bash
# =============================================================================
# run_scanner.sh – Run the C++ BLE scanner and pipe events to the backend
#
# Usage:
#   bash scripts/run_scanner.sh           # start the bridge (idempotent)
#   bash scripts/run_scanner.sh --stop    # stop any running bridge instance
#
# The bridge reads JSON lines from the scanner binary's stdout and POSTs
# each event to the backend's /api/events endpoint via curl.
#
# A PID file at /tmp/ble_scanner_bridge.pid prevents duplicate instances.
# The backend URL is resolved in this order:
#   1. BACKEND_URL environment variable
#   2. "backend_url" key in scanner/config.json
#   3. Hard-coded default: http://127.0.0.1:8000/api/events
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCANNER_BIN="$REPO_ROOT/scanner/build/bin/ble_scanner"
SCANNER_CFG="$REPO_ROOT/scanner/config.json"
PID_FILE="/tmp/ble_scanner_bridge.pid"

# ---------------------------------------------------------------------------
# Resolve backend URL: env var > config.json > default
# ---------------------------------------------------------------------------
_cfg_url=""
if [[ -f "$SCANNER_CFG" ]]; then
    _cfg_url="$(grep -o '"backend_url"[[:space:]]*:[[:space:]]*"[^"]*"' "$SCANNER_CFG" \
                 2>/dev/null \
                 | grep -o '"[^"]*"$' \
                 | tr -d '"' \
                 || true)"
fi
BACKEND_URL="${BACKEND_URL:-${_cfg_url:-http://127.0.0.1:8000/api/events}}"
unset _cfg_url

# ---------------------------------------------------------------------------
# --stop action: kill any running bridge and its scanner child
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--stop" ]]; then
    if [[ -f "$PID_FILE" ]]; then
        OLD_PID="$(cat "$PID_FILE")"
        if kill -0 "$OLD_PID" 2>/dev/null; then
            echo "==> Stopping scanner bridge (pid=$OLD_PID)..."
            kill "$OLD_PID" 2>/dev/null || true
        else
            echo "==> Stale PID file found (pid=$OLD_PID not running)."
        fi
        rm -f "$PID_FILE"
    else
        echo "==> No running scanner bridge PID file found."
    fi
    # Best-effort: also kill any stray scanner binary processes started by this script
    sudo pkill -f "$SCANNER_BIN" 2>/dev/null || true
    echo "==> Done."
    exit 0
fi

# ---------------------------------------------------------------------------
# Idempotency: refuse to start a second bridge instance
# ---------------------------------------------------------------------------
if [[ -f "$PID_FILE" ]]; then
    OLD_PID="$(cat "$PID_FILE")"
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "==> Scanner bridge is already running (pid=$OLD_PID)."
        echo "    Use 'bash scripts/run_scanner.sh --stop' to stop it first."
        exit 0
    else
        echo "==> Removing stale PID file (pid=$OLD_PID)."
        rm -f "$PID_FILE"
    fi
fi

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [[ ! -x "$SCANNER_BIN" ]]; then
    echo "ERROR: Scanner binary not found at $SCANNER_BIN"
    echo "Run: bash scripts/build_scanner.sh"
    exit 1
fi

echo "==> Starting BLE scanner..."
echo "    Binary:  $SCANNER_BIN"
echo "    Config:  $SCANNER_CFG"
echo "    Backend: $BACKEND_URL"
echo "    PID file: $PID_FILE"
echo ""

# Write this shell's PID so --stop and the idempotency check can find us
echo "$$" > "$PID_FILE"

# Remove PID file on exit (normal, Ctrl-C, SIGTERM)
_cleanup() {
    rm -f "$PID_FILE"
}
trap _cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Run scanner and forward JSON events to the backend API via curl
# ---------------------------------------------------------------------------
# Note: curl failures are intentionally ignored (|| true) so a temporary
# backend outage does not kill the entire bridge.  Non-JSON lines (startup
# banners, log lines) are echoed to the terminal for visibility.
sudo "$SCANNER_BIN" "$SCANNER_CFG" | while IFS= read -r line; do
    if [[ "$line" == \{* ]]; then
        curl -s -X POST "$BACKEND_URL" \
             -H "Content-Type: application/json" \
             -d "$line" > /dev/null 2>&1 || true &
    else
        echo "$line"
    fi
done
