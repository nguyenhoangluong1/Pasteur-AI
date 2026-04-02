from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import hashlib
import json
import math
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import get_settings

_WORD_RE = re.compile(r"[a-zA-Z0-9_]+", flags=re.UNICODE)
_SCHEMA_READY = False
_SCHEMA_CHECKED = False
_LAST_INDEXED_AT: dict[str, datetime] = {}


def _is_postgres(db: Session) -> bool:
    bind = db.get_bind()
    return bool(bind and bind.dialect and bind.dialect.name == "postgresql")


def _tokenize(text_value: str) -> list[str]:
    lowered = text_value.lower()
    return _WORD_RE.findall(lowered)


def _embed_text(text_value: str, dims: int) -> list[float]:
    vec = [0.0] * dims
    tokens = _tokenize(text_value)
    if not tokens:
        return vec

    for tok in tokens:
        digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], byteorder="little", signed=False) % dims
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[bucket] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-12:
        return vec
    return [v / norm for v in vec]


def _vec_to_pgvector_literal(vec: Iterable[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def _safe_json_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _build_chunks(patient_row: dict, cfg_row: dict | None, record_rows: list[dict]) -> list[tuple[str, str, str]]:
    chunks: list[tuple[str, str, str]] = []
    patient_id = str(patient_row["id"])

    base_chunk = (
        f"Ho ten: {patient_row.get('full_name') or 'chua co'}\n"
        f"Tom tat: {patient_row.get('medical_summary') or 'khong co'}"
    )
    chunks.append((f"{patient_id}:patient:base", "patient_base", base_chunk))

    if cfg_row:
        cfg_chunk = (
            f"Tom tat bo sung: {cfg_row.get('medical_summary') or 'khong co'}\n"
            f"Benh nen: {_safe_json_text(cfg_row.get('chronic_conditions')) or 'khong co'}\n"
            f"Thuoc dang dung: {_safe_json_text(cfg_row.get('current_medications')) or 'khong co'}\n"
            f"Han che: {cfg_row.get('restrictions') or 'khong co'}"
        )
        chunks.append((f"{patient_id}:config:active", "medical_config", cfg_chunk))

    for row in record_rows:
        recorded_at = row.get("recorded_at")
        date_text = recorded_at.strftime("%Y-%m-%d") if isinstance(recorded_at, datetime) else "khong ro ngay"
        source_id = str(row.get("id"))
        record_chunk = (
            f"Loai ban ghi: {row.get('record_type') or 'record'}\n"
            f"Ngay: {date_text}\n"
            f"Noi dung: {_safe_json_text(row.get('content')) or 'khong co'}"
        )
        chunks.append((f"{patient_id}:record:{source_id}", "medical_record", record_chunk))

    return chunks


def _ensure_schema(db: Session) -> bool:
    global _SCHEMA_READY, _SCHEMA_CHECKED
    if _SCHEMA_CHECKED:
        return _SCHEMA_READY

    _SCHEMA_CHECKED = True
    if not _is_postgres(db):
        _SCHEMA_READY = False
        return False

    settings = get_settings()
    dims = max(32, int(settings.rag_embedding_dims))

    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS public.rag_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    patient_id UUID NOT NULL,
                    source_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector({dims}) NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_rag_chunks_patient ON public.rag_chunks(patient_id)"))
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding "
                "ON public.rag_chunks USING ivfflat (embedding vector_cosine_ops) "
                "WITH (lists = 32)"
            )
        )
        db.commit()
        _SCHEMA_READY = True
        return True
    except Exception:
        db.rollback()
        _SCHEMA_READY = False
        return False


def _upsert_patient_chunks(db: Session, patient_id: str) -> None:
    settings = get_settings()
    dims = max(32, int(settings.rag_embedding_dims))
    limit_records = max(5, int(settings.rag_max_records_per_patient))

    patient = db.execute(
        text(
            """
            SELECT id, full_name, medical_summary
            FROM public.patients
            WHERE id = :patient_id
            LIMIT 1
            """
        ),
        {"patient_id": patient_id},
    ).mappings().first()
    if not patient:
        return

    cfg = db.execute(
        text(
            """
            SELECT medical_summary, chronic_conditions, current_medications, restrictions
            FROM public.patient_medical_config
            WHERE patient_id = :patient_id AND is_active = true
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ),
        {"patient_id": patient_id},
    ).mappings().first()

    rows = db.execute(
        text(
            """
            SELECT id, record_type, content, recorded_at
            FROM public.medical_records
            WHERE patient_id = :patient_id
            ORDER BY recorded_at DESC NULLS LAST, created_at DESC
            LIMIT :limit_records
            """
        ),
        {"patient_id": patient_id, "limit_records": limit_records},
    ).mappings().all()

    chunks = _build_chunks(patient, cfg, list(rows))
    for chunk_id, source_type, content in chunks:
        vec = _embed_text(content, dims)
        vec_literal = _vec_to_pgvector_literal(vec)
        db.execute(
            text(
                """
                INSERT INTO public.rag_chunks (chunk_id, patient_id, source_type, content, embedding, updated_at)
                VALUES (:chunk_id, CAST(:patient_id AS uuid), :source_type, :content, CAST(:embedding AS vector), now())
                ON CONFLICT (chunk_id) DO UPDATE
                SET source_type = EXCLUDED.source_type,
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "chunk_id": chunk_id,
                "patient_id": patient_id,
                "source_type": source_type,
                "content": content,
                "embedding": vec_literal,
            },
        )

    db.execute(
        text(
            """
            DELETE FROM public.rag_chunks
            WHERE patient_id = CAST(:patient_id AS uuid)
              AND updated_at < now() - interval '1 day'
            """
        ),
        {"patient_id": patient_id},
    )
    db.commit()


def _maybe_refresh_index(db: Session, patient_id: str) -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    ttl = max(30, int(settings.rag_index_interval_seconds))
    last = _LAST_INDEXED_AT.get(patient_id)
    if last and (now - last).total_seconds() < ttl:
        return

    _upsert_patient_chunks(db, patient_id)
    _LAST_INDEXED_AT[patient_id] = now


def get_relevant_context(db: Session, *, patient_id: str, query: str) -> str:
    settings = get_settings()
    if not settings.rag_enabled or not query.strip():
        return ""
    if not _ensure_schema(db):
        return ""

    try:
        _maybe_refresh_index(db, patient_id)
    except Exception:
        db.rollback()
        return ""

    dims = max(32, int(settings.rag_embedding_dims))
    top_k = max(1, min(8, int(settings.rag_top_k)))
    q_vec = _vec_to_pgvector_literal(_embed_text(query, dims))

    try:
        rows = db.execute(
            text(
                """
                SELECT content
                FROM public.rag_chunks
                WHERE patient_id = CAST(:patient_id AS uuid)
                ORDER BY embedding <=> CAST(:query_embedding AS vector)
                LIMIT :top_k
                """
            ),
            {
                "patient_id": patient_id,
                "query_embedding": q_vec,
                "top_k": top_k,
            },
        ).mappings().all()
    except Exception:
        db.rollback()
        return ""

    if not rows:
        return ""

    lines = ["[RAG CONTEXT - RELEVANT CHUNKS]"]
    for idx, row in enumerate(rows, start=1):
        lines.append(f"{idx}) {row.get('content') or ''}")
    return "\n".join(lines)
