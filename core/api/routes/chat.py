import base64
import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from google.genai.errors import ClientError, ServerError
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.api.deps import get_db
from core.config import get_settings
from core.db.models import Patient
from core.llm.gemini_http import http_detail_message, suggest_status_for_gemini_client_error
from core.services.chatbot_service import chat_with_gemini
from core.speech import transcribe_audio
from core.speech.tts import synthesize_speech_chunks_async, synthesize_speech_sync


router = APIRouter()
logger = logging.getLogger(__name__)

try:
    from groq import APIError as _GroqAPIError
except ImportError:
    _GroqAPIError = None  # type: ignore[misc, assignment]


def _http_from_groq_error(exc: Exception) -> HTTPException | None:
    if _GroqAPIError is None or not isinstance(exc, _GroqAPIError):
        return None
    status = getattr(exc, "status_code", None)
    code = 429 if status == 429 else 502
    return HTTPException(status_code=code, detail=f"Groq API: {exc}")


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
    except ClientError as exc:
        status = suggest_status_for_gemini_client_error(exc)
        raise HTTPException(status_code=status, detail=http_detail_message(exc)) from exc
    except ServerError as exc:
        raise HTTPException(status_code=502, detail=http_detail_message(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)
        low = msg.lower()
        if "GEMINI_API_KEY" in msg or ("gemini" in low and "not configured" in low):
            raise HTTPException(status_code=503, detail=msg) from exc
        if "GROQ_API_KEY" in msg or ("groq" in low and "not configured" in low):
            raise HTTPException(status_code=503, detail=msg) from exc
        raise
    except Exception as exc:
        groq_http = _http_from_groq_error(exc)
        if groq_http is not None:
            raise groq_http from exc
        raise

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
    request_id = uuid.uuid4().hex[:8]
    t0 = time.perf_counter()
    t_read_done = t0
    t_stt_done = t0
    t_chat_done = t0
    t_tts_done = t0
    audio_size = 0
    settings = get_settings()
    max_audio_bytes = max(1024, int(getattr(settings, "voice_max_audio_bytes", 5 * 1024 * 1024)))

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    audio_bytes = audio.file.read() if audio.file else b""
    t_read_done = time.perf_counter()
    audio_size = len(audio_bytes)
    if audio_size == 0:
        raise HTTPException(status_code=400, detail="Audio is empty")
    if audio_size > max_audio_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large ({audio_size} bytes). Max allowed is {max_audio_bytes} bytes.",
        )
    mime = audio.content_type or "audio/webm"
    stt_hints = _extract_stt_hints(patient, db)

    try:
        transcript = transcribe_audio(audio_bytes, mime, domain_hints=stt_hints)
        t_stt_done = time.perf_counter()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"STT failed: {exc}") from exc

    try:
        assistant_text, conv = chat_with_gemini(
            db,
            patient_id=patient_id,
            user_message=transcript,
            conversation_id=conversation_id,
        )
        t_chat_done = time.perf_counter()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    b64 = None
    audio_mime = None
    if include_tts:
        try:
            audio_out, audio_mime = synthesize_speech_sync(
                assistant_text, voice=tts_voice
            )
            t_tts_done = time.perf_counter()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"TTS failed: {exc}") from exc
        b64 = base64.b64encode(audio_out).decode("ascii") if audio_out else None

    total_done = time.perf_counter()
    logger.info(
        "[VOICE_PIPELINE] request_id=%s patient_id=%s bytes=%s include_tts=%s "
        "read_ms=%.1f stt_ms=%.1f chat_ms=%.1f tts_ms=%.1f total_ms=%.1f",
        request_id,
        patient_id,
        audio_size,
        include_tts,
        (t_read_done - t0) * 1000,
        (t_stt_done - t_read_done) * 1000 if t_stt_done >= t_read_done else 0.0,
        (t_chat_done - t_stt_done) * 1000 if t_chat_done >= t_stt_done else 0.0,
        (t_tts_done - t_chat_done) * 1000 if include_tts and t_tts_done >= t_chat_done else 0.0,
        (total_done - t0) * 1000,
    )

    return ChatResponse(
        conversation_id=conv.id,
        assistant_message=assistant_text,
        messages=_messages_to_schema(conv),
        transcript=transcript,
        audio_base64=b64,
        audio_mime=audio_mime if b64 else None,
    )
