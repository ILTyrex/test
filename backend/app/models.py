import uuid
from sqlalchemy import Column, Integer, String, Text, ForeignKey, TIMESTAMP, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    student_code = Column(String(20), unique=True, nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    current_semester = Column(Integer, default=1)
    created_at = Column(TIMESTAMP, server_default=func.now())

    sessions = relationship("Session", back_populates="student")
    enrollments = relationship("Enrollment", back_populates="student")


class Course(Base):
    __tablename__ = "courses"

    code = Column(String(10), primary_key=True)  # SIS801
    name = Column(String(100), nullable=False)
    credits = Column(Integer, nullable=False)
    semester = Column(Integer, nullable=False)


class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    course_code = Column(String(10), ForeignKey("courses.code"), nullable=False)
    period = Column(String(10), nullable=False)  # 2026-I
    status = Column(String(20), default="active")  # active | cancelled
    enrolled_at = Column(TIMESTAMP, server_default=func.now())
    cancelled_at = Column(TIMESTAMP, nullable=True)

    student = relationship("Student", back_populates="enrollments")
    course = relationship("Course")

    __table_args__ = (
        UniqueConstraint("student_id", "course_code", "period", name="uq_enrollment_student_course_period"),
    )


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    started_at = Column(TIMESTAMP, server_default=func.now())
    ended_at = Column(TIMESTAMP, nullable=True)
    status = Column(String(20), default="active")  # active | ended

    student = relationship("Student", back_populates="sessions")
    messages = relationship("Message", back_populates="session")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False)
    role = Column(String(10), nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    action_json = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    session = relationship("Session", back_populates="messages")


class ActionLog(Base):
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    action_name = Column(String(50), nullable=False)
    parameters = Column(Text, nullable=True)
    result = Column(String(20), nullable=False)
    executed_at = Column(TIMESTAMP, server_default=func.now())