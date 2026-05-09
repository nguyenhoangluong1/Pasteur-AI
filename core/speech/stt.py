"""
Speech-to-text:
- groq (mặc định): Whisper qua Groq + GROQ_API_KEY
- gemini: Gemini multimodal + GEMINI_API_KEY
"""

from __future__ import annotations

import concurrent.futures
import re
import time
import unicodedata
from functools import lru_cache
from io import BytesIO

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from core.config import get_settings

# Whisper: prompt khớp ngôn ngữ nói + từ vựng liên quan; tránh quá dài (API có giới hạn).
_WHISPER_STYLE_VI = (
    "Bản phiên âm tiếng Việt, có dấu đầy đủ, đúng chính tả thông dụng. "
    "Một lớp thoại duy nhất, không ghi chú thích hay nhãn. "
    "Bỏ qua tiếng hít thở, tiếng vỗ miệng, tiếng gõ bàn phím/mic, "
    "và các từ đệm rời rạc (ví dụ ừ, à, hả, hở) nếu không mang nghĩa. "
    "Không bịa nội dung nếu không nghe rõ; có thể bỏ qua đoạn chỉ là ồn nền."
)

_GEMINI_STT_SYSTEM_VI = (
    "Bạn là công cụ phiên âm tiếng Việt. "
    "Nghe audio và ghi lại đúng lời người nói, có dấu đầy đủ, chính tả thông dụng. "
    "Bỏ qua tạp âm môi trường (quạt, xe, trẻ em, click chuột, nhạc nền mờ, gió mic). "
    "Bỏ qua tiếng hít thở, lắp bắp không mang nghĩa; giữ từ đệm có chức năng (ví dụ 'ạ', 'nhé' nếu là phần câu). "
    "Không đoán thêm nếu không nghe rõ; không thêm lời dẫn hay giải thích. "
    "Thuật ngữ y khoa và tên thuốc: ưu tiên viết đúng dạng tiếng Việt thường gặp."
)


def _normalize_mime(mime: str) -> str:
    m = (mime or "audio/webm").split(";")[0].strip().lower()
    if m in ("audio/x-wav", "audio/wave"):
        return "audio/wav"
    return m


def _audio_filename_for_mime(mime: str) -> str:
    if "wav" in mime:
        return "recording.wav"
    if "mpeg" in mime or "mp3" in mime:
        return "recording.mp3"
    if "mp4" in mime or "m4a" in mime:
        return "recording.m4a"
    return "recording.webm"


def _post_process_transcript(text: str, *, enabled: bool) -> str:
    if not enabled or not (text or "").strip():
        return (text or "").strip()
    s = unicodedata.normalize("NFC", text.strip())
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _build_whisper_prompt(hints: list[str], extra_from_env: str) -> str | None:
    parts: list[str] = [_WHISPER_STYLE_VI.strip()]
    extra = (extra_from_env or "").strip()
    if extra:
        parts.append(extra)
    if hints:
        parts.append("Từ khóa ưu tiên (giữ đúng nếu nghe thấy): " + "; ".join(hints[:24]))
    joined = " ".join(parts).strip()
    return joined if joined else None


@lru_cache(maxsize=1)
def _get_stt_client(api_key: str):
    return genai.Client(api_key=api_key)


def _transcribe_groq_whisper(
    audio_bytes: bytes,
    mime: str,
    domain_hints: list[str] | None,
) -> str:
    from groq import Groq

    settings = get_settings()
    key = (settings.groq_api_key or "").strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY chua cau hinh (can cho STT_PROVIDER=groq)")

    timeout = max(1, int(getattr(settings, "stt_timeout_seconds", 35)))
    client = Groq(api_key=key, timeout=timeout)
    model = (settings.groq_stt_model or "whisper-large-v3").strip()

    hints = [h.strip() for h in (domain_hints or []) if h and h.strip()]
    extra = getattr(settings, "stt_whisper_extra_prompt", "") or ""
    prompt = _build_whisper_prompt(hints, extra)

    bio = BytesIO(audio_bytes)
    bio.name = _audio_filename_for_mime(mime)

    tr = client.audio.transcriptions.create(
        file=bio,
        model=model,
        language="vi",
        prompt=prompt,
        temperature=0.0,
    )
    raw = (getattr(tr, "text", None) or "").strip()
    if not raw:
        raise RuntimeError("Groq STT khong tra ve van ban")
    norm = getattr(settings, "stt_normalize_output", True)
    return _post_process_transcript(raw, enabled=norm)


