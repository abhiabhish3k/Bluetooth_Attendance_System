# BLE Beacon Protocol

This document describes the BLE advertisement format used by the student
beacon app and parsed by the C++ scanner.

---

## Overview

Each student's phone runs the `beacon_app` Flutter application, which
continuously broadcasts a **BLE advertisement** containing the student's
unique ID.  The Linux C++ scanner running on the Raspberry Pi reads the
advertisement and extracts the identifier, which is then used by the
Python backend to mark the student as present.

---

## Supported Beacon Formats

The scanner supports two manufacturer-data formats.  The first one
recognised for a given advertisement wins.

---

### Format 1 – Apple iBeacon (recommended)

Used by the Flutter beacon app via the `beacon_broadcast` package.

**BLE advertisement structure (AD record):**

```
Type : 0xFF  (Manufacturer Specific Data)
Len  : 26
Data :
  [0–1]  Company ID  : 0x4C 0x00  (Apple, little-endian = 0x004C)
  [2]    Subtype     : 0x02
  [3]    Subtype len : 0x15  (= 21 bytes following)
  [4–19] UUID        : 16 bytes (institution UUID, see below)
  [20–21] Major      : 2 bytes big-endian (class/institution identifier)
  [22–23] Minor      : 2 bytes big-endian (student beacon ID)
  [24]   TX Power    : 1 byte signed  (e.g. 0xC5 = -59 dBm)
```

**beacon_id produced by the scanner:**

```
"<major>:<minor>"
```

Examples:
- Major = 1, Minor = 1001  →  beacon_id = `"1:1001"`
- Major = 1, Minor = 42    →  beacon_id = `"1:42"`

The `beacon_id` is sent to the backend inside the JSON scan event.

---

### Format 2 – Custom BLE-Attendance Format (optional)

For scenarios where a custom manufacturer data encoding is preferred
(e.g. string IDs like `"CS001"`).

**BLE advertisement structure (AD record):**

```
Type : 0xFF  (Manufacturer Specific Data)
Data :
  [0–1]  Company ID  : 0xFF 0xFF  (private/internal = 0xFFFF, little-endian)
  [2]    Magic byte 0: 0x42  ('B')
  [3]    Magic byte 1: 0x41  ('A')
  [4]    Length      : N     (number of UTF-8 bytes that follow, max 61)
  [5–…]  unique_id   : N bytes of UTF-8 text (e.g. "CS001")
```

**beacon_id produced by the scanner:**

The raw UTF-8 string from the payload, e.g. `"CS001"`.

---

## Institution UUID

The default UUID used by the beacon app is:

```
A8B3F9E2-C4D5-4F6A-7B8C-9D0E1F2A3B4C
```

This is configured in:
- **beacon_app** : `lib/models/student_config.dart` → `BeaconDefaults.uuid`
- **scanner** : `config.json` → `"beacon_uuid"` (informational only; the
  scanner accepts all iBeacons regardless of UUID and reports the
  `<major>:<minor>` beacon_id)

If you want to filter by UUID to prevent collisions with other iBeacons in
the environment, add UUID filtering to the scanner's
`parseBeaconId()` function in `device_parser.cpp`.

---

## Data Flow

```
Student Phone
  └── beacon_app (Flutter)
        └── BeaconBroadcast.start(uuid, major, minor)
              └── BLE Advertisement (iBeacon, 20 Hz)

Raspberry Pi
  └── BlueZ (bluez daemon)
        └── D-Bus: InterfacesAdded / PropertiesChanged signals
              └── C++ BleScanner
                    └── parseManufacturerData() → DeviceParser::parseBeaconId()
                          └── DeviceEvent { address, rssi, timestamp, beacon_id }
                                └── Logger::logEvent() → JSON stdout
                                      └── curl POST /api/events

Python Backend
  └── POST /api/events
        └── ScanEvent { address, rssi, timestamp, name, beacon_id }
              └── attendance_logic.process_scan_event()
                    ├── Match by beacon_id → students.unique_id (primary)
                    ├── Match by beacon_id → student_beacon.beacon_data (fallback)
                    └── Match by MAC address (backward compatible fallback)
                          └── AttendanceORM created → student marked present
```

---

## Registration Flow

1. **Teacher registers the student** in the backend with a `unique_id`:
   ```bash
   curl -X POST http://localhost:8000/api/students \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Alice",
       "roll_number": "CS001",
       "email": "alice@example.com",
       "mac_address": "AA:BB:CC:DD:EE:FF",
       "unique_id": "1:1001"
     }'
   ```

2. **Teacher tells Alice**: "Your beacon ID is **1001**."

3. **Alice installs the app**, opens it, enters:
   - Name: Alice
   - Beacon ID: **1001**
   - (Advanced: Major stays at 1)

4. Alice taps **"Start Broadcasting"**.

5. The scanner detects the iBeacon with minor=1001, emits `beacon_id="1:1001"`.

6. The backend looks up `students.unique_id = "1:1001"` → finds Alice → marks present.

---

## Backward Compatibility

If a device does **not** advertise beacon data (no ManufacturerData), the
`beacon_id` field in the JSON event is omitted and the backend falls back
to MAC address matching – the same behaviour as before the beacon update.

---

## JSON Scan Event Schema

```json
{
  "address":   "AA:BB:CC:DD:EE:FF",
  "rssi":      -65,
  "timestamp": 1712345678,
  "name":      "Alice's iPhone",
  "beacon_id": "1:1001"
}
```

The `name` and `beacon_id` fields are optional.

---

## Student Beacon Table

The `student_beacon` database table tracks the beacon configuration per
student:

```sql
CREATE TABLE student_beacon (
    beacon_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL UNIQUE REFERENCES students(id) ON DELETE CASCADE,
    beacon_data TEXT    NOT NULL,   -- e.g. "1:1001"
    advertised  BOOLEAN NOT NULL DEFAULT 1,
    last_seen   DATETIME,
    created_at  DATETIME NOT NULL DEFAULT (datetime('now'))
);
```

Use `GET /api/students/{id}/beacon` to query this table and
`POST /api/students/{id}/beacon/register` to create or update a mapping.
