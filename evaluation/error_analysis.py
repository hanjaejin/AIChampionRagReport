# file: evaluation/error_analysis.py
"""오류 3단 분류 (Phase 1 설계 5절).

오답의 책임 소재를 검색/재정렬/생성 중 어디인지 분류한다.
E1/E2는 골드 라벨로 LLM 없이 자동 판정(비용 0), E3만 심판 점수 필요.
"""

from __future__ import annotations

from enum import Enum
from typing import Sequence


class ErrorClass(str, Enum):
    """오류 분류.

    OK: 정답 문맥 확보 + 정확한 답변.
    E1: 검색 한계 — 골드가 후보군에도 없음(임베딩/청킹 책임).
    E2: 재정렬/파이프라인 실패 — 후보엔 있으나 최종 문맥에서 탈락(rerank/라우팅 책임).
    E3: 생성 실패 — 문맥에 있는데도 답변 오류(챗/프롬프트 책임).
    """

    OK = "OK"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"


def classify(
    gold: set[str],
    candidate_labels: Sequence[str],
    context_labels: Sequence[str],
    faithfulness: float | None = None,
    correctness: float | None = None,
    faith_threshold: float = 0.5,
    correct_threshold: float = 0.5,
) -> ErrorClass:
    """단일 질의 결과를 오류 클래스로 분류한다.

    Args:
        gold: 정답 라벨 집합.
        candidate_labels: 넓은 검색 후보 라벨(top-20 등). 파이프라인 trace 기준.
        context_labels: 최종 생성에 사용된 문맥 라벨.
        faithfulness: 심판 충실도(없으면 E3 판정 생략).
        correctness: 심판 정확성(없으면 E3 판정 생략).
        faith_threshold: 이 미만이면 생성 실패로 간주.
        correct_threshold: 이 미만이면 생성 실패로 간주.

    Returns:
        ErrorClass.
    """
    gold = set(gold)
    if not gold:
        return ErrorClass.OK

    in_candidates = bool(gold & set(candidate_labels))
    in_contexts = bool(gold & set(context_labels))

    if not in_candidates:
        return ErrorClass.E1
    if not in_contexts:
        return ErrorClass.E2

    # 골드가 최종 문맥에 있음 → 생성 품질로 판정(심판 점수가 있을 때만)
    if faithfulness is not None and correctness is not None:
        if faithfulness < faith_threshold or correctness < correct_threshold:
            return ErrorClass.E3
    return ErrorClass.OK
