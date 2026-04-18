"""
Student management API endpoints.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models.student import (
    StudentORM, StudentBeaconORM,
    StudentCreate, StudentResponse, StudentUpdate,
    BeaconRegisterRequest, BeaconResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/students", tags=["students"])


async def get_db():
    from ..main import async_session_maker
    async with async_session_maker() as session:
        yield session


@router.post(
    "",
    summary="Register a new student",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_student(
    student: StudentCreate,
    db: AsyncSession = Depends(get_db),
):
    new_student = StudentORM(
        name=student.name,
        roll_number=student.roll_number,
        email=student.email,
        mac_address=student.mac_address,
        unique_id=student.unique_id,
    )
    db.add(new_student)
    try:
        await db.commit()
        await db.refresh(new_student)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A student with this roll number, email, MAC address, or unique_id already exists",
        ) from exc
    return new_student


@router.get(
    "",
    summary="List all students",
    response_model=list[StudentResponse],
)
async def list_students(
    search: Optional[str] = Query(None, description="Search by name or roll number"),
    db: AsyncSession = Depends(get_db),
):
    query = select(StudentORM).order_by(StudentORM.roll_number)
    if search:
        like = f"%{search}%"
        query = query.where(
            StudentORM.name.ilike(like) | StudentORM.roll_number.ilike(like)
        )
    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/{student_id}",
    summary="Get a student by ID",
    response_model=StudentResponse,
)
async def get_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudentORM).where(StudentORM.id == student_id)
    )
    student = result.scalar_one_or_none()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student {student_id} not found",
        )
    return student


@router.patch(
    "/{student_id}",
    summary="Update a student",
    response_model=StudentResponse,
)
async def update_student(
    student_id: int,
    updates: StudentUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudentORM).where(StudentORM.id == student_id)
    )
    student = result.scalar_one_or_none()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student {student_id} not found",
        )

    if updates.name is not None:
        student.name = updates.name
    if updates.email is not None:
        student.email = updates.email
    if updates.mac_address is not None:
        student.mac_address = updates.mac_address
    if updates.unique_id is not None:
        student.unique_id = updates.unique_id

    try:
        await db.commit()
        await db.refresh(student)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A student with this email, MAC address, or unique_id already exists",
        ) from exc
    return student


@router.delete(
    "/{student_id}",
    summary="Delete a student",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudentORM).where(StudentORM.id == student_id)
    )
    student = result.scalar_one_or_none()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student {student_id} not found",
        )
    await db.delete(student)
    await db.commit()


# ---------------------------------------------------------------------------
# Beacon registration endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/{student_id}/beacon/register",
    summary="Register a BLE beacon ID for a student",
    status_code=status.HTTP_200_OK,
)
async def register_beacon(
    student_id: int,
    payload: BeaconRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Associate a BLE beacon identifier with a student record.

    The beacon_id should match the value the student's phone advertises
    (e.g. the iBeacon minor field value, or a custom unique_id string).
    """
    # Verify student exists
    stu_result = await db.execute(
        select(StudentORM).where(StudentORM.id == student_id)
    )
    student = stu_result.scalar_one_or_none()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student {student_id} not found",
        )

    # Update or create student_beacon row
    beacon_result = await db.execute(
        select(StudentBeaconORM).where(StudentBeaconORM.student_id == student_id)
    )
    beacon_row = beacon_result.scalar_one_or_none()

    if beacon_row is None:
        beacon_row = StudentBeaconORM(
            student_id=student_id,
            beacon_data=payload.beacon_id,
            advertised=True,
        )
        db.add(beacon_row)
    else:
        beacon_row.beacon_data = payload.beacon_id
        beacon_row.advertised = True

    # Also store in student.unique_id for fast look-ups at scan time
    student.unique_id = payload.beacon_id

    try:
        await db.commit()
        await db.refresh(beacon_row)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"beacon_id '{payload.beacon_id}' is already registered to another student",
        ) from exc

    return {
        "status": "registered",
        "student_id": student_id,
        "beacon_id": beacon_row.beacon_data,
    }


@router.get(
    "/{student_id}/beacon",
    summary="Get the registered beacon ID for a student",
    response_model=BeaconResponse,
)
async def get_beacon(
    student_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return the beacon registration for a student, if one exists."""
    # Verify student exists
    stu_result = await db.execute(
        select(StudentORM).where(StudentORM.id == student_id)
    )
    student = stu_result.scalar_one_or_none()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student {student_id} not found",
        )

    beacon_result = await db.execute(
        select(StudentBeaconORM).where(StudentBeaconORM.student_id == student_id)
    )
    beacon_row = beacon_result.scalar_one_or_none()
    if beacon_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No beacon registered for student {student_id}",
        )

    return BeaconResponse(
        student_id=student_id,
        beacon_id=beacon_row.beacon_data,
        beacon_data=beacon_row.beacon_data,
        advertised=beacon_row.advertised,
        last_seen=beacon_row.last_seen,
    )
