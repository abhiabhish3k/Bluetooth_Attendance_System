"""
Attendance database model and Pydantic schemas.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, UniqueConstraint
from pydantic import BaseModel
from .student import Base


class AttendanceORM(Base):
    """SQLAlchemy ORM model for the attendance table."""

    __tablename__ = "attendance"

    attendance_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.session_id", ondelete="CASCADE"),
                        nullable=False, index=True)
    detected_time = Column(DateTime, nullable=False)
    rssi = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "session_id", name="uq_student_session"),
    )


class ScanLogORM(Base):
    """SQLAlchemy ORM model for raw scan_logs table (debugging)."""

    __tablename__ = "scan_logs"

    log_id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(17), nullable=False, index=True)
    rssi = Column(Integer, nullable=False)
    device_name = Column(String(128), nullable=True)
    detected_time = Column(DateTime, nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.session_id", ondelete="SET NULL"),
                        nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AttendanceResponse(BaseModel):
    attendance_id: int
    student_id: int
    session_id: int
    detected_time: datetime
    rssi: int

    model_config = {"from_attributes": True}


class AttendanceReport(BaseModel):
    session_id: int
    class_name: str
    start_time: datetime
    end_time: Optional[datetime]
    total_students: int
    present_count: int
    absent_count: int
    records: list[dict]
