"""
Scanner event API endpoints.

Receives JSON events emitted by the C++ BLE scanner and processes them
through the attendance logic pipeline.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.attendance_logic import ScanEvent, process_scan_event
from ..utils.validators import validate_scan_event

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
    return result


@router.post(
    "/batch",
    summary="Receive a batch of BLE scan events",
    description="Accepts an array of scan events. Each event is processed independently.",
    status_code=status.HTTP_200_OK,
)
async def receive_batch_events(
    payloads: list[dict],
    db: AsyncSession = Depends(get_db),
):
    if len(payloads) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size cannot exceed 100 events",
        )

    results = []
    for payload in payloads:
        ok, err = validate_scan_event(payload)
        if not ok:
            results.append({"status": "invalid", "reason": err, "payload": payload})
            continue
        try:
            event = ScanEvent(**payload)
            result = await process_scan_event(event, db)
            results.append(result)
        except Exception as exc:
            logger.warning("Error processing event %s: %s", payload, exc)
            results.append({"status": "error", "reason": str(exc)})

    return {"processed": len(results), "results": results}
