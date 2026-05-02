"""
Bluetooth adapter recovery utilities.

These helpers are called by the scanner control service to:
- Check whether the Bluetooth adapter is powered on
- Attempt to power on the adapter automatically (via hciconfig or bluetoothctl)
- Wait for the adapter to become ready before starting the scanner
- Provide clear troubleshooting guidance when automatic recovery fails

Recovery flow used by the scanner pre-flight check::

    attempt_recovery(adapter)
        ├─ check_adapter_powered()  → already on → return success=True, needed=False
        ├─ power_on_adapter()
        │   ├─ _try_hciconfig_up()    → succeeded → return success=True
        │   └─ _try_bluetoothctl_power_on()
        └─ wait_for_adapter_ready()  → poll sysfs until powered or timeout
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# Seconds between power-state polls while waiting for the adapter to come up
_POWER_ON_POLL_INTERVAL: float = 1.0

# Maximum seconds to wait after a power-on command before declaring failure
_POWER_ON_TIMEOUT: int = 15


# ---------------------------------------------------------------------------
# Low-level sysfs helpers
# ---------------------------------------------------------------------------

def check_adapter_powered(adapter: str) -> bool:
    """Return True when *adapter* is powered on according to sysfs.

    Reads ``/sys/class/bluetooth/<adapter>/powered``.  Returns ``False`` if
    the path cannot be read (adapter absent, sysfs unavailable, etc.).
    """
    powered_path = Path(f"/sys/class/bluetooth/{adapter}/powered")
    try:
        return powered_path.read_text().strip() == "1"
    except OSError:
        return False


def get_adapter_info(adapter: str) -> dict[str, Any]:
    """Return a detailed info dict for a specific adapter.

    Keys:
    - ``adapter``: the adapter name (e.g. ``hci0``)
    - ``exists``: whether the adapter is visible in sysfs
    - ``powered``: bool or ``None`` when not readable
    - ``address``: BD_ADDR string or ``None``
    - ``detail``: human-readable summary including fix hints
    """
    sysfs_path = Path(f"/sys/class/bluetooth/{adapter}")
    if not sysfs_path.exists():
        return {
            "adapter": adapter,
            "exists": False,
            "powered": None,
            "address": None,
            "detail": (
                f"Adapter '{adapter}' not found in sysfs. "
                "Check available adapters with: hciconfig -a  or  ls /sys/class/bluetooth/"
            ),
        }

    powered: bool | None = None
    address: str | None = None

    try:
        powered = (sysfs_path / "powered").read_text().strip() == "1"
    except OSError:
        pass

    try:
        address = (sysfs_path / "address").read_text().strip()
    except OSError:
        pass

    if powered is True:
        detail = f"Adapter '{adapter}' is present and powered on"
    elif powered is False:
        detail = (
            f"Adapter '{adapter}' is present but NOT powered on. "
            f"Fix: sudo hciconfig {adapter} up  or  sudo bluetoothctl power on"
        )
    else:
        detail = f"Adapter '{adapter}' is present but power state is unknown"

    return {
        "adapter": adapter,
        "exists": True,
        "powered": powered,
        "address": address,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Power-on helpers
# ---------------------------------------------------------------------------

def _try_hciconfig_up(adapter: str) -> dict[str, Any]:
    """Attempt to power on *adapter* via ``sudo hciconfig <adapter> up``."""
    try:
        result = subprocess.run(
            ["sudo", "hciconfig", adapter, "up"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            logger.info("Powered on Bluetooth adapter '%s' via hciconfig", adapter)
            return {
                "success": True,
                "method": "hciconfig",
                "detail": f"hciconfig {adapter} up succeeded",
            }
        detail = (result.stderr or result.stdout or "no output").strip()
        logger.debug(
            "hciconfig %s up failed (code=%d): %s", adapter, result.returncode, detail
        )
        return {"success": False, "method": "hciconfig", "detail": detail}
    except FileNotFoundError:
        return {"success": False, "method": "hciconfig", "detail": "hciconfig not found"}
    except subprocess.TimeoutExpired:
        return {"success": False, "method": "hciconfig", "detail": "hciconfig timed out"}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "method": "hciconfig", "detail": str(exc)}


def _try_bluetoothctl_power_on() -> dict[str, Any]:
    """Attempt to power on the default adapter via ``sudo bluetoothctl power on``."""
    try:
        result = subprocess.run(
            ["sudo", "bluetoothctl", "power", "on"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        combined = (result.stdout + result.stderr).strip()
        if result.returncode == 0 and "succeeded" in combined.lower():
            logger.info("Powered on Bluetooth adapter via bluetoothctl")
            return {"success": True, "method": "bluetoothctl", "detail": combined}
        logger.debug("bluetoothctl power on returned: %s", combined)
        return {
            "success": False,
            "method": "bluetoothctl",
            "detail": combined or "no output",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "method": "bluetoothctl",
            "detail": "bluetoothctl not found",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "method": "bluetoothctl",
            "detail": "bluetoothctl timed out",
        }
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "method": "bluetoothctl", "detail": str(exc)}


def power_on_adapter(adapter: str) -> dict[str, Any]:
    """Attempt to power on the Bluetooth adapter.

    Tries the following methods in order:
    1. ``sudo hciconfig <adapter> up``
    2. ``sudo bluetoothctl power on``

    Returns a dict with:
    - ``success``: bool
    - ``method``: which method was tried last
    - ``detail``: human-readable outcome
    """
    hciconfig_result = _try_hciconfig_up(adapter)
    if hciconfig_result["success"]:
        return hciconfig_result

    bluetoothctl_result = _try_bluetoothctl_power_on()
    if bluetoothctl_result["success"]:
        return bluetoothctl_result

    return {
        "success": False,
        "method": "all",
        "detail": (
            f"All automatic power-on methods failed for adapter '{adapter}'.\n"
            f"  Manual fixes:\n"
            f"    sudo hciconfig {adapter} up\n"
            f"    sudo bluetoothctl power on\n"
            f"    sudo systemctl restart bluetooth"
        ),
    }


# ---------------------------------------------------------------------------
# Wait helper
# ---------------------------------------------------------------------------

def wait_for_adapter_ready(
    adapter: str,
    timeout: int = _POWER_ON_TIMEOUT,
    poll_interval: float = _POWER_ON_POLL_INTERVAL,
) -> bool:
    """Poll until *adapter* reports powered=1 in sysfs or *timeout* expires.

    Returns ``True`` when the adapter becomes ready, ``False`` on timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check_adapter_powered(adapter):
            return True
        time.sleep(poll_interval)
    return False


