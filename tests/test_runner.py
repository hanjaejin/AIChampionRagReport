# file: tests/test_runner.py
"""러너(runner) 테스트 — 가짜 파이프라인/심판으로 채점 흐름 검증."""

from __future__ import annotations

from evaluation.benchmark import QAItem
from evaluation.runner import evaluate_answer, run_benchmark, summarize
from naive_rag import RagAnswer


def _answer(pipeline="naive", articles=("제35조",), candidates=None, model="openai/gpt-4o-mini"):
    contexts = [{"article_no": a, "content": f"{a} 내용"} for a in articles]
    trace = {"candidate_labels": list(candidates)} if candidates is not None else {}
    if pipeline == "modular":
        trace["route"] = "semantic"
    return RagAnswer(
        question="유출 신고?", answer="제35조에 따라 신고합니다.", contexts=contexts,
        input_tokens=100, output_tokens=20, model=model, elapsed_sec=1.0,
        pipeline=pipeline, trace=trace,
    )


class FakePipeline:
    def __init__(self, answer): self._answer = answer
    def answer(self, question): return self._answer


class FakeJudge:
    def judge(self, question, answer, contexts):
        from evaluation.judge import JudgeResult
        return JudgeResult(faithfulness=0.9, correctness=0.9, rationale="ok",
                           input_tokens=30, output_tokens=5)


ITEM = QAItem(id="q01", question="유출 신고?", gold={"제35조"}, category="semantic")


def test_evaluate_answer_metrics_and_cost() -> None:
    r = evaluate_answer(ITEM, _answer(), rerank_model=None)
    assert r.recall == 1.0
    assert r.mrr == 1.0
    assert r.hit is True
    assert r.cost_usd > 0.0          # 챗 토큰 비용
    assert r.error_class == "OK"     # 심판 없음 + 문맥에 골드


def test_evaluate_answer_e1_when_gold_missing() -> None:
    ans = _answer(articles=("제1조",), candidates=["제1조", "제2조"])
    r = evaluate_answer(ITEM, ans)
    assert r.error_class == "E1"
    assert r.recall == 0.0


def test_evaluate_answer_with_judge_ok() -> None:
    r = evaluate_answer(ITEM, _answer(), judge=FakeJudge())
    assert r.faithfulness == 0.9
    assert r.error_class == "OK"


def test_advanced_rerank_cost_included() -> None:
    ans = _answer(pipeline="advanced")
    r = evaluate_answer(ITEM, ans, rerank_model="rerank-multilingual-v3.0")
    # rerank 1회(=$2/1000=$0.002)가 비용에 포함
    assert r.cost_usd >= 0.002


def test_run_benchmark_and_summarize() -> None:
    pipelines = {
        "naive": FakePipeline(_answer("naive")),
        "advanced": FakePipeline(_answer("advanced")),
    }
    results = run_benchmark(pipelines, [ITEM], rerank_model="rerank-multilingual-v3.0")
    assert len(results) == 2
    summary = summarize(results)
    assert set(summary) == {"naive", "advanced"}
    assert summary["naive"]["recall@k"] == 1.0
    assert summary["naive"]["error_dist"]["OK"] == 1


def test_run_benchmark_isolates_failures() -> None:
    class Boom:
        def answer(self, q): raise RuntimeError("boom")

    results = run_benchmark({"naive": Boom()}, [ITEM])
    assert results[0].error_class == "ERROR"
    assert "boom" in results[0].answer
