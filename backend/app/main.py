"""
FastAPI Application Entry Point for BLE Attendance System.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from .config import settings
from .models.student import Base as StudentBase
from .models.session import Base as SessionBase  # noqa: F401 – same Base via inheritance
from .models.attendance import AttendanceORM, ScanLogORM  # noqa: F401 – register models
from .models.student import StudentBeaconORM  # noqa: F401 – register beacon model
from .models.settings import AppSettingORM  # noqa: F401 – register settings model

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: log configuration and validate environment
    settings.log_startup_config()
    warnings = settings.validate_startup()
    for w in warnings:
        logger.warning("Startup check: %s", w)
    if not warnings:
        logger.info("Startup check: all configuration checks passed")

    # Startup: log Bluetooth adapter status
    from .utils.bluetooth_recovery import get_adapter_info
    adapter_info = get_adapter_info(settings.bt_adapter)
    if adapter_info["exists"] and adapter_info["powered"] is True:
        logger.info("Bluetooth: %s", adapter_info["detail"])
    elif adapter_info["exists"] and adapter_info["powered"] is False:
        logger.warning(
            "Bluetooth: %s – scanner will fail with 'Resource Not Ready' until fixed.\n"
            "  Quick fix: sudo hciconfig %s up  or  bash scripts/enable_bluetooth.sh",
            adapter_info["detail"],
            settings.bt_adapter,
        )
    elif not adapter_info["exists"]:
        logger.warning(
            "Bluetooth: %s – scanner cannot start without a Bluetooth adapter.",
            adapter_info["detail"],
        )
    else:
        logger.info("Bluetooth adapter '%s': power state unknown", settings.bt_adapter)

    # Startup: create all tables
    async with engine.begin() as conn:
        await conn.run_sync(StudentBase.metadata.create_all)
    logger.info("Database tables ensured")
    yield
    # Shutdown: dispose engine
    await engine.dispose()
    logger.info("Database engine disposed")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "REST API for the Bluetooth Attendance System. "
        "Receives BLE scan events from the C++ scanner and manages student attendance."
    ),
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from .api.scanner import router as scanner_router
from .api.scanner_control import router as scanner_control_router
from .api.attendance import router as attendance_router
from .api.students import router as students_router
from .api.sessions import router as sessions_router
from .api.health import router as health_router
from .api.websocket import router as websocket_router

app.include_router(scanner_router)
app.include_router(scanner_control_router)
app.include_router(attendance_router)
app.include_router(students_router)
app.include_router(sessions_router)
app.include_router(health_router)
app.include_router(websocket_router)


# ---------------------------------------------------------------------------
# Health check (lightweight)
# ---------------------------------------------------------------------------
@app.get("/health", tags=["system"])
async def health_check():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/", tags=["system"])
async def root():
    return {
        "message": "BLE Attendance System API",
        "docs": "/docs",
        "health": "/health",
        "diagnostics": "/api/health/diagnostics",
    }
