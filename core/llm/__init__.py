"""
Gemini client helper using the official `google-genai` SDK.
"""

from google import genai

from core.config import get_settings

_model = None


def get_gemini_model():
    """
    Lazily configure and return a Gemini client object
    có method `generate_content(contents=..., system_instruction=...)`.
    """
    global _model
    if _model is not None:
        return _model

    settings = get_settings()
    if not getattr(settings, "gemini_api_key", None):
        raise RuntimeError("GEMINI_API_KEY is not configured in settings/.env")

    api_key = settings.gemini_api_key
    model_name = getattr(settings, "gemini_model", "gemini-1.5-flash-002")

    client = genai.Client(api_key=api_key)

    class _GeminiWrapper:
        def __init__(self, client: genai.Client, model: str):
            self._client = client
            self._model = model

        def generate_content(self, contents, system_instruction=None):
            kwargs = {}
            if system_instruction is not None:
                kwargs["config"] = {"system_instruction": system_instruction}
            return self._client.models.generate_content(
                model=self._model,
                contents=contents,
                **kwargs,
            )

    _model = _GeminiWrapper(client, model_name)
    return _model

