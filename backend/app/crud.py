import json
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from app import models


# ---------- Session ----------
def create_session(db: Session, student_id: int) -> models.Session:
    session = models.Session(student_id=student_id, status="active")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: str) -> Optional[models.Session]:
    return db.query(models.Session).filter(models.Session.id == session_id).first()


def end_session(db: Session, session_obj: models.Session) -> models.Session:
    session_obj.status = "ended"
    db.commit()
    db.refresh(session_obj)
    return session_obj


# ---------- Messages ----------
def create_message(
    db: Session,
    session_id: str,
    role: str,
    content: str,
    action_json: Optional[str] = None,
) -> models.Message:
    msg = models.Message(
        session_id=session_id,
        role=role,
        content=content,
        action_json=action_json,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_recent_messages(db: Session, session_id: str, limit: int = 10):
    rows = (
        db.query(models.Message)
        .filter(models.Message.session_id == session_id)
        .order_by(desc(models.Message.created_at))
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


# ---------- Courses ----------
def get_courses_by_semester(db: Session, semester: int):
    return (
        db.query(models.Course)
        .filter(models.Course.semester == semester)
        .order_by(models.Course.code.asc())
        .all()
    )


def get_course(db: Session, course_code: str) -> Optional[models.Course]:
    return db.query(models.Course).filter(models.Course.code == course_code).first()


# ---------- Enrollments ----------
def create_enrollment(db: Session, student_id: int, course_code: str, period: str):
    enrollment = models.Enrollment(
        student_id=student_id,
        course_code=course_code,
        period=period,
        status="active",
    )
    db.add(enrollment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(enrollment)
    return enrollment


def cancel_enrollment(db: Session, student_id: int, course_code: str, period: str):
    enrollment = (
        db.query(models.Enrollment)
        .filter(
            models.Enrollment.student_id == student_id,
            models.Enrollment.course_code == course_code,
            models.Enrollment.period == period,
            models.Enrollment.status == "active",
        )
        .first()
    )
    if not enrollment:
        return None

    enrollment.status = "cancelled"
    db.commit()
    db.refresh(enrollment)
    return enrollment


def get_student_history(db: Session, student_id: int):
    return (
        db.query(models.Enrollment)
        .filter(models.Enrollment.student_id == student_id)
        .order_by(models.Enrollment.enrolled_at.desc())
        .all()
    )


# ---------- Action Logs ----------
def log_action(
    db: Session,
    session_id: str,
    student_id: int,
    action_name: str,
    parameters: dict,
    result: str,
):
    row = models.ActionLog(
        session_id=session_id,
        student_id=student_id,
        action_name=action_name,
        parameters=json.dumps(parameters or {}),
        result=result,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row