"""
Attendance API endpoints.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.attendance import AttendanceORM, AttendanceResponse
from ..models.session import SessionORM
from ..services.attendance_logic import get_attendance_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/attendance", tags=["attendance"])


async def get_db():
    from ..main import async_session_maker
    async with async_session_maker() as session:
        yield session


@router.get(
    "/report/{session_id}",
    summary="Get attendance report for a session",
)
async def attendance_report(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    report = await get_attendance_report(session_id, db)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return report


@router.get(
    "",
    summary="List attendance records",
    response_model=list[AttendanceResponse],
)
async def list_attendance(
    session_id: Optional[int] = Query(None, description="Filter by session ID"),
    student_id: Optional[int] = Query(None, description="Filter by student ID"),
    db: AsyncSession = Depends(get_db),
):
    query = select(AttendanceORM)
    if session_id is not None:
        query = query.where(AttendanceORM.session_id == session_id)
    if student_id is not None:
        query = query.where(AttendanceORM.student_id == student_id)

    result = await db.execute(query.order_by(AttendanceORM.detected_time.desc()))
    records = result.scalars().all()
    return records


@router.delete(
    "/{attendance_id}",
    summary="Delete an attendance record",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_attendance(
    attendance_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AttendanceORM).where(AttendanceORM.attendance_id == attendance_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attendance record {attendance_id} not found",
        )
    await db.delete(record)
    await db.commit()
