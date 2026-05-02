"""
Application configuration – reads from environment variables or a .env file.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings

REPO_ROOT = Path(__file__).resolve().parents[2]

logger = logging.getLogger(__name__)


def _detect_bluetooth_adapter() -> Optional[str]:
    """Return the name of the first available Bluetooth adapter (e.g. ``hci0``).

    Tries the standard sysfs path ``/sys/class/bluetooth`` first, then falls
    back to scanning ``/dev`` for ``hciN`` device nodes.  Returns ``None``
    when no adapter can be found (e.g. in a CI / container environment).
    """
    # Primary: sysfs exposes each adapter as a directory
    sysfs = Path("/sys/class/bluetooth")
    if sysfs.is_dir():
        adapters = sorted(p.name for p in sysfs.iterdir() if p.name.startswith("hci"))
        if adapters:
            return adapters[0]

    # Fallback: look for /dev/hciN character devices
    dev = Path("/dev")
    if dev.is_dir():
        adapters = sorted(p.name for p in dev.iterdir() if p.name.startswith("hci"))
        if adapters:
            return adapters[0]

    return None


def _resolve_bt_adapter() -> str:
    """Return the Bluetooth adapter name to use.

    Priority:
    1. ``BT_ADAPTER`` environment variable (explicit override).
    2. Auto-detected first available adapter from sysfs / dev.
    3. Hard-coded default ``hci0``.
    """
    env_override = os.environ.get("BT_ADAPTER", "").strip()
    if env_override:
        return env_override

    detected = _detect_bluetooth_adapter()
    if detected:
        return detected

    return "hci0"


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

    # Bluetooth adapter (auto-detected; can be overridden via BT_ADAPTER env var)
    bt_adapter: str = Field(
        default_factory=_resolve_bt_adapter,
        description=(
            "Bluetooth adapter name (e.g. hci0). Auto-detected from sysfs when "
            "not set. Override via BT_ADAPTER environment variable."
        ),
    )

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def scanner_backend_url(self) -> str:
        """URL where the stdout-reader thread POSTs BLE scan events.

        Derived from ``port`` so it stays consistent when the port is
        overridden via environment variable or .env file.
        """
        return f"http://127.0.0.1:{self.port}/api/events"

    def log_startup_config(self) -> None:
        """Emit all relevant configuration values at INFO level on startup."""
        logger.info("=== BLE Attendance System – configuration ===")
        logger.info("  app_name              : %s", self.app_name)
        logger.info("  app_version           : %s", self.app_version)
        logger.info("  debug                 : %s", self.debug)
        logger.info("  host                  : %s", self.host)
        logger.info("  port                  : %s", self.port)
        logger.info("  database_url          : %s", self.database_url)
        logger.info("  scanner_command       : %s", self.scanner_command)
        logger.info("  scanner_args          : %s", self.scanner_args)
        logger.info("  scanner_backend_url   : %s", self.scanner_backend_url)
        logger.info("  bt_adapter            : %s", self.bt_adapter)
        logger.info("  rssi_threshold        : %s dBm", self.rssi_attendance_threshold)
        logger.info("  session_grace_seconds : %s", self.session_close_grace_seconds)
        logger.info("  log_level             : %s", self.log_level)
        logger.info("=============================================")

    def validate_startup(self) -> list[str]:
        """Return a list of warning strings for potential configuration issues.

        Does not raise – callers should log the returned warnings and decide
        whether to abort or continue with degraded functionality.
        """
        warnings: list[str] = []

        scanner_path = Path(self.scanner_command)
        if not scanner_path.exists():
            warnings.append(
                f"Scanner binary not found: {self.scanner_command} – "
                "compile it with: cd scanner && cmake -B build && cmake --build build"
            )
        elif not os.access(self.scanner_command, os.X_OK):
            warnings.append(
                f"Scanner binary is not executable: {self.scanner_command} – "
                f"run: chmod +x {self.scanner_command}"
            )

        config_arg = self.scanner_args.split()[0] if self.scanner_args.strip() else ""
        if config_arg and not Path(config_arg).exists():
            warnings.append(
                f"Scanner config file not found: {config_arg}"
            )

        detected = _detect_bluetooth_adapter()
        if detected is None:
            warnings.append(
                "No Bluetooth adapter detected in /sys/class/bluetooth or /dev/hci* – "
                "ensure a BLE adapter is present and the bluetooth service is running "
                "(sudo systemctl start bluetooth)"
            )
        else:
            # Only warn about adapter mismatch when bt_adapter was not explicitly
            # overridden by the user via the BT_ADAPTER environment variable.
            env_override = os.environ.get("BT_ADAPTER", "").strip()
            if not env_override and detected != self.bt_adapter:
                warnings.append(
                    f"Configured adapter '{self.bt_adapter}' differs from detected "
                    f"adapter '{detected}' – set BT_ADAPTER={detected} to use the "
                    "detected adapter"
                )

        return warnings


settings = Settings()
