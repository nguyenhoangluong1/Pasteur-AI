"""
Speech-to-text:
- gemini (mac dinh): Gemini multimodal + GEMINI_API_KEY
- groq: Whisper qua Groq OpenAI-compatible API + GROQ_API_KEY (it huong khi Google chan khu vuc)
"""

from __future__ import annotations

import concurrent.futures
import time
from functools import lru_cache
from io import BytesIO

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from core.config import get_settings


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

    timeout = max(1, int(getattr(settings, "stt_timeout_seconds", 20)))
    client = Groq(api_key=key, timeout=timeout)
    model = (settings.groq_stt_model or "whisper-large-v3-turbo").strip()

    hints = [h.strip() for h in (domain_hints or []) if h and h.strip()]
    prompt = None
    if hints:
        prompt = "Tu khoa uu tien (ghi dung neu nghe thay): " + "; ".join(hints[:30])

    bio = BytesIO(audio_bytes)
    bio.name = _audio_filename_for_mime(mime)

    tr = client.audio.transcriptions.create(
        file=bio,
        model=model,
        language="vi",
        prompt=prompt,
        temperature=0.0,
    )
    text = (getattr(tr, "text", None) or "").strip()
    if not text:
        raise RuntimeError("Groq STT khong tra ve van ban")
    return text


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
    timeout_seconds = max(1, int(getattr(settings, "stt_timeout_seconds", 20)))
    retry_attempts = max(1, int(getattr(settings, "stt_retry_attempts", 2)))

    hints = [h.strip() for h in (domain_hints or []) if h and h.strip()]
    hint_block = ""
    if hints:
        hint_block = (
            "\n\nTu khoa uu tien (neu nghe thay thi giu nguyen): "
            + "; ".join(hints[:10])
        )

    prompt = (
        "Ban la cong cu chuyen loi noi thanh chu. "
        "Nghe file audio va ghi lai DUNG loi nguoi noi bang tieng Viet. "
        "Bo qua tap am moi truong (quat, xe, tieng tre em, tieng click, am thanh nen,...). "
        "Khong doan them noi dung neu khong nghe ro. "
        "Neu co thuat ngu/ten thuoc y khoa, uu tien ghi dung chinh ta tieng Viet."
        "Chi tra ve ban ghi chu, khong giai thich, khong them dau ngoac hay tien to."
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
            return result
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
    provider = (getattr(settings, "stt_provider", None) or "gemini").strip().lower()

    if provider == "groq":
        return _transcribe_groq_whisper(audio_bytes, mime, domain_hints)

    return _transcribe_gemini(audio_bytes, mime, domain_hints)
