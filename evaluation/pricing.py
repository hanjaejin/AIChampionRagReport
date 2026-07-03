# file: evaluation/pricing.py
"""토큰/호출 → 비용(USD) 계산.

주의: 단가는 2026년 기준 공개 가격의 근사치이며 수시로 변동한다.
정확한 비용은 각 서비스 콘솔을 확인해야 하고, 여기 값은 비교·추정용이다.
단가는 PRICING dict에서 조정할 수 있다(레포트에 근거 명시).
"""

from __future__ import annotations

from dataclasses import dataclass

# USD per 1,000,000 tokens (입력/출력), rerank는 per 1,000 searches
PRICING: dict[str, dict[str, float]] = {
    # 임베딩
    "text-embedding-3-small": {"input_per_1m": 0.02, "output_per_1m": 0.0},
    "gemini-embedding-001": {"input_per_1m": 0.15, "output_per_1m": 0.0},
    # 챗 (OpenRouter 경유 단가 근사)
    "openai/gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60},
    "google/gemini-2.5-flash": {"input_per_1m": 0.30, "output_per_1m": 2.50},
    # 챗 (Gemini 네이티브)
    "gemini-2.5-flash": {"input_per_1m": 0.30, "output_per_1m": 2.50},
    # rerank (검색 1,000회당)
    "rerank-multilingual-v3.0": {"per_1k_searches": 2.00},
}


@dataclass
class CostBreakdown:
    """단일 질의 비용 분해(USD).

    Attributes:
        embedding: 임베딩 비용.
        chat: 챗 생성 비용(재작성+생성 등 합).
        rerank: 재정렬 비용.
        total: 합계.
    """

    embedding: float
    chat: float
    rerank: float

    @property
    def total(self) -> float:
        return self.embedding + self.chat + self.rerank


def chat_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """챗 모델 토큰 비용을 계산한다.

    Args:
        model: 모델 식별자(PRICING 키).
        input_tokens: 입력 토큰 수.
        output_tokens: 출력 토큰 수.

    Returns:
        USD 비용. 단가 미등록 모델이면 0.0.
    """
    rate = PRICING.get(model)
    if not rate:
        return 0.0
    return (
        input_tokens * rate.get("input_per_1m", 0.0)
        + output_tokens * rate.get("output_per_1m", 0.0)
    ) / 1_000_000


def embedding_cost(model: str, tokens: int) -> float:
    """임베딩 토큰 비용을 계산한다.

    Args:
        model: 임베딩 모델 식별자.
        tokens: 임베딩 토큰 수.

    Returns:
        USD 비용.
    """
    rate = PRICING.get(model)
    if not rate:
        return 0.0
    return tokens * rate.get("input_per_1m", 0.0) / 1_000_000


def rerank_cost(model: str, searches: int) -> float:
    """rerank 호출 비용을 계산한다(검색 횟수 기준).

    Args:
        model: rerank 모델 식별자.
        searches: rerank 호출(검색) 횟수.

    Returns:
        USD 비용.
    """
    rate = PRICING.get(model)
    if not rate:
        return 0.0
    return searches * rate.get("per_1k_searches", 0.0) / 1_000


def query_cost(
    *,
    chat_model: str,
    chat_input_tokens: int,
    chat_output_tokens: int,
    embedding_model: str = "text-embedding-3-small",
    embedding_tokens: int = 0,
    rerank_model: str | None = None,
    rerank_searches: int = 0,
) -> CostBreakdown:
    """단일 질의의 총비용을 분해해 계산한다.

    Args:
        chat_model: 챗 모델.
        chat_input_tokens: 챗 입력 토큰 합.
        chat_output_tokens: 챗 출력 토큰 합.
        embedding_model: 임베딩 모델.
        embedding_tokens: 질의 임베딩 토큰(추정).
        rerank_model: rerank 모델(사용 시).
        rerank_searches: rerank 호출 수.

    Returns:
        CostBreakdown.
    """
    return CostBreakdown(
        embedding=embedding_cost(embedding_model, embedding_tokens),
        chat=chat_cost(chat_model, chat_input_tokens, chat_output_tokens),
        rerank=rerank_cost(rerank_model, rerank_searches) if rerank_model else 0.0,
    )
