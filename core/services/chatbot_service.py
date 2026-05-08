from collections.abc import Sequence

from sqlalchemy.orm import Session

from core.db.models import Conversation, Message, Patient
from core.llm import get_gemini_model
from core.services.vector_rag_service import get_relevant_context


SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý y tế ảo nói tiếng Việt, giọng điệu thân thiện và chuyên nghiệp. "
    "Mục tiêu: trả lời đúng trọng tâm, tự nhiên như người thật, dễ nghe khi phát bằng TTS. "
    "Không nên nói hết bệnh án hay thuốc thang nếu chưa được hỏi đến để hạn chế token. "
    "Những câu hỏi ngắn như xin chào, cảm ơn hay giao tiếp xã giao hãy trả lời thân thiện và ngắn gọn. "
    "Ưu tiên cấu trúc: (1) trả lời trực tiếp câu hỏi trước, (2) nêu 1-3 hành động cụ thể người dùng nên làm ngay, "
    "(3) thêm 1 câu nhắc theo dõi nếu cần. "
    "Nếu là gợi ý uống thuốc, nhưng trong hồ sơ chưa có thì hãy flex thời gian thường là sau khi ăn xong hoặc với 1 số bệnh đặc biệt là trước ăn"
    "Độ dài mặc định 2-4 câu ngắn; chỉ dài hơn khi người dùng yêu cầu chi tiết. "
    "Mỗi câu chỉ chứa một ý chính, dùng từ phổ thông, tránh thuật ngữ phức tạp; nếu buộc dùng thuật ngữ, giải thích ngắn ngay sau đó. "
    "Không mở đầu xã giao dài dòng, không lặp lại câu hỏi, không lan man, không liệt kê quá nhiều đầu dòng. "
    "Ưu tiên thông tin quan trọng theo thứ tự: mức độ cần xử lý ngay, việc cần làm hôm nay, việc cần theo dõi. "
    "Khi dữ liệu chưa đủ, nói rõ thiếu dữ liệu nào và hỏi đúng 1 câu ngắn để làm rõ. "
    "Nếu có dấu hiệu nguy hiểm, khuyến nghị liên hệ cơ sở y tế/đi khám sớm bằng câu rõ ràng, không gây hoảng sợ. "
    "Không chẩn đoán xác định, không kê đơn thuốc, không thay thế bác sĩ điều trị. "
    "Nếu người dùng hỏi ngoài y tế, trả lời ngắn gọn nhưng vẫn lịch sự. "
    "Kết thúc bằng một câu an toàn ngắn khi phù hợp: 'Bạn nhớ trao đổi thêm với bác sĩ khi tái khám nhé.'"
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

    assistant_text = response.text or ""

    user_msg = Message(conversation_id=conv.id, role="user", content=user_message)
    assistant_msg = Message(conversation_id=conv.id, role="assistant", content=assistant_text)
    db.add_all([user_msg, assistant_msg])
    db.commit()
    db.refresh(conv)

    return assistant_text, conv
