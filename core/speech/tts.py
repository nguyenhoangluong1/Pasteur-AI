"""
Text-to-speech: edge-tts (Microsoft Edge voices), giong tieng Viet, khong can API key.
"""

from __future__ import annotations

import asyncio

import edge_tts

from core.config import get_settings


def _normalize_tts_input(text: str, voice: str | None = None) -> tuple[str, str]:
    raw = (text or "").strip()
    settings = get_settings()
    max_chars = getattr(settings, "tts_max_chars", 5000)
    if len(raw) > max_chars:
        raw = raw[: max_chars - 3] + "..."
    v = (voice or "").strip() or settings.tts_voice
    return raw, v


async def synthesize_speech_chunks_async(text: str, voice: str | None = None):
    """
    Stream cac chunk audio MP3 tu edge-tts.
    """
    raw, v = _normalize_tts_input(text, voice=voice)
    if not raw:
        return
    settings = get_settings()
    timeout_seconds = max(1, int(getattr(settings, "tts_timeout_seconds", 20)))
    communicate = edge_tts.Communicate(raw, v)

    async def _stream_audio():
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    agen = _stream_audio()
    while True:
        try:
            chunk = await asyncio.wait_for(agen.__anext__(), timeout=timeout_seconds)
        except StopAsyncIteration:
            break
        yield chunk


async def synthesize_speech_async(
    text: str, voice: str | None = None
) -> tuple[bytes, str]:
    """
    Tra ve (audio_bytes, mime_type). Dinh dang mp3.
    `voice`: override giong edge-tts (vd vi-VN-HoaiMyNeural); None = lay tu settings.
    """
    raw = (text or "").strip()
    if not raw:
        return b"", "audio/mpeg"
    normalized_text, v = _normalize_tts_input(raw, voice=voice)
    communicate = edge_tts.Communicate(normalized_text, v)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks), "audio/mpeg"


def synthesize_speech_sync(text: str, voice: str | None = None) -> tuple[bytes, str]:
    """Chay TTS dong bo (dung trong FastAPI sync route)."""
    settings = get_settings()
    timeout_seconds = max(1, int(getattr(settings, "tts_timeout_seconds", 20)))
    return asyncio.run(
        asyncio.wait_for(synthesize_speech_async(text, voice=voice), timeout_seconds)
    )
