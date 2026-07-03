# file: evaluation/judge.py
"""LLM-as-judge — 답변의 faithfulness(충실도)와 correctness(정확성) 평가.

Phase 0 Q6 우려(자기 채점 순환)를 피하려면 답변 생성 모델과 다른 모델을
심판으로 주입하는 것이 권장된다(생성=gpt-4o-mini면 심판=Gemini 등).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

import prompts

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class _Chat(Protocol):
    model: str

    def complete(self, user: str, system: str | None = ..., temperature: float = ...,
                 max_tokens: int = ...) -> Any: ...


@dataclass
class JudgeResult:
    """심판 결과.

    Attributes:
        faithfulness: 문맥 근거 충실도(0~1).
        correctness: 질문 대비 정확성(0~1).
        rationale: 심판 근거 요약.
        input_tokens: 심판 LLM 입력 토큰.
        output_tokens: 심판 LLM 출력 토큰.
    """

    faithfulness: float
    correctness: float
    rationale: str
    input_tokens: int
    output_tokens: int


class LLMJudge:
    """LLM 기반 답변 심판.

    Args:
        chat: 심판에 사용할 ChatProvider(생성 모델과 다른 것 권장).
    """

    def __init__(self, chat: _Chat) -> None:
        self._chat = chat

    def judge(
        self, question: str, answer: str, contexts: list[dict[str, Any]]
    ) -> JudgeResult:
        """답변을 평가해 faithfulness/correctness를 반환한다.

        파싱 실패 시 0점 처리하고 rationale에 사유를 남긴다(평가는 중단하지 않음).

        Args:
            question: 원 질문.
            answer: 평가 대상 답변.
            contexts: 답변이 사용한 문맥.

        Returns:
            JudgeResult.
        """
        result = self._chat.complete(
            user=prompts.build_judge_prompt(question, answer, contexts),
            system=prompts.JUDGE_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=400,
        )
        faith, correct, rationale = self._parse(result.text)
        return JudgeResult(
            faithfulness=faith,
            correctness=correct,
            rationale=rationale,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

    @staticmethod
    def _parse(text: str) -> tuple[float, float, str]:
        """심판 응답 텍스트에서 JSON을 추출·파싱한다(코드펜스 제거)."""
        cleaned = (text or "").replace("```json", "").replace("```", "")
        match = _JSON_RE.search(cleaned)
        if not match:
            logger.warning("심판 응답에서 JSON을 찾지 못함: %r", cleaned[:80])
            return 0.0, 0.0, "파싱 실패"
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            logger.warning("심판 JSON 파싱 실패: %r", match.group()[:80])
            return 0.0, 0.0, "JSON 파싱 실패"
        return (
            _clamp(data.get("faithfulness", 0.0)),
            _clamp(data.get("correctness", 0.0)),
            str(data.get("rationale", "")),
        )


def _clamp(value: Any) -> float:
    """값을 0.0~1.0으로 제한한다(비수치는 0.0)."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
