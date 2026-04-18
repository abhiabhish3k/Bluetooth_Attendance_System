-- =============================================================================
-- Bluetooth Attendance System – Full Database Schema
-- =============================================================================
-- Compatible with: SQLite 3.x and PostgreSQL 12+
-- =============================================================================

PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- students
-- Stores registered students and their known BLE device MAC addresses.
-- unique_id is the student's beacon identifier broadcast via BLE (optional).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS students (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    roll_number  TEXT    NOT NULL UNIQUE,
    email        TEXT    NOT NULL UNIQUE,
    mac_address  TEXT    NOT NULL UNIQUE,          -- "AA:BB:CC:DD:EE:FF" (upper-case)
    unique_id    TEXT    UNIQUE,                   -- BLE beacon identifier (e.g. "1001")
    created_at   DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_students_mac       ON students (mac_address);
CREATE INDEX IF NOT EXISTS idx_students_roll      ON students (roll_number);
CREATE INDEX IF NOT EXISTS idx_students_unique_id ON students (unique_id);

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
-- beacon_id is set when the device is advertising a recognised beacon payload.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_logs (
    log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    mac_address   TEXT    NOT NULL,
    rssi          INTEGER NOT NULL,
    device_name   TEXT,
    beacon_id     TEXT,                            -- extracted beacon identifier, if any
    detected_time DATETIME NOT NULL,
    session_id    INTEGER REFERENCES sessions(session_id) ON DELETE SET NULL,
    created_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_scan_logs_mac      ON scan_logs (mac_address);
CREATE INDEX IF NOT EXISTS idx_scan_logs_session  ON scan_logs (session_id);
CREATE INDEX IF NOT EXISTS idx_scan_logs_time     ON scan_logs (detected_time);
CREATE INDEX IF NOT EXISTS idx_scan_logs_beacon   ON scan_logs (beacon_id);

-- -----------------------------------------------------------------------------
-- student_beacon
-- Tracks beacon advertisement configuration per student.
-- beacon_data is the string identifier broadcast by the student's phone.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS student_beacon (
    beacon_id   INTEGER  PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER  NOT NULL UNIQUE REFERENCES students(id) ON DELETE CASCADE,
    beacon_data TEXT     NOT NULL,                 -- e.g. "1001" (iBeacon minor value)
    advertised  BOOLEAN  NOT NULL DEFAULT 1,
    last_seen   DATETIME,
    created_at  DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_student_beacon_student ON student_beacon (student_id);
CREATE INDEX IF NOT EXISTS idx_student_beacon_data    ON student_beacon (beacon_data);
