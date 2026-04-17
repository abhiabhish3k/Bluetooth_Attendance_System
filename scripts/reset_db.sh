#!/usr/bin/env bash
# =============================================================================
# reset_db.sh – Completely reset the attendance database
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB_PATH="${DB_PATH:-$REPO_ROOT/backend/attendance.db}"

echo "WARNING: This will permanently delete all data in: $DB_PATH"
read -r -p "Are you sure? (yes/N) " answer

if [[ "$answer" != "yes" ]]; then
    echo "Aborted."
    exit 0
fi

echo "==> Resetting database..."
python "$REPO_ROOT/database/init_db.py" \
    --db "$DB_PATH" \
    --reset

echo "==> Database reset complete."
echo ""
echo "To seed sample data, run:"
echo "  python database/init_db.py --db $DB_PATH --seed"