# ---------------------------------------------------------------------------
# High-level recovery
# ---------------------------------------------------------------------------

def attempt_recovery(adapter: str) -> dict[str, Any]:
    """Full recovery flow: check → power-on → wait → verify.

    Returns a dict with:
    - ``needed``: whether recovery was attempted (``False`` if already powered)
    - ``success``: whether the adapter is powered after recovery
    - ``power_on_result``: result dict from :func:`power_on_adapter`, or ``None``
    - ``detail``: human-readable summary
    """
    if check_adapter_powered(adapter):
        return {
            "needed": False,
            "success": True,
            "power_on_result": None,
            "detail": f"Adapter '{adapter}' is already powered on",
        }

    logger.warning(
        "Bluetooth adapter '%s' is not powered on – attempting automatic recovery",
        adapter,
    )

    power_result = power_on_adapter(adapter)

    if power_result["success"]:
        ready = wait_for_adapter_ready(adapter)
        if ready:
            logger.info(
                "Bluetooth adapter '%s' successfully powered on and ready", adapter
            )
            return {
                "needed": True,
                "success": True,
                "power_on_result": power_result,
                "detail": f"Adapter '{adapter}' powered on successfully",
            }
        logger.warning(
            "Bluetooth adapter '%s' power-on command succeeded but adapter not "
            "ready within %ds",
            adapter,
            _POWER_ON_TIMEOUT,
        )
        return {
            "needed": True,
            "success": False,
            "power_on_result": power_result,
            "detail": (
                f"Adapter '{adapter}' power-on command succeeded but adapter did not "
                f"report powered state within {_POWER_ON_TIMEOUT}s"
            ),
        }

    logger.error(
        "Automatic Bluetooth adapter power-on failed for '%s': %s\n"
        "  Manual fix: sudo hciconfig %s up",
        adapter,
        power_result["detail"],
        adapter,
    )
    return {
        "needed": True,
        "success": False,
        "power_on_result": power_result,
        "detail": (
            f"Could not automatically power on adapter '{adapter}'. "
            f"Manual fix: sudo hciconfig {adapter} up"
        ),
    }
