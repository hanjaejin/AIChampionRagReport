# file: router.py
"""질의 라우터 — Modular RAG의 2단 라우팅.

1단(규칙 기반, 무료·즉시): 질문에 조번호/별표번호 패턴이 있으면 직접 조회 경로,
    서식·표 관련 키워드가 있으면 표 검색 경로로 분류.
2단(LLM, 1단 미분류 시에만): TABLE/SEMANTIC 분류.

조번호가 명시된 질문은 벡터 검색보다 메타데이터 직접 조회가 항상 우월하므로
이 경로의 존재가 Modular RAG의 핵심 차별점이다(Phase 1 설계 2-3).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import prompts

logger = logging.getLogger(__name__)

_ARTICLE_RE = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?")
_ANNEX_RE = re.compile(r"별표\s*(\d+)")
# 표/서식류 키워드(규칙 기반 TABLE 경로)
_TABLE_KEYWORDS = ("서식", "양식", "별지", "대장", "기준표", "별표", "표를", "서류")


class Route(str, Enum):
    """검색 경로."""

    DIRECT = "direct"      # 조번호/별표번호 직접 조회
    TABLE = "table"        # 표(별표) 검색
    SEMANTIC = "semantic"  # 일반 하이브리드 의미 검색


class _Chat(Protocol):
    def complete(self, user: str, system: str | None = ..., temperature: float = ...,
                 max_tokens: int = ...) -> Any: ...


@dataclass
class RouteDecision:
    """라우팅 결정 결과.

    Attributes:
        route: 선택된 경로.
        tier: 결정 계층('rule' 또는 'llm').
        article_no: DIRECT 경로에서 추출한 조번호(예: '제36조').
        annex_no: DIRECT 경로에서 추출한 별표번호.
        input_tokens: LLM 분류 입력 토큰(규칙 결정 시 0).
        output_tokens: LLM 분류 출력 토큰.
    """

    route: Route
    tier: str
    article_no: str | None = None
    annex_no: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0


class QueryRouter:
    """규칙+LLM 2단 질의 라우터.

    Args:
        chat: 2단 LLM 분류용 ChatProvider(None이면 규칙 미분류 시 SEMANTIC로 폴백).
    """

    def __init__(self, chat: _Chat | None = None) -> None:
        self._chat = chat

    def route(self, question: str) -> RouteDecision:
        """질문을 검색 경로로 분류한다.

        Args:
            question: 사용자 질문.

        Returns:
            라우팅 결정(RouteDecision).
        """
        # 1단: 규칙 기반
        if annex := _ANNEX_RE.search(question):
            return RouteDecision(Route.DIRECT, "rule", annex_no=int(annex.group(1)))
        if article := _ARTICLE_RE.search(question):
            no = f"제{article.group(1)}조"
            if article.group(2):
                no += f"의{article.group(2)}"
            return RouteDecision(Route.DIRECT, "rule", article_no=no)
        if any(kw in question for kw in _TABLE_KEYWORDS):
            return RouteDecision(Route.TABLE, "rule")

        # 2단: LLM 분류 (chat 없으면 SEMANTIC 폴백)
        if self._chat is None:
            return RouteDecision(Route.SEMANTIC, "rule")
        return self._llm_route(question)

    def _llm_route(self, question: str) -> RouteDecision:
        result = self._chat.complete(
            user=prompts.build_route_prompt(question),
            system=prompts.ROUTE_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=8,
        )
        label = (result.text or "").strip().upper()
        route = Route.TABLE if "TABLE" in label else Route.SEMANTIC
        logger.info("LLM 라우팅: %r → %s", question, route.value)
        return RouteDecision(
            route, "llm",
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
        )
