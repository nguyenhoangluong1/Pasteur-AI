import base64
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.api.deps import get_db
from core.db.models import Patient
from core.services.chatbot_service import chat_with_gemini
from core.speech import transcribe_audio
from core.speech.tts import synthesize_speech_chunks_async, synthesize_speech_sync


router = APIRouter()


class ChatRequest(BaseModel):
    patient_id: str
    conversation_id: str | None = None
    message: str


class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    conversation_id: str
    assistant_message: str
    messages: list[ChatMessage]
    """Van ban nguoi dung noi (chi khi goi /audio)."""
    transcript: str | None = None
    """Audio tra loi (base64), chi khi goi /audio va TTS thanh cong."""
    audio_base64: str | None = None
    audio_mime: str | None = None


class TTSOnlyRequest(BaseModel):
    """Phat lai TTS cho mot doan van ban (nut loa duoi message AI)."""
    text: str
    voice: str | None = None


class TTSOnlyResponse(BaseModel):
    audio_base64: str
    audio_mime: str


def _role_to_str(role) -> str:
    if role is None:
        return "assistant"
    return role.value if hasattr(role, "value") else str(role)


def _messages_to_schema(conv) -> list[ChatMessage]:
    out: list[ChatMessage] = []
    for m in conv.messages:
        out.append(
            ChatMessage(
                id=str(m.id),
                role=_role_to_str(m.role),
                content=m.content,
                created_at=m.created_at,
            )
        )
    return out


def _extract_stt_hints(patient: Patient, db: Session) -> list[str]:
    hints: list[str] = []
    if patient.full_name:
        hints.append(patient.full_name)

    cfg = db.execute(
        text(
            """
        SELECT chronic_conditions, current_medications
        FROM public.patient_medical_config
        WHERE patient_id = :patient_id AND is_active = true
        ORDER BY updated_at DESC
        LIMIT 1
        """
        ),
        {"patient_id": patient.id},
    ).mappings().first()
    if not cfg:
        return hints

    chronic = cfg.get("chronic_conditions") or []
    if isinstance(chronic, list):
        hints.extend(str(item) for item in chronic if item)

    meds = cfg.get("current_medications") or []
    if isinstance(meds, list):
        for med in meds:
            if isinstance(med, dict):
                name = med.get("name")
                if name:
                    hints.append(str(name))
    # Keep hints concise to improve STT latency.
    seen: set[str] = set()
    compact: list[str] = []
    for h in hints:
        key = h.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        compact.append(h.strip())
        if len(compact) >= 10:
            break
    return compact


@router.post("", response_model=ChatResponse)
def chat(body: ChatRequest, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == body.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    try:
        assistant_text, conv = chat_with_gemini(
            db,
            patient_id=body.patient_id,
            user_message=body.message,
            conversation_id=body.conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ChatResponse(
        conversation_id=conv.id,
        assistant_message=assistant_text,
        messages=_messages_to_schema(conv),
        transcript=None,
        audio_base64=None,
        audio_mime=None,
    )


@router.post("/tts", response_model=TTSOnlyResponse)
def tts_only(body: TTSOnlyRequest):
    """TTS theo van ban (khong qua chat). Dung cho nut doc lai duoi moi tin assistant."""
    raw = (body.text or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="text is empty")
    try:
        audio_out, audio_mime = synthesize_speech_sync(raw, voice=body.voice)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TTS failed: {exc}") from exc
    if not audio_out:
        raise HTTPException(status_code=500, detail="TTS returned empty audio")
    b64 = base64.b64encode(audio_out).decode("ascii")
    return TTSOnlyResponse(audio_base64=b64, audio_mime=audio_mime)


@router.post("/tts/stream")
async def tts_stream(body: TTSOnlyRequest):
    """TTS streaming audio/mpeg de frontend phat mem hon."""
    raw = (body.text or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="text is empty")

    return StreamingResponse(
        synthesize_speech_chunks_async(raw, voice=body.voice),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tts/voices")
def tts_voice_list():
    """Danh sach giong edge-tts tieng Viet (de frontend chon)."""
    return [
        {"id": "vi-VN-HoaiMyNeural", "label": "Tiếng Việt — Nữ (Hoài My)"},
        {"id": "vi-VN-NamMinhNeural", "label": "Tiếng Việt — Nam (Minh)"},
    ]


@router.post("/audio", response_model=ChatResponse)
def chat_audio(
    patient_id: str = Form(...),
    conversation_id: str | None = Form(None),
    tts_voice: str | None = Form(None),
    include_tts: bool = Form(True),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Gui file audio (webm/wav/mp3/...) -> STT -> chat -> TTS -> tra ve JSON + audio base64.
    Dung sync route + doc file sync de tranh dung Session SQLAlchemy sai thread.
    """
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    audio_bytes = audio.file.read() if audio.file else b""
    mime = audio.content_type or "audio/webm"
    stt_hints = _extract_stt_hints(patient, db)

    try:
        transcript = transcribe_audio(audio_bytes, mime, domain_hints=stt_hints)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"STT failed: {exc}") from exc

    try:
        assistant_text, conv = chat_with_gemini(
            db,
            patient_id=patient_id,
            user_message=transcript,
            conversation_id=conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    b64 = None
    audio_mime = None
    if include_tts:
        try:
            audio_out, audio_mime = synthesize_speech_sync(
                assistant_text, voice=tts_voice
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"TTS failed: {exc}") from exc
        b64 = base64.b64encode(audio_out).decode("ascii") if audio_out else None

    return ChatResponse(
        conversation_id=conv.id,
        assistant_message=assistant_text,
        messages=_messages_to_schema(conv),
        transcript=transcript,
        audio_base64=b64,
        audio_mime=audio_mime if b64 else None,
    )
