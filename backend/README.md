# BLE Attendance System – Python Backend

FastAPI backend that receives BLE scanner events and manages student attendance.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialise database
python ../database/init_db.py --seed

# Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or use the provided script
bash ../scripts/run_backend.sh
```

## API

- Interactive docs: http://localhost:8000/docs
- Full reference: [../docs/API.md](../docs/API.md)

## Configuration

Create a `.env` file in this directory:

```env
DATABASE_URL=sqlite+aiosqlite:///./attendance.db
RSSI_ATTENDANCE_THRESHOLD=-75
DEBUG=false
LOG_LEVEL=INFO
```

## Project Structure

```
app/
├── main.py                  # FastAPI app, DB engine
├── config.py                # Settings (pydantic-settings)
├── api/
│   ├── scanner.py           # POST /api/events
│   ├── students.py          # CRUD /api/students
│   ├── sessions.py          # CRUD /api/sessions
│   └── attendance.py        # GET /api/attendance
├── models/
│   ├── student.py           # ORM + Pydantic schemas
│   ├── session.py
│   └── attendance.py
├── services/
│   ├── attendance_logic.py  # Core business logic
│   └── scanner_ingest.py    # Line-by-line JSON parser
└── utils/
    ├── validators.py        # Input validation
    └── time.py              # Datetime helpers
```
