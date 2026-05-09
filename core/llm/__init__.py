"""
LLM provider helpers.
Default: Gemini API.
Optional extension: local/offline model (e.g. Qwen2.5-3B) via HTTP endpoint.
"""

from __future__ import annotations

import json
import threading
from urllib import request

from google import genai
from google.genai.errors import ClientError, ServerError

from core.config import get_settings
from core.llm.gemini_http import gemini_region_blocked

_model = None


class _SimpleResponse:
    def __init__(self, text: str):
        self.text = text


class _GeminiWrapper:
    def __init__(
        self,
        client: genai.Client,
        model: str,
        *,
        alternate_model: str | None = None,
        round_robin: bool = False,
    ):
        self._client = client
        self._model = model
        self._alternate_model = alternate_model
        self._round_robin = bool(round_robin and alternate_model and alternate_model != model)
        self._rr_counter = 0
        self._rr_lock = threading.Lock()
        self._fallback_model = "gemini-2.5-flash"

    def _pick_model(self) -> str:
        if not self._round_robin:
            return self._model
        with self._rr_lock:
            selected = self._model if self._rr_counter % 2 == 0 else self._alternate_model
            self._rr_counter += 1
        return selected or self._model

    def generate_content(self, contents, system_instruction=None):
        kwargs = {}
        if system_instruction is not None:
            kwargs["config"] = {"system_instruction": system_instruction}
        selected_model = self._pick_model()
        try:
            return self._client.models.generate_content(
                model=selected_model,
                contents=contents,
                **kwargs,
            )
        except ClientError as exc:
            # Geo / billing policy: switching model will not help.
            if gemini_region_blocked(exc):
                raise
            # Handle unsupported / unavailable model slug for current API key.
            text = str(exc).lower()
            should_fallback = (
                selected_model != self._fallback_model
                and ("not found" in text or "not supported" in text)
            )
            if not should_fallback:
                raise
            return self._client.models.generate_content(
                model=self._fallback_model,
                contents=contents,
                **kwargs,
            )
        except ServerError:
            # Some Gemma endpoints can intermittently return 500.
            if selected_model == self._fallback_model:
                raise
            return self._client.models.generate_content(
                model=self._fallback_model,
                contents=contents,
                **kwargs,
            )


class _LocalOpenAICompatWrapper:
    """
    Local model wrapper (offline extension), expects OpenAI-compatible endpoint:
    POST /v1/chat/completions
    """

    def __init__(self, endpoint: str, model: str, timeout_seconds: int):
        self._endpoint = endpoint
        self._model = model
        self._timeout_seconds = timeout_seconds

    def _to_openai_messages(self, contents, system_instruction=None):
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        for item in contents or []:
            role = item.get("role", "user")
            if role == "model":
                role = "assistant"
            parts = item.get("parts") or []
            text = " ".join((p.get("text") or "").strip() for p in parts if isinstance(p, dict)).strip()
            if text:
                messages.append({"role": role, "content": text})
        return messages

    def generate_content(self, contents, system_instruction=None):
        payload = {
            "model": self._model,
            "messages": self._to_openai_messages(contents, system_instruction=system_instruction),
            "temperature": 0.2,
        }
        raw = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self._endpoint,
            data=raw,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self._timeout_seconds) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        text = (
            ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
            or ""
        )
        return _SimpleResponse(text=text)


def _build_gemini_wrapper():
    settings = get_settings()
    if not getattr(settings, "gemini_api_key", None):
        raise RuntimeError("GEMINI_API_KEY is not configured in settings/.env")
    client = genai.Client(api_key=settings.gemini_api_key)
    model_name = settings.resolved_chat_model
    alternate_name = settings.resolved_chat_alternate_model
    return _GeminiWrapper(
        client,
        model_name,
        alternate_model=alternate_name,
        round_robin=getattr(settings, "chat_model_round_robin", False),
    )


def _build_local_wrapper():
    settings = get_settings()
    endpoint = (settings.local_llm_endpoint or "").strip()
    if not settings.local_llm_enabled or not endpoint:
        raise RuntimeError("Local LLM is not enabled/configured")
    return _LocalOpenAICompatWrapper(
        endpoint=endpoint,
        model=settings.local_llm_model,
        timeout_seconds=max(5, int(settings.local_llm_timeout_seconds)),
    )


def get_gemini_model():
    """Return routed model wrapper based on settings."""
    global _model
    if _model is not None:
        return _model

    settings = get_settings()
    mode = (settings.llm_router_mode or "api_only").strip().lower()

    if mode == "local_only":
        _model = _build_local_wrapper()
        return _model

    if mode == "hybrid":
        try:
            _model = _build_local_wrapper()
            return _model
        except Exception:
            _model = _build_gemini_wrapper()
            return _model

    # Default / safe mode for hosted environments.
    _model = _build_gemini_wrapper()
    return _model

