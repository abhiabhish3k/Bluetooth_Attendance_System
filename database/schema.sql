-- =============================================================================
-- Bluetooth Attendance System – Full Database Schema
-- =============================================================================
-- Compatible with: SQLite 3.x and PostgreSQL 12+
-- =============================================================================

PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- students
-- Stores registered students and their known BLE device MAC addresses.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS students (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    roll_number  TEXT    NOT NULL UNIQUE,
    email        TEXT    NOT NULL UNIQUE,
    mac_address  TEXT    NOT NULL UNIQUE,          -- "AA:BB:CC:DD:EE:FF" (upper-case)
    created_at   DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_students_mac  ON students (mac_address);
CREATE INDEX IF NOT EXISTS idx_students_roll ON students (roll_number);

-- -----------------------------------------------------------------------------
-- devices
-- Tracks secondary devices (a student may own multiple BLE devices).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    device_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    mac_address  TEXT    NOT NULL UNIQUE,
    device_type  TEXT    NOT NULL DEFAULT 'phone',  -- 'phone', 'laptop', 'wearable', ...
    owner_id     INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    registered_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_devices_owner ON devices (owner_id);
CREATE INDEX IF NOT EXISTS idx_devices_mac   ON devices (mac_address);

-- -----------------------------------------------------------------------------
-- sessions
-- Represents a single lecture / lab period during which attendance is taken.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name     TEXT    NOT NULL,
    start_time     DATETIME NOT NULL,
    end_time       DATETIME,                        -- NULL means session is still open
    threshold_rssi INTEGER NOT NULL DEFAULT -75,    -- dBm; weaker signals are ignored
    created_at     DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions (start_time);

-- -----------------------------------------------------------------------------
-- attendance
-- One row per (student, session) pair – first detection wins.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attendance (
    attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES students(id)          ON DELETE CASCADE,
    session_id    INTEGER NOT NULL REFERENCES sessions(session_id)  ON DELETE CASCADE,
    detected_time DATETIME NOT NULL,
    rssi          INTEGER  NOT NULL,
    UNIQUE (student_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance (student_id);
CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance (session_id);

-- -----------------------------------------------------------------------------
-- scan_logs
-- Raw log of every BLE detection event (including unknowns).
-- Used for debugging, RSSI analysis, and replaying events.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_logs (
    log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    mac_address   TEXT    NOT NULL,
    rssi          INTEGER NOT NULL,
    device_name   TEXT,
    detected_time DATETIME NOT NULL,
    session_id    INTEGER REFERENCES sessions(session_id) ON DELETE SET NULL,
    created_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_scan_logs_mac     ON scan_logs (mac_address);
CREATE INDEX IF NOT EXISTS idx_scan_logs_session ON scan_logs (session_id);
CREATE INDEX IF NOT EXISTS idx_scan_logs_time    ON scan_logs (detected_time);
