"""
Class session management API endpoints.
"""

import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models.session import SessionORM, SessionCreate, SessionResponse, SessionUpdate
from ..services.attendance_logic import set_active_session, get_active_session_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


async def get_db():
    from ..main import async_session_maker
    async with async_session_maker() as session:
        yield session


@router.post(
    "",
    summary="Create a new attendance session",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    session_data: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    if session_data.end_time and session_data.end_time <= session_data.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_time must be after start_time",
        )

    new_session = SessionORM(
        class_name=session_data.class_name,
        start_time=session_data.start_time,
        end_time=session_data.end_time,
        threshold_rssi=session_data.threshold_rssi,
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)

    # Automatically activate if it starts now (within 60s)
    now = datetime.now(tz=timezone.utc)
    start = new_session.start_time
    if not start.tzinfo:
        start = start.replace(tzinfo=timezone.utc)
    if abs((start - now).total_seconds()) <= 6000:
        set_active_session(new_session.session_id)

    return new_session


@router.get(
    "",
    summary="List all sessions",
    response_model=list[SessionResponse],
)
async def list_sessions(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SessionORM).order_by(SessionORM.start_time.desc())
    )
    return result.scalars().all()


@router.get(
    "/active",
    summary="Get the currently active session",
)
async def get_active_session(db: AsyncSession = Depends(get_db)):
    session_id = get_active_session_id()
    if session_id is None:
        return {"active": False, "session": None}

    result = await db.execute(
        select(SessionORM).where(SessionORM.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        set_active_session(None)
        return {"active": False, "session": None}

    return {"active": True, "session": SessionResponse.model_validate(session)}


@router.get(
    "/{session_id}",
    summary="Get session by ID",
    response_model=SessionResponse,
)
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SessionORM).where(SessionORM.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return session


@router.patch(
    "/{session_id}",
    summary="Update a session (e.g. set end_time to close it)",
    response_model=SessionResponse,
)
async def update_session(
    session_id: int,
    updates: SessionUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SessionORM).where(SessionORM.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    if updates.end_time is not None:
        session.end_time = updates.end_time
    if updates.threshold_rssi is not None:
        session.threshold_rssi = updates.threshold_rssi

    await db.commit()
    await db.refresh(session)
    return session


@router.post(
    "/{session_id}/activate",
    summary="Manually set a session as the active session",
)
async def activate_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SessionORM).where(SessionORM.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    set_active_session(session_id)
    return {"message": f"Session {session_id} activated", "session_id": session_id}
