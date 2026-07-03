# file: recompute_benchmark.py
"""저장된 벤치마크 원시 결과에서 검색 지표를 재계산한다(API 재호출 없음).

nDCG 중복 버그 수정 반영 + 지연 중앙값 계산. benchmark_results.json의
per-result context_labels/gold로 recall/mrr/ndcg를 다시 산출하고 요약을 갱신한다.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from evaluation import metrics

SRC = Path("docs") / "benchmark_results.json"


def _recompute() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    rows = data["results"]

    # per-result 재계산 (중복 제거된 라벨로)
    for r in rows:
        labels = metrics.dedupe_labels(r["context_labels"])
        gold = set(r["gold"])
        r["recall"] = metrics.recall_at_k(labels, gold, k=5)
        r["mrr"] = metrics.reciprocal_rank(labels, gold)
        r["ndcg"] = metrics.ndcg_at_k(labels, gold, k=5)
        r["hit"] = bool(set(labels) & gold)

    # 파이프라인별 재집계 (지연은 평균+중앙값)
    by_pl: dict[str, list] = {}
    for r in rows:
        by_pl.setdefault(r["pipeline"], []).append(r)

    summary = {}
    for name, rs in by_pl.items():
        n = len(rs)
        faiths = [r["faithfulness"] for r in rs if r["faithfulness"] is not None]
        corrects = [r["correctness"] for r in rs if r["correctness"] is not None]
        lat = [r["elapsed_sec"] for r in rs]
        err: dict[str, int] = {}
        for r in rs:
            err[r["error_class"]] = err.get(r["error_class"], 0) + 1
        summary[name] = {
            "n": n,
            "recall@k": sum(r["recall"] for r in rs) / n,
            "mrr": sum(r["mrr"] for r in rs) / n,
            "ndcg@k": sum(r["ndcg"] for r in rs) / n,
            "hit_rate": sum(1 for r in rs if r["hit"]) / n,
            "faithfulness": sum(faiths) / len(faiths) if faiths else None,
            "correctness": sum(corrects) / len(corrects) if corrects else None,
            "median_latency_sec": statistics.median(lat),
            "mean_latency_sec": sum(lat) / n,
            "total_cost_usd": sum(r["cost_usd"] for r in rs),
            "avg_tokens": sum(r["input_tokens"] + r["output_tokens"] for r in rs) / n,
            "error_dist": err,
        }

    data["summary"] = summary
    data["recomputed"] = True
    SRC.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 콘솔 출력
    print(f"{'파이프라인':<10} {'Recall@5':>8} {'MRR':>6} {'nDCG@5':>7} {'Faith':>6} "
          f"{'Correct':>7} {'지연(중앙)':>9} {'지연(평균)':>9} {'비용$':>8}")
    for name, a in summary.items():
        print(f"{name:<10} {a['recall@k']:>8.3f} {a['mrr']:>6.3f} {a['ndcg@k']:>7.3f} "
              f"{a['faithfulness']:>6.3f} {a['correctness']:>7.3f} "
              f"{a['median_latency_sec']:>9.1f} {a['mean_latency_sec']:>9.1f} "
              f"{a['total_cost_usd']:>8.5f}")


if __name__ == "__main__":
    _recompute()
