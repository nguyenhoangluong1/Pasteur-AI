"""
Tiền xử lý âm thanh trước STT (tuỳ chọn).

- ffmpeg_highpass / ffmpeg_bandpass: high-pass + low-pass dải thoại + mono 16 kHz WAV (giảm gió/HF hiss).
  Cần ffmpeg trong PATH hoặc đường dẫn đầy đủ qua STT_FFMPEG_BIN. Thất bại → dùng nguyên bản ghi.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)
_FFMPEG_MISSING_LOGGED = False

# Dải thoại gọn + cắt gió thấp; low-pass giảm nhiễu HF không mang ngữ âm rõ cho Whisper 16 kHz.
_FFMPEG_SPEECH_AF = "highpass=f=150,lowpass=f=6800"


def preprocess_audio_for_stt(
    audio_bytes: bytes,
    mime: str,
    *,
    mode: str,
    ffmpeg_bin: str,
) -> tuple[bytes, str]:
    """Trả về (bytes, mime). Không đổi nếu mode none, lỗi, hoặc thiếu ffmpeg."""
    m = (mode or "none").strip().lower()
    if m == "none" or not audio_bytes:
        return audio_bytes, mime
    if m not in ("ffmpeg_highpass", "ffmpeg_bandpass"):
        logger.warning("Unknown STT audio preprocess mode %r — skip.", mode)
        return audio_bytes, mime

    out = _ffmpeg_speech_chain_wav(audio_bytes, mime, ffmpeg_bin=ffmpeg_bin)
    if out:
        return out, "audio/wav"
    return audio_bytes, mime


def _resolve_ffmpeg_executable(ffmpeg_bin: str) -> str | None:
    raw = (ffmpeg_bin or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return str(p.resolve())
    found = shutil.which(raw)
    return found


def _suffix_for_mime(mime: str) -> str:
    ml = (mime or "").lower()
    if "wav" in ml:
        return ".wav"
    if "mpeg" in ml or "mp3" in ml:
        return ".mp3"
    if "mp4" in ml or "m4a" in ml:
        return ".m4a"
    if "ogg" in ml:
        return ".ogg"
    return ".webm"


def _ffmpeg_highpass_wav(audio_bytes: bytes, mime: str, *, ffmpeg_bin: str) -> bytes | None:
    global _FFMPEG_MISSING_LOGGED
    exe = _resolve_ffmpeg_executable(ffmpeg_bin)
    if not exe:
        if not _FFMPEG_MISSING_LOGGED:
            logger.warning(
                "Không tìm thấy ffmpeg (%s) — bỏ qua STT_AUDIO_PREPROCESS.",
                ffmpeg_bin,
            )
            _FFMPEG_MISSING_LOGGED = True
        return None

    suffix = _suffix_for_mime(mime)
    in_path: str | None = None
    out_path: str | None = None
    try:
        fd_in, in_path = tempfile.mkstemp(suffix=suffix)
        os.write(fd_in, audio_bytes)
        os.close(fd_in)
        out_tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        out_path = out_tmp.name
        out_tmp.close()

        cmd = [
            exe,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            in_path,
            "-af",
            _FFMPEG_SPEECH_AF,
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            out_path,
        ]
        subprocess.run(
            cmd,
            check=True,
            timeout=120,
            capture_output=True,
        )
        data = Path(out_path).read_bytes()
        # WAV tối thiểu ~44 byte header; ít hơn ≈ lỗi ffmpeg im lặng
        if len(data) < 64:
            logger.debug("ffmpeg output too small (%s bytes) — fallback to original.", len(data))
            return None
        return data
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("ffmpeg preprocess failed: %s", exc)
        return None
    finally:
        if in_path:
            Path(in_path).unlink(missing_ok=True)
        if out_path:
            Path(out_path).unlink(missing_ok=True)
