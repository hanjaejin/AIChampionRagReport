# file: ingest.py
"""문서 적재(ingest) 파이프라인 — 청킹 → 임베딩 → 저장.

CLI(load_to_supabase.py)와 Streamlit 업로드 탭(Phase 7)이 **동일하게** 호출하는
단일 진입점이다. 로직 중복을 막기 위해 여기에만 오케스트레이션을 둔다.
chunker/embedder/store 를 의존성 주입으로 받아 테스트 가능하게 한다.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Protocol

from chunker import Chunk, RegulationChunker

logger = logging.getLogger(__name__)

# 진행률 콜백: (0.0~1.0 비율, 사람이 읽는 메시지)
ProgressCallback = Callable[[float, str], None]


class _Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class _Store(Protocol):
    def document_by_filename(self, filename: str) -> dict | None: ...

    def replace_document(self, **fields: object) -> str: ...

    def add_chunks(self, doc_id: str, rows: list[dict]) -> int: ...


@dataclass
class IngestReport:
    """적재 결과 요약(업로드 탭 결과 표시·레포트용).

    Attributes:
        doc_id: 생성된 문서 ID.
        doc_title: 문서 제목.
        source_filename: 원본 파일명.
        chunk_count: 적재된 청크 수.
        type_counts: content_type별 청크 수.
        replaced: 기존 동일 파일명 문서를 교체했는지 여부.
        embedding_tokens: 임베딩에 사용된 토큰 수(비용 계산용).
        embedding_version: 사용한 임베딩 모델 식별자.
        elapsed_sec: 총 소요 시간(초).
    """

    doc_id: str
    doc_title: str
    source_filename: str
    chunk_count: int
    type_counts: dict[str, int]
    replaced: bool
    embedding_tokens: int
    embedding_version: str
    elapsed_sec: float


# Chunk dataclass → rag_chunks 컬럼 매핑에 쓰는 필드 목록
_CHUNK_COLUMNS = (
    "content",
    "embed_text",
    "content_type",
    "chunk_index",
    "token_count",
    "chapter_seq",
    "chapter_no",
    "chapter_title",
    "section_no",
    "section_title",
    "article_no",
    "article_title",
    "clause_range",
    "annex_no",
    "related_articles",
    "table_caption",
)


def _chunk_to_row(
    chunk: Chunk, embedding: list[float], embedding_version: str
) -> dict:
    """Chunk와 임베딩을 rag_chunks 삽입용 dict로 변환한다."""
    row = {col: getattr(chunk, col) for col in _CHUNK_COLUMNS}
    row["related_articles"] = list(chunk.related_articles)
    row["embedding"] = embedding
    row["embedding_version"] = embedding_version
    return row


def ingest_markdown(
    text: str,
    source_filename: str,
    *,
    embedder: _Embedder,
    store: _Store,
    chunker: RegulationChunker | None = None,
    embedding_version: str | None = None,
    progress: ProgressCallback | None = None,
) -> IngestReport:
    """마크다운 규정 문서를 청킹·임베딩하여 저장소에 적재한다.

    Args:
        text: 규정 문서 전문(마크다운).
        source_filename: 원본 파일명(재업로드 판별 키).
        embedder: 임베딩 Provider(생성자 주입).
        store: VectorStore(생성자 주입).
        chunker: 청커(미지정 시 기본 RegulationChunker).
        embedding_version: 임베딩 버전 태그(미지정 시 embedder.model).
        progress: 진행률 콜백(Streamlit progress bar 연동용).

    Returns:
        적재 결과 요약 IngestReport.

    Raises:
        ChunkingError: 규정 문서로 인식할 수 없는 입력일 때(chunker에서 전파).
    """
    start = time.perf_counter()
    chunker = chunker or RegulationChunker()
    embedding_version = embedding_version or getattr(embedder, "model", "unknown")

    def _report(frac: float, msg: str) -> None:
        if progress:
            progress(frac, msg)

    _report(0.0, "문서 청킹 중…")
    result = chunker.chunk(text)  # 비규정 파일이면 ChunkingError
    chunks = result.chunks
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    replaced = store.document_by_filename(source_filename) is not None

    _report(0.3, f"{len(chunks)}개 청크 임베딩 중…")
    embeddings = embedder.embed([c.embed_text for c in chunks])

    _report(0.7, "Supabase 적재 중…")
    doc_id = store.replace_document(
        doc_title=result.metadata.doc_title,
        doc_version=result.metadata.doc_version,
        revision_date=result.metadata.revision_date,
        source_filename=source_filename,
        content_hash=content_hash,
    )
    rows = [
        _chunk_to_row(chunk, emb, embedding_version)
        for chunk, emb in zip(chunks, embeddings)
    ]
    store.add_chunks(doc_id, rows)

    _report(1.0, "완료")
    elapsed = time.perf_counter() - start
    logger.info(
        "적재 완료: %s → 청크 %d건, %.1f초", source_filename, len(chunks), elapsed
    )
    return IngestReport(
        doc_id=doc_id,
        doc_title=result.metadata.doc_title,
        source_filename=source_filename,
        chunk_count=len(chunks),
        type_counts=dict(Counter(c.content_type for c in chunks)),
        replaced=replaced,
        embedding_tokens=getattr(embedder, "total_tokens", 0),
        embedding_version=embedding_version,
        elapsed_sec=elapsed,
    )
