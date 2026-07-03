# file: evaluation/metrics.py
"""검색 지표 계산 — 순수 함수 (LLM 불필요, 결정적).

Recall@k, MRR, nDCG@k 를 조번호/별표 라벨 기준으로 계산한다.
골드 라벨이 article_no 기준이므로 청킹 방식이 바뀌어도 평가 세트를 재사용할 수 있다.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence


def context_label(chunk: dict[str, Any]) -> str:
    """청크의 평가 라벨을 만든다(조번호 우선, 없으면 별표번호).

    Args:
        chunk: 검색 결과 청크 dict.

    Returns:
        '제35조' 또는 '별표3' 형식 라벨. 둘 다 없으면 빈 문자열.
    """
    if chunk.get("article_no"):
        return str(chunk["article_no"])
    if chunk.get("annex_no") is not None:
        return f"별표{chunk['annex_no']}"
    return ""


def context_labels(chunks: Sequence[dict[str, Any]]) -> list[str]:
    """청크 목록을 라벨 목록으로 변환한다(순서 보존)."""
    return [context_label(c) for c in chunks]


def dedupe_labels(labels: Sequence[str]) -> list[str]:
    """라벨을 순서 보존하며 중복 제거한다(빈 라벨 제외).

    조문이 분할(R2)되면 같은 조번호 청크가 여러 개 나올 수 있다. 조번호 단위
    검색 평가에서는 같은 조를 1건으로 취급해야 nDCG가 1.0을 넘지 않는다.

    Args:
        labels: 순위 순 라벨 목록.

    Returns:
        중복이 제거된 순서 보존 라벨 목록.
    """
    seen: set[str] = set()
    result: list[str] = []
    for label in labels:
        if label and label not in seen:
            seen.add(label)
            result.append(label)
    return result


def recall_at_k(retrieved: Sequence[str], gold: set[str], k: int) -> float:
    """상위 k개 안에서 회수된 골드 비율.

    Args:
        retrieved: 순위대로 정렬된 검색 라벨.
        gold: 정답 라벨 집합.
        k: 상위 컷.

    Returns:
        |gold ∩ retrieved[:k]| / |gold|. gold가 비면 0.0.
    """
    if not gold:
        return 0.0
    hits = set(retrieved[:k]) & gold
    return len(hits) / len(gold)


def reciprocal_rank(retrieved: Sequence[str], gold: set[str]) -> float:
    """첫 골드 히트의 역순위(MRR의 단일 질의 값).

    Args:
        retrieved: 순위대로 정렬된 검색 라벨.
        gold: 정답 라벨 집합.

    Returns:
        1/rank(첫 히트). 히트 없으면 0.0.
    """
    for rank, label in enumerate(retrieved, start=1):
        if label in gold:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: Sequence[str], gold: set[str], k: int) -> float:
    """이진 관련도 기준 nDCG@k.

    Args:
        retrieved: 순위대로 정렬된 검색 라벨.
        gold: 정답 라벨 집합.
        k: 상위 컷.

    Returns:
        DCG/IDCG. 정답이 하나도 없으면 0.0.
    """
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, label in enumerate(retrieved[:k], start=1)
        if label in gold
    )
    ideal_hits = min(len(gold), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def evaluate_retrieval(
    contexts: Sequence[dict[str, Any]], gold: set[str], k: int = 5
) -> dict[str, Any]:
    """단일 질의의 검색 지표 묶음을 계산한다.

    Args:
        contexts: 파이프라인이 반환한 최종 문맥 청크(순위 순).
        gold: 정답 라벨 집합.
        k: 상위 컷.

    Returns:
        recall/mrr/ndcg/hit 를 담은 dict.
    """
    # 조번호 단위 평가: 분할 청크로 인한 라벨 중복 제거(nDCG ≤ 1.0 보장)
    labels = dedupe_labels(context_labels(contexts))
    return {
        "recall": recall_at_k(labels, gold, k),
        "mrr": reciprocal_rank(labels, gold),
        "ndcg": ndcg_at_k(labels, gold, k),
        "hit": bool(set(labels) & gold),
    }


def aggregate(
    rows: Iterable[dict[str, Any]], keys: Sequence[str]
) -> dict[str, float]:
    """행 목록에서 지정 키들의 산술 평균을 낸다.

    Args:
        rows: 질의별 지표 dict 목록.
        keys: 평균낼 키 목록.

    Returns:
        키별 평균 dict. 행이 없으면 각 키 0.0.
    """
    rows = list(rows)
    if not rows:
        return {key: 0.0 for key in keys}
    return {
        key: sum(float(row.get(key, 0.0)) for row in rows) / len(rows) for key in keys
    }
