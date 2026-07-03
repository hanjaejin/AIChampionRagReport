# file: evaluation/runner.py
"""벤치마크 러너 — 파이프라인을 QA 세트에 실행해 지표·비용·오류를 수집.

파이프라인/심판은 주입받아 외부 서비스 없이도(가짜로) 테스트 가능하다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from evaluation import metrics, pricing
from evaluation.benchmark import QAItem
from evaluation.error_analysis import ErrorClass, classify

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, str], None]


@dataclass
class QAResult:
    """단일 (질의 × 파이프라인) 평가 결과.

    Attributes:
        item_id: 질의 ID.
        question: 질문.
        pipeline: 파이프라인 이름.
        answer: 생성 답변.
        gold: 정답 라벨.
        context_labels: 최종 문맥 라벨.
        recall/mrr/ndcg/hit: 검색 지표.
        faithfulness/correctness: 심판 점수(심판 미사용 시 None).
        error_class: 오류 분류(E1/E2/E3/OK).
        input_tokens/output_tokens: 파이프라인 LLM 토큰 합.
        elapsed_sec: 소요 시간.
        cost_usd: 추정 비용(USD).
        route: (Modular) 라우팅 경로.
    """

    item_id: str
    question: str
    pipeline: str
    answer: str
    gold: list[str]
    context_labels: list[str]
    recall: float
    mrr: float
    ndcg: float
    hit: bool
    faithfulness: float | None
    correctness: float | None
    error_class: str
    input_tokens: int
    output_tokens: int
    elapsed_sec: float
    cost_usd: float
    route: str | None = None


def evaluate_answer(
    item: QAItem,
    answer: Any,
    *,
    k: int = 5,
    judge: Any | None = None,
    embedding_model: str = "text-embedding-3-small",
    rerank_model: str | None = None,
) -> QAResult:
    """파이프라인이 반환한 RagAnswer를 채점해 QAResult로 만든다.

    Args:
        item: 벤치마크 질의.
        answer: 파이프라인 RagAnswer.
        k: 지표 상위 컷.
        judge: LLMJudge(있으면 faithfulness/correctness 계산 및 E3 판정).
        embedding_model: 임베딩 모델(비용 계산).
        rerank_model: rerank 모델(비용 계산, 사용 시).

    Returns:
        QAResult.
    """
    retrieval = metrics.evaluate_retrieval(answer.contexts, item.gold, k=k)
    labels = metrics.context_labels(answer.contexts)
    candidate_labels = answer.trace.get("candidate_labels", labels)

    faith = correct = None
    judge_in = judge_out = 0
    if judge is not None:
        verdict = judge.judge(item.question, answer.answer, answer.contexts)
        faith, correct = verdict.faithfulness, verdict.correctness
        judge_in, judge_out = verdict.input_tokens, verdict.output_tokens

    error = classify(
        gold=item.gold,
        candidate_labels=candidate_labels,
        context_labels=labels,
        faithfulness=faith,
        correctness=correct,
    )

    # 비용: 파이프라인 LLM 토큰 + (rerank 사용 파이프라인은 검색 1회). 심판 비용은 제외.
    uses_rerank = answer.pipeline in ("advanced", "modular") and rerank_model
    cost = pricing.query_cost(
        chat_model=answer.model,
        chat_input_tokens=answer.input_tokens,
        chat_output_tokens=answer.output_tokens,
        embedding_model=embedding_model,
        embedding_tokens=0,
        rerank_model=rerank_model if uses_rerank else None,
        rerank_searches=1 if uses_rerank else 0,
    )

    return QAResult(
        item_id=item.id,
        question=item.question,
        pipeline=answer.pipeline,
        answer=answer.answer,
        gold=sorted(item.gold),
        context_labels=labels,
        recall=retrieval["recall"],
        mrr=retrieval["mrr"],
        ndcg=retrieval["ndcg"],
        hit=retrieval["hit"],
        faithfulness=faith,
        correctness=correct,
        error_class=error.value,
        input_tokens=answer.input_tokens,
        output_tokens=answer.output_tokens,
        elapsed_sec=answer.elapsed_sec,
        cost_usd=cost.total,
        route=answer.trace.get("route"),
    )


def run_benchmark(
    pipelines: dict[str, Any],
    items: Sequence[QAItem],
    *,
    k: int = 5,
    judge: Any | None = None,
    embedding_model: str = "text-embedding-3-small",
    rerank_model: str | None = None,
    progress: ProgressCallback | None = None,
) -> list[QAResult]:
    """여러 파이프라인을 QA 세트 전체에 실행한다.

    Args:
        pipelines: {이름: 파이프라인} 매핑.
        items: QA 항목 목록.
        k: 지표 상위 컷.
        judge: LLMJudge(선택).
        embedding_model: 임베딩 모델(비용).
        rerank_model: rerank 모델(비용).
        progress: 진행률 콜백.

    Returns:
        모든 (질의×파이프라인) QAResult 목록.
    """
    results: list[QAResult] = []
    total = len(items) * len(pipelines)
    done = 0
    for item in items:
        for name, pipeline in pipelines.items():
            if progress:
                progress(done / total, f"[{name}] {item.id}")
            try:
                answer = pipeline.answer(item.question)
                results.append(
                    evaluate_answer(
                        item, answer, k=k, judge=judge,
                        embedding_model=embedding_model, rerank_model=rerank_model,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 한 항목 실패가 전체를 막지 않도록
                logger.exception("실행 실패: %s / %s", name, item.id)
                results.append(_error_result(item, name, exc))
            done += 1
    if progress:
        progress(1.0, "완료")
    return results


def summarize(results: Sequence[QAResult]) -> dict[str, dict[str, Any]]:
    """파이프라인별 지표·비용·오류 분포를 집계한다.

    Args:
        results: QAResult 목록.

    Returns:
        {파이프라인: {recall, mrr, ndcg, hit_rate, faithfulness, correctness,
                     avg_latency, total_cost, error_dist}} 매핑.
    """
    by_pipeline: dict[str, list[QAResult]] = {}
    for r in results:
        by_pipeline.setdefault(r.pipeline, []).append(r)

    summary: dict[str, dict[str, Any]] = {}
    for name, rows in by_pipeline.items():
        n = len(rows)
        faiths = [r.faithfulness for r in rows if r.faithfulness is not None]
        corrects = [r.correctness for r in rows if r.correctness is not None]
        error_dist: dict[str, int] = {}
        for r in rows:
            error_dist[r.error_class] = error_dist.get(r.error_class, 0) + 1
        summary[name] = {
            "n": n,
            "recall@k": sum(r.recall for r in rows) / n,
            "mrr": sum(r.mrr for r in rows) / n,
            "ndcg@k": sum(r.ndcg for r in rows) / n,
            "hit_rate": sum(1 for r in rows if r.hit) / n,
            "faithfulness": sum(faiths) / len(faiths) if faiths else None,
            "correctness": sum(corrects) / len(corrects) if corrects else None,
            "avg_latency_sec": sum(r.elapsed_sec for r in rows) / n,
            "total_cost_usd": sum(r.cost_usd for r in rows),
            "avg_tokens": sum(r.input_tokens + r.output_tokens for r in rows) / n,
            "error_dist": error_dist,
        }
    return summary


def _error_result(item: QAItem, pipeline: str, exc: Exception) -> QAResult:
    """실행 예외를 실패 QAResult로 감싼다."""
    return QAResult(
        item_id=item.id, question=item.question, pipeline=pipeline,
        answer=f"[실행 오류] {type(exc).__name__}: {exc}", gold=sorted(item.gold),
        context_labels=[], recall=0.0, mrr=0.0, ndcg=0.0, hit=False,
        faithfulness=None, correctness=None, error_class="ERROR",
        input_tokens=0, output_tokens=0, elapsed_sec=0.0, cost_usd=0.0,
    )
