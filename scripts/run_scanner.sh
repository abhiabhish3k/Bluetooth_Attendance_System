#!/usr/bin/env bash
# =============================================================================
# run_scanner.sh – Run the C++ BLE scanner and pipe events to the backend
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCANNER_BIN="$REPO_ROOT/scanner/build/bin/ble_scanner"
SCANNER_CFG="$REPO_ROOT/scanner/config.json"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000/api/events}"

if [[ ! -x "$SCANNER_BIN" ]]; then
    echo "ERROR: Scanner binary not found at $SCANNER_BIN"
    echo "Run: bash scripts/build_scanner.sh"
    exit 1
fi

echo "==> Starting BLE scanner..."
echo "    Binary:  $SCANNER_BIN"
echo "    Config:  $SCANNER_CFG"
echo "    Backend: $BACKEND_URL"
echo ""

# Run scanner and forward JSON events to the backend API via curl
sudo "$SCANNER_BIN" "$SCANNER_CFG" | while IFS= read -r line; do
    # Only forward lines that look like JSON objects (start with '{')
    if [[ "$line" == \{* ]]; then
        curl -s -X POST "$BACKEND_URL" \
             -H "Content-Type: application/json" \
             -d "$line" &
    else
        echo "$line"
    fi
done
