# Threat Model

## Assets

1. **Student attendance records** – accuracy and integrity of who was present.
2. **Student PII** – names, email addresses, roll numbers.
3. **System availability** – the scanner and backend must stay up during class.

## Threat Scenarios

### T1: MAC Address Spoofing
**Description**: A student clones another student's BLE MAC address.  
**Impact**: Fraudulent attendance mark.  
**Mitigation**:
- Combine BLE MAC detection with a secondary factor (mobile app OTP, NFC card).
- Log all raw scan events in `scan_logs` for post-hoc auditing.
- Monitor for simultaneous detection of the same MAC from multiple scanners (physical impossibility).

### T2: Replay Attack
**Description**: An attacker captures a scan event JSON payload and replays it.  
**Impact**: Marks attendance for a student who is not present.  
**Mitigation**:
- Validate `timestamp` field is within a recent window (e.g. ±60 seconds of server time).
- Add HMAC signature to events using a shared secret between scanner and backend.

### T3: Rogue Scanner
**Description**: Attacker posts fake events directly to `POST /api/events`.  
**Impact**: Marks attendance for absent students.  
**Mitigation**:
- Bind backend to `127.0.0.1` (localhost only) and route through an authenticated proxy.
- Add API key authentication to the events endpoint.

### T4: RSSI Distance Exploitation
**Description**: Student stands near the classroom door with strong signal, then leaves.  
**Impact**: Marked present without actually attending.  
**Mitigation**:
- Require multiple detections spread across the session duration (not just first detection).
- Use multiple scanners placed throughout the room to triangulate presence.

### T5: Database Injection
**Description**: Malformed MAC or name values in scan events.  
**Impact**: Data corruption, potential SQL injection.  
**Mitigation**:
- All inputs validated by `validators.py` before touching the database.
- SQLAlchemy ORM with parameterised queries – no raw SQL string interpolation.
- MAC addresses sanitised to `XX:XX:XX:XX:XX:XX` uppercase format.

### T6: Denial of Service
**Description**: Flood of fake scan events overwhelms the backend.  
**Impact**: Backend crashes, legitimate events dropped.  
**Mitigation**:
- Rate limiting middleware (add `slowapi` to FastAPI).
- Scanner-side deduplication reduces event volume.
- Batch endpoint limited to 100 events per request.

## Security Recommendations for Production

1. Add API key authentication to all endpoints.
2. Use HTTPS (TLS) for all HTTP traffic.
3. Bind backend to localhost; expose only through a reverse proxy (nginx).
4. Use PostgreSQL with restricted database user (no DROP TABLE privilege).
5. Enable audit logging for all attendance modifications.
6. Store student PII in accordance with local data protection regulations (GDPR, FERPA, etc.).
