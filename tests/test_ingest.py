# file: tests/test_ingest.py
"""ingest 파이프라인 테스트 — 가짜(fake) 임베더/스토어로 오케스트레이션만 검증.

외부 네트워크 없이 청킹→임베딩→적재의 흐름·계약을 검증한다.
실제 OpenAI/Supabase 연동은 load_to_supabase.py 통합 실행으로 검증한다.
"""

from __future__ import annotations

import pytest

from chunker import ChunkingError
from ingest import ingest_markdown

SAMPLE = """규정 샘플

전부개정 2024.06.27. 제2024-23호

제1장 총칙

제1조(목적) 이 규정은 목적을 정한다.

제2조(정의) 용어의 뜻을 정한다.

## [별표 1](제1조 관련)

샘플 표

| 항목 | 값 |
| --- | --- |
| 가 | 1 |
"""


class FakeEmbedder:
    """embed_text 개수만큼 결정적 벡터를 돌려주고 토큰 사용량을 누적한다."""

    model = "fake-embed-v1"
    dimension = 4

    def __init__(self) -> None:
        self.total_tokens = 0
        self.seen_texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.seen_texts.extend(texts)
        self.total_tokens += sum(len(t) for t in texts)
        return [[float(len(t)), 0.0, 0.0, 0.0] for t in texts]


class FakeStore:
    """메모리에 문서/청크를 저장하는 가짜 VectorStore."""

    def __init__(self, existing_filenames: set[str] | None = None) -> None:
        self.docs: dict[str, dict] = {}
        self.chunks: dict[str, list[dict]] = {}
        self._existing = existing_filenames or set()

    def document_by_filename(self, filename: str) -> dict | None:
        if filename in self._existing:
            return {"doc_id": "existing-id", "source_filename": filename}
        return None

    def replace_document(self, **fields) -> str:
        doc_id = "doc-1"
        self.docs[doc_id] = fields
        self.chunks[doc_id] = []
        return doc_id

    def add_chunks(self, doc_id: str, rows: list[dict]) -> int:
        self.chunks[doc_id] = rows
        return len(rows)


def test_ingest_happy_path() -> None:
    embedder, store = FakeEmbedder(), FakeStore()
    report = ingest_markdown(SAMPLE, "sample.md", embedder=embedder, store=store)

    # 청크 수 = 적재된 행 수 = 임베딩된 텍스트 수
    assert report.chunk_count == len(store.chunks["doc-1"])
    assert report.chunk_count == len(embedder.seen_texts)
    assert report.chunk_count >= 3  # 조문 2 + 별표 1 + preamble

    # 유형 집계
    assert report.type_counts["article"] == 2
    assert report.type_counts["table"] == 1

    # 신규 문서이므로 replaced=False, 토큰 사용량 누적됨
    assert report.replaced is False
    assert report.embedding_tokens > 0
    assert report.embedding_version == "fake-embed-v1"


def test_ingest_embeds_embed_text_not_content() -> None:
    """임베딩 입력은 content가 아니라 embed_text여야 한다(R7/R9 검증)."""
    embedder, store = FakeEmbedder(), FakeStore()
    ingest_markdown(SAMPLE, "sample.md", embedder=embedder, store=store)

    # 표 청크의 embed_text(캡션)에는 파이프 기호가 없어야 한다
    table_texts = [t for t in embedder.seen_texts if "별표 1" in t]
    assert table_texts, "표 청크의 embed_text가 임베딩 입력에 포함되어야 한다"
    assert all("|" not in t for t in table_texts)


def test_ingest_marks_replaced_when_filename_exists() -> None:
    embedder = FakeEmbedder()
    store = FakeStore(existing_filenames={"sample.md"})
    report = ingest_markdown(SAMPLE, "sample.md", embedder=embedder, store=store)
    assert report.replaced is True


def test_ingest_reports_progress() -> None:
    calls: list[tuple[float, str]] = []
    ingest_markdown(
        SAMPLE, "sample.md",
        embedder=FakeEmbedder(), store=FakeStore(),
        progress=lambda frac, msg: calls.append((frac, msg)),
    )
    assert calls, "progress 콜백이 호출되어야 한다"
    assert calls[-1][0] == 1.0  # 마지막은 100%


def test_ingest_rejects_non_regulation_file() -> None:
    with pytest.raises(ChunkingError):
        ingest_markdown(
            "그냥 메모입니다.\n", "memo.md",
            embedder=FakeEmbedder(), store=FakeStore(),
        )
