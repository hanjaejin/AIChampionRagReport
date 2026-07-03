# file: query_rewriter.py
"""쿼리 재작성기 — 구어체 질문을 규정 검색에 적합하게 변환.

Advanced/Modular RAG의 검색 전 최적화 단계. ChatProvider를 주입받아
LLM으로 질문을 규정 용어로 정규화하고 동의어를 확장한다(검색 재현율 향상).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import prompts

logger = logging.getLogger(__name__)


class _Chat(Protocol):
    def complete(
        self, user: str, system: str | None = ..., temperature: float = ...,
        max_tokens: int = ...,
    ) -> Any: ...


@dataclass
class RewriteResult:
    """쿼리 재작성 결과.

    Attributes:
        original: 원 질문.
        rewritten: 재작성된 검색 질의.
        input_tokens: 재작성 LLM 입력 토큰.
        output_tokens: 재작성 LLM 출력 토큰.
    """

    original: str
    rewritten: str
    input_tokens: int
    output_tokens: int


class QueryRewriter:
    """LLM 기반 쿼리 재작성기.

    Args:
        chat: 재작성에 사용할 ChatProvider.
    """

    def __init__(self, chat: _Chat) -> None:
        self._chat = chat

    def rewrite(self, question: str) -> RewriteResult:
        """질문을 규정 검색용으로 재작성한다.

        실패(빈 응답)하면 원 질문을 그대로 사용한다(폴백).

        Args:
            question: 원 질문.

        Returns:
            재작성 결과. rewritten이 비면 original로 대체된다.
        """
        result = self._chat.complete(
            user=prompts.build_rewrite_prompt(question),
            system=prompts.REWRITE_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=128,
        )
        rewritten = (result.text or "").strip().splitlines()
        text = rewritten[0].strip() if rewritten else ""
        if not text:
            logger.warning("쿼리 재작성 결과가 비어 원 질문을 사용합니다.")
            text = question
        return RewriteResult(
            original=question,
            rewritten=text,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
