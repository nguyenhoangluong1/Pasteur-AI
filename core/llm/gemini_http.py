"""Map Gemini SDK failures to HTTP-friendly signals (avoid opaque 500)."""

from __future__ import annotations

from google.genai.errors import ClientError, ServerError


def gemini_region_blocked(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "user location is not supported" in s or (
        "failed_precondition" in s and "location" in s
    )


def suggest_status_for_gemini_client_error(exc: ClientError) -> int:
    low = str(exc).lower()
    if gemini_region_blocked(exc):
        return 503
    if "429" in low or "resource_exhausted" in low or "quota" in low:
        return 429
    if "401" in low or "403" in low or "permission" in low or "api key" in low:
        return 502
    return 502


def http_detail_message(exc: BaseException) -> str:
    if gemini_region_blocked(exc):
        return (
            "Gemini API không khả dụng tại khu vực mạng của máy chủ (Google: "
            "User location is not supported). Gợi ý: chạy backend trên VPS ở quốc gia "
            "được Google hỗ trợ, hoặc cấu hình LLM_ROUTER_MODE=local_only/hybrid với "
            "LOCAL_LLM_ENDPOINT."
        )
    if isinstance(exc, ServerError):
        return f"Gemini API tạm không phản hồi: {exc}"
    if isinstance(exc, ClientError):
        return f"Lỗi Gemini API: {exc}"
    return str(exc)
