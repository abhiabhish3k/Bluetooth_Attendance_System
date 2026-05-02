"""
Tests for ESP32 scanner ingestion.

Covers:
- normalise_timestamp: seconds passthrough and ms → s conversion
- validate_timestamp: accepts both seconds and millisecond timestamps
- POST /api/events/batch with bare array (legacy Linux scanner format)
- POST /api/events/batch with {"events": [...]} envelope (ESP32 format)
- POST /api/events/batch with millisecond timestamp (ESP32 may send ms)
- POST /api/events/batch with invalid body shape returns 400
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# ---------------------------------------------------------------------------
# Unit tests for normalise_timestamp / validate_timestamp (no DB required)
# ---------------------------------------------------------------------------

def test_normalise_timestamp_seconds_passthrough():
    """Unix-second values below the ms threshold are returned unchanged."""
    from app.utils.validators import normalise_timestamp
    ts_s = 1_712_345_678  # 2024 in seconds
    assert normalise_timestamp(ts_s) == ts_s


def test_normalise_timestamp_ms_to_seconds():
    """Unix-millisecond values are divided by 1000."""
    from app.utils.validators import normalise_timestamp
    ts_ms = 1_712_345_678_000  # same instant in ms
    assert normalise_timestamp(ts_ms) == 1_712_345_678


def test_validate_timestamp_accepts_seconds():
    """validate_timestamp returns True for a plausible Unix-second value."""
    from app.utils.validators import validate_timestamp
    assert validate_timestamp(1_712_345_678) is True


def test_validate_timestamp_accepts_milliseconds():
    """validate_timestamp returns True for a plausible Unix-millisecond value."""
    from app.utils.validators import validate_timestamp
    assert validate_timestamp(1_712_345_678_000) is True


def test_validate_timestamp_rejects_old_value():
    """validate_timestamp rejects a timestamp before 2020-01-01."""
    from app.utils.validators import validate_timestamp
    assert validate_timestamp(1_000_000_000) is False  # 2001


def test_validate_timestamp_rejects_zero():
    """validate_timestamp rejects 0 (boot millis from NTP-unsynced ESP32)."""
    from app.utils.validators import validate_timestamp
    assert validate_timestamp(0) is False


# ---------------------------------------------------------------------------
# HTTP integration fixtures (shared across batch-endpoint tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="module")
async def app():
    """Create a test FastAPI app backed by an in-memory SQLite database."""
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
    orig_engine = main_module.engine
    orig_session = main_module.async_session_maker
    main_module.engine = test_engine
    main_module.async_session_maker = test_session_maker

    yield fastapi_app

    main_module.engine = orig_engine
    main_module.async_session_maker = orig_session
    await test_engine.dispose()


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Batch endpoint – body shape tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_batch_bare_array_accepted(client):
    """POST /api/events/batch with a bare JSON array returns 200."""
    payload = [
        {
            "address":   "AA:BB:CC:DD:EE:FF",
            "rssi":      -62,
            "timestamp": 1_712_345_678,
            "beacon_id": "1:1001",
        }
    ]
    response = await client.post("/api/events/batch", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "processed" in data
    assert data["processed"] == 1


@pytest.mark.anyio
async def test_batch_esp32_envelope_accepted(client):
    """POST /api/events/batch with {"events":[...]} envelope returns 200."""
    payload = {
        "events": [
            {
                "address":   "AA:BB:CC:DD:EE:01",
                "rssi":      -65,
                "timestamp": 1_712_345_680,
                "beacon_id": "1:1002",
            },
            {
                "address":   "AA:BB:CC:DD:EE:02",
                "rssi":      -70,
                "timestamp": 1_712_345_681,
                "beacon_id": "1:1003",
            },
        ]
    }
    response = await client.post("/api/events/batch", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 2


@pytest.mark.anyio
async def test_batch_esp32_millisecond_timestamp(client):
    """Millisecond timestamp from ESP32 is normalised and accepted."""
    # 1_712_345_678_000 ms = 1_712_345_678 s (valid)
    payload = {
        "events": [
            {
                "address":   "BB:CC:DD:EE:FF:10",
                "rssi":      -68,
                "timestamp": 1_712_345_678_000,  # milliseconds
                "beacon_id": "1:1004",
            }
        ]
    }
    response = await client.post("/api/events/batch", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1


@pytest.mark.anyio
async def test_batch_invalid_body_returns_400(client):
    """A body that is neither an array nor an {events:[...]} object returns 400."""
    payload = {"not_events": "oops"}
    response = await client.post("/api/events/batch", json=payload)
    assert response.status_code == 400


@pytest.mark.anyio
async def test_batch_events_not_array_returns_400(client):
    """{"events": "string"} returns 400 (events must be an array)."""
    payload = {"events": "not-an-array"}
    response = await client.post("/api/events/batch", json=payload)
    assert response.status_code == 400


@pytest.mark.anyio
async def test_batch_exceeds_limit_returns_400(client):
    """More than 100 events in one batch returns 400."""
    event = {
        "address":   "CC:DD:EE:FF:00:01",
        "rssi":      -60,
        "timestamp": 1_712_345_678,
        "beacon_id": "1:9999",
    }
    payload = {"events": [event] * 101}
    response = await client.post("/api/events/batch", json=payload)
    assert response.status_code == 400


@pytest.mark.anyio
async def test_batch_invalid_event_in_envelope(client):
    """An event with a bad MAC inside the envelope is marked invalid, not rejected wholesale."""
    payload = {
        "events": [
            {
                "address":   "not-a-mac",
                "rssi":      -62,
                "timestamp": 1_712_345_678,
                "beacon_id": "1:1001",
            }
        ]
    }
    response = await client.post("/api/events/batch", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1
    assert data["results"][0]["status"] == "invalid"
