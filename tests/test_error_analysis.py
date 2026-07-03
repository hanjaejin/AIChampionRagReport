# file: tests/test_error_analysis.py
"""오류 분류(error_analysis) 테스트."""

from __future__ import annotations

from evaluation.error_analysis import ErrorClass, classify


def test_e1_gold_not_in_candidates() -> None:
    result = classify(
        gold={"제35조"},
        candidate_labels=["제1조", "제2조"],
        context_labels=["제1조"],
    )
    assert result == ErrorClass.E1


def test_e2_gold_in_candidates_not_in_context() -> None:
    result = classify(
        gold={"제35조"},
        candidate_labels=["제35조", "제1조", "제2조"],
        context_labels=["제1조", "제2조"],
    )
    assert result == ErrorClass.E2


def test_e3_gold_in_context_but_bad_generation() -> None:
    result = classify(
        gold={"제35조"},
        candidate_labels=["제35조"],
        context_labels=["제35조"],
        faithfulness=0.2, correctness=0.3,
    )
    assert result == ErrorClass.E3


def test_ok_gold_in_context_good_generation() -> None:
    result = classify(
        gold={"제35조"},
        candidate_labels=["제35조"],
        context_labels=["제35조"],
        faithfulness=0.9, correctness=0.9,
    )
    assert result == ErrorClass.OK


def test_ok_when_no_judge_scores() -> None:
    # 심판 점수 없으면 문맥에 골드가 있으면 OK(E3 판정 생략)
    result = classify(
        gold={"제35조"},
        candidate_labels=["제35조"],
        context_labels=["제35조"],
    )
    assert result == ErrorClass.OK


def test_e1_precedence_over_e3_scores() -> None:
    # 검색 실패면 심판 점수와 무관하게 E1
    result = classify(
        gold={"제35조"},
        candidate_labels=["제1조"],
        context_labels=["제1조"],
        faithfulness=0.9, correctness=0.9,
    )
    assert result == ErrorClass.E1
