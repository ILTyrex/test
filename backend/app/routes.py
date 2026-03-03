from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from app import crud
from app import schemas
from app.database import get_db
from app import models as m

router = APIRouter()


# ─── Health ──────────────────────────────────────────────
@router.get("/health")
def health():
    return {"status": "ok"}


# ─── Users ───────────────────────────────────────────────
@router.post("/users", response_model=schemas.UserOut, tags=["Users"])
def create_user(data: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = crud.get_user_by_code(db, data.student_code)
    if existing:
        raise HTTPException(status_code=400, detail="Código de estudiante ya registrado")
    return crud.create_user(db, data)

@router.get("/users/{user_id}", response_model=schemas.UserOut, tags=["Users"])
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

@router.post("/login", response_model=schemas.LoginResponse, tags=["Auth"])
def login(
    data: Optional[schemas.LoginRequest] = Body(default=None),
    cedula: Optional[str] = Query(default=None),
    clave: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    resolved_cedula = data.cedula if data else cedula
    resolved_clave = data.clave if data else clave

    if not resolved_cedula or not resolved_clave:
        raise HTTPException(
            status_code=400,
            detail="Debes enviar credenciales como JSON o query params",
        )

    user = crud.authenticate_user(db, resolved_cedula, resolved_clave)
    if not user:
        raise HTTPException(status_code=401, detail="Cédula o contraseña incorrectas")
    return {"message": "Login exitoso", "user_id": user.id}


# ─── Conversations ───────────────────────────────────────
@router.post("/conversations", response_model=schemas.ConversationOut, tags=["Conversations"])
def start_conversation(data: schemas.ConversationCreate, db: Session = Depends(get_db)):
    user = crud.get_user(db, data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return crud.create_conversation(db, data.user_id)

@router.patch("/conversations/{conversation_id}/close", response_model=schemas.ConversationOut, tags=["Conversations"])
def close_conversation(conversation_id: int, db: Session = Depends(get_db)):
    conv = crud.close_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return conv

@router.get("/conversations", response_model=List[schemas.ConversationOut], tags=["Conversations"])
def list_conversations(
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return crud.get_conversations(db, user_id, status, start_date, end_date)

@router.get("/conversations/{conversation_id}/history", response_model=schemas.ConversationHistory, tags=["Conversations"])
def get_history(conversation_id: int, db: Session = Depends(get_db)):
    conv = db.query(m.Conversation).filter(m.Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    messages = crud.get_messages(db, conversation_id)
    return schemas.ConversationHistory(conversation=conv, messages=messages)


# ─── Messages ────────────────────────────────────────────
@router.post("/messages", response_model=schemas.MessageOut, tags=["Messages"])
def add_message(data: schemas.MessageCreate, db: Session = Depends(get_db)):
    return crud.add_message(db, data)
