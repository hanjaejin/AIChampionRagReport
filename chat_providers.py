# file: chat_providers.py
"""ChatProvider 추상화 — OpenRouter / Google Gemini 이중 지원.

Phase 1 설계의 `ChatProvider` 경계를 구현한다. RAG 파이프라인 코드는
구체 Provider(OpenRouter/Gemini)를 몰라도 되도록 이 프로토콜에만 의존한다.
두 구현은 서로 다른 SDK를 사용해(추상화의 가치를 실증):
    - OpenRouterProvider : openai SDK(OpenAI 호환) + OpenRouter base_url
    - GeminiProvider     : google-genai SDK(네이티브)
폐쇄망 전환 시 vLLM 등 로컬 구현체를 같은 인터페이스로 추가하면 된다.
API 키는 생성자 주입으로 받는다(UI 입력 키 정책 지원).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from retry_util import retry_call

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class ChatResult:
    """LLM 응답 + 사용량(비용 계산용).

    Attributes:
        text: 생성된 답변 텍스트.
        input_tokens: 입력(프롬프트) 토큰 수.
        output_tokens: 출력(생성) 토큰 수.
        model: 실제 사용된 모델 식별자.
    """

    text: str
    input_tokens: int
    output_tokens: int
    model: str


@runtime_checkable
class ChatProvider(Protocol):
    """단일 턴 채팅 완성 인터페이스."""

    model: str

    def complete(
        self,
        user: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> ChatResult:
        """system+user 프롬프트로 답변을 생성한다.

        Args:
            user: 사용자 메시지.
            system: 시스템 지시문(없으면 생략).
            temperature: 샘플링 온도(기본 0.0 — 결정적, 비교 공정성).
            max_tokens: 최대 생성 토큰.

        Returns:
            생성 결과 ChatResult.
        """
        ...


class OpenRouterProvider:
    """OpenRouter(OpenAI 호환) 챗 Provider.

    Args:
        api_key: OpenRouter API 키(생성자 주입).
        model: 모델 식별자(예: 'openai/gpt-4o-mini', 'google/gemini-2.5-flash').
        client: 테스트용 주입 클라이언트(미지정 시 openai.OpenAI 생성).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4o-mini",
        client: Any | None = None,
    ) -> None:
        self.model = model
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
        self._client = client

    def complete(
        self,
        user: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> ChatResult:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        response = retry_call(
            lambda: self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            what="OpenRouter 챗",
        )
        usage = response.usage
        return ChatResult(
            text=response.choices[0].message.content or "",
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            model=self.model,
        )


class GeminiProvider:
    """Google Gemini(네이티브 google-genai SDK) 챗 Provider.

    Args:
        api_key: Gemini API 키(생성자 주입).
        model: 모델 식별자(예: 'gemini-2.5-flash').
        client: 테스트용 주입 클라이언트(미지정 시 genai.Client 생성).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        client: Any | None = None,
        thinking_budget: int = 0,
    ) -> None:
        self.model = model
        # gemini-2.5-* 는 기본으로 사고(thinking)가 켜져 출력 토큰을 소진한다.
        # RAG 답변/심판/라우팅은 직접 출력이 필요하므로 기본 비활성화(0)한다.
        self._thinking_budget = thinking_budget
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client

    def complete(
        self,
        user: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> ChatResult:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=self._thinking_budget),
        )
        response = retry_call(
            lambda: self._client.models.generate_content(
                model=self.model, contents=user, config=config
            ),
            what="Gemini 챗",
        )
        usage = response.usage_metadata
        return ChatResult(
            text=response.text or "",
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            model=self.model,
        )
