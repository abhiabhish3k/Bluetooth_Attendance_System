"""
Scanner control service.

Manages the lifecycle of the C++ BLE scanner engine as a child process.
A module-level singleton protected by a threading.Lock makes this safe for
use inside a single FastAPI worker process.

Event forwarding
----------------
When the backend spawns the scanner, the scanner writes JSON objects (one
per line) to stdout.  A daemon thread (``_read_stdout``) reads that stream
and POSTs each event to the backend's own ``/api/events`` endpoint using
``httpx``.  This mirrors the behaviour of the ``run_scanner.sh`` bridge
script so that starting the scanner from the UI works end-to-end.
"""

import json
import logging
import subprocess
import threading
from datetime import datetime, timezone
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class ScannerControlService:
    """Thread-safe singleton that starts/stops the C++ scanner process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
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

    def _read_stdout(self, proc: subprocess.Popen, event_url: str) -> None:
        """Background daemon thread: read scanner stdout, parse JSON events,
        and POST each one to *event_url*.

        Non-JSON lines (startup banners, log lines) are forwarded to the
        logger at DEBUG level so they still appear in the backend log.
        The loop exits naturally when the scanner process closes stdout.

        Each HTTP POST is dispatched to a small thread pool so that a
        slow or unreachable backend does not stall the stdout-read loop
        and fill the scanner's pipe buffer.
        """
        from concurrent.futures import ThreadPoolExecutor

        logger.info("Scanner stdout reader started, forwarding to %s", event_url)

        def _post(payload: dict) -> None:
            try:
                with httpx.Client(timeout=2.0) as http:
                    resp = http.post(event_url, json=payload)
                if resp.status_code == 200:
                    logger.info(
                        "Scanner event forwarded addr=%s rssi=%s → HTTP %d",
                        payload.get("address"),
                        payload.get("rssi"),
                        resp.status_code,
                    )
                elif resp.status_code == 422:
                    logger.warning(
                        "Scanner event rejected (422 Unprocessable Entity) – "
                        "malformed payload? addr=%s body=%s",
                        payload.get("address"),
                        resp.text[:200],
                    )
                else:
                    logger.warning(
                        "Unexpected HTTP %d from event endpoint: %s",
                        resp.status_code,
                        resp.text[:200],
                    )
            except httpx.RequestError as exc:
                logger.warning("Failed to POST scanner event: %s", exc)

        try:
            with ThreadPoolExecutor(max_workers=4, thread_name_prefix="scanner-post") as pool:
                for raw in proc.stdout:  # type: ignore[union-attr]
                    try:
                        line = raw.decode("utf-8", errors="replace").strip()
                    except Exception:
                        continue
                    if not line:
                        continue
                    if not line.startswith("{"):
                        logger.debug("Scanner: %s", line)
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Scanner invalid JSON on stdout: %s", line)
                        continue
                    pool.submit(_post, payload)
        except Exception as exc:
            logger.error("Scanner stdout reader crashed: %s", exc)
        finally:
            logger.info("Scanner stdout reader exited")

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

        A daemon thread is spawned to read the scanner's stdout and POST
        each JSON event to ``settings.scanner_backend_url``.
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

            # Spawn daemon thread to forward stdout events to /api/events
            self._reader_thread = threading.Thread(
                target=self._read_stdout,
                args=(self._process, settings.scanner_backend_url),
                name="scanner-stdout-reader",
                daemon=True,
            )
            self._reader_thread.start()

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
            # The reader thread is a daemon; it will exit once stdout is closed
            # (which happens when the process is terminated above).
            self._reader_thread = None
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
