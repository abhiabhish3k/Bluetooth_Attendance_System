# Database Design

## Entity Relationship Overview

```
students ──(1:N)── devices
students ──(1:N)── attendance
sessions ──(1:N)── attendance
sessions ──(1:N)── scan_logs
```

## Tables

### `students`
Primary entity. Stores one registered student per row.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Student full name |
| roll_number | TEXT UNIQUE | Institution roll number |
| email | TEXT UNIQUE | Student email |
| mac_address | TEXT UNIQUE | Primary BLE device MAC (upper-case) |
| created_at | DATETIME | Row creation timestamp |

### `devices`
Allows a student to register multiple BLE devices.

| Column | Type | Notes |
|--------|------|-------|
| device_id | INTEGER PK | Auto-increment |
| mac_address | TEXT UNIQUE | Device MAC address |
| device_type | TEXT | 'phone', 'laptop', 'wearable', … |
| owner_id | INTEGER FK | → students.id |
| registered_at | DATETIME | Registration timestamp |

### `sessions`
A single lecture/lab period.

| Column | Type | Notes |
|--------|------|-------|
| session_id | INTEGER PK | Auto-increment |
| class_name | TEXT | e.g. "CS101 – Data Structures" |
| start_time | DATETIME | When the session begins |
| end_time | DATETIME NULL | NULL = session still open |
| threshold_rssi | INTEGER | Minimum RSSI to count attendance (default: −75) |
| created_at | DATETIME | Row creation timestamp |

### `attendance`
One row per (student, session) pair.

| Column | Type | Notes |
|--------|------|-------|
| attendance_id | INTEGER PK | Auto-increment |
| student_id | INTEGER FK | → students.id |
| session_id | INTEGER FK | → sessions.session_id |
| detected_time | DATETIME | First detection timestamp |
| rssi | INTEGER | RSSI at first detection |

**Unique constraint**: `(student_id, session_id)` – idempotent, first detection wins.

### `scan_logs`
Raw event log. Every BLE detection (including unknowns) lands here.

| Column | Type | Notes |
|--------|------|-------|
| log_id | INTEGER PK | Auto-increment |
| mac_address | TEXT | Detected device MAC |
| rssi | INTEGER | Signal strength |
| device_name | TEXT NULL | Advertising name if available |
| detected_time | DATETIME | Detection timestamp |
| session_id | INTEGER FK NULL | Active session at detection time |
| created_at | DATETIME | Row insert timestamp |

## Indexes

| Table | Column(s) | Purpose |
|-------|-----------|---------|
| students | mac_address | MAC lookup during event processing |
| students | roll_number | Search by roll number |
| devices | mac_address | MAC lookup (secondary devices) |
| devices | owner_id | List devices for a student |
| sessions | start_time | Find active session by time range |
| attendance | student_id | Fetch records for a student |
| attendance | session_id | Fetch records for a session |
| scan_logs | mac_address | Debug: find all detections for a device |
| scan_logs | session_id | Debug: find all detections in a session |
| scan_logs | detected_time | Debug: time-range queries |

## Constraints

- `students.mac_address` format enforced at application layer: `XX:XX:XX:XX:XX:XX` (upper-case)
- `attendance.rssi` must be in range [−120, +10] dBm (enforced at application layer)
- `sessions.end_time` must be after `start_time` (enforced at application layer)
