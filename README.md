# Pasteur AI

Medical chat backend (FastAPI) + web UI: Gemini, optional Supabase/Postgres, RAG, STT/TTS.

Public repo: [github.com/nguyenhoangluong1/Pasteur-AI](https://github.com/nguyenhoangluong1/Pasteur-AI).

## Quick start

```bash
python -m venv venv
# Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Sửa .env: thêm GEMINI_API_KEY (và DB nếu dùng Postgres)

source venv/bin/activate
uvicorn core.api.main:app --reload --host 127.0.0.1 --port 8000
```

Giao diện chat: mở `http://127.0.0.1:8000/app/` (mic/STT cần HTTPS hoặc localhost).

## Environment

| Biến | Mô tả |
|------|--------|
| `GEMINI_API_KEY` hoặc `GOOGLE_API_KEY` | Bắt buộc cho chat + STT |
| `DATABASE_URL` *hoặc* `SUPABASE_*` | DB; không set thì dùng SQLite local |
| `GEMINI_MODEL` | Tuỳ chọn, mặc định `gemini-2.5-flash` |
| `LLM_ROUTER_MODE`, `LOCAL_LLM_*` | Tuỳ chọn offline mode (Qwen2.5-3B local); mặc định vẫn API |
| `TTS_*` | Giọng / giới hạn ký tự TTS (edge-tts) |
| `RAG_*` | Bật/tắt và tham số RAG |

Chi tiết mẫu: xem [`.env.example`](.env.example).

### Offline mode (optional extension)

- Mặc định hệ thống chạy `LLM_ROUTER_MODE=api_only` (Gemini), phù hợp môi trường như Render free tier.
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
