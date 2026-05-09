from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Cách 1: set trực tiếp (mật khẩu có @ [ ] phải URL-encode)
    database_url: str | None = None

    # Cách 2: Supabase – set các biến dưới, mật khẩu để bình thường (có ký tự đặc biệt cũng được)
    supabase_db_host: str | None = None  # db.xxxx.supabase.co (Direct) hoặc aws-0-xx.pooler.supabase.com (Pooler)
    supabase_db_port: int = 5432  # Direct: 5432, Pooler: 6543
    supabase_db_user: str = "postgres"  # Direct: postgres, Pooler: postgres.xxxx
    supabase_db_password: str | None = None
    supabase_db_name: str = "postgres"

    # Gemini / Google Gen AI — khi CHAT_LLM_PROVIDER=gemini hoặc STT_PROVIDER=gemini
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    # Tên model theo SDK mới `google-genai` (client tự thêm tiền tố `models/`)
    # Có thể override bằng biến môi trường GEMINI_MODEL nếu muốn.
    gemini_model: str = "gemini-2.5-flash"

    # Groq — chat (OpenAI-compatible) + Whisper STT; tránh chặn khu vực của Google API
    groq_api_key: str | None = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_model: str = "llama-3.3-70b-versatile"
    # whisper-large-v3: chính xác hơn (tiếng Việt + nền nhiễu); turbo nhanh hơn nhưng dễ lệch hơn.
    groq_stt_model: str = "whisper-large-v3"
    groq_timeout_seconds: int = 60
    # gemini | groq (mặc định groq — ổn trên Render/hosting nhiều khu vực)
    chat_llm_provider: str = "groq"
    # gemini | groq
    stt_provider: str = "groq"

    # STT Gemini: tach model rieng vi Gemma chat model khong toi uu cho audio.
    stt_model: str | None = "gemini-2.5-flash"
    stt_model_fallback_enabled: bool = True
    stt_timeout_seconds: int = 35
    stt_retry_attempts: int = 2
    # Gắn thêm vào prompt Whisper (Groq); để trống = chỉ dùng prompt mặc định trong code.
    stt_whisper_extra_prompt: str = ""
    # Chuẩn hóa Unicode (NFC) + gọn khoảng trắng sau STT.
    stt_normalize_output: bool = True
    # Lọc transcript: off | light | medium | strict (mặc định light — tránh chặn nhầm câu ngắn đúng)
    stt_noise_guard_level: str = "light"
    # True = nhét tên thuốc/BN vào prompt Whisper (dễ bias khi chỉ có nền nhiễu). Mặc định tắt.
    stt_whisper_include_hints: bool = False
    # none | ffmpeg_highpass — high-pass + WAV mono 16 kHz trước Whisper (cần ffmpeg).
    stt_audio_preprocess: str = "none"
    stt_ffmpeg_bin: str = "ffmpeg"
    voice_max_audio_bytes: int = 5 * 1024 * 1024
    chat_model_round_robin: bool = False
    # Routing LLM:
    # - api_only: dùng CHAT_LLM_PROVIDER (mặc định groq); gemini nếu chỉ định
    # - local_only: chỉ dùng local model
    # - hybrid: ưu tiên local, lỗi thì fallback Gemini
    llm_router_mode: str = "api_only"
    local_llm_enabled: bool = False
    # Endpoint local OpenAI-compatible, ví dụ:
    # http://127.0.0.1:11434/v1/chat/completions
    local_llm_endpoint: str | None = None
    local_llm_model: str = "qwen2.5:3b-instruct"
    local_llm_timeout_seconds: int = 20

    # TTS (edge-tts — giong tieng Viet, khong can API key)
    tts_voice: str = "vi-VN-HoaiMyNeural"
    tts_max_chars: int = 5000
    tts_timeout_seconds: int = 20

    # Vector RAG (thiet ke nhe cho Raspberry Pi)
    rag_enabled: bool = True
    # Câu quá ngắn: không đính kèm khối tham chiếu (tóm tắt BN + RAG); chỉ gửi đúng tin nhắn người dùng
    rag_gate_short_queries: bool = True
    # Hai điều kiện cùng lúc (AND): đủ ký tự và đủ từ — giữ thấp để vẫn RAG cho triệu chứng ngắn (vd. "đau đầu").
    rag_min_query_chars: int = 8
    rag_min_query_words: int = 2
    rag_embedding_dims: int = 128
    rag_top_k: int = 4
    rag_index_interval_seconds: int = 300
    rag_max_records_per_patient: int = 40

    def _resolve_model_alias(self, model_name: str | None, default: str) -> str:
        value = (model_name or "").strip().lower()
        if not value:
            return default
        aliases = {
            "flash": "gemini-2.5-flash",
            "2.5-flash": "gemini-2.5-flash",
            "flash_lite": "gemini-2.5-flash-lite",
            "flash-lite": "gemini-2.5-flash-lite",
            "2.5-flash-lite": "gemini-2.5-flash-lite",
        }
        return aliases.get(value, (model_name or default).strip())

    @property
    def resolved_chat_model(self) -> str:
        return self._resolve_model_alias(self.gemini_model, "gemini-2.5-flash")

    @property
    def resolved_stt_model(self) -> str:
        source = self.stt_model if self.stt_model else self.gemini_model
        return self._resolve_model_alias(source, "gemini-2.5-flash")

    @property
    def resolved_stt_alternate_model(self) -> str:
        primary = self.resolved_stt_model
        if primary == "gemini-2.5-flash":
            return "gemini-2.5-flash-lite"
        if primary == "gemini-2.5-flash-lite":
            return "gemini-2.5-flash"
        return "gemini-2.5-flash-lite"

    @property
    def resolved_chat_alternate_model(self) -> str:
        primary = self.resolved_chat_model
        if primary == "gemini-2.5-flash":
            return "gemini-2.5-flash-lite"
        if primary == "gemini-2.5-flash-lite":
            return "gemini-2.5-flash"
        return "gemini-2.5-flash-lite"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.supabase_db_host and self.supabase_db_password is not None:
            safe_password = quote_plus(self.supabase_db_password)
            return (
                f"postgresql://{self.supabase_db_user}:{safe_password}"
                f"@{self.supabase_db_host}:{self.supabase_db_port}/{self.supabase_db_name}"
            )
        return "sqlite:///./pasteur.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()

