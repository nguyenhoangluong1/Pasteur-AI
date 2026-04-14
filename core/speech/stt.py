"""
Speech-to-text: dùng Gemini multimodal (audio + prompt) với cùng GEMINI_API_KEY.
"""

from __future__ import annotations

from google import genai
from google.genai import types

from core.config import get_settings


def _normalize_mime(mime: str) -> str:
    m = (mime or "audio/webm").split(";")[0].strip().lower()
    if m in ("audio/x-wav", "audio/wave"):
        return "audio/wav"
    return m


def transcribe_audio(audio_bytes: bytes, mime_type: str | None = None) -> str:
    """
    Chuyen audio thanh van ban tieng Viet.
    mime_type: audio/webm, audio/wav, audio/mpeg, audio/mp4, ...
    """
    if not audio_bytes:
        raise ValueError("Audio rong")

    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY chua cau hinh (can cho STT)")

    mime = _normalize_mime(mime_type or "audio/webm")
    client = genai.Client(api_key=settings.gemini_api_key)
    model = settings.gemini_model

    prompt = (
        "Ban la cong cu chuyen loi noi thanh chu. "
        "Nghe file audio va ghi lai DUNG loi nguoi noi bang tieng Viet. "
        "Bo qua tap am moi truong (quat, xe, tieng tre em, tieng click, am thanh nen). "
        "Khong doan them noi dung neu khong nghe ro. "
        "Chi tra ve ban ghi chu, khong giai thich, khong them dau ngoac hay tien to."
    )

    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_text(text=prompt),
            types.Part.from_bytes(data=audio_bytes, mime_type=mime),
        ],
        config=types.GenerateContentConfig(
            temperature=0.0,
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("STT khong tra ve van ban")
    return text
