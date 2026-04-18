# Bluetooth Attendance System

A production-grade, automated student attendance system using Bluetooth Low Energy (BLE).

Students run a **beacon app** on their phones that advertises their unique student ID via
BLE manufacturer data.  The C++ scanner on a Raspberry Pi (or any Linux machine with
BlueZ) detects the beacons, emits structured JSON events, and the Python FastAPI backend
matches beacon IDs to registered students, recording attendance in a SQLite database.

MAC-address-based detection is still fully supported as a fallback for devices without
the beacon app.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│            Student Phones (beacon_app Flutter)                 │
│  BLE iBeacon: UUID / Major / Minor (= student beacon ID)       │
└──────────────────────────┬─────────────────────────────────────┘
                           │ BLE radio
                           ▼
┌────────────────────────────────────────────────────────────────┐
│              C++ Scanner (BlueZ D-Bus, Linux)                  │
│  Parses ManufacturerData → extracts beacon_id                  │
│  JSON: {"address":"AA:BB:...","rssi":-62,"timestamp":...,      │
│         "beacon_id":"1:1001"}                                   │
└──────────────────────────┬─────────────────────────────────────┘
                           │ HTTP POST /api/events
                           ▼
┌────────────────────────────────────────────────────────────────┐
│              Python FastAPI Backend                            │
│  Matches beacon_id → student.unique_id                         │
│  Falls back to MAC address if no beacon data                   │
└──────────────────────────┬─────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────────────┐
│                     SQLite Database                            │
│  students · sessions · attendance · scan_logs · student_beacon │
└────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
bluetooth-attendance-system/
├── beacon_app/               # Flutter student beacon app (Android + iOS)
│   ├── pubspec.yaml
│   ├── README.md
│   ├── lib/
│   │   ├── main.dart
│   │   ├── models/student_config.dart
│   │   ├── screens/
│   │   │   ├── login_screen.dart
│   │   │   └── beacon_screen.dart
│   │   └── services/beacon_service.dart
│   ├── android/              # Android manifest + permissions
│   └── ios/                  # iOS Info.plist + background modes
├── scanner/                  # C++ BLE scanner (BlueZ D-Bus)
│   ├── CMakeLists.txt
│   ├── config.json
│   ├── include/              # Header files
│   │   ├── ble_scanner.h
│   │   ├── device_parser.h
│   │   ├── deduplicator.h
│   │   └── logger.h
│   └── src/                  # Implementation files
│       ├── main.cpp
│       ├── ble_scanner.cpp
│       ├── device_parser.cpp
│       ├── deduplicator.cpp
│       └── logger.cpp
├── backend/                  # Python FastAPI backend
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── api/              # REST endpoints
│       ├── models/           # SQLAlchemy + Pydantic models
│       ├── services/         # Business logic
│       └── utils/            # Validators, helpers
├── database/
│   ├── schema.sql            # Full DB schema
│   └── init_db.py            # Initialisation script
├── shared/
│   ├── protocols/            # JSON Schema event specs
│   ├── constants/            # Threshold configs
│   └── utils/                # Shared Python utilities
├── scripts/
│   ├── build_scanner.sh
│   ├── run_scanner.sh
│   ├── run_backend.sh
│   └── reset_db.sh
└── docs/
    ├── architecture.md
    ├── API.md
    └── BEACON_PROTOCOL.md    # Beacon format & integration guide
```

---

## Quick Start

### 1. System Requirements

- Linux with BlueZ (Ubuntu 20.04+ recommended)
- CMake ≥ 3.14, GCC/Clang with C++17 support
- Python ≥ 3.10
- Bluetooth adapter (USB or built-in)

### 2. Build the C++ Scanner

```bash
bash scripts/build_scanner.sh
```

### 3. Set Up the Python Backend

```bash
cd backend
pip install -r requirements.txt
```

### 4. Initialise the Database

```bash
python database/init_db.py --seed   # creates DB + sample data
```

### 5. Start the Backend

```bash
bash scripts/run_backend.sh
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### 6. Register Students

Register each student with an optional `unique_id` (the beacon ID they will
broadcast from the phone app):

```bash
curl -X POST http://localhost:8000/api/students \
  -H "Content-Type: application/json" \
  -d '{"name":"Alice","roll_number":"CS001","email":"alice@example.com","mac_address":"AA:BB:CC:DD:EE:FF","unique_id":"1:1001"}'
```

If you need to add or update a beacon registration later:

```bash
curl -X POST http://localhost:8000/api/students/1/beacon/register \
  -H "Content-Type: application/json" \
  -d '{"beacon_id": "1:1001"}'
```

### 7. Create a Session

```bash
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"class_name":"CS101","start_time":"2024-01-15T09:00:00Z","threshold_rssi":-75}'
```

### 8. Run the Scanner

```bash
sudo bash scripts/run_scanner.sh
```

### 9. Get Attendance Report

```bash
curl http://localhost:8000/api/attendance/report/1
```

---

## Configuration

### Scanner (`scanner/config.json`)

| Key | Default | Description |
|-----|---------|-------------|
| `adapter` | `hci0` | Bluetooth adapter name |
| `rssi_threshold` | `-80` | Ignore signals weaker than this (dBm) |
| `dedup_window` | `5` | Seconds to suppress duplicate events |
| `log_file` | `scanner.log` | Log file path |
| `log_level` | `INFO` | Log verbosity (DEBUG/INFO/WARN/ERROR) |
| `beacon_uuid` | `A8B3F9E2-...` | Expected iBeacon UUID (informational) |
| `beacon_major` | `1` | Expected iBeacon Major (informational) |

### Backend (environment variables or `.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./attendance.db` | Database URL |
| `RSSI_ATTENDANCE_THRESHOLD` | `-75` | Minimum RSSI to mark attendance |
| `DEBUG` | `false` | Enable debug mode |
| `PORT` | `8000` | Server port |

---

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/events` | Receive a BLE scan event |
| `POST` | `/api/events/batch` | Receive multiple events |
| `GET`  | `/api/students` | List students |
| `POST` | `/api/students` | Register a student |
| `POST` | `/api/students/{id}/beacon/register` | Register beacon ID for a student |
| `GET`  | `/api/students/{id}/beacon` | Get a student's beacon registration |
| `POST` | `/api/sessions` | Create a session |
| `GET`  | `/api/sessions/active` | Get active session |
| `GET`  | `/api/attendance/report/{id}` | Get attendance report |
| `GET`  | `/health` | Health check |

Full documentation: [docs/API.md](docs/API.md)

---

## Data Flow Detail

1. **C++ Scanner** starts BlueZ discovery on `hci0`
2. BlueZ fires D-Bus `InterfacesAdded` / `PropertiesChanged` signals as devices are seen
3. Scanner extracts MAC address, RSSI, device name, **and ManufacturerData** → parses beacon_id
4. 5-second deduplication prevents spam from the same device
5. JSON event (including `beacon_id` if detected) is sent via `curl` to `POST /api/events`
6. Backend validates the event:
   - If `beacon_id` is present → look up `students.unique_id` or `student_beacon.beacon_data`
   - Otherwise → fall back to MAC address look-up (backward compatible)
7. If a matching student is found and RSSI ≥ threshold, attendance is recorded
8. Teacher queries `GET /api/attendance/report/{session_id}` for the final list

See [docs/BEACON_PROTOCOL.md](docs/BEACON_PROTOCOL.md) for the full beacon integration guide.

---

## License

MIT License – see [LICENSE](LICENSE) for details.
