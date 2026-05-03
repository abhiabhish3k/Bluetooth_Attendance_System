"""
Scanner event API endpoints.

Receives JSON events emitted by the C++ BLE scanner and processes them
through the attendance logic pipeline.

Batch endpoint (`POST /api/events/batch`) accepts two body shapes:

  • Bare array (Linux C++ scanner, legacy format):
      [{"address": "...", ...}, ...]

  • Envelope object (ESP32 scanner format):
      {"events": [{"address": "...", ...}, ...]}

Both shapes carry the same per-event schema (address, rssi, timestamp,
name?, beacon_id?).
"""

import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.attendance_logic import ScanEvent, process_scan_event
from ..services.scanner_control import scanner_service
from ..utils.validators import validate_scan_event
from ..core.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["scanner"])


async def get_db():
    """Dependency that provides a database session."""
    from ..main import async_session_maker
    async with async_session_maker() as session:
        yield session


@router.post(
    "",
    summary="Receive a BLE scan event",
    description=(
        "Accepts a JSON BLE device detection event from the C++ scanner. "
        "The event is logged and, if a student MAC is recognised during an "
        "active session, attendance is recorded."
    ),
    status_code=status.HTTP_200_OK,
)
async def receive_scan_event(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    # Validate raw payload before Pydantic parsing
    ok, err = validate_scan_event(payload)
    if not ok:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=err)

    try:
        event = ScanEvent(**payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=str(exc)) from exc

    result = await process_scan_event(event, db)
    scanner_service.update_last_event()

    # Broadcast raw scan event to any subscribed dashboard clients
    asyncio.create_task(ws_manager.broadcast("scan", {
        "type": "scan",
        "address": event.address,
        "rssi": event.rssi,
        "beacon_id": event.beacon_id,
        "timestamp": event.timestamp,
        "scanner_id": event.scanner_id,
    }))

    return result


@router.post(
    "/batch",
    summary="Receive a batch of BLE scan events",
    description=(
        "Accepts up to 100 scan events in a single request.\n\n"
        "Two body shapes are supported for backward compatibility:\n\n"
        "• **Bare array** (Linux C++ scanner): `[{...}, ...]`\n\n"
        "• **Envelope object** (ESP32 scanner): `{\"events\": [{...}, ...]}`\n\n"
        "Each event uses the same schema as `POST /api/events`."
    ),
    status_code=status.HTTP_200_OK,
)
async def receive_batch_events(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be valid JSON",
        )

    # Accept both bare array [...] (Linux scanner) and {"events":[...]} (ESP32)
    if isinstance(body, list):
        payloads = body
    elif isinstance(body, dict) and "events" in body:
        payloads = body["events"]
        if not isinstance(payloads, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='"events" must be an array',
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Expected a JSON array or an object with an "events" array',
        )

    if len(payloads) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size cannot exceed 100 events",
        )

    results = []
    scan_broadcasts = []
    for payload in payloads:
        ok, err = validate_scan_event(payload)
        if not ok:
            results.append({"status": "invalid", "reason": err, "payload": payload})
            continue
        try:
            event = ScanEvent(**payload)
            result = await process_scan_event(event, db)
            results.append(result)
            # Collect raw scan event for WebSocket broadcast
            scan_broadcasts.append({
                "type": "scan",
                "address": event.address,
                "rssi": event.rssi,
                "beacon_id": event.beacon_id,
                "timestamp": event.timestamp,
                "scanner_id": event.scanner_id,
            })
        except Exception as exc:
            logger.warning("Error processing event %s: %s", payload, exc)
            results.append({"status": "error", "reason": "processing_failed"})

    scanner_service.update_last_event()

    # Broadcast raw scan events (fire-and-forget; don't block the response)
    for msg in scan_broadcasts:
        asyncio.create_task(ws_manager.broadcast("scan", msg))
    return {"processed": len(results), "results": results}
