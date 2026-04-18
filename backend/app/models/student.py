"""
Student database model and Pydantic schemas.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase
from pydantic import BaseModel, EmailStr, field_validator
import re


class Base(DeclarativeBase):
    pass


class StudentORM(Base):
    """SQLAlchemy ORM model for the students table."""

    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    roll_number = Column(String(32), unique=True, nullable=False, index=True)
    email = Column(String(256), unique=True, nullable=False)
    mac_address = Column(String(17), unique=True, nullable=False, index=True)
    unique_id = Column(String(64), unique=True, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class StudentBeaconORM(Base):
    """SQLAlchemy ORM model for the student_beacon table."""

    __tablename__ = "student_beacon"

    beacon_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    beacon_data = Column(String(64), nullable=False)
    advertised = Column(Boolean, nullable=False, default=True)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class StudentCreate(BaseModel):
    name: str
    roll_number: str
    email: str
    mac_address: str
    unique_id: Optional[str] = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        pattern = r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"
        if not re.match(pattern, v):
            raise ValueError("Invalid MAC address format. Expected XX:XX:XX:XX:XX:XX")
        return v.upper()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        if len(v) > 128:
            raise ValueError("Name too long (max 128 characters)")
        return v

    @field_validator("roll_number")
    @classmethod
    def validate_roll_number(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Roll number cannot be empty")
        return v

    @field_validator("unique_id")
    @classmethod
    def validate_unique_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if len(v) > 64:
            raise ValueError("unique_id too long (max 64 characters)")
        return v


class StudentResponse(BaseModel):
    id: int
    name: str
    roll_number: str
    email: str
    mac_address: str
    unique_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    mac_address: Optional[str] = None
    unique_id: Optional[str] = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        pattern = r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"
        if not re.match(pattern, v):
            raise ValueError("Invalid MAC address format. Expected XX:XX:XX:XX:XX:XX")
        return v.upper()

    @field_validator("unique_id")
    @classmethod
    def validate_unique_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if len(v) > 64:
            raise ValueError("unique_id too long (max 64 characters)")
        return v


# ---------------------------------------------------------------------------
# Beacon Pydantic schemas
# ---------------------------------------------------------------------------

class BeaconRegisterRequest(BaseModel):
    beacon_id: str

    @field_validator("beacon_id")
    @classmethod
    def validate_beacon_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("beacon_id cannot be empty")
        if len(v) > 64:
            raise ValueError("beacon_id too long (max 64 characters)")
        return v


class BeaconResponse(BaseModel):
    student_id: int
    beacon_id: str
    beacon_data: str
    advertised: bool
    last_seen: Optional[datetime]

    model_config = {"from_attributes": True}
