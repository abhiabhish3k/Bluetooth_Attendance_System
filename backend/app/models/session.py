"""
Class session database model and Pydantic schemas.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, func
from pydantic import BaseModel, field_validator
from .student import Base


class SessionORM(Base):
    """SQLAlchemy ORM model for the sessions table."""

    __tablename__ = "sessions"

    session_id = Column(Integer, primary_key=True, index=True)
    class_name = Column(String(128), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    threshold_rssi = Column(Integer, nullable=False, default=-75)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class SessionCreate(BaseModel):
    class_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    threshold_rssi: int = -75

    @field_validator("class_name")
    @classmethod
    def validate_class_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Class name cannot be empty")
        return v

    @field_validator("threshold_rssi")
    @classmethod
    def validate_rssi(cls, v: int) -> int:
        if v < -120 or v > 10:
            raise ValueError("RSSI threshold must be between -120 and 10 dBm")
        return v


class SessionResponse(BaseModel):
    session_id: int
    class_name: str
    start_time: datetime
    end_time: Optional[datetime]
    threshold_rssi: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionUpdate(BaseModel):
    end_time: Optional[datetime] = None
    threshold_rssi: Optional[int] = None
