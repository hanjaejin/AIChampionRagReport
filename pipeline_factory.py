# file: pipeline_factory.py
"""파이프라인 조립 팩토리 — CLI/러너/Streamlit 앱이 공유.

설정(Settings)과 사용자가 선택한 Provider로부터 3개 RAG 파이프라인을 조립한다.
동일한 embedder/store/chat/reranker 를 공유해 공정 비교를 보장한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from advanced_rag import AdvancedRAG
from chat_providers import GeminiProvider, OpenRouterProvider
from config import Settings
from embeddings import GeminiEmbeddingProvider, OpenAIEmbeddingProvider
from modular_rag import ModularRAG
from naive_rag import NaiveRAG
from reranker import CohereReranker
from router import QueryRouter
from vector_store import SupabaseVectorStore

logger = logging.getLogger(__name__)

# 기본 임베딩 Provider (OpenAI 크레딧 이슈로 Gemini로 전환).
# OpenRouter는 임베딩 API가 없어 임베딩 대안은 Gemini 또는 OpenAI뿐이다.
DEFAULT_EMBEDDING_PROVIDER = "gemini"

# provider 이름 → (기본 모델, ChatProvider 생성 함수)
_CHAT_PROVIDERS = {
    "openrouter": "openai/gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
}


@dataclass
class Components:
    """3개 파이프라인이 공유하는 구성 요소.

    Attributes:
        embedder: 임베딩 Provider.
        store: 벡터 스토어.
        chat: 챗 Provider.
        reranker: 재정렬기.
        chat_model: 챗 모델 식별자(비용 계산용).
        rerank_model: rerank 모델 식별자(비용 계산용).
        embedding_model: 임베딩 모델 식별자.
    """

    embedder: OpenAIEmbeddingProvider
    store: SupabaseVectorStore
    chat: Any
    reranker: CohereReranker
    chat_model: str
    rerank_model: str
    embedding_model: str


def build_chat(settings: Settings, provider: str, model: str | None = None) -> Any:
    """선택한 Provider의 ChatProvider를 생성한다.

    Args:
        settings: 비밀값.
        provider: 'openrouter' 또는 'gemini'.
        model: 모델 오버라이드(미지정 시 Provider 기본).

    Returns:
        ChatProvider 인스턴스.

    Raises:
        ValueError: 알 수 없는 provider.
    """
    if provider == "openrouter":
        settings.require("openrouter_api_key")
        return OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            model=model or _CHAT_PROVIDERS["openrouter"],
        )
    if provider == "gemini":
        settings.require("gemini_api_key")
        return GeminiProvider(
            api_key=settings.gemini_api_key, model=model or _CHAT_PROVIDERS["gemini"]
        )
    raise ValueError(f"알 수 없는 provider: {provider}")


def build_embedder(
    settings: Settings,
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER,
    task_type: str = "RETRIEVAL_QUERY",
) -> Any:
    """선택한 Provider의 임베딩 구현체를 생성한다.

    Args:
        settings: 비밀값.
        embedding_provider: 'gemini' 또는 'openai'.
        task_type: Gemini 전용 — 'RETRIEVAL_QUERY'(질의) 또는
            'RETRIEVAL_DOCUMENT'(문서 적재). OpenAI는 무시.

    Returns:
        EmbeddingProvider 인스턴스.

    Raises:
        ValueError: 알 수 없는 embedding_provider.
    """
    if embedding_provider == "gemini":
        settings.require("gemini_api_key")
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key, task_type=task_type
        )
    if embedding_provider == "openai":
        settings.require("openai_api_key")
        return OpenAIEmbeddingProvider(api_key=settings.openai_api_key)
    raise ValueError(f"알 수 없는 embedding_provider: {embedding_provider}")


def build_components(
    settings: Settings,
    provider: str = "openrouter",
    chat_model: str | None = None,
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER,
) -> Components:
    """설정으로부터 공유 구성 요소를 조립한다.

    Args:
        settings: 비밀값(임베딩/supabase/cohere/챗 키).
        provider: 챗 Provider 선택.
        chat_model: 챗 모델 오버라이드.
        embedding_provider: 임베딩 Provider 선택(기본 gemini).

    Returns:
        Components.
    """
    settings.require("supabase_url", "supabase_service_key")
    # 질의 임베딩(RETRIEVAL_QUERY) — 문서는 적재 시 RETRIEVAL_DOCUMENT로 임베딩됨
    embedder = build_embedder(settings, embedding_provider, task_type="RETRIEVAL_QUERY")
    store = SupabaseVectorStore(
        url=settings.supabase_url, service_key=settings.supabase_service_key
    )
    chat = build_chat(settings, provider, chat_model)
    settings.require("cohere_api_key")
    reranker = CohereReranker(api_key=settings.cohere_api_key)
    return Components(
        embedder=embedder,
        store=store,
        chat=chat,
        reranker=reranker,
        chat_model=chat.model,
        rerank_model=reranker.model,
        embedding_model=embedder.model,
    )


def build_pipelines(
    components: Components, doc_id: str | None = None, top_k: int = 5
) -> dict[str, Any]:
    """공유 구성 요소로 3개 파이프라인을 조립한다.

    Args:
        components: 공유 구성 요소.
        doc_id: 특정 문서로 검색 제한.
        top_k: 최종 문맥 개수(공정 비교 동일값).

    Returns:
        {'naive': ..., 'advanced': ..., 'modular': ...}
    """
    c = components
    return {
        "naive": NaiveRAG(
            embedder=c.embedder, store=c.store, chat=c.chat, top_k=top_k, doc_id=doc_id
        ),
        "advanced": AdvancedRAG(
            embedder=c.embedder, store=c.store, chat=c.chat, reranker=c.reranker,
            top_k=top_k, doc_id=doc_id,
        ),
        "modular": ModularRAG(
            embedder=c.embedder, store=c.store, chat=c.chat, reranker=c.reranker,
            router=QueryRouter(c.chat), top_k=top_k, doc_id=doc_id,
        ),
    }
