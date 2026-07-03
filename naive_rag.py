# file: naive_rag.py
"""Naive RAG — 가장 기본형 파이프라인 (retrieve → generate).

질문을 임베딩해 벡터 검색으로 top-k 청크를 뽑고, 공유 프롬프트로 답변을 생성한다.
쿼리 재작성·재정렬·라우팅 등 최적화는 없다(Advanced/Modular와 비교 기준선).

embedder/store/chat 을 의존성 주입으로 받아 구체 구현(OpenAI/Supabase/OpenRouter·Gemini)을
몰라도 되게 한다. 세 파이프라인은 동일한 prompts.py 템플릿을 공유한다(공정 비교).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import prompts

logger = logging.getLogger(__name__)


class _Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class _Store(Protocol):
    def match(
        self,
        query_embedding: list[float],
        match_count: int = 5,
        doc_id: str | None = None,
        content_type: str | None = None,
    ) -> list[dict]: ...


class _Chat(Protocol):
    model: str

    def complete(
        self, user: str, system: str | None = ..., temperature: float = ...,
        max_tokens: int = ...,
    ) -> Any: ...


@dataclass
class RagAnswer:
    """RAG 응답 결과(3개 파이프라인 공통 반환 타입).

    Attributes:
        question: 원 질문.
        answer: 생성된 답변.
        contexts: 답변 근거로 사용한 검색 청크 목록.
        input_tokens: 파이프라인 전체 LLM 입력 토큰 합계(재작성+생성 등 모든 호출).
        output_tokens: 파이프라인 전체 LLM 출력 토큰 합계.
        model: 사용한 챗 모델.
        elapsed_sec: 총 소요 시간(초).
        pipeline: 파이프라인 이름.
        trace: 파이프라인 내부 단계 기록(단계별 토큰 분해 포함, 디버깅·대시보드용).
    """

    question: str
    answer: str
    contexts: list[dict]
    input_tokens: int
    output_tokens: int
    model: str
    elapsed_sec: float
    pipeline: str = "naive"
    trace: dict[str, Any] = field(default_factory=dict)


class NaiveRAG:
    """기본형 RAG 파이프라인.

    Args:
        embedder: 질문 임베딩 Provider.
        store: 벡터 검색 스토어.
        chat: 답변 생성 챗 Provider.
        top_k: 검색할 청크 수(공정 비교 기본 5).
        doc_id: 특정 문서로 검색 제한(None이면 전체).
    """

    def __init__(
        self,
        *,
        embedder: _Embedder,
        store: _Store,
        chat: _Chat,
        top_k: int = 5,
        doc_id: str | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._chat = chat
        self._top_k = top_k
        self._doc_id = doc_id

    def answer(self, question: str) -> RagAnswer:
        """질문에 대해 retrieve→generate로 답변한다.

        Args:
            question: 사용자 질문.

        Returns:
            답변·근거 문맥·토큰·시간을 담은 RagAnswer.
        """
        start = time.perf_counter()

        query_vec = self._embedder.embed([question])[0]
        contexts = self._store.match(
            query_vec, match_count=self._top_k, doc_id=self._doc_id
        )
        logger.info("Naive RAG 검색: %d개 청크", len(contexts))

        user_prompt = prompts.build_answer_prompt(question, contexts)
        result = self._chat.complete(
            user=user_prompt, system=prompts.ANSWER_SYSTEM_PROMPT, temperature=0.0
        )

        return RagAnswer(
            question=question,
            answer=result.text,
            contexts=contexts,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model=result.model,
            elapsed_sec=time.perf_counter() - start,
            trace={"retrieved": len(contexts), "top_k": self._top_k},
        )
