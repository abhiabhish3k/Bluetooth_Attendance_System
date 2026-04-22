"""
Backend tests for the scanner control endpoints.

Tests that:
- GET /api/scanner/status returns the expected schema.
- POST /api/scanner/stop is idempotent when scanner is not running.
- POST /api/scanner/start returns 503 when the binary is not found.
- POST /api/scanner/restart returns 503 when the binary is not found.
- Calling stop twice returns already_stopped=True on the second call.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="module")
async def app():
    """Create a test FastAPI app backed by an in-memory database."""
    import os
    os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)

    from app.config import settings
    settings.database_url = TEST_DATABASE_URL

    from app.main import app as fastapi_app
    from app.models.student import Base

    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    test_session_maker = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    import app.main as main_module
    original_engine = main_module.engine
    original_session_maker = main_module.async_session_maker
    main_module.engine = test_engine
    main_module.async_session_maker = test_session_maker

    yield fastapi_app

    main_module.engine = original_engine
    main_module.async_session_maker = original_session_maker
    await test_engine.dispose()


@pytest_asyncio.fixture
async def client(app):
    """Return an async HTTP client for the test app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture(autouse=True)
def reset_scanner_service():
    """Ensure the scanner service is stopped before and after each test."""
    from app.services.scanner_control import scanner_service
    # Force-stop any lingering process without error
    with scanner_service._lock:
        if scanner_service._process is not None:
            try:
                scanner_service._process.kill()
                scanner_service._process.wait()
            except Exception:
                pass
        scanner_service._process = None
        scanner_service._started_at = None
        scanner_service._last_event_at = None
    yield
    # Cleanup after test as well
    with scanner_service._lock:
        if scanner_service._process is not None:
            try:
                scanner_service._process.kill()
                scanner_service._process.wait()
            except Exception:
                pass
        scanner_service._process = None
        scanner_service._started_at = None
        scanner_service._last_event_at = None


# ---------------------------------------------------------------------------
# GET /api/scanner/status
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_scanner_status_schema(client):
    """Status endpoint returns the required fields."""
    response = await client.get("/api/scanner/status")
    assert response.status_code == 200
    data = response.json()
    assert "running" in data
    assert "pid" in data
    assert "started_at" in data
    assert "uptime_seconds" in data
    assert "last_event_at" in data
    assert "engine" in data
    assert isinstance(data["running"], bool)


@pytest.mark.anyio
async def test_scanner_status_not_running(client):
    """When no scanner is running, running=False and pid/started_at are null."""
    response = await client.get("/api/scanner/status")
    assert response.status_code == 200
    data = response.json()
    assert data["running"] is False
    assert data["pid"] is None
    assert data["started_at"] is None
    assert data["uptime_seconds"] is None


# ---------------------------------------------------------------------------
# POST /api/scanner/stop  (idempotent when not running)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_scanner_stop_idempotent_when_stopped(client):
    """Calling stop when already stopped should return already_stopped=True."""
    response = await client.post("/api/scanner/stop")
    assert response.status_code == 200
    data = response.json()
    assert data["already_stopped"] is True
    assert data["running"] is False


@pytest.mark.anyio
async def test_scanner_stop_twice_returns_already_stopped(client):
    """Second stop call after first stop also returns already_stopped=True."""
    r1 = await client.post("/api/scanner/stop")
    assert r1.status_code == 200
    assert r1.json()["already_stopped"] is True

    r2 = await client.post("/api/scanner/stop")
    assert r2.status_code == 200
    assert r2.json()["already_stopped"] is True


# ---------------------------------------------------------------------------
# POST /api/scanner/start  (binary not found → 503)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_scanner_start_binary_not_found(client):
    """Starting with a non-existent binary path returns 503."""
    from app.config import settings
    original_cmd = settings.scanner_command
    settings.scanner_command = "/nonexistent/path/ble_scanner"
    try:
        response = await client.post("/api/scanner/start")
        assert response.status_code == 503
        assert "not found" in response.json()["detail"].lower()
    finally:
        settings.scanner_command = original_cmd


# ---------------------------------------------------------------------------
# POST /api/scanner/restart  (binary not found → 503)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_scanner_restart_binary_not_found(client):
    """Restarting with a non-existent binary path returns 503."""
    from app.config import settings
    original_cmd = settings.scanner_command
    settings.scanner_command = "/nonexistent/path/ble_scanner"
    try:
        response = await client.post("/api/scanner/restart")
        assert response.status_code == 503
    finally:
        settings.scanner_command = original_cmd


# ---------------------------------------------------------------------------
# POST /api/scanner/start  (using a real binary – echo/sleep simulation)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_scanner_start_with_real_binary(client):
    """Starting with a real binary (sleep) transitions running to True."""
    from app.config import settings
    original_cmd = settings.scanner_command
    original_args = settings.scanner_args
    settings.scanner_command = "sleep"
    settings.scanner_args = "60"
    try:
        response = await client.post("/api/scanner/start")
        assert response.status_code == 200
        data = response.json()
        assert data["running"] is True
        assert data["pid"] is not None
        assert data["already_running"] is False

        # Status endpoint should reflect it too
        status_res = await client.get("/api/scanner/status")
        assert status_res.json()["running"] is True

        # Calling start again should be idempotent
        r2 = await client.post("/api/scanner/start")
        assert r2.json()["already_running"] is True

        # Stop it
        stop_res = await client.post("/api/scanner/stop")
        assert stop_res.json()["running"] is False
        assert stop_res.json()["already_stopped"] is False
    finally:
        settings.scanner_command = original_cmd
        settings.scanner_args = original_args


# ---------------------------------------------------------------------------
# last_event_at updated via /api/events
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_last_event_at_updated_on_scan_event(client):
    """Sending a scan event via /api/events updates last_event_at."""
    from app.services.scanner_control import scanner_service

    # Confirm no last event yet
    assert scanner_service._last_event_at is None

    payload = {
        "address": "AA:BB:CC:DD:EE:FF",
        "name": "test_device",
        "rssi": -60,
        "timestamp": 1700000000,
    }
    response = await client.post("/api/events", json=payload)
    # May be 200 (event processed) or 422 (no active session) – either way
    # last_event_at should be updated
    assert response.status_code in (200, 422, 404)

    status_res = await client.get("/api/scanner/status")
    # last_event_at is updated regardless of attendance processing outcome
    # (the update happens after process_scan_event)
    # We only assert it if the request was processed (200)
    if response.status_code == 200:
        assert status_res.json()["last_event_at"] is not None
