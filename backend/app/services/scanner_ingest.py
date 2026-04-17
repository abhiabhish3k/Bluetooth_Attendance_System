"""
Scanner ingest service.

Provides helper functions for piping C++ scanner output (line-by-line JSON)
to the attendance logic processor.  Useful when running the scanner as a
sub-process instead of via HTTP.
"""

import json
import logging
from typing import Optional

from .attendance_logic import ScanEvent, process_scan_event
from ..utils.validators import validate_scan_event

logger = logging.getLogger(__name__)


def parse_scanner_line(line: str) -> Optional[ScanEvent]:
    """
    Parse a single JSON line produced by the C++ scanner.

    Returns a ScanEvent on success, or None if the line is invalid.
    """
    line = line.strip()
    if not line:
        return None

    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON from scanner: %s – %s", line, exc)
        return None

    ok, err = validate_scan_event(payload)
    if not ok:
        logger.warning("Scanner event validation failed: %s – %s", line, err)
        return None

    try:
        return ScanEvent(**payload)
    except Exception as exc:
        logger.warning("ScanEvent parse error: %s – %s", line, exc)
        return None
