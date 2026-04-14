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

    # Gemini / Google Gen AI — chỉ cần một trong hai biến (ưu tiên GEMINI_API_KEY nếu cả hai đều có)
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    # Tên model theo SDK mới `google-genai` (client tự thêm tiền tố `models/`)
    # Có thể override bằng biến môi trường GEMINI_MODEL nếu muốn.
    gemini_model: str = "gemini-2.5-flash-lite"

    # TTS (edge-tts — giong tieng Viet, khong can API key)
    tts_voice: str = "vi-VN-HoaiMyNeural"
    tts_max_chars: int = 5000

    # Vector RAG (thiet ke nhe cho Raspberry Pi)
    rag_enabled: bool = True
    rag_embedding_dims: int = 128
    rag_top_k: int = 4
    rag_index_interval_seconds: int = 300
    rag_max_records_per_patient: int = 40

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

