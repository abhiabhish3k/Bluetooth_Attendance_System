"""
Event serialisation utilities shared between scanner integration tests
and backend tooling.
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional, Union


MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def serialise_scan_event(
    address: str,
    rssi: int,
    timestamp: Union[int, datetime],
    name: str = "",
) -> str:
    """
    Serialise a BLE scan event to a compact JSON string (no extra whitespace).

    Parameters
    ----------
    address:   MAC address string (case-insensitive; will be normalised to upper-case).
    rssi:      RSSI value in dBm.
    timestamp: Unix timestamp (int) or datetime object.
    name:      Optional device advertising name.

    Returns
    -------
    Single-line JSON string.

    Raises
    ------
    ValueError if any argument fails validation.
    """
    # Normalise and validate MAC
    address = address.upper().strip()
    if not MAC_PATTERN.match(address):
        raise ValueError(f"Invalid MAC address: {address!r}")

    # Validate RSSI
    if not (-120 <= rssi <= 10):
        raise ValueError(f"RSSI {rssi} out of valid range [-120, 10]")

    # Normalise timestamp
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        ts_int = int(timestamp.timestamp())
    else:
        ts_int = int(timestamp)

    if ts_int < 1_577_836_800:
        raise ValueError(f"Timestamp {ts_int} is before 2020-01-01")

    payload = {
        "address": address,
        "name": name,
        "rssi": rssi,
        "timestamp": ts_int,
    }
    return json.dumps(payload, separators=(",", ":"))


def deserialise_scan_event(line: str) -> Optional[dict]:
    """
    Parse a JSON string produced by the C++ scanner or ``serialise_scan_event``.

    Returns the parsed dict on success, or None if the line is not valid JSON
    or fails field validation.
    """
    line = line.strip()
    if not line:
        return None

    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None

    required = {"address", "rssi", "timestamp"}
    if not required.issubset(obj.keys()):
        return None

    if not MAC_PATTERN.match(str(obj.get("address", ""))):
        return None

    try:
        rssi = int(obj["rssi"])
        ts   = int(obj["timestamp"])
    except (TypeError, ValueError):
        return None

    if not (-120 <= rssi <= 10):
        return None

    return {
        "address":   obj["address"].upper(),
        "name":      str(obj.get("name", "")),
        "rssi":      rssi,
        "timestamp": ts,
    }
