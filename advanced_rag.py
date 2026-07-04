# file: advanced_rag.py
"""Advanced RAG — 검색 전/후 최적화 파이프라인.

Naive 대비 3가지를 추가한다:
    1. (검색 전) 쿼리 재작성 — 구어체→규정 용어, 동의어 확장으로 재현율↑
    2. 넓게 회수(top-20) 후 Cohere Rerank로 정밀 재정렬(top-5)
    3. (검색 후) 점수 임계치 필터링 — 관련도 낮은 문맥 제거(압축)

embedder/store/chat/reranker/rewriter 를 주입받아 구체 구현을 몰라도 되게 한다.
답변 프롬프트는 Naive와 동일한 prompts.py 를 공유한다(공정 비교).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

import prompts
from naive_rag import RagAnswer
from query_rewriter import QueryRewriter
from reranker import Reranker

logger = logging.getLogger(__name__)


def _candidate_label(chunk: dict, doc_key_map: dict[str, str] | None = None) -> str:
    """오류 분석용 후보 라벨(조번호 우선, 없으면 별표번호).

    다중 문서 평가 시 doc_key_map(doc_id → 문서 단축키)이 주어지면 조번호
    앞에 문서 키를 붙여("법률:제1조") 문서 간 조번호 충돌을 방지한다.
    """
    if chunk.get("article_no"):
        base = str(chunk["article_no"])
    elif chunk.get("annex_no") is not None:
        base = f"별표{chunk['annex_no']}"
    else:
        return ""
    if doc_key_map and chunk.get("doc_id") in doc_key_map:
        return f"{doc_key_map[chunk['doc_id']]}:{base}"
    return base


class _Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class _Store(Protocol):
    def match(
        self, query_embedding: list[float], match_count: int = 5,
        doc_id: str | None = None, content_type: str | None = None,
    ) -> list[dict]: ...


class _Chat(Protocol):
    model: str

    def complete(self, user: str, system: str | None = ..., temperature: float = ...,
                 max_tokens: int = ...) -> Any: ...


class AdvancedRAG:
    """검색 전/후 최적화를 적용한 RAG 파이프라인.

    Args:
        embedder: 질문 임베딩 Provider.
        store: 벡터 검색 스토어.
        chat: 답변 생성 챗 Provider.
        reranker: 재정렬기(Cohere 등).
        rewriter: 쿼리 재작성기(미지정 시 chat으로 생성).
        retrieve_k: 벡터 검색 회수 개수(넓게, 기본 20).
        top_k: rerank 후 최종 문맥 개수(기본 5).
        min_rerank_score: 이 점수 미만 문맥 제거(0.0이면 필터 없음).
        doc_id: 특정 문서로 검색 제한.
        doc_key_map: doc_id → 문서 단축키 매핑(다중 문서 평가 시 candidate_labels 충돌 방지, 선택).
    """

    def __init__(
        self,
        *,
        embedder: _Embedder,
        store: _Store,
        chat: _Chat,
        reranker: Reranker,
        rewriter: QueryRewriter | None = None,
        retrieve_k: int = 20,
        top_k: int = 5,
        min_rerank_score: float = 0.0,
        doc_id: str | None = None,
        doc_key_map: dict[str, str] | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._chat = chat
        self._reranker = reranker
        self._rewriter = rewriter or QueryRewriter(chat)
        self._retrieve_k = retrieve_k
        self._top_k = top_k
        self._min_score = min_rerank_score
        self._doc_id = doc_id
        self._doc_key_map = doc_key_map

    def answer(self, question: str) -> RagAnswer:
        """쿼리 재작성→넓은 검색→rerank→필터→생성으로 답변한다.

        Args:
            question: 사용자 질문.

        Returns:
            답변·근거 문맥·토큰(재작성+생성 합)·시간을 담은 RagAnswer.
        """
        start = time.perf_counter()

        # 1. 검색 전: 쿼리 재작성
        rewrite = self._rewriter.rewrite(question)
        logger.info("쿼리 재작성: %r → %r", question, rewrite.rewritten)

        # 2. 넓은 벡터 검색
        query_vec = self._embedder.embed([rewrite.rewritten])[0]
        candidates = self._store.match(
            query_vec, match_count=self._retrieve_k, doc_id=self._doc_id
        )

        # 3. Cohere Rerank (원 질문 기준 — 사용자 의도 보존)
        reranked = self._rerank(question, candidates)

        # 4. 검색 후: 점수 임계치 필터링(압축)
        contexts = [c for c in reranked if c["rerank_score"] >= self._min_score][
            : self._top_k
        ]

        # 5. 생성 (공유 프롬프트)
        gen = self._chat.complete(
            user=prompts.build_answer_prompt(question, contexts),
            system=prompts.ANSWER_SYSTEM_PROMPT,
            temperature=0.0,
        )

        return RagAnswer(
            question=question,
            answer=gen.text,
            contexts=contexts,
            input_tokens=rewrite.input_tokens + gen.input_tokens,
            output_tokens=rewrite.output_tokens + gen.output_tokens,
            model=gen.model,
            elapsed_sec=time.perf_counter() - start,
            pipeline="advanced",
            trace={
                "rewritten_query": rewrite.rewritten,
                "retrieved": len(candidates),
                "after_rerank": len(reranked),
                "after_filter": len(contexts),
                "candidate_labels": [_candidate_label(c, self._doc_key_map) for c in candidates],
                "rewrite_tokens": [rewrite.input_tokens, rewrite.output_tokens],
                "generation_tokens": [gen.input_tokens, gen.output_tokens],
            },
        )

    def _rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """후보를 rerank 점수로 재정렬하고 각 dict에 rerank_score를 부여한다."""
        if not candidates:
            return []
        docs = [c.get("content", "") for c in candidates]
        results = self._reranker.rerank(query, docs, top_n=len(docs))
        ordered: list[dict] = []
        for item in results:
            chunk = dict(candidates[item.index])
            chunk["rerank_score"] = item.score
            ordered.append(chunk)
        return ordered
