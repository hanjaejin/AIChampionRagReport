# file: run_benchmark.py
"""전체 벤치마크 실행 CLI — 결과를 JSON/Markdown으로 저장.

사용법:
    python run_benchmark.py                 # 심판 없이(검색 지표·비용·지연)
    python run_benchmark.py --judge         # LLM 심판 포함(faithfulness/correctness/E3)
    python run_benchmark.py --limit 6       # 앞 N문항만

챗=OpenRouter, 임베딩=Gemini, rerank=Cohere. 심판은 생성과 다른 모델(gpt-4o).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from config import load_settings
from evaluation.benchmark import load_benchmark
from evaluation.judge import LLMJudge
from evaluation.runner import run_benchmark, summarize
from pipeline_factory import build_chat, build_components, build_pipelines

logger = logging.getLogger(__name__)

RESULTS_JSON = Path("docs") / "benchmark_results.json"
RESULTS_MD = Path("docs") / "benchmark_results.md"


def _fmt(value, digits=3):
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "-"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description="RAG 벤치마크 실행")
    parser.add_argument("--judge", action="store_true", help="LLM 심판 포함")
    parser.add_argument("--limit", type=int, default=None, help="앞 N문항만")
    parser.add_argument("--chat", default="openrouter", choices=["openrouter", "gemini"])
    args = parser.parse_args(argv)

    settings = load_settings()
    components = build_components(
        settings, provider=args.chat, embedding_provider="gemini"
    )
    pipelines = build_pipelines(components)

    judge = None
    if args.judge:
        judge_model = "openai/gpt-4o" if args.chat == "openrouter" else None
        judge = LLMJudge(build_chat(settings, "openrouter", judge_model))

    items = load_benchmark()
    if args.limit:
        items = items[: args.limit]

    print(f"벤치마크 실행: {len(items)}문항 x 3파이프라인, 심판={'ON' if judge else 'OFF'}")
    print(f"  임베딩={components.embedding_model} 챗={components.chat_model} rerank={components.rerank_model}\n")

    def _progress(frac, msg):
        print(f"\r  [{int(frac*100):3d}%] {msg:40}", end="", flush=True)

    results = run_benchmark(
        pipelines, items, judge=judge,
        rerank_model=components.rerank_model, progress=_progress,
    )
    print()
    summary = summarize(results)

    # 콘솔 요약
    print("\n===== 파이프라인별 요약 =====")
    header = f"{'파이프라인':<10} {'Recall@5':>9} {'MRR':>6} {'nDCG@5':>7} {'Hit율':>6} {'Faith':>6} {'Correct':>7} {'지연s':>6} {'비용$':>9} {'오류분포'}"
    print(header)
    for name, agg in summary.items():
        print(
            f"{name:<10} {_fmt(agg['recall@k']):>9} {_fmt(agg['mrr']):>6} "
            f"{_fmt(agg['ndcg@k']):>7} {_fmt(agg['hit_rate']):>6} "
            f"{_fmt(agg['faithfulness']):>6} {_fmt(agg['correctness']):>7} "
            f"{_fmt(agg['avg_latency_sec'],1):>6} {_fmt(agg['total_cost_usd'],5):>9} "
            f"{agg['error_dist']}"
        )

    # 저장
    RESULTS_JSON.write_text(
        json.dumps(
            {
                "date": date.today().isoformat(),
                "config": {
                    "embedding": components.embedding_model,
                    "chat": components.chat_model,
                    "rerank": components.rerank_model,
                    "judge": bool(judge),
                    "n_items": len(items),
                },
                "summary": summary,
                "results": [asdict(r) for r in results],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    _write_markdown(summary, components, bool(judge), len(items))
    print(f"\n저장: {RESULTS_JSON}  /  {RESULTS_MD}")
    return 0


def _write_markdown(summary, components, judged, n_items) -> None:
    lines = [
        "# 벤치마크 실측 결과",
        "",
        f"> 실행일: {date.today().isoformat()} · {n_items}문항 x 3파이프라인 · "
        f"심판={'ON' if judged else 'OFF'}",
        f"> 임베딩={components.embedding_model} · 챗={components.chat_model} · "
        f"rerank={components.rerank_model}",
        "",
        "## 파이프라인별 요약",
        "",
        "| 파이프라인 | Recall@5 | MRR | nDCG@5 | Hit율 | Faithful | Correct | 평균지연(s) | 총비용($) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, agg in summary.items():
        lines.append(
            f"| {name} | {_fmt(agg['recall@k'])} | {_fmt(agg['mrr'])} | "
            f"{_fmt(agg['ndcg@k'])} | {_fmt(agg['hit_rate'])} | "
            f"{_fmt(agg['faithfulness'])} | {_fmt(agg['correctness'])} | "
            f"{_fmt(agg['avg_latency_sec'],1)} | {_fmt(agg['total_cost_usd'],5)} |"
        )
    lines += ["", "## 오류 분류 분포 (E1 검색 / E2 재정렬 / E3 생성)", ""]
    lines.append("| 파이프라인 | " + " | ".join(["OK", "E1", "E2", "E3", "ERROR"]) + " |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for name, agg in summary.items():
        d = agg["error_dist"]
        lines.append(
            f"| {name} | " + " | ".join(str(d.get(k, 0)) for k in ["OK", "E1", "E2", "E3", "ERROR"]) + " |"
        )
    RESULTS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
