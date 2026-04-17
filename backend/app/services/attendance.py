"""
Attendance service re-export (for backwards compatibility).
"""
from .attendance_logic import (  # noqa: F401
    process_scan_event,
    get_attendance_report,
    set_active_session,
    get_active_session_id,
)
