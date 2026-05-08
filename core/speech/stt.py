"""
Speech-to-text: dùng Gemini multimodal (audio + prompt) với cùng GEMINI_API_KEY.
"""

from __future__ import annotations

import concurrent.futures
import time
from functools import lru_cache

from google import genai
from google.genai import types

from core.config import get_settings


def _normalize_mime(mime: str) -> str:
    m = (mime or "audio/webm").split(";")[0].strip().lower()
    if m in ("audio/x-wav", "audio/wave"):
        return "audio/wav"
    return m


@lru_cache(maxsize=1)
def _get_stt_client(api_key: str):
    # Reuse client across requests to cut per-call setup overhead.
    return genai.Client(api_key=api_key)


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
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY chua cau hinh (can cho STT)")

    mime = _normalize_mime(mime_type or "audio/webm")
    client = _get_stt_client(settings.gemini_api_key)
    model = settings.resolved_stt_model
    timeout_seconds = max(1, int(getattr(settings, "stt_timeout_seconds", 20)))
    retry_attempts = max(1, int(getattr(settings, "stt_retry_attempts", 2)))

    hints = [h.strip() for h in (domain_hints or []) if h and h.strip()]
    hint_block = ""
    if hints:
        # Boost recognition for medical names/terms from patient profile.
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

    def _generate_once() -> str:
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

    last_error: Exception | None = None
    for attempt in range(1, retry_attempts + 1):
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_generate_once)
        try:
            result = future.result(timeout=timeout_seconds)
            executor.shutdown(wait=False, cancel_futures=True)
            return result
        except concurrent.futures.TimeoutError:
            last_error = RuntimeError(
                f"STT timeout sau {timeout_seconds}s (lan {attempt}/{retry_attempts})"
            )
            future.cancel()
            # Do not block current request while background worker finishes.
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception as exc:
            last_error = exc
            executor.shutdown(wait=False, cancel_futures=True)

        if attempt < retry_attempts:
            time.sleep(0.4 * attempt)

    raise RuntimeError(f"STT failed: {last_error}") from last_error
