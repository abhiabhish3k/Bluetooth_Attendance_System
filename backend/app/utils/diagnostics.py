"""
System diagnostics utilities for the BLE Attendance System.

These helpers are called by the ``/api/health/diagnostics`` endpoint to
produce a comprehensive snapshot of the runtime environment, Bluetooth
hardware, and application configuration so that operators can quickly
identify root causes when the scanner fails to start or produce events.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .bluetooth_recovery import get_adapter_info


# ---------------------------------------------------------------------------
# Bluetooth / BlueZ helpers
# ---------------------------------------------------------------------------

def list_bluetooth_adapters() -> list[dict[str, Any]]:
    """Return a list of Bluetooth adapter info dicts found in sysfs.

    Each dict contains:
    - ``name``: adapter name (e.g. ``hci0``)
    - ``address``: BD_ADDR from sysfs (or ``null`` if not readable)
    - ``powered``: bool – whether the adapter is powered on
    """
    adapters: list[dict[str, Any]] = []
    sysfs = Path("/sys/class/bluetooth")
    if not sysfs.is_dir():
        return adapters

    for entry in sorted(sysfs.iterdir()):
        if not entry.name.startswith("hci"):
            continue
        addr: str | None = None
        powered: bool | None = None
        try:
            addr = (entry / "address").read_text().strip()
        except OSError:
            pass
        try:
            powered_val = (entry / "powered").read_text().strip()
            powered = powered_val == "1"
        except OSError:
            pass
        adapters.append({"name": entry.name, "address": addr, "powered": powered})

    return adapters


def check_dbus_available() -> dict[str, Any]:
    """Check whether the D-Bus system bus is reachable.

    Returns a dict with:
    - ``available``: bool
    - ``detail``: human-readable explanation
    """
    dbus_socket = Path("/run/dbus/system_bus_socket")
    if dbus_socket.exists():
        return {"available": True, "detail": "D-Bus system socket found"}

    # Some distros use a different path
    alt_socket = Path("/var/run/dbus/system_bus_socket")
    if alt_socket.exists():
        return {"available": True, "detail": "D-Bus system socket found (alt path)"}

    return {
        "available": False,
        "detail": (
            "D-Bus system socket not found – ensure dbus is running "
            "(sudo systemctl start dbus)"
        ),
    }


def check_bluetooth_service() -> dict[str, Any]:
    """Check whether the BlueZ (bluetooth) service is active.

    Returns a dict with:
    - ``active``: bool or None when systemctl is unavailable
    - ``detail``: output from systemctl or an explanation
    """
    if not shutil.which("systemctl"):
        return {"active": None, "detail": "systemctl not available"}

    try:
        result = subprocess.run(
            ["systemctl", "is-active", "bluetooth"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        active = result.stdout.strip() == "active"
        return {"active": active, "detail": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"active": None, "detail": "systemctl check timed out"}
    except Exception:
        return {"active": None, "detail": "systemctl check failed"}


# ---------------------------------------------------------------------------
# Scanner binary helpers
# ---------------------------------------------------------------------------

def check_scanner_binary(command: str) -> dict[str, Any]:
    """Check whether the scanner binary exists and is executable."""
    path = Path(command)
    exists = path.exists()
    executable = os.access(command, os.X_OK) if exists else False
    detail: str
    if not exists:
        detail = (
            f"Binary not found: {command} – compile with: "
            "cd scanner && cmake -B build && cmake --build build"
        )
    elif not executable:
        detail = f"Binary not executable: {command} – run: chmod +x {command}"
    else:
        detail = "Binary found and executable"

    return {"path": str(path), "exists": exists, "executable": executable, "detail": detail}


def check_scanner_config(config_path: str) -> dict[str, Any]:
    """Check whether the scanner config file exists and is valid JSON."""
    path = Path(config_path)
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "valid_json": False,
            "detail": f"Config file not found: {config_path}",
        }

    try:
        data = json.loads(path.read_text())
        return {
            "path": str(path),
            "exists": True,
            "valid_json": True,
            "adapter": data.get("adapter"),
            "rssi_threshold": data.get("rssi_threshold"),
            "log_file": data.get("log_file"),
            "log_level": data.get("log_level"),
            "detail": "Config file found and valid JSON",
        }
    except json.JSONDecodeError:
        return {
            "path": str(path),
            "exists": True,
            "valid_json": False,
            "detail": "Config file exists but contains invalid JSON",
        }
    except OSError:
        return {
            "path": str(path),
            "exists": True,
            "valid_json": False,
            "detail": "Config file exists but could not be read",
        }


# ---------------------------------------------------------------------------
# Consolidated health snapshot
# ---------------------------------------------------------------------------

def build_diagnostics() -> dict[str, Any]:
    """Return a comprehensive diagnostics snapshot.

    Aggregates Bluetooth adapter info, D-Bus availability, BlueZ service
    status, scanner binary checks, and configuration warnings from Settings.
    Includes per-adapter power state and recovery hints.
    """
    from ..config import settings

    adapters = list_bluetooth_adapters()
    dbus = check_dbus_available()
    bluetooth_svc = check_bluetooth_service()
    binary = check_scanner_binary(settings.scanner_command)

    config_arg = settings.scanner_args.split()[0] if settings.scanner_args.strip() else ""
    config_file = check_scanner_config(config_arg) if config_arg else None

    config_warnings = settings.validate_startup()

    # Detailed power-state check for the configured adapter
    adapter_detail = get_adapter_info(settings.bt_adapter)

    # Derive extra warnings from adapter state
    bt_warnings: list[str] = []
    if not adapter_detail["exists"]:
        bt_warnings.append(
            f"Adapter '{settings.bt_adapter}' not found in sysfs. "
            "Check: hciconfig -a"
        )
    elif adapter_detail["powered"] is False:
        bt_warnings.append(
            f"Adapter '{settings.bt_adapter}' exists but is NOT powered on. "
            f"Fix: sudo hciconfig {settings.bt_adapter} up  "
            f"or run: bash scripts/enable_bluetooth.sh"
        )

    overall_ok = (
        binary["executable"]
        and dbus["available"]
        and (bluetooth_svc["active"] is not False)
        and len(adapters) > 0
        and adapter_detail.get("powered") is True
        and not config_warnings
        and not bt_warnings
    )

    return {
        "overall_ok": overall_ok,
        "bluetooth_adapters": adapters,
        "adapter_detail": adapter_detail,
        "dbus": dbus,
        "bluetooth_service": bluetooth_svc,
        "scanner_binary": binary,
        "scanner_config": config_file,
        "config_warnings": config_warnings,
        "bluetooth_warnings": bt_warnings,
        "settings": {
            "scanner_command": settings.scanner_command,
            "scanner_args": settings.scanner_args,
            "scanner_backend_url": settings.scanner_backend_url,
            "bt_adapter": settings.bt_adapter,
            "rssi_attendance_threshold": settings.rssi_attendance_threshold,
            "session_close_grace_seconds": settings.session_close_grace_seconds,
        },
    }
