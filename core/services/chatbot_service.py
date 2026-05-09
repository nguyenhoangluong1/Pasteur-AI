from collections.abc import Sequence

from sqlalchemy.orm import Session

from core.db.models import Conversation, Message, Patient
from core.llm import get_gemini_model
from core.services.vector_rag_service import get_relevant_context


SYSTEM_INSTRUCTION = (
    "Phân tích câu hỏi từ người dùng nếu không phải là câu hỏi y tế thì trả lời ngắn gọn và không đưa ra thông tin người dùng nếu họ không hỏi (dùng context khi cần). "
    "Phát hiện hành vi người dùng ngay trong prompt để trả lời phù hợp và đúng trọng tâm, không đưa ra thông tin người dùng nếu họ không hỏi (dùng context khi cần). "
    "Khi người dùng hỏi các thông tin về bản thân thì hãy sử dụng context để trả lời. "
    
)

def _conversation_to_messages(conversation: Conversation, limit: int = 20) -> list[dict]:
    """
    Build chat history for Gemini: list of {role, parts: [{text}]}.
    Oldest messages first, limited by `limit`.
    """
    msgs: Sequence[Message] = conversation.messages[-limit:] if len(conversation.messages) > limit else conversation.messages
    contents: list[dict] = []
    for m in msgs:
        role = "user" if m.role == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m.content}]})
    return contents


def _build_patient_context(patient: Patient) -> str:
    return (
        f"[BENH NHAN]\n"
        f"- Ho ten: {patient.full_name or 'chua co'}\n"
        f"- Tom tat: {patient.medical_summary or 'chua co mo ta chi tiet'}\n"
    )


def chat_with_gemini(
    db: Session,
    *,
    patient_id: str,
    user_message: str,
    conversation_id: str | None = None,
) -> tuple[str, Conversation]:
    """
    Core chat flow:
    - ensure patient exists
    - get or create conversation
    - load recent messages as context
    - call Gemini
    - store user + assistant messages
    """
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise ValueError("Patient not found")

    if conversation_id:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.patient_id == patient_id)
            .first()
        )
    else:
        conv = None

    if conv is None:
        conv = Conversation(patient_id=patient_id, title=None)
        db.add(conv)
        db.flush()

    history_contents = _conversation_to_messages(conv)

    # Keep only minimal patient context + vector retrieval.
    patient_context = _build_patient_context(patient)
    rag_context = get_relevant_context(db, patient_id=patient_id, query=user_message)
    if rag_context:
        patient_context = f"{patient_context}\n\n{rag_context}"

    user_content = {
        "role": "user",
        "parts": [
            {"text": patient_context},
            {"text": user_message},
        ],
    }

    model = get_gemini_model()

    response = model.generate_content(
        contents=history_contents + [user_content],
        system_instruction=SYSTEM_INSTRUCTION,
    )

    try:
        assistant_text = (response.text or "").strip()
    except Exception:
        assistant_text = ""

    user_msg = Message(conversation_id=conv.id, role="user", content=user_message)
    assistant_msg = Message(conversation_id=conv.id, role="assistant", content=assistant_text)
    db.add_all([user_msg, assistant_msg])
    db.commit()
    db.refresh(conv)

    return assistant_text, conv
