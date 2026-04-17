# System Architecture

## Overview

The Bluetooth Attendance System is composed of three main layers:

```
┌─────────────────────────────────────────────────────────────┐
│                     BLE Devices (Phones)                    │
│              Broadcast Bluetooth advertisements             │
└─────────────────────────┬───────────────────────────────────┘
                          │ BLE radio signals
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  Linux BLE Hardware Layer                   │
│                 BlueZ (Bluetooth Daemon)                    │
│           /org/bluez/hci0  (D-Bus ObjectManager)           │
└─────────────────────────┬───────────────────────────────────┘
                          │ D-Bus signals
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              C++ BLE Scanner (scanner/)                     │
│                                                             │
│  BleScanner ──→ DeviceParser ──→ Deduplicator ──→ Logger   │
│                                                             │
│  Output: {"address":"...","rssi":-62,"timestamp":...}       │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP POST (JSON)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Python FastAPI Backend (backend/)              │
│                                                             │
│  /api/events ──→ attendance_logic ──→ Database              │
│  /api/students                                              │
│  /api/sessions                                              │
│  /api/attendance/report                                     │
└─────────────────────────┬───────────────────────────────────┘
                          │ SQLAlchemy async
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   SQLite Database                           │
│                                                             │
│  students │ sessions │ attendance │ scan_logs │ devices     │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Descriptions

### 1. C++ Scanner (`scanner/`)

**Purpose**: Hardware-facing BLE sensor layer.

**Key classes**:

| Class | File | Responsibility |
|-------|------|----------------|
| `BleScanner` | `ble_scanner.cpp` | D-Bus connection, BlueZ discovery, signal parsing |
| `DeviceParser` | `device_parser.cpp` | MAC extraction, RSSI/name validation |
| `Deduplicator` | `deduplicator.cpp` | Suppress duplicate events within time window |
| `Logger` | `logger.cpp` | JSON event output + human-readable logs |

**D-Bus signals monitored**:
- `org.freedesktop.DBus.ObjectManager.InterfacesAdded` – new device discovered
- `org.freedesktop.DBus.Properties.PropertiesChanged` (for `org.bluez.Device1`) – RSSI update

**Output format**:
```json
{"address":"AA:BB:CC:DD:EE:FF","name":"Alice's Phone","rssi":-62,"timestamp":1712345678}
```

---

### 2. Python Backend (`backend/`)

**Purpose**: Business logic, REST API, persistence.

**Technology**: FastAPI + SQLAlchemy (async) + Pydantic v2

**Modules**:

| Module | Purpose |
|--------|---------|
| `app/main.py` | FastAPI app, DB engine, startup/shutdown |
| `app/config.py` | Settings from environment variables |
| `app/api/scanner.py` | POST /api/events – receive scan events |
| `app/api/students.py` | CRUD for student registration |
| `app/api/sessions.py` | CRUD for class sessions |
| `app/api/attendance.py` | Attendance reports and queries |
| `app/services/attendance_logic.py` | Core processing: MAC lookup → attendance marking |
| `app/utils/validators.py` | Input validation functions |

---

### 3. Database (`database/`)

**Technology**: SQLite (development) / PostgreSQL (production)

**Tables**:

| Table | Purpose |
|-------|---------|
| `students` | Registered students with MAC addresses |
| `devices` | Secondary devices per student |
| `sessions` | Class periods (start/end time, RSSI threshold) |
| `attendance` | One row per (student, session) – first detection wins |
| `scan_logs` | All raw BLE detections (for debugging / auditing) |

---

## Data Flow (Detailed)

```
1. Teacher creates a session via POST /api/sessions
        {class_name: "CS101", start_time: "...", threshold_rssi: -75}

2. Students enter the classroom with their phones

3. C++ scanner detects devices:
   BlueZ D-Bus signal → BleScanner::handleInterfacesAdded()
   → DeviceParser::buildEvent()
   → Deduplicator::shouldProcess()  [5-second window]
   → Logger::logEvent()  →  stdout JSON

4. run_scanner.sh pipes JSON to backend:
   curl -X POST /api/events -d '{"address":"...","rssi":-62,"timestamp":...}'

5. Backend processes event:
   validate_scan_event() → ScanEvent()
   → process_scan_event()
     → find active session
     → check RSSI >= threshold_rssi
     → look up MAC in students table
     → INSERT INTO attendance (idempotent)

6. Teacher queries report:
   GET /api/attendance/report/1
   → Returns list of all students with present/absent status
```

---

## Security Considerations

- **Spoofing**: BLE MAC addresses can be spoofed. For high-security deployments,
  combine with an application-level token (e.g. student app with a rotating code).
- **RSSI accuracy**: RSSI varies with device hardware, orientation, and obstacles.
  Calibrate thresholds in your specific environment.
- **Database**: Use PostgreSQL + proper credentials for production deployments.
- **API authentication**: Add OAuth2 or API key middleware before exposing the
  backend on a public network.

---

## Scalability Notes

- **Multiple scanners**: Deploy one scanner per room; all scanners POST to the same
  backend URL. Sessions are shared by `session_id`.
- **Database**: Swap `sqlite+aiosqlite` for `postgresql+asyncpg` in `DATABASE_URL`.
- **Scanner → Backend**: The current shell pipe (`run_scanner.sh`) is suitable for
  a single machine. For multi-room setups use MQTT or a message queue.
