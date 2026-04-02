from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from core.api.deps import get_db
from core.db.models import Conversation, Message

router = APIRouter()


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: str
    patient_id: str
    title: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationWithMessagesOut(ConversationOut):
    messages: list[MessageOut] = []


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    patient_id: str = Query(..., description="Filter by patient ID"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(Conversation).filter(Conversation.patient_id == patient_id)
    return q.order_by(Conversation.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{conversation_id}", response_model=ConversationWithMessagesOut)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv
