"""
Heuristic kiểm tra transcript STT / câu hỏi ngắn — tránh hallucination và RAG nhầm.

Nguyên tắc:
- Tiếng Việt: dùng tách theo khoảng trắng (từ), không dùng heuristic filler/số ký tự 1-char (dễ sai).
- Whisper: không gộp gợi ý thuốc/tên BN vào prompt nếu không bật — giảm bias khi chỉ có nền nhiễu.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

_VI_SPLIT = re.compile(r"\s+")


def normalize_text_for_check(text: str) -> str:
    s = unicodedata.normalize("NFC", (text or "").strip().lower())
    return re.sub(r"\s+", " ", s)


def looks_like_media_promo_hallucination(text: str) -> bool:
    """
    Whisper hay trả về câu outro/subscribe kiểu YouTube khi chỉ có nền nhiễu (silence + fan).
    Không chặn hội thoại thường — chỉ khớp cụm đặc trưng template quảng bá/kênh.
    """
    s = normalize_text_for_check(text)
    if len(s) < 10:
        return False

    # Kênh viral hay xuất hiện trong hallucination tiếng Việt
    if all(p in s for p in ("ghiền", "mì", "gõ")):
        return True

    if "để không bỏ lỡ" in s and "video" in s:
        return True

    if re.search(r"bật\s+chuông(?:\s+thông\s+báo)?", s):
        return True

    if any(p in s for p in ("nhấn like", "like và subscribe", "ấn nút đăng ký", "ấn đăng ký")):
        return True

    if "subscribe" in s or "subcribe" in s:
        # Combo điển hình outro / đăng ký kênh (không khớp "subscribe" đứng một mình)
        if any(x in s for x in ("để không bỏ lỡ", "chuông", "video")):
            return True
        if "kênh" in s and len(s) < 120:
            return True

    return False


def looks_like_repetition_hallucination(text: str) -> bool:
    """Lặp cụm/từ bất thường — hay gặp khi chỉ có nền hoặc silence."""
    s = normalize_text_for_check(text)
    if len(s) < 2:
        return True
    if len(s) > 80 and " " not in s:
        return True

    words = [w for w in _VI_SPLIT.split(s) if w]
    if len(words) < 4:
        return False

    uniq_ratio = len(set(words)) / len(words)
    if len(words) >= 12 and uniq_ratio < 0.28:
        return True

    if len(words) >= 10:
        bigrams = list(zip(words, words[1:]))
        if bigrams:
            top = Counter(bigrams).most_common(1)[0][1]
            if top / len(bigrams) > 0.42:
                return True

    if re.search(r"(.)\1{7,}", s):
        return True

    return False


def transcript_acceptable(text: str, *, level: str) -> bool:
    """
    level: off | light | medium | strict
    - off: chỉ chặn rỗng
    - light: rỗng + lặp/hallucination rõ (không siết độ dài — tránh chặn nhầm câu ngắn đúng)
    - medium: light + chặn transcript cực ngắn không rõ nghĩa (trừ whitelist)
    - strict: medium + độ dài tối thiểu cao hơn
    """
    lv = (level or "light").strip().lower()
    if lv == "normal":
        lv = "light"  # tương thích .env cũ (normal | strict)
    s = normalize_text_for_check(text)
    if not s:
        return False
    if lv == "off":
        return True
    if looks_like_repetition_hallucination(text):
        return False
    if looks_like_media_promo_hallucination(text):
        return False

    words = [w for w in _VI_SPLIT.split(s) if w]

    short_ok_1 = frozenset(
        {
            "có",
            "không",
            "ừ",
            "ừm",
            "vâng",
            "dạ",
            "ok",
            "dừng",
            "tiếp",
            "rồi",
            "được",
            "nghe",
        }
    )
    short_ok_2 = frozenset({"được không", "xin chào"})

    if lv in ("medium", "strict"):
        if len(words) == 1 and words[0] in short_ok_1:
            return True
        if len(words) == 2 and " ".join(words) in short_ok_2:
            return True
        # medium: ít nhất 2 từ HOẶC 1 từ dài (tránh "ơ", "à")
        if lv == "medium":
            if len(words) >= 2:
                return True
            if len(words) == 1 and len(words[0]) >= 5:
                return True
            return False
        # strict
        if len(words) >= 3 and len(s) >= 14:
            return True
        if len(words) == 2 and len(s) >= 10:
            return True
        return False

    return True


def query_passes_reference_gate(
    query: str,
    *,
    gate_short_queries: bool,
    min_chars: int,
    min_words: int,
) -> bool:
    """
    Câu đủ “có nghĩa” để gắn khối tham chiếu (hồ sơ / RAG) — không sửa chữa input,
    chỉ quyết định có đính kèm tài liệu tham chiếu hay không (tránh transcript rác sau mic).
    """
    q = normalize_text_for_check(query)
    if not q:
        return False
    if looks_like_repetition_hallucination(query):
        return False
    if looks_like_media_promo_hallucination(query):
        return False
    if not gate_short_queries:
        return True
    words = [w for w in _VI_SPLIT.split(q) if w]
    if len(q) < max(1, min_chars) or len(words) < max(1, min_words):
        return False
    return True


def query_should_use_rag(
    query: str,
    *,
    rag_enabled: bool,
    gate_short_queries: bool,
    min_chars: int,
    min_words: int,
) -> bool:
    """Chỉ gọi embedding/RAG khi bật rag và câu vượt cổng tham chiếu."""
    if not rag_enabled:
        return False
    return query_passes_reference_gate(
        query,
        gate_short_queries=gate_short_queries,
        min_chars=min_chars,
        min_words=min_words,
    )
