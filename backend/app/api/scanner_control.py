"""
Scanner control API endpoints.

Exposes start / stop / restart / status operations for the C++ BLE scanner
engine.  The actual process management is delegated to
``services.scanner_control.scanner_service``.
"""

import logging
from fastapi import APIRouter, HTTPException, status

from ..services.scanner_control import scanner_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scanner", tags=["scanner-control"])


@router.get(
    "/status",
    summary="Get scanner engine status",
    description=(
        "Returns the current runtime status of the C++ BLE scanner engine, "
        "including whether it is running, its PID, uptime, and the timestamp "
        "of the last scan event received."
    ),
    status_code=status.HTTP_200_OK,
)
async def get_scanner_status():
    return scanner_service.status()


@router.post(
    "/start",
    summary="Start the scanner engine",
    description=(
        "Launches the C++ BLE scanner as a child process. "
        "Idempotent: returns current status if the scanner is already running."
    ),
    status_code=status.HTTP_200_OK,
)
async def start_scanner():
    try:
        result = scanner_service.start()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Scanner binary not found: {exc}",
        ) from exc
    return result


@router.post(
    "/stop",
    summary="Stop the scanner engine",
    description=(
        "Terminates the C++ BLE scanner process. "
        "Idempotent: returns current status if the scanner is already stopped."
    ),
    status_code=status.HTTP_200_OK,
)
async def stop_scanner():
    return scanner_service.stop()


@router.post(
    "/restart",
    summary="Restart the scanner engine",
    description="Stops the scanner (if running) then starts it again.",
    status_code=status.HTTP_200_OK,
)
async def restart_scanner():
    try:
        result = scanner_service.restart()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Scanner binary not found: {exc}",
        ) from exc
    return result
