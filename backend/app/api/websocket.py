"""
WebSocket endpoints for real-time event streaming.

Channels
--------
``/ws/scan``
    Raw scan events as they arrive from any scanner (ESP32 or Linux C++).
    Message shape::

        {
          "type": "scan",
          "address": "AA:BB:CC:DD:EE:FF",
          "rssi": -62,
          "beacon_id": "1:1001",
          "timestamp": 1712345678,
          "scanner_id": "esp32-main"   // optional
        }

``/ws/attendance``
    Attendance records as they are freshly written to the database.
    Message shape::

        {
          "type": "attendance_marked",
          "student_id": 7,
          "student_name": "Alice",
          "session_id": 3,
          "rssi": -62,
          "matched_by": "beacon",
          "timestamp": 1712345678
        }

Clients should silently ignore messages whose ``type`` is ``"ping"``
(keepalive sent every 25 s).

WebSocket message format docs: ``docs/API.md``
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

_PING_INTERVAL = 25  # seconds between server-side keepalive pings


async def _keepalive(ws: WebSocket, channel: str) -> None:
    """Send periodic pings and exit when the socket closes."""
    try:
        while True:
            await asyncio.sleep(_PING_INTERVAL)
            await ws.send_text('{"type":"ping"}')
    except Exception:
        pass
    finally:
        ws_manager.disconnect(channel, ws)


@router.websocket("/ws/scan")
async def scan_ws(websocket: WebSocket) -> None:
    """Stream raw BLE scan events to connected dashboard clients."""
    await ws_manager.connect("scan", websocket)
    ping_task = asyncio.create_task(_keepalive(websocket, "scan"))
    try:
        # Block until the client disconnects; we don't process client frames.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ping_task.cancel()
        ws_manager.disconnect("scan", websocket)


@router.websocket("/ws/attendance")
async def attendance_ws(websocket: WebSocket) -> None:
    """Stream attendance-marked events to connected dashboard clients."""
    await ws_manager.connect("attendance", websocket)
    ping_task = asyncio.create_task(_keepalive(websocket, "attendance"))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ping_task.cancel()
        ws_manager.disconnect("attendance", websocket)
