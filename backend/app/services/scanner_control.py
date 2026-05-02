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

A separate daemon thread (``_read_stderr``) drains the scanner's stderr pipe
and forwards all output to the backend logger at WARNING level so that
crash messages, permission errors, and BlueZ diagnostics are always visible
in the application log even when the default log level is INFO.
"""

import json
import logging
import subprocess
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration for HTTP event forwarding
# ---------------------------------------------------------------------------
_POST_INITIAL_DELAY = 0.5   # seconds before first retry
_POST_MAX_DELAY = 8.0       # maximum back-off cap
_POST_MAX_RETRIES = 3       # attempts after the initial try


class ScannerControlService:
    """Thread-safe singleton that starts/stops the C++ scanner process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._started_at: Optional[datetime] = None
        self._last_event_at: Optional[datetime] = None
        self._last_exit_code: Optional[int] = None
        self._events_received: int = 0
        self._events_forwarded: int = 0
        self._events_failed: int = 0

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
            "last_exit_code": self._last_exit_code,
            "metrics": {
                "events_received": self._events_received,
                "events_forwarded": self._events_forwarded,
                "events_failed": self._events_failed,
            },
            "engine": {
                "command": settings.scanner_command,
                "args": settings.scanner_args or None,
            },
        }

    def _read_stderr(self, proc: subprocess.Popen) -> None:
        """Background daemon thread: drain scanner stderr and log at WARNING.

        Keeping stderr drained is important on all POSIX systems – if the pipe
        buffer fills up the scanner process will block on its writes and appear
        to hang.  Logging at WARNING means the messages are always visible when
        the default log level is INFO, which helps diagnose D-Bus permission
        errors, missing adapters, and similar startup failures.
        """
        try:
            for raw in proc.stderr:  # type: ignore[union-attr]
                try:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    continue
                if line:
                    logger.warning("Scanner stderr: %s", line)
        except Exception as exc:
            logger.debug("Scanner stderr reader error: %s", exc)
        finally:
            logger.debug("Scanner stderr reader exited")

    def _read_stdout(self, proc: subprocess.Popen, event_url: str) -> None:
        """Background daemon thread: read scanner stdout, parse JSON events,
        and POST each one to *event_url*.

        Non-JSON lines (startup banners, log lines) are forwarded to the
        logger at INFO level so they always appear in the backend log.
        The loop exits naturally when the scanner process closes stdout.

        Each HTTP POST is dispatched to a small thread pool so that a
        slow or unreachable backend does not stall the stdout-read loop
        and fill the scanner's pipe buffer.  Failed POSTs are retried with
        exponential back-off up to ``_POST_MAX_RETRIES`` times.
        """
        from concurrent.futures import ThreadPoolExecutor

        logger.info("Scanner stdout reader started, forwarding to %s", event_url)

        def _post_with_retry(payload: dict) -> None:
            """POST *payload* to *event_url*, retrying with exponential back-off."""
            delay = _POST_INITIAL_DELAY
            with httpx.Client(timeout=5.0) as http:
                for attempt in range(1 + _POST_MAX_RETRIES):
                    try:
                        resp = http.post(event_url, json=payload)
                        if resp.status_code == 200:
                            logger.info(
                                "Scanner event forwarded addr=%s rssi=%s → HTTP %d",
                                payload.get("address"),
                                payload.get("rssi"),
                                resp.status_code,
                            )
                            with self._lock:
                                self._events_forwarded += 1
                            return
                        if resp.status_code == 422:
                            logger.warning(
                                "Scanner event rejected (422 Unprocessable Entity) – "
                                "malformed payload? addr=%s body=%s",
                                payload.get("address"),
                                resp.text[:200],
                            )
                            with self._lock:
                                self._events_failed += 1
                            return  # Retrying a malformed payload won't help
                        logger.warning(
                            "Unexpected HTTP %d from event endpoint (attempt %d/%d): %s",
                            resp.status_code,
                            attempt + 1,
                            1 + _POST_MAX_RETRIES,
                            resp.text[:200],
                        )
                    except httpx.RequestError as exc:
                        logger.warning(
                            "Failed to POST scanner event (attempt %d/%d): %s",
                            attempt + 1,
                            1 + _POST_MAX_RETRIES,
                            exc,
                        )
                    if attempt < _POST_MAX_RETRIES:
                        time.sleep(delay)
                        delay = min(delay * 2, _POST_MAX_DELAY)

            logger.error(
                "Giving up forwarding event addr=%s after %d attempts",
                payload.get("address"),
                1 + _POST_MAX_RETRIES,
            )
            with self._lock:
                self._events_failed += 1

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
                        # Log scanner diagnostic/status lines at INFO so they
                        # are always visible (not only when DEBUG is enabled).
                        logger.info("Scanner stdout: %s", line)
                        continue
                    with self._lock:
                        self._events_received += 1
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Scanner invalid JSON on stdout: %s", line)
                        continue
                    pool.submit(_post_with_retry, payload)
        except Exception as exc:
            logger.error(
                "Scanner stdout reader crashed: %s\n%s",
                exc,
                traceback.format_exc(),
            )
        finally:
            exit_code = proc.poll()
            with self._lock:
                self._last_exit_code = exit_code
            if exit_code is not None and exit_code != 0:
                logger.error(
                    "Scanner process exited with code %d – check stderr output above "
                    "for the root cause (Bluetooth adapter missing? D-Bus permissions?)",
                    exit_code,
                )
            else:
                logger.info(
                    "Scanner stdout reader exited (exit_code=%s)",
                    exit_code,
                )

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

        Two daemon threads are spawned:
        - ``_read_stdout``: reads JSON events and POSTs them to /api/events.
        - ``_read_stderr``: drains stderr and logs output at WARNING level.
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
                    stderr=subprocess.PIPE,  # Separate pipe so errors are logged distinctly
                )
                self._started_at = datetime.now(timezone.utc)
                self._last_exit_code = None
                self._events_received = 0
                self._events_forwarded = 0
                self._events_failed = 0
                logger.info(
                    "Scanner started (pid=%d) cmd=%s", self._process.pid, cmd
                )
            except FileNotFoundError:
                logger.error(
                    "Scanner binary not found: %s – ensure the C++ scanner is "
                    "compiled (cd scanner && cmake -B build && cmake --build build)",
                    settings.scanner_command,
                )
                self._process = None
                self._started_at = None
                raise
            except PermissionError:
                logger.error(
                    "Permission denied launching scanner binary: %s – "
                    "check file permissions (chmod +x) and D-Bus/BlueZ policy",
                    settings.scanner_command,
                )
                self._process = None
                self._started_at = None
                raise

            # Spawn stdout reader thread
            self._reader_thread = threading.Thread(
                target=self._read_stdout,
                args=(self._process, settings.scanner_backend_url),
                name="scanner-stdout-reader",
                daemon=True,
            )
            self._reader_thread.start()

            # Spawn stderr drain thread
            self._stderr_thread = threading.Thread(
                target=self._read_stderr,
                args=(self._process,),
                name="scanner-stderr-reader",
                daemon=True,
            )
            self._stderr_thread.start()

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

            self._last_exit_code = self._process.returncode
            self._process = None
            self._started_at = None
            # The reader threads are daemons; they exit once their pipes close.
            self._reader_thread = None
            self._stderr_thread = None
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
