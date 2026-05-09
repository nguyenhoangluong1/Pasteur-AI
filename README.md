# Pasteur AI

Medical chat backend (FastAPI) + web UI: Groq (LLM + Whisper STT) mặc định, Gemini tùy chọn, optional Supabase/Postgres, RAG, TTS (edge-tts).

Public repo: [github.com/nguyenhoangluong1/Pasteur-AI](https://github.com/nguyenhoangluong1/Pasteur-AI).

## Quick start

```bash
python -m venv venv
# Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Sửa .env: thêm GROQ_API_KEY (và DB nếu dùng Postgres). Gemini nếu đặt CHAT_LLM_PROVIDER=gemini / STT_PROVIDER=gemini.

source venv/bin/activate
uvicorn core.api.main:app --reload --host 127.0.0.1 --port 8000
```

Giao diện chat: mở `http://127.0.0.1:8000/app/` (mic/STT cần HTTPS hoặc localhost).

## Environment

| Biến | Mô tả |
|------|--------|
| `GROQ_API_KEY` | **Bắt buộc** mặc định cho chat + STT (Whisper qua Groq) |
| `CHAT_LLM_PROVIDER`, `STT_PROVIDER` | Mặc định `groq`. Đặt `gemini` nếu chỉ dùng Google (`GEMINI_API_KEY`) |
| `GEMINI_API_KEY` hoặc `GOOGLE_API_KEY` | Chỉ cần khi provider có nhánh Gemini |
| `DATABASE_URL` *hoặc* `SUPABASE_*` | DB; không set thì dùng SQLite local |
| `GEMINI_MODEL`, `GROQ_MODEL`, `GROQ_STT_MODEL` | Tuỳ chọn (xem `.env.example`) |
| `LLM_ROUTER_MODE`, `LOCAL_LLM_*` | Tuỳ chọn offline mode (Qwen2.5-3B local); mặc định `api_only` |
| `TTS_*` | Giọng / giới hạn ký tự TTS (edge-tts) |
| `RAG_*` | Bật/tắt và tham số RAG |

Chi tiết mẫu: xem [`.env.example`](.env.example).

### Offline mode (optional extension)

- Mặc định `LLM_ROUTER_MODE=api_only` và chat qua Groq (tránh chặn khu vực Google API trên nhiều host).
- Có thể bật local model (ví dụ Qwen2.5-3B) khi chạy trên máy cá nhân:
  - `LOCAL_LLM_ENABLED=true`
  - `LLM_ROUTER_MODE=local_only` hoặc `hybrid`
  - `LOCAL_LLM_ENDPOINT=http://127.0.0.1:11434/v1/chat/completions`
  - `LOCAL_LLM_MODEL=qwen2.5:3b-instruct`

## Security

- **Không** commit `.env` hoặc bất kỳ file chứa API key / mật khẩu DB.
- Nếu key từng bị lộ (ví dụ đẩy nhầm lên Git), hãy **xoá key cũ** và tạo key mới trên [Google AI Studio](https://aistudio.google.com/apikey).
- Thư mục `docs/` (báo cáo / ghi chú nội bộ) được liệt kê trong `.gitignore` để không lên remote; muốn public docs thì chỉnh `.gitignore`.

## License

Apache-2.0 (theo file `LICENSE` trong repo).
