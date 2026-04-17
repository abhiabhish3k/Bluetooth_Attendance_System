# BLE Event Flow

## Signal Path: Device → Attendance Record

```
Student's Phone
       │
       │  Broadcasts BLE advertisements (ADV_IND / ADV_NONCONN_IND)
       ▼
Linux Kernel / BlueZ HCI Layer
       │
       │  hci0 receives advertising report
       ▼
BlueZ bluetoothd daemon
       │
       │  Creates /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF object
       │  Fires: ObjectManager.InterfacesAdded signal (first detection)
       │  Fires: Properties.PropertiesChanged signal (RSSI updates)
       ▼
C++ BleScanner (D-Bus message filter)
       │
       │  parseDevice1Properties()
       │    ├── extracts Address, Name, RSSI from D-Bus variant dict
       │    └── calls DeviceParser::buildEvent()
       ▼
DeviceParser
       │
       │  validateMac()   – format check
       │  validateRssi()  – range check [-120, +10]
       │  sanitiseName()  – strip control characters
       ▼
Deduplicator (5-second window)
       │
       │  If same MAC seen within 5s → discard
       │  Otherwise → update timestamp, pass through
       ▼
Logger
       │
       │  Writes JSON to stdout + log file:
       │  {"address":"AA:BB:CC:DD:EE:FF","name":"...","rssi":-62,"timestamp":1712345678}
       ▼
run_scanner.sh (pipe)
       │
       │  curl -X POST http://localhost:8000/api/events -d '<json>'
       ▼
FastAPI Backend: POST /api/events
       │
       │  validate_scan_event() – field presence + format
       │  ScanEvent Pydantic model – type coercion + MAC normalisation
       ▼
process_scan_event()
       │
       ├── log to scan_logs (always)
       │
       ├── find active session (by start_time <= now <= end_time)
       │
       ├── check rssi >= session.threshold_rssi
       │
       ├── SELECT student WHERE mac_address = event.address
       │
       └── INSERT INTO attendance (student_id, session_id, ...)
                │  – UNIQUE constraint prevents duplicates
                ▼
           {"status": "marked", "student_id": 3, ...}
```

## Deduplication Detail

The 5-second deduplication window prevents the backend from being flooded
with repeated detections of the same device.

```
t=0.0s  AA:BB:CC:11:22:33 seen → PASS (new)
t=0.5s  AA:BB:CC:11:22:33 seen → SUPPRESS (within 5s window)
t=2.1s  AA:BB:CC:11:22:33 seen → SUPPRESS
t=5.1s  AA:BB:CC:11:22:33 seen → PASS (window expired)
```

Even if multiple events reach the backend, the attendance table's
`UNIQUE(student_id, session_id)` constraint ensures idempotency.

## RSSI Proximity Mapping

| RSSI Range | Approximate Distance | Recommended Use |
|------------|---------------------|-----------------|
| > -55 dBm  | < 1 metre           | Desk-level check-in |
| -55 to -65 | 1–3 metres          | Small seminar room |
| -65 to -75 | 3–7 metres          | Normal classroom |
| -75 to -85 | 7–15 metres         | Large lecture hall |
| < -85 dBm  | > 15 metres         | Should be ignored |
