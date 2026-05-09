from collections.abc import Sequence

from sqlalchemy.orm import Session

from core.config import get_settings
from core.db.models import Conversation, Message, Patient
from core.llm import get_gemini_model
from core.services.vector_rag_service import get_relevant_context
from core.speech.stt_noise import (
    looks_like_stt_promo_or_template_hallucination,
    query_passes_reference_gate,
    query_should_use_rag,
)

# Không gọi LLM — tránh trả lời theo transcript “ảo” sau STT trên nền nhiễu (outro video, subscribe,...).
_PROMO_OR_OUTRO_NOISE_REPLY = (
    "Nội dung giống transcript máy khi chỉ có tiếng nền (mic/webcam), không phải câu bạn muốn nói. "
    "Hãy nói lại gần mic, giảm quạt/TV gần đó. "
    "Nếu cần hỏi sức khỏe, xin nói rõ triệu chứng."
)

SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý sức khỏe tiếng Việt trong ứng dụng hồ sơ bệnh nhân. "
    "Ưu tiên hỗ trợ câu hỏi y tế, giải thích dễ hiểu, câu ngắn nếu cần đọc loa; không chẩn đoán chắc chắn, không kê đơn hay thay bác sĩ. "
    "Nếu câu hiện tại không liên quan y tế/hồ sơ (địa lý, tin học, thể thao, đố vui, kiến thức phổ thông,...): trả lời trúng điểm điều họ hỏi; "
    "KHÔNG chào tên bệnh nhân, KHÔNG nhắc lịch thuốc, KHÔNG tự tóm tắt hồ sơ — kể cả khi họ đã gửi kèm khối '[NGỮ CẢNH]' (đó chỉ là tài liệu tham chiếu có điều kiện, khi không cần thì bỏ qua như không tồn tại). "
    "Trò chuyện và yêu cầu bên lề khác: vẫn trả lời tự nhiên, có thể thêm một câu mời hỗ trợ sức khỏe nếu phù hợp — nhưng đừng lấn át ý họ hỏi. "
    "Chỉ khi họ đang hỏi về sức khỏe, triệu chứng, điều trị, thuốc, hoặc thông tin trong hồ sơ của họ: khi đó hãy dùng ngữ cảnh bệnh nhân/RAG (nếu có), đúng trọng tâm, không lộ chi tiết hồ sơ nếu họ không hỏi tới. "
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
        f"[HỒ SƠ BỆNH NHÂN — chỉ áp dụng khi câu đang hỏi về y tế / thông tin này]\n"
        f"- Họ tên: {patient.full_name or 'chưa có'}\n"
        f"- Tóm tắt: {patient.medical_summary or 'chưa có mô tả chi tiết'}\n"
    )


def _wrap_retrieval_reference(inner: str) -> str:
    """Model thường ưu tiên khối RAG có thuốc; bọc chỉ-dùng-khi-cần để câu bên lề không bị ép."""
    trimmed = (inner or "").strip()
    if not trimmed:
        return ""
    return (
        "[NGỮ CẢNH THAM CHIẾU — Bỏ qua HOÀN TOÀN nếu tin nhắn hiện tại không hỏi về y tế, thuốc, triệu chứng, hoặc hồ sơ]\n"
        "Không được mở bài hay kết thúc bằng việc đọc lại lịch thuốc nếu họ không nhắc tới điều đó trong câu hỏi.\n\n"
        f"{trimmed}\n"
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

    if looks_like_stt_promo_or_template_hallucination(user_message):
        assistant_text = _PROMO_OR_OUTRO_NOISE_REPLY
        user_msg = Message(conversation_id=conv.id, role="user", content=user_message)
        assistant_msg = Message(conversation_id=conv.id, role="assistant", content=assistant_text)
        db.add_all([user_msg, assistant_msg])
        db.commit()
        db.refresh(conv)
        return assistant_text, conv

    history_contents = _conversation_to_messages(conv)

    # Không sửa nội dung user_message — chỉ quyết định có đính kèm khối tham chiếu hay không.
    # Cùng cổng cho hồ sơ tối thiểu + RAG: câu quá ngắn/giống rác STT → chỉ gửi đúng câu người dùng (xử lý qua).
    settings = get_settings()
    gate_sq = bool(getattr(settings, "rag_gate_short_queries", True))
    min_c = int(getattr(settings, "rag_min_query_chars", 8))
    min_w = int(getattr(settings, "rag_min_query_words", 2))
    attach_reference = query_passes_reference_gate(
        user_message,
        gate_short_queries=gate_sq,
        min_chars=min_c,
        min_words=min_w,
    )
    ref_block = ""
    if attach_reference:
        patient_context = _build_patient_context(patient)
        rag_context = ""
        if query_should_use_rag(
            user_message,
            rag_enabled=bool(settings.rag_enabled),
            gate_short_queries=gate_sq,
            min_chars=min_c,
            min_words=min_w,
        ):
            rag_context = get_relevant_context(db, patient_id=patient_id, query=user_message)
        ref_block = _wrap_retrieval_reference(
            f"{patient_context}\n\n{rag_context}" if rag_context else patient_context
        )
    assembled = (
        ref_block.strip() + "\n\n────────────────\n[CÂU HIỆN TẠI — trả lời đúng dòng sau]\n"
        if ref_block.strip()
        else ""
    )
    assembled += user_message.strip()

    user_content = {"role": "user", "parts": [{"text": assembled}]}

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
