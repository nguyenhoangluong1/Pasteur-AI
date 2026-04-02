"""
Chạy API: từ thư mục gốc pasteur-ai:
  python run.py
  hoặc: uvicorn core.api.main:app --reload
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("core.api.main:app", host="0.0.0.0", port=8000, reload=True)
