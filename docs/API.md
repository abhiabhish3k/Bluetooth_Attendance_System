# API Documentation

Base URL: `http://localhost:8000`

Interactive Swagger UI: `http://localhost:8000/docs`

---

## Authentication

> Not required in Phase 1. Add API key / OAuth2 before production deployment.

---

## Endpoints

### Health & System

#### `GET /health`
Returns application health status.

**Response 200**
```json
{
  "status": "ok",
  "app": "BLE Attendance System",
  "version": "1.0.0"
}
```

---

### Scanner Events

#### `POST /api/events`
Receive a single BLE scan event from the C++ scanner.

**Request body**
```json
{
  "address": "AA:BB:CC:DD:EE:FF",
  "name": "Alice's iPhone",
  "rssi": -62,
  "timestamp": 1712345678
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `address` | string | ✅ | MAC address `XX:XX:XX:XX:XX:XX` |
| `rssi` | integer | ✅ | Signal strength in dBm (−120 to +10) |
| `timestamp` | integer | ✅ | Unix timestamp (seconds) |
| `name` | string | ❌ | Device advertising name |

**Response 200** – event processed
```json
{
  "status": "marked",
  "student_id": 3,
  "student_name": "Alice Johnson",
  "session_id": 1,
  "rssi": -62
}
```

Possible `status` values:

| Value | Meaning |
|-------|---------|
| `marked` | Attendance recorded |
| `already_marked` | Student already present in this session |
| `logged` | Logged to scan_logs but no active session |
| `ignored` | RSSI too weak or unknown device |

**Response 422** – validation error

---

#### `POST /api/events/batch`
Receive up to 100 events in a single request.

**Request body**: array of event objects (same schema as above).

**Response 200**
```json
{
  "processed": 2,
  "results": [...]
}
```

---

### Students

#### `GET /api/students`
List all registered students.

**Query params**

| Param | Type | Description |
|-------|------|-------------|
| `search` | string | Filter by name or roll number |

**Response 200**
```json
[
  {
    "id": 1,
    "name": "Alice Johnson",
    "roll_number": "CS2021001",
    "email": "alice@example.com",
    "mac_address": "AA:BB:CC:11:22:33",
    "created_at": "2024-01-15T08:00:00"
  }
]
```

---

#### `POST /api/students`
Register a new student.

**Request body**
```json
{
  "name": "Alice Johnson",
  "roll_number": "CS2021001",
  "email": "alice@example.com",
  "mac_address": "AA:BB:CC:11:22:33"
}
```

**Response 201** – student created  
**Response 409** – duplicate roll number, email, or MAC address  
**Response 422** – validation error

---

#### `GET /api/students/{student_id}`
Get a single student by ID.

**Response 200** – student object  
**Response 404** – not found

---

#### `PATCH /api/students/{student_id}`
Update a student's details.

**Request body** (all fields optional)
```json
{
  "name": "Alice J. Smith",
  "email": "alicenew@example.com",
  "mac_address": "AA:BB:CC:11:22:44"
}
```

---

#### `DELETE /api/students/{student_id}`
Delete a student (and their attendance records).

**Response 204** – deleted  
**Response 404** – not found

---

### Sessions

#### `GET /api/sessions`
List all class sessions ordered by start time (descending).

---

#### `POST /api/sessions`
Create a new attendance session.

**Request body**
```json
{
  "class_name": "CS101 – Introduction to Programming",
  "start_time": "2024-04-15T09:00:00Z",
  "end_time": "2024-04-15T10:00:00Z",
  "threshold_rssi": -75
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `class_name` | string | ✅ | Human-readable class name |
| `start_time` | datetime | ✅ | ISO 8601 UTC datetime |
| `end_time` | datetime | ❌ | If omitted, session stays open until patched |
| `threshold_rssi` | integer | ❌ | RSSI cut-off (default: −75 dBm) |

**Response 201** – session created

---

#### `GET /api/sessions/active`
Get the currently active session.

**Response 200**
```json
{
  "active": true,
  "session": {
    "session_id": 1,
    "class_name": "CS101",
    "start_time": "2024-04-15T09:00:00",
    "end_time": null,
    "threshold_rssi": -75,
    "created_at": "2024-04-15T08:55:00"
  }
}
```

---

#### `PATCH /api/sessions/{session_id}`
Update a session (e.g. set `end_time` to close it).

```json
{ "end_time": "2024-04-15T10:00:00Z" }
```

---

#### `POST /api/sessions/{session_id}/activate`
Manually set a session as the active session for new scan events.

---

### Attendance

#### `GET /api/attendance/report/{session_id}`
Get the full attendance report for a session.

**Response 200**
```json
{
  "session_id": 1,
  "class_name": "CS101",
  "start_time": "2024-04-15T09:00:00",
  "end_time": "2024-04-15T10:00:00",
  "total_students": 30,
  "present_count": 25,
  "absent_count": 5,
  "records": [
    {
      "student_id": 1,
      "name": "Alice Johnson",
      "roll_number": "CS2021001",
      "status": "present",
      "detected_time": "2024-04-15T09:02:34",
      "rssi": -62
    },
    {
      "student_id": 2,
      "name": "Bob Smith",
      "roll_number": "CS2021002",
      "status": "absent",
      "detected_time": null,
      "rssi": null
    }
  ]
}
```

---

#### `GET /api/attendance`
List attendance records with optional filtering.

**Query params**

| Param | Type | Description |
|-------|------|-------------|
| `session_id` | integer | Filter by session |
| `student_id` | integer | Filter by student |

---

#### `DELETE /api/attendance/{attendance_id}`
Delete an attendance record (e.g. to correct an error).

**Response 204** – deleted

---

## Error Responses

All errors follow RFC 7807 Problem Details format:

```json
{
  "detail": "Human-readable error description"
}
```

| Status Code | Meaning |
|-------------|---------|
| 400 | Bad request (e.g. invalid date range) |
| 404 | Resource not found |
| 409 | Conflict (duplicate unique field) |
| 422 | Validation error (field format invalid) |
| 500 | Internal server error |
