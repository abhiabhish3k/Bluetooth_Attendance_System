#!/usr/bin/env python3
"""
Database initialisation script.

Creates all tables defined in schema.sql (SQLite) and optionally seeds
some sample data for local development/testing.

If an existing database is detected that pre-dates the Beacon UUID migration,
the script automatically runs the migration (via migrate.py) before applying
the full schema so that index creation never fails on missing columns.

Usage:
    python database/init_db.py [--db path/to/db.sqlite] [--seed]
"""

import argparse
import sqlite3
import os
import sys
from pathlib import Path

from migrate import run_migrations, needs_migration

SCHEMA_FILE = Path(__file__).parent / "schema.sql"
DEFAULT_DB  = Path(__file__).parent.parent / "backend" / "attendance.db"


def create_tables(conn: sqlite3.Connection) -> None:
    """Execute the full schema.sql against the given connection.

    If the database already has tables from the old MAC-address-only schema,
    the migration is applied first so that all columns exist before the index
    creation statements in schema.sql are executed.
    """
    if needs_migration(conn):
        print("[init_db] Old schema detected – running migrations first …")
        run_migrations(conn)

    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    # SQLite's executescript does not support multiple statements from executemany;
    # split on semicolons and execute each statement individually.
    conn.executescript(schema)
    print("[init_db] Tables created successfully.")


def seed_data(conn: sqlite3.Connection) -> None:
    """Insert sample data for development/testing."""
    cursor = conn.cursor()

    # Sample students
    students = [
        ("Alice Johnson",  "CS2021001", "alice@example.com",  "AA:BB:CC:11:22:33"),
        ("Bob Smith",      "CS2021002", "bob@example.com",    "AA:BB:CC:44:55:66"),
        ("Carol Williams", "CS2021003", "carol@example.com",  "AA:BB:CC:77:88:99"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO students (name, roll_number, email, mac_address) "
        "VALUES (?, ?, ?, ?)",
        students,
    )

    # Sample session
    cursor.execute(
        "INSERT OR IGNORE INTO sessions (class_name, start_time, threshold_rssi) "
        "VALUES (?, datetime('now'), ?)",
        ("CS101 – Introduction to Programming", -75),
    )

    conn.commit()
    print(f"[init_db] Seeded {len(students)} sample students.")
    print("[init_db] Seeded 1 sample session.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise the attendance database.")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help=f"Path to SQLite database file (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed the database with sample data",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing database file before initialising",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if args.reset and db_path.exists():
        db_path.unlink()
        print(f"[init_db] Removed existing database: {db_path}")

    print(f"[init_db] Initialising database: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        create_tables(conn)
        if args.seed:
            seed_data(conn)
        print("[init_db] Done.")
    except Exception as exc:
        print(f"[init_db] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
