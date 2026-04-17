"""
Core attendance processing logic.

Receives validated BLE scan events, matches MAC addresses to students,
and records attendance for the active session.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ..models.student import StudentORM
from ..models.session import SessionORM
from ..models.attendance import AttendanceORM, ScanLogORM
from ..config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scan event Pydantic schema
# ---------------------------------------------------------------------------
from pydantic import BaseModel, field_validator
from ..utils.validators import validate_mac_address, normalise_mac, validate_rssi


class ScanEvent(BaseModel):
    address: str
    rssi: int
    timestamp: int
    name: str = ""

    @field_validator("address")
    @classmethod
    def norm_mac(cls, v: str) -> str:
        if not validate_mac_address(v):
            raise ValueError(f"Invalid MAC address: {v}")
        return normalise_mac(v)

    @field_validator("rssi")
    @classmethod
    def check_rssi(cls, v: int) -> int:
        if not validate_rssi(v):
            raise ValueError(f"RSSI {v} out of valid range")
        return v


# ---------------------------------------------------------------------------
# Active session cache (lightweight in-process cache)
# ---------------------------------------------------------------------------
_active_session_id: Optional[int] = None


def set_active_session(session_id: Optional[int]) -> None:
    """Set the globally active session ID."""
    global _active_session_id
    _active_session_id = session_id
    logger.info("Active session set to: %s", session_id)


def get_active_session_id() -> Optional[int]:
    """Return the currently active session ID, or None."""
    return _active_session_id


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

async def process_scan_event(event: ScanEvent, db: AsyncSession) -> dict:
    """
    Process a BLE scan event:
      1. Log it to scan_logs (always).
      2. Find the active session (from DB if not cached).
      3. Check if event meets RSSI threshold.
      4. Match MAC to a student.
      5. Mark attendance (idempotent – first detection wins).

    Returns a status dict describing what happened.
    """
    detected_time = datetime.fromtimestamp(event.timestamp, tz=timezone.utc)

    # ------------------------------------------------------------------
    # Step 1: Find active session
    # ------------------------------------------------------------------
    session = await _find_active_session(db)
    session_id = session.session_id if session else None

    # ------------------------------------------------------------------
    # Step 2: Log raw event
    # ------------------------------------------------------------------
    scan_log = ScanLogORM(
        mac_address=event.address,
        rssi=event.rssi,
        device_name=event.name or None,
        detected_time=detected_time,
        session_id=session_id,
    )
    db.add(scan_log)
    await db.flush()

    if session is None:
        await db.commit()
        return {"status": "logged", "reason": "no_active_session", "mac": event.address}

    # ------------------------------------------------------------------
    # Step 3: RSSI threshold check
    # ------------------------------------------------------------------
    rssi_threshold = session.threshold_rssi or settings.rssi_attendance_threshold
    if event.rssi < rssi_threshold:
        await db.commit()
        return {
            "status": "ignored",
            "reason": "rssi_below_threshold",
            "mac": event.address,
            "rssi": event.rssi,
            "threshold": rssi_threshold,
        }

    # ------------------------------------------------------------------
    # Step 4: Match MAC to student
    # ------------------------------------------------------------------
    result = await db.execute(
        select(StudentORM).where(StudentORM.mac_address == event.address)
    )
    student = result.scalar_one_or_none()

    if student is None:
        await db.commit()
        return {"status": "ignored", "reason": "unknown_device", "mac": event.address}

    # ------------------------------------------------------------------
    # Step 5: Record attendance (idempotent)
    # ------------------------------------------------------------------
    existing = await db.execute(
        select(AttendanceORM).where(
            and_(
                AttendanceORM.student_id == student.id,
                AttendanceORM.session_id == session.session_id,
            )
        )
    )
    if existing.scalar_one_or_none() is not None:
        await db.commit()
        return {
            "status": "already_marked",
            "student_id": student.id,
            "session_id": session.session_id,
        }

    attendance = AttendanceORM(
        student_id=student.id,
        session_id=session.session_id,
        detected_time=detected_time,
        rssi=event.rssi,
    )
    db.add(attendance)
    await db.commit()

    logger.info(
        "Attendance marked: student=%s session=%s rssi=%d",
        student.id, session.session_id, event.rssi,
    )
    return {
        "status": "marked",
        "student_id": student.id,
        "student_name": student.name,
        "session_id": session.session_id,
        "rssi": event.rssi,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _find_active_session(db: AsyncSession) -> Optional[SessionORM]:
    """Return the most recently started open session, or None."""
    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        select(SessionORM)
        .where(
            and_(
                SessionORM.start_time <= now,
                (SessionORM.end_time == None) | (SessionORM.end_time >= now),  # noqa: E711
            )
        )
        .order_by(SessionORM.start_time.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_attendance_report(session_id: int, db: AsyncSession) -> dict:
    """
    Return an attendance summary for a given session.
    """
    # Get session info
    sess_result = await db.execute(
        select(SessionORM).where(SessionORM.session_id == session_id)
    )
    session = sess_result.scalar_one_or_none()
    if session is None:
        return {}

    # Get all students
    all_students = (await db.execute(select(StudentORM))).scalars().all()

    # Get attendance records for this session
    att_result = await db.execute(
        select(AttendanceORM).where(AttendanceORM.session_id == session_id)
    )
    attendance_records = att_result.scalars().all()
    present_ids = {r.student_id for r in attendance_records}

    records = []
    for student in all_students:
        att = next((r for r in attendance_records if r.student_id == student.id), None)
        records.append({
            "student_id": student.id,
            "name": student.name,
            "roll_number": student.roll_number,
            "status": "present" if student.id in present_ids else "absent",
            "detected_time": att.detected_time.isoformat() if att else None,
            "rssi": att.rssi if att else None,
        })

    return {
        "session_id": session.session_id,
        "class_name": session.class_name,
        "start_time": session.start_time.isoformat(),
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "total_students": len(all_students),
        "present_count": len(present_ids),
        "absent_count": len(all_students) - len(present_ids),
        "records": records,
    }
