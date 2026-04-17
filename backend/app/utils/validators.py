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


def validate_timestamp(ts: int) -> bool:
    """Return True if ts is a plausible Unix timestamp (after 2020-01-01)."""
    MIN_TS = 1_577_836_800  # 2020-01-01T00:00:00Z
    MAX_TS = 4_102_444_800  # 2100-01-01T00:00:00Z
    return MIN_TS <= ts <= MAX_TS


def validate_scan_event(event: dict) -> tuple[bool, Optional[str]]:
    """
    Validate a raw BLE scan event dictionary.

    Expected keys: address, rssi, timestamp.
    Optional keys: name.

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

    return True, None
