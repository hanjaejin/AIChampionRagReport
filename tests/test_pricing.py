# file: tests/test_pricing.py
"""pricing 모듈 테스트."""

from __future__ import annotations

import math

from evaluation import pricing


def test_chat_cost() -> None:
    # gpt-4o-mini: 1M input=$0.15, 1M output=$0.60
    cost = pricing.chat_cost("openai/gpt-4o-mini", 1_000_000, 1_000_000)
    assert math.isclose(cost, 0.75)


def test_chat_cost_unknown_model_zero() -> None:
    assert pricing.chat_cost("unknown/model", 1000, 1000) == 0.0


def test_embedding_cost() -> None:
    cost = pricing.embedding_cost("text-embedding-3-small", 1_000_000)
    assert math.isclose(cost, 0.02)


def test_rerank_cost() -> None:
    cost = pricing.rerank_cost("rerank-multilingual-v3.0", 1000)
    assert math.isclose(cost, 2.00)


def test_query_cost_breakdown_and_total() -> None:
    bd = pricing.query_cost(
        chat_model="openai/gpt-4o-mini",
        chat_input_tokens=2_000_000,
        chat_output_tokens=0,
        embedding_tokens=1_000_000,
        rerank_model="rerank-multilingual-v3.0",
        rerank_searches=1000,
    )
    assert math.isclose(bd.embedding, 0.02)
    assert math.isclose(bd.chat, 0.30)
    assert math.isclose(bd.rerank, 2.00)
    assert math.isclose(bd.total, 2.32)
