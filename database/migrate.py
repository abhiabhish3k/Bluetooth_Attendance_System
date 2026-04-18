#!/usr/bin/env python3
"""
Database migration script.

Upgrades an existing attendance.db from the old MAC-address-only schema to
the current Beacon UUID schema by adding any missing columns and indexes.

Migrations applied:
  - students.unique_id  (TEXT UNIQUE)           – BLE beacon identifier
  - scan_logs.beacon_id (TEXT)                  – extracted beacon identifier
  - idx_students_unique_id index on students(unique_id)
  - idx_scan_logs_beacon   index on scan_logs(beacon_id)

Usage:
    python database/migrate.py [--db path/to/db.sqlite]
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).parent.parent / "backend" / "attendance.db"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KNOWN_TABLES = frozenset(
    {"students", "devices", "sessions", "attendance", "scan_logs", "student_beacon"}
)


def _column_names(conn: sqlite3.Connection, table: str) -> set:
    """Return the set of column names for *table*.

    *table* must be one of the known schema tables; this is enforced to
    prevent SQL injection since PRAGMA statements do not accept bind
    parameters for identifiers.
    """
    if table not in _KNOWN_TABLES:
        raise ValueError(f"Unknown table name: {table!r}")
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Return True if *table* exists in the database."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def needs_migration(conn: sqlite3.Connection) -> bool:
    """Return True if the database is missing any of the new Beacon UUID columns.

    Returns False for a brand-new (empty) database because schema.sql will
    create both tables and their columns from scratch.  Each table is guarded
    with _table_exists so that a partially-initialised database is handled
    correctly without touching non-existent tables.
    """
    students_exists  = _table_exists(conn, "students")
    scan_logs_exists = _table_exists(conn, "scan_logs")

    if not students_exists and not scan_logs_exists:
        # Completely empty database – nothing to migrate.
        return False

    if students_exists and "unique_id" not in _column_names(conn, "students"):
        return True

    if scan_logs_exists and "beacon_id" not in _column_names(conn, "scan_logs"):
        return True

    return False


def _backup(db_path: Path) -> Path:
    """Copy *db_path* to a timestamped backup file and return the backup path."""
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.with_name(f"{db_path.stem}.{ts}.bak{db_path.suffix}")
    shutil.copy2(db_path, backup_path)
    print(f"[migrate] Backup created: {backup_path}")
    return backup_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_migrations(conn: sqlite3.Connection) -> None:
    """
    Apply all pending schema migrations to *conn* in-place.

    Safe to call on an already-up-to-date database (all checks are
    idempotent).  Does *not* commit or close the connection.
    """
    # ---- students.unique_id ------------------------------------------------
    if _table_exists(conn, "students"):
        if "unique_id" not in _column_names(conn, "students"):
            print("[migrate] Adding column students.unique_id …")
            # SQLite does not allow ADD COLUMN with an inline UNIQUE constraint,
            # so the column is added without it and uniqueness is enforced by the
            # UNIQUE INDEX created unconditionally below (IF NOT EXISTS makes it
            # a no-op when the column was already present and the index exists).
            conn.execute("ALTER TABLE students ADD COLUMN unique_id TEXT")

        # Created unconditionally: IF NOT EXISTS makes it idempotent whether the
        # column was just added or was already present from a previous migration.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_students_unique_id"
            " ON students (unique_id)"
        )

    # ---- scan_logs.beacon_id -----------------------------------------------
    if _table_exists(conn, "scan_logs"):
        if "beacon_id" not in _column_names(conn, "scan_logs"):
            print("[migrate] Adding column scan_logs.beacon_id …")
            conn.execute("ALTER TABLE scan_logs ADD COLUMN beacon_id TEXT")

        # Created unconditionally for the same idempotency reason as above.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scan_logs_beacon"
            " ON scan_logs (beacon_id)"
        )

    conn.commit()


def migrate(db_path: Path) -> None:
    """
    Open *db_path*, back it up if migration is required, then migrate.
    """
    if not db_path.exists():
        print(f"[migrate] Database not found at {db_path}; nothing to migrate.")
        return

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        if not needs_migration(conn):
            print("[migrate] Database is already up-to-date; no migration needed.")
            return

        _backup(db_path)
        print("[migrate] Applying migrations …")
        run_migrations(conn)
        print("[migrate] Migration complete.")
    except Exception as exc:
        print(f"[migrate] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate an existing attendance.db to the current schema."
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help=f"Path to SQLite database file (default: {DEFAULT_DB})",
    )
    args = parser.parse_args()
    migrate(Path(args.db))


if __name__ == "__main__":
    main()
