# file: vector_store.py
"""VectorStore 추상화 — Supabase(pgvector) 구현체.

Phase 1 설계의 `VectorStore` 경계를 구현한다. 폐쇄망 전환 시
자체 PostgreSQL+pgvector 로 교체할 수 있도록 파이프라인은 이 인터페이스에만 의존한다.
테이블은 rag_ 네임스페이스(rag_documents, rag_chunks)를 사용한다.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# ingest.py가 만드는 청크 행 dict의 임베딩 키
_EMBEDDING_KEY = "embedding"


class VectorStore(Protocol):
    """문서/청크 적재 및 벡터 검색 인터페이스."""

    def document_by_filename(self, filename: str) -> dict | None: ...

    def replace_document(
        self,
        *,
        doc_title: str,
        doc_version: str | None,
        revision_date: date | None,
        source_filename: str,
        content_hash: str,
    ) -> str: ...

    def add_chunks(self, doc_id: str, rows: list[dict]) -> int: ...

    def match(
        self,
        query_embedding: list[float],
        match_count: int = 5,
        doc_id: str | None = None,
        content_type: str | None = None,
    ) -> list[dict]: ...


def _to_pgvector(vector: list[float]) -> str:
    """파이썬 실수 리스트를 pgvector 리터럴 문자열로 변환한다.

    Args:
        vector: 임베딩 벡터.

    Returns:
        "[0.1,0.2,...]" 형식 문자열(PostgREST가 vector 컬럼으로 캐스팅).
    """
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


class SupabaseVectorStore:
    """Supabase 기반 VectorStore 구현.

    Args:
        url: Supabase 프로젝트 URL.
        service_key: service_role 키.
        client: 테스트용 주입 클라이언트(미지정 시 supabase.create_client 생성).
        chunk_batch_size: 청크 삽입 배치 크기.
    """

    DOC_TABLE = "rag_documents"
    CHUNK_TABLE = "rag_chunks"

    def __init__(
        self,
        url: str,
        service_key: str,
        client: Any | None = None,
        chunk_batch_size: int = 200,
    ) -> None:
        if client is None:
            from supabase import create_client

            client = create_client(url, service_key)
        self._client = client
        self._batch = chunk_batch_size

    def document_by_filename(self, filename: str) -> dict | None:
        """파일명으로 기존 문서 행을 조회한다(재업로드 판별용)."""
        res = (
            self._client.table(self.DOC_TABLE)
            .select("*")
            .eq("source_filename", filename)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def replace_document(
        self,
        *,
        doc_title: str,
        doc_version: str | None,
        revision_date: date | None,
        source_filename: str,
        content_hash: str,
    ) -> str:
        """같은 파일명 문서를 삭제(청크 cascade)한 뒤 새로 삽입한다.

        Returns:
            새로 생성된 문서의 doc_id.
        """
        self._client.table(self.DOC_TABLE).delete().eq(
            "source_filename", source_filename
        ).execute()
        res = (
            self._client.table(self.DOC_TABLE)
            .insert(
                {
                    "doc_title": doc_title,
                    "doc_version": doc_version,
                    "revision_date": revision_date.isoformat() if revision_date else None,
                    "source_filename": source_filename,
                    "content_hash": content_hash,
                }
            )
            .execute()
        )
        doc_id = res.data[0]["doc_id"]
        logger.info("문서 적재: %s (doc_id=%s)", source_filename, doc_id)
        return doc_id

    def add_chunks(self, doc_id: str, rows: list[dict]) -> int:
        """청크 행들을 배치로 삽입하고 문서의 chunk_count를 갱신한다.

        Args:
            doc_id: 소속 문서 ID.
            rows: 컬럼명 dict 목록(embedding은 list[float]).

        Returns:
            삽입한 청크 수.
        """
        payload = []
        for row in rows:
            item = dict(row)
            item["doc_id"] = doc_id
            if item.get(_EMBEDDING_KEY) is not None:
                item[_EMBEDDING_KEY] = _to_pgvector(item[_EMBEDDING_KEY])
            if "related_articles" in item:
                item["related_articles"] = list(item["related_articles"])
            payload.append(item)

        for start in range(0, len(payload), self._batch):
            self._client.table(self.CHUNK_TABLE).insert(
                payload[start : start + self._batch]
            ).execute()

        self._client.table(self.DOC_TABLE).update({"chunk_count": len(payload)}).eq(
            "doc_id", doc_id
        ).execute()
        logger.info("청크 %d건 적재 완료 (doc_id=%s)", len(payload), doc_id)
        return len(payload)

    def match(
        self,
        query_embedding: list[float],
        match_count: int = 5,
        doc_id: str | None = None,
        content_type: str | None = None,
    ) -> list[dict]:
        """match_rag_chunks RPC로 벡터 유사도 상위 청크를 조회한다.

        Args:
            query_embedding: 질의 임베딩 벡터.
            match_count: 반환할 청크 수.
            doc_id: 특정 문서로 제한(None이면 전체).
            content_type: 유형 필터(예: 'table').

        Returns:
            유사도 내림차순 청크 dict 목록(similarity 포함).
        """
        res = self._client.rpc(
            "match_rag_chunks",
            {
                "query_embedding": _to_pgvector(query_embedding),
                "match_count": match_count,
                "filter_doc_id": doc_id,
                "filter_content_type": content_type,
            },
        ).execute()
        return res.data or []

    def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        match_count: int = 5,
        doc_id: str | None = None,
    ) -> list[dict]:
        """hybrid_search_rag_chunks RPC로 BM25+벡터 RRF 융합 검색을 수행한다.

        Args:
            query_text: 키워드 검색용 원문 질의.
            query_embedding: 벡터 검색용 임베딩.
            match_count: 반환할 청크 수.
            doc_id: 특정 문서로 제한.

        Returns:
            rrf_score 내림차순 청크 dict 목록.
        """
        res = self._client.rpc(
            "hybrid_search_rag_chunks",
            {
                "query_text": query_text,
                "query_embedding": _to_pgvector(query_embedding),
                "match_count": match_count,
                "filter_doc_id": doc_id,
            },
        ).execute()
        return res.data or []

    def get_by_article(self, article_no: str, doc_id: str | None = None) -> list[dict]:
        """조번호로 청크를 직접 조회한다(Modular 라우팅 '직접 조회' 경로).

        Args:
            article_no: 조 번호(예: '제36조').
            doc_id: 특정 문서로 제한.

        Returns:
            해당 조문 청크 목록(chunk_index 순). 없으면 빈 리스트.
        """
        query = (
            self._client.table(self.CHUNK_TABLE)
            .select(
                "id, doc_id, chunk_index, content_type, content, article_no, "
                "article_title, chapter_no, chapter_title, section_no, annex_no, "
                "related_articles"
            )
            .eq("article_no", article_no)
        )
        if doc_id:
            query = query.eq("doc_id", doc_id)
        res = query.order("chunk_index").execute()
        return res.data or []

    def get_adjacent(
        self, doc_id: str, from_index: int, to_index: int
    ) -> list[dict]:
        """chunk_index 범위로 인접 청크를 조회한다(인접 청크 확장용).

        Args:
            doc_id: 문서 ID.
            from_index: 시작 chunk_index(포함).
            to_index: 끝 chunk_index(포함).

        Returns:
            chunk_index 오름차순 청크 목록.
        """
        res = self._client.rpc(
            "get_adjacent_rag_chunks",
            {"p_doc_id": doc_id, "p_from_index": from_index, "p_to_index": to_index},
        ).execute()
        return res.data or []
