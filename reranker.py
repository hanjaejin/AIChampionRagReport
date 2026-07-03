# file: reranker.py
"""Reranker 추상화 — Cohere Rerank 구현체.

Phase 1 설계의 `Reranker` 경계를 구현한다. 벡터 검색으로 넓게 회수한 후보를
질문과의 관련도로 재정렬해 상위 N개만 남긴다. 폐쇄망 전환 시
BGE-reranker-v2-m3 로컬 구현체로 교체할 수 있도록 이 인터페이스에만 의존한다.
API 키는 생성자 주입으로 받는다.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


def _is_rate_limit(exc: Exception) -> bool:
    """예외가 레이트리밋/일시적 자원 소진인지 판별한다."""
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "too many" in text


@dataclass
class RerankResult:
    """재정렬 결과 1건.

    Attributes:
        index: 입력 documents 리스트에서의 원 인덱스.
        score: 관련도 점수(0~1, 높을수록 관련).
    """

    index: int
    score: float


@runtime_checkable
class Reranker(Protocol):
    """질문-문서 관련도 재정렬 인터페이스."""

    def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[RerankResult]:
        """문서를 질문 관련도로 재정렬한다.

        Args:
            query: 질문.
            documents: 후보 문서 텍스트 목록.
            top_n: 반환할 상위 개수.

        Returns:
            점수 내림차순 RerankResult 목록(최대 top_n개).
        """
        ...


class CohereReranker:
    """Cohere Rerank 구현체 (다국어 모델 — 한국어 지원).

    Args:
        api_key: Cohere API 키(생성자 주입).
        model: rerank 모델명.
        client: 테스트용 주입 클라이언트(미지정 시 cohere.ClientV2 생성).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "rerank-multilingual-v3.0",
        client: Any | None = None,
        max_retries: int = 4,
    ) -> None:
        self.model = model
        self._max_retries = max_retries
        if client is None:
            import cohere

            client = cohere.ClientV2(api_key=api_key)
        self._client = client

    def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[RerankResult]:
        """Cohere Rerank API로 재정렬한다(레이트리밋 시 지수 백오프 재시도).

        Args:
            query: 질문.
            documents: 후보 문서 텍스트 목록.
            top_n: 반환할 상위 개수(문서 수보다 크면 문서 수로 제한).

        Returns:
            점수 내림차순 RerankResult 목록.
        """
        if not documents:
            return []
        response = self._rerank_with_retry(query, documents, min(top_n, len(documents)))
        results = [
            RerankResult(index=item.index, score=item.relevance_score)
            for item in response.results
        ]
        logger.info("Cohere rerank: %d→%d", len(documents), len(results))
        return results

    def _rerank_with_retry(self, query: str, documents: list[str], top_n: int) -> Any:
        """rerank 호출을 레이트리밋 재시도와 함께 수행한다."""
        delay = 2.0
        for attempt in range(self._max_retries):
            try:
                return self._client.rerank(
                    model=self.model, query=query, documents=documents, top_n=top_n
                )
            except Exception as exc:  # noqa: BLE001 - 재시도 판단 후 재발생
                if attempt == self._max_retries - 1 or not _is_rate_limit(exc):
                    raise
                logger.warning("rerank 레이트리밋, %.0f초 후 재시도", delay)
                time.sleep(delay)
                delay *= 2
        raise RuntimeError("rerank 재시도 소진")  # 도달 불가(방어)
