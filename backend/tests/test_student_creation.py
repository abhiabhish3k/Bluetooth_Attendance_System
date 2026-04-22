"""
Backend tests for student creation endpoint.

Tests that:
- A valid student creation request returns 201 with the student data.
- An invalid MAC address returns 422 with Pydantic validation error detail.
- A missing required field returns 422.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="module")
async def app():
    """Create a test FastAPI app backed by an in-memory database."""
    import os
    os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)

    # Patch settings before importing the app
    from app.config import settings
    settings.database_url = TEST_DATABASE_URL

    from app.main import app as fastapi_app
    from app.models.student import Base

    # Create all tables in the in-memory DB
    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Patch the session maker to use the test engine
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


@pytest.mark.anyio
async def test_create_student_success(client):
    """A valid payload should return 201 with all fields."""
    payload = {
        "name": "Alice Johnson",
        "roll_number": "CS2021001",
        "email": "alice@example.com",
        "mac_address": "AA:BB:CC:11:22:33",
    }
    response = await client.post("/api/students", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "Alice Johnson"
    assert data["roll_number"] == "CS2021001"
    assert data["email"] == "alice@example.com"
    assert data["mac_address"] == "AA:BB:CC:11:22:33"
    assert "id" in data


@pytest.mark.anyio
async def test_create_student_invalid_mac(client):
    """An invalid MAC address should return 422 with Pydantic error detail."""
    payload = {
        "name": "Bob Kumar",
        "roll_number": "CS2021002",
        "email": "bob@example.com",
        "mac_address": "not-a-mac",
    }
    response = await client.post("/api/students", json=payload)
    assert response.status_code == 422
    data = response.json()
    # FastAPI returns detail as a list of error dicts
    assert isinstance(data["detail"], list)
    error = data["detail"][0]
    # Each error must have the Pydantic v2 shape: type, loc, msg, input
    assert "msg" in error
    assert "loc" in error


@pytest.mark.anyio
async def test_create_student_missing_required_field(client):
    """Omitting a required field should return 422."""
    payload = {
        # Missing 'name', 'email', 'mac_address'
        "roll_number": "CS2021003",
    }
    response = await client.post("/api/students", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert isinstance(data["detail"], list)
    # Should report multiple missing fields
    assert len(data["detail"]) >= 1


@pytest.mark.anyio
async def test_create_student_duplicate_roll_number(client):
    """Duplicate roll number should return 409 conflict."""
    payload = {
        "name": "Charlie P.",
        "roll_number": "DUPLICATE001",
        "email": "charlie@example.com",
        "mac_address": "AA:BB:CC:44:55:66",
    }
    # First creation should succeed
    r1 = await client.post("/api/students", json=payload)
    assert r1.status_code == 201

    # Second creation with same roll_number should fail
    payload2 = {**payload, "email": "charlie2@example.com", "mac_address": "AA:BB:CC:44:55:77"}
    r2 = await client.post("/api/students", json=payload2)
    assert r2.status_code == 409
