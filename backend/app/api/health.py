"""
Comprehensive health / diagnostics API endpoint.

GET /api/health/diagnostics  –  returns a full snapshot of all system
components: Bluetooth adapters, D-Bus, BlueZ service, scanner binary,
scanner config, and configuration warnings.  Useful for operators who need
to quickly diagnose why the scanner is not starting or not forwarding events.
"""

import logging

from fastapi import APIRouter

from ..services.scanner_control import scanner_service
from ..utils.diagnostics import build_diagnostics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get(
    "/diagnostics",
    summary="Full system diagnostics",
    description=(
        "Returns a comprehensive health snapshot including Bluetooth adapter "
        "status, D-Bus availability, BlueZ service state, scanner binary "
        "checks, and configuration warnings.  Also includes live scanner "
        "process metrics (events received / forwarded / failed)."
    ),
)
async def get_diagnostics():
    diag = build_diagnostics()
    diag["scanner"] = scanner_service.status()
    return diag
