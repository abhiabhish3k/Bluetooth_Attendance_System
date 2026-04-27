"""
Application configuration – reads from environment variables or a .env file.
"""

from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Application
    app_name: str = "BLE Attendance System"
    app_version: str = "1.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./attendance.db",
        description="SQLAlchemy async database URL",
    )

    # BLE thresholds
    rssi_attendance_threshold: int = Field(
        default=-75,
        description="Minimum RSSI (dBm) to count a detection as attendance",
    )
    session_close_grace_seconds: int = Field(
        default=300,
        description="Seconds after session end_time during which scans still count",
    )

    # Scanner engine
    scanner_command: str = Field(
        default=str(REPO_ROOT / "scanner" / "build" / "bin" / "ble_scanner"),
        description="Path or command used to launch the C++ BLE scanner engine",
    )
    scanner_args: str = Field(
        default=str(REPO_ROOT / "scanner" / "config.json"),
        description="Space-separated extra arguments passed to the scanner command",
    )

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
