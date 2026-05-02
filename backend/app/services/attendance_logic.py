"""
Core attendance processing logic.

Receives validated BLE scan events, matches MAC addresses or beacon IDs to
students, and records attendance for the active session.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ..models.student import StudentORM, StudentBeaconORM
from ..models.session import SessionORM
from ..models.attendance import AttendanceORM, ScanLogORM
from ..config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scan event Pydantic schema
# ---------------------------------------------------------------------------
from pydantic import BaseModel, field_validator, model_validator
from ..utils.validators import (
    validate_mac_address,
    normalise_mac,
    validate_rssi,
    normalise_timestamp,
)


class ScanEvent(BaseModel):
    address: str
    rssi: int
    timestamp: int
    name: str = ""
    beacon_id: Optional[str] = None
    scanner_id: Optional[str] = None

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

    @field_validator("timestamp")
    @classmethod
    def normalise_ts(cls, v: int) -> int:
        """Normalise millisecond timestamps to seconds for backward compat."""
        return normalise_timestamp(v)

    @field_validator("beacon_id")
    @classmethod
    def clean_beacon_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v if v else None


# ---------------------------------------------------------------------------
# Active session cache (lightweight in-process cache)
# ---------------------------------------------------------------------------
_active_session_id: Optional[int] = None

_ACTIVE_SESSION_KEY = "active_session_id"


def set_active_session(session_id: Optional[int]) -> None:
    """Update the in-memory active-session cache."""
    global _active_session_id
    _active_session_id = session_id
    logger.info("Active session set to: %s", session_id)


async def persist_active_session(session_id: Optional[int], db: AsyncSession) -> None:
    """Persist the active session to the database and update the in-memory cache.

    Calling this from API endpoints (activate, create, delete) ensures that
    manual session switches survive backend restarts.
    """
    from ..models.settings import AppSettingORM

    set_active_session(session_id)

    value = str(session_id) if session_id is not None else None
    result = await db.execute(
        select(AppSettingORM).where(AppSettingORM.key == _ACTIVE_SESSION_KEY)
    )
    setting = result.scalar_one_or_none()
    if setting is None:
        db.add(AppSettingORM(key=_ACTIVE_SESSION_KEY, value=value))
    else:
        setting.value = value
    await db.commit()
    logger.info("Active session persisted to DB: %s", session_id)


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
      4. Match beacon_id → student (preferred) or MAC → student (fallback).
      5. Mark attendance (idempotent – first detection wins).

    Returns a status dict describing what happened.
    """
    detected_time = datetime.fromtimestamp(event.timestamp, tz=timezone.utc)

    logger.debug(
        "Processing scan event: addr=%s rssi=%d beacon_id=%s ts=%s",
        event.address,
        event.rssi,
        event.beacon_id or "none",
        detected_time.isoformat(),
    )

    # ------------------------------------------------------------------
    # Step 1: Find active session
    # ------------------------------------------------------------------
    session = await _find_active_session(db)
    session_id = session.session_id if session else None

    # ------------------------------------------------------------------
    # Step 2: Log raw event (including beacon_id if present)
    # ------------------------------------------------------------------
    scan_log = ScanLogORM(
        mac_address=event.address,
        rssi=event.rssi,
        device_name=event.name or None,
        beacon_id=event.beacon_id or None,
        detected_time=detected_time,
        session_id=session_id,
    )
    db.add(scan_log)
    await db.flush()

    if session is None:
        await db.commit()
        logger.info(
            "Scan ignored – no active session (addr=%s rssi=%d beacon_id=%s)",
            event.address, event.rssi, event.beacon_id or "none",
        )
        return {"status": "logged", "reason": "no_active_session", "mac": event.address}

    # ------------------------------------------------------------------
    # Step 3: RSSI threshold check
    # ------------------------------------------------------------------
    rssi_threshold = session.threshold_rssi or settings.rssi_attendance_threshold
    if event.rssi < rssi_threshold:
        await db.commit()
        logger.info(
            "Scan ignored – RSSI too low: addr=%s rssi=%d threshold=%d session=%s",
            event.address, event.rssi, rssi_threshold, session.session_id,
        )
        return {
            "status": "ignored",
            "reason": "rssi_below_threshold",
            "mac": event.address,
            "rssi": event.rssi,
            "threshold": rssi_threshold,
        }

    # ------------------------------------------------------------------
    # Step 4: Match student – beacon_id takes priority over MAC address
    # ------------------------------------------------------------------
    student = None

    if event.beacon_id:
        # Try matching via unique_id column on students table
        result = await db.execute(
            select(StudentORM).where(StudentORM.unique_id == event.beacon_id)
        )
        student = result.scalar_one_or_none()

        if student is not None:
            logger.debug(
                "Student matched by unique_id: student_id=%s beacon_id=%s",
                student.id, event.beacon_id,
            )
            # Update last_seen in the student_beacon table if a row exists
            beacon_result = await db.execute(
                select(StudentBeaconORM).where(
                    StudentBeaconORM.student_id == student.id
                )
            )
            beacon_row = beacon_result.scalar_one_or_none()
            if beacon_row is not None:
                beacon_row.last_seen = detected_time
                db.add(beacon_row)

        # Fallback: check the student_beacon mapping table
        if student is None:
            beacon_result = await db.execute(
                select(StudentBeaconORM).where(
                    StudentBeaconORM.beacon_data == event.beacon_id
                )
            )
            beacon_row = beacon_result.scalar_one_or_none()
            if beacon_row:
                stu_result = await db.execute(
                    select(StudentORM).where(StudentORM.id == beacon_row.student_id)
                )
                student = stu_result.scalar_one_or_none()

                # Update last_seen on the beacon row
                if student is not None:
                    logger.debug(
                        "Student matched by beacon_data mapping: student_id=%s beacon_id=%s",
                        student.id, event.beacon_id,
                    )
                    beacon_row.last_seen = detected_time
                    db.add(beacon_row)

    if student is None:
        # Fallback: match by MAC address
        result = await db.execute(
            select(StudentORM).where(StudentORM.mac_address == event.address)
        )
        student = result.scalar_one_or_none()
        if student is not None:
            logger.debug(
                "Student matched by MAC address: student_id=%s addr=%s",
                student.id, event.address,
            )

    if student is None:
        await db.commit()
        logger.info(
            "Scan ignored – unknown device: addr=%s beacon_id=%s session=%s",
            event.address, event.beacon_id or "none", session.session_id,
        )
        return {
            "status": "ignored",
            "reason": "unknown_device",
            "mac": event.address,
            "beacon_id": event.beacon_id,
        }

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
        logger.debug(
            "Attendance already marked: student_id=%s session=%s",
            student.id, session.session_id,
        )
        return {
            "status": "already_marked",
            "student_id": student.id,
            "session_id": session.session_id,
        }

    try:
        attendance = AttendanceORM(
            student_id=student.id,
            session_id=session.session_id,
            detected_time=detected_time,
            rssi=event.rssi,
        )
        db.add(attendance)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(
            "Failed to record attendance for student_id=%s session=%s: %s",
            student.id, session.session_id, exc,
        )
        raise

    matched_by = "beacon" if event.beacon_id else "mac"
    logger.info(
        "Attendance marked: student=%s (%s) session=%s rssi=%d matched_by=%s",
        student.id, student.name, session.session_id, event.rssi, matched_by,
    )

    result = {
        "status": "marked",
        "student_id": student.id,
        "student_name": student.name,
        "session_id": session.session_id,
        "rssi": event.rssi,
        "matched_by": matched_by,
    }

    # Broadcast attendance update to all connected dashboard WebSocket clients
    try:
        import asyncio
        from ..core.ws_manager import ws_manager
        asyncio.ensure_future(ws_manager.broadcast("attendance", {
            "type": "attendance_marked",
            "student_id": student.id,
            "student_name": student.name,
            "session_id": session.session_id,
            "rssi": event.rssi,
            "matched_by": matched_by,
            "timestamp": event.timestamp,
        }))
    except Exception as _exc:
        logger.debug("WS broadcast skipped: %s", _exc)

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _find_active_session(db: AsyncSession) -> Optional[SessionORM]:
    """Return the active session, preferring the manually-persisted session ID.

    Priority:
    1. If a session was manually activated via ``persist_active_session()``,
       validate that it is still open and return it.
       1a. If the in-memory cache is empty but a persisted value exists in the
           database (e.g. after a backend restart), restore it first.
    2. If the persisted session is no longer valid, fall back to the most
       recently *started* open session from the database.
    3. Clear the persisted value when the stored session is found invalid.
    """
    from ..models.settings import AppSettingORM

    now = datetime.now(tz=timezone.utc)

    # ------------------------------------------------------------------
    # Priority 1: use manually cached session if it is still open
    # ------------------------------------------------------------------
    active_id = _active_session_id

    # 1a: cache is empty – try restoring from DB (survives backend restarts)
    if active_id is None:
        db_result = await db.execute(
            select(AppSettingORM).where(AppSettingORM.key == _ACTIVE_SESSION_KEY)
        )
        setting = db_result.scalar_one_or_none()
        if setting and setting.value:
            try:
                restored_id = int(setting.value)
                set_active_session(restored_id)
                active_id = restored_id
                logger.info("Restored active session from DB: %s", restored_id)
            except (ValueError, TypeError):
                pass

    if active_id is not None:
        result = await db.execute(
            select(SessionORM).where(SessionORM.session_id == active_id)
        )
        session = result.scalar_one_or_none()
        if session is not None:
            start = session.start_time
            if not start.tzinfo:
                start = start.replace(tzinfo=timezone.utc)
            end = session.end_time
            if end is not None and not end.tzinfo:
                end = end.replace(tzinfo=timezone.utc)
            if start <= now and (end is None or end >= now):
                logger.debug(
                    "Using manually cached active session: %s", active_id
                )
                return session
            # Log why the cached session is rejected
            if start > now:
                logger.info(
                    "Cached session %s not yet started (start=%s now=%s); clearing cache",
                    active_id, start.isoformat(), now.isoformat(),
                )
            else:
                logger.info(
                    "Cached session %s has ended (end=%s now=%s); clearing cache",
                    active_id,
                    end.isoformat() if end else "None",
                    now.isoformat(),
                )
        else:
            logger.info(
                "Cached session %s not found in database; clearing cache", active_id
            )
        # Cached session is missing or no longer open – clear it
        set_active_session(None)

    # ------------------------------------------------------------------
    # Priority 2: auto-detect most recently started open session
    # ------------------------------------------------------------------
    result = await db.execute(
        select(SessionORM)
        .where(
            and_(
                SessionORM.start_time <= now,
                (SessionORM.end_time.is_(None)) | (SessionORM.end_time >= now),
            )
        )
        .order_by(SessionORM.start_time.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if session is not None:
        logger.info(
            "Auto-detected active session: id=%s class=%s start=%s",
            session.session_id,
            session.class_name,
            session.start_time.isoformat(),
        )
    else:
        logger.debug("No active session found (now=%s)", now.isoformat())
    return session


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