def _transcribe_gemini(
    audio_bytes: bytes,
    mime: str,
    domain_hints: list[str] | None,
) -> str:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY chua cau hinh (can cho STT)")

    client = _get_stt_client(settings.gemini_api_key)
    model = settings.resolved_stt_model
    fallback_model = settings.resolved_stt_alternate_model
    fallback_enabled = bool(
        getattr(settings, "stt_model_fallback_enabled", True)
        and fallback_model
        and fallback_model != model
    )
    timeout_seconds = max(1, int(getattr(settings, "stt_timeout_seconds", 35)))
    retry_attempts = max(1, int(getattr(settings, "stt_retry_attempts", 2)))

    hints = [h.strip() for h in (domain_hints or []) if h and h.strip()]
    hint_block = ""
    if hints:
        hint_block = (
            "\n\nTừ khóa ưu tiên (giữ đúng nếu nghe thấy): "
            + "; ".join(hints[:10])
        )

    prompt = (
        _GEMINI_STT_SYSTEM_VI
        + " Chỉ trả về bản ghi chép, không giả thích, không thêm ngoặc hay tiền tố."
        + hint_block
    )

    def _generate_once(model_name: str) -> str:
        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=audio_bytes, mime_type=mime),
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
            ),
        )
        text_out = (response.text or "").strip()
        if not text_out:
            raise RuntimeError("STT khong tra ve van ban")
        return text_out

    last_error: Exception | None = None
    for attempt in range(1, retry_attempts + 1):
        current_model = model
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_generate_once, current_model)
        try:
            result = future.result(timeout=timeout_seconds)
            executor.shutdown(wait=False, cancel_futures=True)
            norm = getattr(settings, "stt_normalize_output", True)
            return _post_process_transcript(result, enabled=norm)
        except concurrent.futures.TimeoutError:
            last_error = RuntimeError(
                f"STT timeout sau {timeout_seconds}s (lan {attempt}/{retry_attempts})"
            )
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
        except ClientError as exc:
            last_error = exc
            executor.shutdown(wait=False, cancel_futures=True)
            text = str(exc).lower()
            should_switch_model = (
                fallback_enabled
                and (
                    "quota" in text
                    or "resource_exhausted" in text
                    or "rate limit" in text
                    or "429" in text
                    or "not found" in text
                    or "not supported" in text
                )
            )
            if should_switch_model:
                model = fallback_model
                fallback_enabled = False
        except Exception as exc:
            last_error = exc
            executor.shutdown(wait=False, cancel_futures=True)

        if attempt < retry_attempts:
            time.sleep(0.4 * attempt)

    raise RuntimeError(f"STT failed: {last_error}") from last_error


def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str | None = None,
    *,
    domain_hints: list[str] | None = None,
) -> str:
    """
    Chuyen audio thanh van ban tieng Viet.
    mime_type: audio/webm, audio/wav, audio/mpeg, audio/mp4, ...
    """
    if not audio_bytes:
        raise ValueError("Audio rong")

    settings = get_settings()
    mime = _normalize_mime(mime_type or "audio/webm")
    provider = (getattr(settings, "stt_provider", None) or "groq").strip().lower()

    if provider == "groq":
        return _transcribe_groq_whisper(audio_bytes, mime, domain_hints)

    return _transcribe_gemini(audio_bytes, mime, domain_hints)
