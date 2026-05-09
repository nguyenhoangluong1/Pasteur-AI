"""
Cổng năng lượng trên PCM WAV (mono/stereo int16) sau tiền xử lý ffmpeg.

Mục tiêu: giảm gửi Whisper các đoạn chỉ có nền đều (quạt, máy lạnh) — RMS toàn clip có thể cao
nhưng ít biến động theo thời gian so với tiếng nói có âm tiết.
"""

from __future__ import annotations

import logging
import struct
import wave
from io import BytesIO

logger = logging.getLogger(__name__)


def wav_voice_metrics(audio_bytes: bytes) -> dict[str, float] | None:
    """
    Trả về peak, overall_rms, max_window_rms, mean_window_rms, modulation (max/mean window).
    None nếu không parse được WAV / không phải PCM 16-bit.
    """
    try:
        bio = BytesIO(audio_bytes)
        with wave.open(bio, "rb") as wf:
            channels = wf.getnchannels()
            sw = wf.getsampwidth()
            sr = wf.getframerate()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
    except Exception as exc:
        logger.debug("wav parse skip: %s", exc)
        return None

    if sw != 2 or channels < 1 or not raw or sr < 8000:
        return None

    # Chỉ kênh 0 (mono hoặc “mic trái”)
    frame_bytes = 2 * channels
    n = len(raw) // frame_bytes
    if n < 16:
        return None

    samples: list[float] = []
    peak = 0.0
    sum_sq = 0.0
    for i in range(n):
        off = i * frame_bytes
        v_i16 = struct.unpack_from("<h", raw, off)[0]
        v = v_i16 / 32768.0
        samples.append(v)
        a = abs(v)
        if a > peak:
            peak = a
        sum_sq += v * v

    overall_rms = (sum_sq / n) ** 0.5

    # ~100 ms @ 16 kHz
    win = max(int(sr * 0.1), 400)
    window_rms_vals: list[float] = []
    for start in range(0, len(samples) - win + 1, max(win // 2, 200)):
        chunk = samples[start : start + win]
        ssum = sum(x * x for x in chunk)
        window_rms_vals.append((ssum / len(chunk)) ** 0.5)

    if not window_rms_vals:
        window_rms_vals = [overall_rms]

    max_wrms = max(window_rms_vals)
    mean_wrms = sum(window_rms_vals) / len(window_rms_vals)
    modulation = max_wrms / (mean_wrms + 1e-9)

    return {
        "peak": peak,
        "overall_rms": overall_rms,
        "max_window_rms": max_wrms,
        "mean_window_rms": mean_wrms,
        "modulation": modulation,
    }


def wav_passes_voice_gate(
    audio_bytes: bytes,
    *,
    min_peak: float,
    min_window_rms: float,
    min_modulation: float,
    loud_peak_bypass: float,
) -> tuple[bool, dict[str, float] | None]:
    """
    loud_peak_bypass: nếu peak >= ngưỡng này thì bỏ qua kiểm tra modulation (tránh FP tiếng đều nhưng to).
    """
    m = wav_voice_metrics(audio_bytes)
    if m is None:
        return True, None

    peak = m["peak"]
    max_wrms = m["max_window_rms"]
    mod = m["modulation"]

    if peak < min_peak:
        return False, m
    if max_wrms < min_window_rms:
        return False, m
    if peak >= loud_peak_bypass:
        return True, m
    if mod < min_modulation:
        return False, m
    return True, m


def raise_if_wav_too_quiet_or_flat(
    audio_bytes: bytes,
    *,
    enabled: bool,
    min_peak: float,
    min_window_rms: float,
    min_modulation: float,
    loud_peak_bypass: float,
) -> None:
    if not enabled:
        return
    ok, metrics = wav_passes_voice_gate(
        audio_bytes,
        min_peak=min_peak,
        min_window_rms=min_window_rms,
        min_modulation=min_modulation,
        loud_peak_bypass=loud_peak_bypass,
    )
    if ok:
        return
    logger.info(
        "STT wav gate reject peak=%.4f max_win_rms=%.4f mod=%.3f",
        (metrics or {}).get("peak", 0),
        (metrics or {}).get("max_window_rms", 0),
        (metrics or {}).get("modulation", 0),
    )
    raise RuntimeError(
        "Âm thanh giống nền hoặc quá nhỏ (không đủ độ biến động như tiếng nói). "
        "Hãy nói gần mic hơn, tắt quạt gần mic hoặc giảm tiếng xung quanh rồi thử lại."
    )
