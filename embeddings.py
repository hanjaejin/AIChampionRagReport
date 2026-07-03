# file: embeddings.py
"""임베딩 Provider 추상화.

Phase 1 설계의 `EmbeddingProvider` 경계를 구현한다. 폐쇄망 전환 시
OpenAI 대신 BGE-M3/KURE 등 로컬 임베딩 구현체로 교체할 수 있도록,
파이프라인 코드는 이 프로토콜에만 의존한다. API 키는 생성자 주입으로 받는다.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from retry_util import retry_call

logger = logging.getLogger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """텍스트 목록을 임베딩 벡터 목록으로 변환하는 인터페이스."""

    model: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 목록을 임베딩한다.

        Args:
            texts: 임베딩할 텍스트 목록.

        Returns:
            각 텍스트에 대응하는 벡터 목록(입력과 순서·길이 동일).
        """
        ...


class OpenAIEmbeddingProvider:
    """OpenAI 임베딩 구현체 (기본: text-embedding-3-small, 1536차원).

    Args:
        api_key: OpenAI API 키(생성자 주입 — UI 입력 키 정책 지원).
        model: 임베딩 모델명.
        dimension: 출력 차원(스키마 vector 차원과 일치해야 함).
        batch_size: 한 번의 API 호출에 넣을 최대 텍스트 수.
        client: 테스트용 주입 클라이언트(미지정 시 openai.OpenAI 생성).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        batch_size: int = 100,
        client: object | None = None,
    ) -> None:
        self.model = model
        self.dimension = dimension
        self._batch_size = batch_size
        self.total_tokens = 0
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
        self._client = client

    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트를 배치로 나눠 임베딩하고 토큰 사용량을 누적한다.

        Args:
            texts: 임베딩할 텍스트 목록.

        Returns:
            입력 순서를 보존한 임베딩 벡터 목록.
        """
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            response = self._client.embeddings.create(
                model=self.model, input=batch, dimensions=self.dimension
            )
            self.total_tokens += response.usage.total_tokens
            vectors.extend(item.embedding for item in response.data)
            logger.debug("임베딩 배치 %d건 완료", len(batch))
        return vectors


class GeminiEmbeddingProvider:
    """Google Gemini 임베딩 구현체 (gemini-embedding-001).

    검색 품질을 위해 문서/질의에 서로 다른 task_type을 사용한다
    (문서 적재=RETRIEVAL_DOCUMENT, 질의=RETRIEVAL_QUERY). 출력 차원을
    지정할 수 있어(MRL) 기존 스키마 vector(1536)와 호환된다.

    참고: Gemini 임베딩 응답은 토큰 사용량을 제공하지 않아 total_tokens는
    글자수 기반 추정치이며 비용은 근사값이다.

    Args:
        api_key: Gemini API 키(생성자 주입).
        model: 임베딩 모델명.
        dimension: 출력 차원(스키마와 일치, 기본 1536).
        task_type: RETRIEVAL_DOCUMENT | RETRIEVAL_QUERY | SEMANTIC_SIMILARITY 등.
        batch_size: 한 요청당 최대 텍스트 수.
        client: 테스트용 주입 클라이언트(미지정 시 genai.Client 생성).
        max_retries: 레이트리밋(429) 시 지수 백오프 재시도 횟수.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-001",
        dimension: int = 1536,
        task_type: str = "RETRIEVAL_DOCUMENT",
        batch_size: int = 32,
        client: Any | None = None,
        max_retries: int = 4,
    ) -> None:
        self.model = model
        self.dimension = dimension
        self.task_type = task_type
        self._batch_size = batch_size
        self._max_retries = max_retries
        self.total_tokens = 0
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client

    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트를 배치로 임베딩한다(레이트리밋 시 재시도).

        Args:
            texts: 임베딩할 텍스트 목록.

        Returns:
            입력 순서를 보존한 임베딩 벡터 목록.
        """
        from google.genai import types

        config = types.EmbedContentConfig(
            task_type=self.task_type, output_dimensionality=self.dimension
        )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            response = self._embed_batch(batch, config)
            vectors.extend(list(item.values) for item in response.embeddings)
            self.total_tokens += sum(max(1, len(t) // 4) for t in batch)  # 추정
            logger.debug("Gemini 임베딩 배치 %d건 완료", len(batch))
        return vectors

    def _embed_batch(self, batch: list[str], config: Any) -> Any:
        """배치 임베딩을 일시 오류(429/503 등) 재시도와 함께 호출한다."""
        return retry_call(
            lambda: self._client.models.embed_content(
                model=self.model, contents=batch, config=config
            ),
            max_retries=self._max_retries,
            what="Gemini 임베딩",
        )
