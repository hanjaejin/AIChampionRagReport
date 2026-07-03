# file: tests/test_metrics.py
"""검색 지표(metrics) 테스트 — 알려진 값으로 정확성 검증."""

from __future__ import annotations

import math

from evaluation import metrics


def test_context_label_article() -> None:
    assert metrics.context_label({"article_no": "제35조"}) == "제35조"


def test_context_label_annex() -> None:
    assert metrics.context_label({"annex_no": 3}) == "별표3"


def test_recall_at_k_hit() -> None:
    retrieved = ["제33조", "제35조", "제1조"]
    assert metrics.recall_at_k(retrieved, {"제35조"}, k=3) == 1.0
    assert metrics.recall_at_k(retrieved, {"제35조"}, k=1) == 0.0  # k=1엔 없음


def test_recall_at_k_partial_multi_gold() -> None:
    retrieved = ["제33조", "제99조", "제1조"]
    assert metrics.recall_at_k(retrieved, {"제33조", "제35조"}, k=3) == 0.5


def test_reciprocal_rank() -> None:
    assert metrics.reciprocal_rank(["제1조", "제35조"], {"제35조"}) == 0.5
    assert metrics.reciprocal_rank(["제35조"], {"제35조"}) == 1.0
    assert metrics.reciprocal_rank(["제1조"], {"제35조"}) == 0.0


def test_ndcg_perfect_vs_lower() -> None:
    gold = {"제35조"}
    # 1위에 정답 → nDCG=1
    assert metrics.ndcg_at_k(["제35조", "제1조"], gold, k=5) == 1.0
    # 2위에 정답 → 1/log2(3) / 1 < 1
    lower = metrics.ndcg_at_k(["제1조", "제35조"], gold, k=5)
    assert 0.0 < lower < 1.0
    assert math.isclose(lower, 1.0 / math.log2(3))


def test_ndcg_no_gold_hit() -> None:
    assert metrics.ndcg_at_k(["제1조", "제2조"], {"제35조"}, k=5) == 0.0


def test_aggregate_mean() -> None:
    rows = [
        {"recall": 1.0, "mrr": 1.0, "ndcg": 1.0},
        {"recall": 0.0, "mrr": 0.0, "ndcg": 0.0},
    ]
    agg = metrics.aggregate(rows, keys=("recall", "mrr", "ndcg"))
    assert agg["recall"] == 0.5
    assert agg["mrr"] == 0.5


def test_evaluate_retrieval_bundles_metrics() -> None:
    contexts = [{"article_no": "제1조"}, {"article_no": "제35조"}]
    result = metrics.evaluate_retrieval(contexts, {"제35조"}, k=5)
    assert result["recall"] == 1.0
    assert result["mrr"] == 0.5
    assert 0.0 < result["ndcg"] < 1.0
    assert result["hit"] is True


def test_dedupe_labels_preserves_order() -> None:
    assert metrics.dedupe_labels(["제8조", "제8조", "제1조", ""]) == ["제8조", "제1조"]


def test_ndcg_not_exceed_one_with_split_article() -> None:
    """분할 조문으로 같은 조번호가 2번 나와도 nDCG는 1.0을 넘지 않아야 한다."""
    contexts = [{"article_no": "제8조"}, {"article_no": "제8조"}, {"article_no": "제72조"}]
    result = metrics.evaluate_retrieval(contexts, {"제8조"}, k=5)
    assert result["ndcg"] == 1.0
    assert result["recall"] == 1.0
