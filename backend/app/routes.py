import csv
import io
import json
import os
from typing import Any, Dict, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.database import get_db

router = APIRouter()


SYSTEM_PROMPT = """
Eres un asistente de inscripciones universitarias.
Responde SIEMPRE en JSON con este formato:
{
  "answer": "texto para el estudiante",
  "action": "none|list_courses|enroll|cancel_course|get_history|end_session",
  "parameters": {}
}
"""


@router.get("/health")
def health():
    return {"status": "ok"}


def _build_prompt(db: Session, session_id: str, new_message: str) -> str:
    history = crud.get_recent_messages(
        db=db,
        session_id=session_id,
        limit=int(os.getenv("MAX_CONTEXT_MESSAGES", "10")),
    )
    catalog = db.query(models.Course).order_by(models.Course.semester.asc(), models.Course.code.asc()).all()

    prompt = f"<|system|>\n{SYSTEM_PROMPT}\n\nCatalogo:\n"
    for c in catalog:
        prompt += f"- {c.code} | {c.name} | {c.credits} creditos | semestre {c.semester}\n"
    prompt += "</s>\n"

    for msg in history:
        tag = "user" if msg.role == "user" else "assistant"
        prompt += f"<|{tag}|>\n{msg.content}</s>\n"

    prompt += f"<|user|>\n{new_message}</s>\n<|assistant|>\n"
    return prompt


async def _call_tinyllama(prompt: str) -> schemas.ChatActionResult:
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        return schemas.ChatActionResult(
            answer="Falta HF_TOKEN en variables de entorno.",
            action="none",
            parameters={},
        )

    model = os.getenv("HF_CHAT_MODEL")
    if not model:
        return schemas.ChatActionResult(
            answer="Falta HF_CHAT_MODEL en variables de entorno.",
            action="none",
            parameters={},
        )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 250,
    }

    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers=headers,
            json=payload,
        )

    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()

    try:
        parsed = json.loads(content)
        return schemas.ChatActionResult(**parsed)
    except Exception:
        return schemas.ChatActionResult(
            answer=content,
            action="none",
            parameters={},
        )


def _dispatch(
    db: Session,
    action: str,
    parameters: Dict[str, Any],
    student_id: int,
    session_obj: models.Session,
) -> Tuple[Dict[str, Any], str]:
    if action == "none":
        return {}, "success"

    if action == "list_courses":
        semester = int(parameters.get("semester", 1))
        courses = crud.get_courses_by_semester(db, semester)
        return {
            "semester": semester,
            "courses": [
                {"code": c.code, "name": c.name, "credits": c.credits, "semester": c.semester}
                for c in courses
            ],
        }, "success"

    if action == "enroll":
        course_code = parameters.get("course_code")
        period = parameters.get("period", os.getenv("DEFAULT_PERIOD", "2026-I"))
        if not course_code:
            return {"error": "course_code requerido"}, "error"

        if not crud.get_course(db, course_code):
            return {"error": f"Materia {course_code} no existe"}, "error"

        enrollment = crud.create_enrollment(db, student_id, course_code, period)
        if not enrollment:
            return {"error": "Ya existe inscripción para esa materia en ese periodo"}, "error"
        return {"enrollment_id": enrollment.id, "course_code": course_code, "period": period}, "success"

    if action in {"cancel_course", "remove_course"}:
        course_code = parameters.get("course_code")
        period = parameters.get("period", os.getenv("DEFAULT_PERIOD", "2026-I"))
        if not course_code:
            return {"error": "course_code requerido"}, "error"

        cancelled = crud.cancel_enrollment(db, student_id, course_code, period)
        if not cancelled:
            return {"error": "No existe inscripción activa para cancelar"}, "error"
        return {"course_code": course_code, "period": period, "status": "cancelled"}, "success"

    if action == "get_history":
        rows = crud.get_student_history(db, student_id)
        return {
            "enrollments": [
                {
                    "id": r.id,
                    "course_code": r.course_code,
                    "period": r.period,
                    "status": r.status,
                }
                for r in rows
            ]
        }, "success"

    if action == "end_session":
        crud.end_session(db, session_obj)
        return {"session_id": session_obj.id, "status": "ended"}, "success"

    return {"error": f"Acción no soportada: {action}"}, "error"


