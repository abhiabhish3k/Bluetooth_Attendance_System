# API Design Notes

See [API.md](API.md) for the full endpoint reference.

## Design Principles

1. **REST conventions** – resources are nouns, HTTP verbs express actions.
2. **Idempotency** – `POST /api/events` is safe to retry; the database unique
   constraint prevents duplicate attendance records.
3. **Validation at the boundary** – all inputs are validated in `validators.py`
   before entering business logic.
4. **Async throughout** – FastAPI + SQLAlchemy async avoids blocking the event
   loop during I/O.
5. **Separation of concerns** – API routes delegate to service functions; no
   SQL in route handlers.

## Event Processing Flow

```
POST /api/events
  → validate_scan_event()       # field presence + format
  → ScanEvent (Pydantic)        # type coercion
  → process_scan_event()        # business logic
      → scan_logs INSERT        # always
      → find active session
      → RSSI threshold check
      → student MAC lookup
      → attendance INSERT       # idempotent
  → return status dict
```

## Error Handling

- `422` – validation failures (missing fields, invalid MAC, RSSI out of range)
- `404` – resource not found (student, session, attendance record)
- `409` – unique constraint violation (duplicate student registration)
- `400` – logical errors (end_time before start_time, batch > 100 events)
