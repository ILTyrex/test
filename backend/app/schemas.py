from datetime import datetime
from typing import Optional, Any, Dict, List
from pydantic import BaseModel


class SessionStartRequest(BaseModel):
    student_id: int


class SessionStartResponse(BaseModel):
    session_id: str
    status: str


class SessionMessageRequest(BaseModel):
    message: str


class SessionMessageResponse(BaseModel):
    reply: str
    action: str
    data: Optional[Dict[str, Any]] = None


class SessionEndResponse(BaseModel):
    session_id: str
    status: str


class CourseOut(BaseModel):
    code: str
    name: str
    credits: int
    semester: int

    class Config:
        from_attributes = True


class EnrollmentCreate(BaseModel):
    student_id: int
    course_code: str
    period: str


class EnrollmentOut(BaseModel):
    id: int
    student_id: int
    course_code: str
    period: str
    status: str
    enrolled_at: datetime
    cancelled_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StudentHistoryOut(BaseModel):
    student_id: int
    enrollments: List[EnrollmentOut]


class ChatActionResult(BaseModel):
    answer: str
    action: str
    parameters: Dict[str, Any] = {}