@router.post("/session/start", response_model=schemas.SessionStartResponse)
def start_session(data: schemas.SessionStartRequest, db: Session = Depends(get_db)):
    student = db.query(models.Student).filter(models.Student.id == data.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    session_obj = crud.create_session(db, data.student_id)
    return {"session_id": session_obj.id, "status": session_obj.status}


@router.post("/session/{session_id}/message", response_model=schemas.SessionMessageResponse)
async def session_message(
    session_id: str,
    data: schemas.SessionMessageRequest,
    db: Session = Depends(get_db),
):
    session_obj = crud.get_session(db, session_id)
    if not session_obj or session_obj.status != "active":
        raise HTTPException(status_code=400, detail="Sesión no activa")

    crud.create_message(db, session_id=session_id, role="user", content=data.message)

    prompt = _build_prompt(db, session_id, data.message)
    try:
        llm_result = await _call_tinyllama(prompt)
    except Exception as ex:
        llm_result = schemas.ChatActionResult(
            answer=f"Ocurrió un error procesando el modelo: {str(ex)}",
            action="none",
            parameters={},
        )

    action_data, result = _dispatch(
        db=db,
        action=llm_result.action,
        parameters=llm_result.parameters,
        student_id=session_obj.student_id,
        session_obj=session_obj,
    )

    crud.log_action(
        db=db,
        session_id=session_obj.id,
        student_id=session_obj.student_id,
        action_name=llm_result.action,
        parameters=llm_result.parameters,
        result=result,
    )

    action_json = json.dumps(
        {"action": llm_result.action, "parameters": llm_result.parameters},
        ensure_ascii=False,
    )
    crud.create_message(
        db,
        session_id=session_id,
        role="assistant",
        content=llm_result.answer,
        action_json=action_json,
    )

    return {
        "reply": llm_result.answer,
        "action": llm_result.action,
        "data": action_data,
    }


@router.post("/session/{session_id}/end", response_model=schemas.SessionEndResponse)
def close_session(session_id: str, db: Session = Depends(get_db)):
    session_obj = crud.get_session(db, session_id)
    if not session_obj:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    session_obj = crud.end_session(db, session_obj)
    return {"session_id": session_obj.id, "status": session_obj.status}


@router.get("/student/{student_id}/history", response_model=schemas.StudentHistoryOut)
def student_history(student_id: int, db: Session = Depends(get_db)):
    rows = crud.get_student_history(db, student_id)
    return {"student_id": student_id, "enrollments": rows}


@router.get("/courses/semester/{semester}", response_model=list[schemas.CourseOut])
def courses_by_semester(semester: int, db: Session = Depends(get_db)):
    return crud.get_courses_by_semester(db, semester)


@router.post("/enroll", response_model=schemas.EnrollmentOut)
def enroll(data: schemas.EnrollmentCreate, db: Session = Depends(get_db)):
    if not crud.get_course(db, data.course_code):
        raise HTTPException(status_code=404, detail="Materia no existe")

    row = crud.create_enrollment(db, data.student_id, data.course_code, data.period)
    if not row:
        raise HTTPException(status_code=400, detail="Inscripción duplicada")
    return row


@router.delete("/enroll/{course_code}")
def cancel_enroll(
    course_code: str,
    student_id: int = Query(...),
    period: str = Query(...),
    db: Session = Depends(get_db),
):
    row = crud.cancel_enrollment(db, student_id, course_code, period)
    if not row:
        raise HTTPException(status_code=404, detail="Inscripción activa no encontrada")
    return {"message": "Materia cancelada", "course_code": course_code, "period": period}


@router.get("/enrollment/confirm")
def enrollment_confirm(
    student_id: int = Query(...),
    period: str = Query(...),
    fmt: str = Query(default="csv"),
    db: Session = Depends(get_db),
):
    rows = crud.get_student_history(db, student_id)
    rows = [r for r in rows if r.period == period and r.status == "active"]

    if fmt.lower() != "csv":
        raise HTTPException(status_code=400, detail="Solo fmt=csv está soportado por ahora")

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["student_id", "course_code", "period", "status", "enrolled_at"])
    for r in rows:
        writer.writerow([r.student_id, r.course_code, r.period, r.status, r.enrolled_at])

    buffer.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="enrollment_{student_id}_{period}.csv"'}
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers=headers)
