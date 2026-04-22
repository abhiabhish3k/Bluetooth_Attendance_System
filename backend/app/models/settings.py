"""
Application settings persisted to the database.

A lightweight key/value store used to survive backend restarts
(e.g. the currently active session ID).
"""

from sqlalchemy import Column, String
from .student import Base


class AppSettingORM(Base):
    """SQLAlchemy ORM model for the app_settings table."""

    __tablename__ = "app_settings"

    key = Column(String(64), primary_key=True)
    value = Column(String(256), nullable=True)
