"""
Time utility helpers.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)


def unix_to_utc(timestamp: int) -> datetime:
    """Convert a Unix timestamp (integer seconds) to a UTC datetime."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def utc_to_unix(dt: datetime) -> int:
    """Convert a datetime to a Unix timestamp integer."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())
