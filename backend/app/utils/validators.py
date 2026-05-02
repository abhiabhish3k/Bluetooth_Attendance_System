"""
Data validation utilities for BLE scan events and API inputs.
"""

import re
from typing import Optional
from datetime import datetime, timezone


MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

MIN_RSSI = -120
MAX_RSSI = 10


def validate_mac_address(mac: str) -> bool:
    """Return True if mac is a well-formed IEEE 802 MAC address."""
    return bool(MAC_PATTERN.match(mac))


def normalise_mac(mac: str) -> str:
    """Return the MAC address in upper-case colon-separated format."""
    return mac.upper().strip()


def validate_rssi(rssi: int) -> bool:
    """Return True if rssi is within the physically plausible range."""
    return MIN_RSSI <= rssi <= MAX_RSSI


_MIN_TS_S = 1_577_836_800   # 2020-01-01T00:00:00Z in seconds
_MAX_TS_S = 4_102_444_800   # 2100-01-01T00:00:00Z in seconds
_MS_THRESHOLD = _MIN_TS_S * 1_000  # timestamps >= this are treated as milliseconds


def normalise_timestamp(ts: int) -> int:
    """Return ts as Unix seconds, converting from milliseconds if necessary.

    The ESP32 (and some other embedded scanners) may send Unix milliseconds
    instead of seconds.  A value >= 2020-01-01 in milliseconds (~1.58 × 10¹²)
    is well above the maximum plausible Unix-second value (~4.1 × 10⁹), so
    the conversion is unambiguous.
    """
    if ts >= _MS_THRESHOLD:
        return ts // 1_000
    return ts


def validate_timestamp(ts: int) -> bool:
    """Return True if ts is a plausible Unix timestamp (after 2020-01-01).

    Accepts both Unix seconds and Unix milliseconds; millisecond values are
    normalised before the range check so that ESP32 clients that send
    milliseconds continue to pass validation.
    """
    normalised = normalise_timestamp(ts)
    return _MIN_TS_S <= normalised <= _MAX_TS_S


def validate_scan_event(event: dict) -> tuple[bool, Optional[str]]:
    """
    Validate a raw BLE scan event dictionary.

    Required keys: address, rssi, timestamp.
    Optional keys: name, beacon_id.

    Returns (is_valid, error_message).
    """
    if "address" not in event:
        return False, "Missing required field: address"
    if "rssi" not in event:
        return False, "Missing required field: rssi"
    if "timestamp" not in event:
        return False, "Missing required field: timestamp"

    if not validate_mac_address(str(event["address"])):
        return False, f"Invalid MAC address: {event['address']}"

    try:
        rssi = int(event["rssi"])
    except (TypeError, ValueError):
        return False, f"RSSI must be an integer, got: {event['rssi']!r}"
    if not validate_rssi(rssi):
        return False, f"RSSI {rssi} out of valid range [{MIN_RSSI}, {MAX_RSSI}]"

    try:
        ts = int(event["timestamp"])
    except (TypeError, ValueError):
        return False, f"Timestamp must be an integer, got: {event['timestamp']!r}"
    if not validate_timestamp(ts):
        return False, f"Timestamp {ts} is not a valid Unix timestamp"

    if "beacon_id" in event and event["beacon_id"] is not None:
        bid = str(event["beacon_id"]).strip()
        if len(bid) > 64:
            return False, "beacon_id too long (max 64 characters)"

    return True, None
