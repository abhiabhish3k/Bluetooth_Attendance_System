"""
Student management API endpoints.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models.student import StudentORM, StudentCreate, StudentResponse, StudentUpdate

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
    )
    db.add(new_student)
    try:
        await db.commit()
        await db.refresh(new_student)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A student with this roll number, email or MAC address already exists",
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

    try:
        await db.commit()
        await db.refresh(student)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A student with this email or MAC address already exists",
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
