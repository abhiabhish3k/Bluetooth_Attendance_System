"""
Scanner control service.

Manages the lifecycle of the C++ BLE scanner engine as a child process.
A module-level singleton protected by a threading.Lock makes this safe for
use inside a single FastAPI worker process.
"""

import logging
import subprocess
import threading
from datetime import datetime, timezone
from typing import Optional

from ..config import settings

logger = logging.getLogger(__name__)


class ScannerControlService:
    """Thread-safe singleton that starts/stops the C++ scanner process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._started_at: Optional[datetime] = None
        self._last_event_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_running(self) -> bool:
        """Return True when the managed process exists and has not exited."""
        return self._process is not None and self._process.poll() is None

    def _build_cmd(self) -> list[str]:
        cmd = [settings.scanner_command]
        if settings.scanner_args.strip():
            cmd.extend(settings.scanner_args.split())
        return cmd

    def _status_unlocked(self) -> dict:
        """Compute status snapshot without acquiring the lock (caller must hold it)."""
        running = self._is_running()
        pid = self._process.pid if running else None
        started_at = self._started_at.isoformat() if self._started_at else None
        uptime_seconds: Optional[int] = None
        if running and self._started_at:
            delta = datetime.now(timezone.utc) - self._started_at
            uptime_seconds = int(delta.total_seconds())
        last_event_at = (
            self._last_event_at.isoformat() if self._last_event_at else None
        )
        return {
            "running": running,
            "pid": pid,
            "started_at": started_at,
            "uptime_seconds": uptime_seconds,
            "last_event_at": last_event_at,
            "engine": {
                "command": settings.scanner_command,
                "args": settings.scanner_args or None,
            },
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Return a JSON-serialisable status snapshot."""
        with self._lock:
            return self._status_unlocked()

    def start(self) -> dict:
        """
        Start the scanner engine.  Idempotent: if already running, returns
        the current status with ``already_running=True``.
        """
        with self._lock:
            if self._is_running():
                return {**self._status_unlocked(), "already_running": True}

            cmd = self._build_cmd()
            logger.info("Starting scanner: %s", cmd)
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                self._started_at = datetime.now(timezone.utc)
                logger.info(
                    "Scanner started (pid=%d)", self._process.pid
                )
            except FileNotFoundError:
                logger.error(
                    "Scanner binary not found: %s", settings.scanner_command
                )
                self._process = None
                self._started_at = None
                raise
            return {**self._status_unlocked(), "already_running": False}

    def stop(self) -> dict:
        """
        Stop the scanner engine gracefully (SIGTERM then SIGKILL).
        Idempotent: if already stopped, returns current status with
        ``already_stopped=True``.
        """
        with self._lock:
            if not self._is_running():
                return {**self._status_unlocked(), "already_stopped": True}

            logger.info(
                "Stopping scanner (pid=%d)", self._process.pid
            )
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Scanner did not stop in time – sending SIGKILL")
                self._process.kill()
                self._process.wait()

            self._process = None
            self._started_at = None
            return {**self._status_unlocked(), "already_stopped": False}

    def restart(self) -> dict:
        """Stop (if running) then start."""
        self.stop()
        return self.start()

    def update_last_event(self) -> None:
        """Called by ingestion endpoints each time an event is received."""
        with self._lock:
            self._last_event_at = datetime.now(timezone.utc)


# Module-level singleton used by the API layer.
scanner_service = ScannerControlService()
