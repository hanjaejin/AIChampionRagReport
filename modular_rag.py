# file: modular_rag.py
"""Modular RAG — 라우팅 + 하이브리드 검색 + 조건부 인접 청크 확장.

Naive/Advanced 대비 모듈 조합형:
    1. 라우팅(2단): 조번호/별표 → 직접 조회, 표 키워드 → 표 검색, 그 외 → 하이브리드
    2. 하이브리드 검색: BM25(tsvector) + 벡터를 RRF로 융합
    3. Cohere Rerank로 정밀 재정렬(직접 조회 경로는 생략)
    4. 조건부 인접 청크 확장: 최상위 청크가 분할 청크이거나 참조 표현을 포함하면
       chunk_index ±1 이웃을 직접 조회해 문맥 보강(최종 예산 top_k 유지)

reranker/rewriter/router 는 주입받아 재사용한다. 답변 프롬프트는 공유(prompts.py).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Protocol

import prompts
from naive_rag import RagAnswer
from reranker import Reranker
from router import QueryRouter, Route

logger = logging.getLogger(__name__)

# 인접 확장 트리거: 주변 조문을 참조하는 표현
_REFERENCE_RE = re.compile(r"전조|전항|다음\s*각\s*[호항]|제\d+항에\s*따라|제\d+호에\s*따라")


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
    def get_by_article(self, article_no: str, doc_id: str | None = ...) -> list[dict]: ...
    def match(self, query_embedding: list[float], match_count: int = ...,
              doc_id: str | None = ..., content_type: str | None = ...) -> list[dict]: ...
    def hybrid_search(self, query_text: str, query_embedding: list[float],
                      match_count: int = ..., doc_id: str | None = ...) -> list[dict]: ...
    def get_adjacent(self, doc_id: str, from_index: int, to_index: int) -> list[dict]: ...


class _Chat(Protocol):
    model: str

    def complete(self, user: str, system: str | None = ..., temperature: float = ...,
                 max_tokens: int = ...) -> Any: ...


class ModularRAG:
    """모듈 조합형 RAG 파이프라인.

    Args:
        embedder: 질문 임베딩 Provider.
        store: 검색 스토어(직접 조회/하이브리드/인접 지원).
        chat: 답변 생성 챗 Provider.
        reranker: 재정렬기.
        router: 질의 라우터(미지정 시 chat 기반 2단 라우터).
        retrieve_k: 하이브리드/표 검색 회수 개수.
        top_k: 최종 문맥 개수(공정 비교 기본 5).
        expand_adjacent: 조건부 인접 청크 확장 사용 여부.
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
        router: QueryRouter | None = None,
        retrieve_k: int = 20,
        top_k: int = 5,
        expand_adjacent: bool = True,
        doc_id: str | None = None,
        doc_key_map: dict[str, str] | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._chat = chat
        self._reranker = reranker
        self._router = router or QueryRouter(chat)
        self._retrieve_k = retrieve_k
        self._top_k = top_k
        self._expand = expand_adjacent
        self._doc_id = doc_id
        self._doc_key_map = doc_key_map

    def answer(self, question: str) -> RagAnswer:
        """라우팅→검색→(재정렬)→(인접 확장)→생성으로 답변한다.

        Args:
            question: 사용자 질문.

        Returns:
            답변·근거 문맥·토큰(라우팅+생성 합)·시간을 담은 RagAnswer.
        """
        start = time.perf_counter()
        trace: dict[str, Any] = {}

        decision = self._router.route(question)
        trace["route"] = decision.route.value
        trace["route_tier"] = decision.tier

        contexts = self._retrieve(question, decision, trace)
        contexts = contexts[: self._top_k]

        if self._expand:
            contexts = self._maybe_expand(contexts, trace)

        gen = self._chat.complete(
            user=prompts.build_answer_prompt(question, contexts),
            system=prompts.ANSWER_SYSTEM_PROMPT,
            temperature=0.0,
        )

        return RagAnswer(
            question=question,
            answer=gen.text,
            contexts=contexts,
            input_tokens=decision.input_tokens + gen.input_tokens,
            output_tokens=decision.output_tokens + gen.output_tokens,
            model=gen.model,
            elapsed_sec=time.perf_counter() - start,
            pipeline="modular",
            trace=trace,
        )

    # ------------------------------------------------------------------
    # 경로별 검색
    # ------------------------------------------------------------------
    def _retrieve(
        self, question: str, decision: Any, trace: dict
    ) -> list[dict]:
        if decision.route == Route.DIRECT:
            hits = self._direct_lookup(decision)
            if hits:
                trace["candidate_labels"] = [_candidate_label(c, self._doc_key_map) for c in hits]
                return hits
            trace["direct_fallback"] = True  # 직접 조회 실패 → 하이브리드 폴백

        if decision.route == Route.TABLE:
            query_vec = self._embedder.embed([question])[0]
            candidates = self._store.match(
                query_vec, match_count=self._retrieve_k,
                doc_id=self._doc_id, content_type="table",
            )
        else:
            # SEMANTIC(또는 DIRECT 폴백): 하이브리드 검색
            query_vec = self._embedder.embed([question])[0]
            candidates = self._store.hybrid_search(
                query_text=question, query_embedding=query_vec,
                match_count=self._retrieve_k, doc_id=self._doc_id,
            )
        trace["candidate_labels"] = [_candidate_label(c, self._doc_key_map) for c in candidates]
        return self._rerank(question, candidates)

    def _direct_lookup(self, decision: Any) -> list[dict]:
        """조번호/별표번호로 청크를 직접 조회한다(rerank 불필요)."""
        if decision.article_no:
            return self._store.get_by_article(decision.article_no, doc_id=self._doc_id)
        if decision.annex_no is not None:
            query_vec = self._embedder.embed([f"별표 {decision.annex_no}"])[0]
            tables = self._store.match(
                query_vec, match_count=self._retrieve_k,
                doc_id=self._doc_id, content_type="table",
            )
            return [t for t in tables if t.get("annex_no") == decision.annex_no]
        return []

    def _rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        if not candidates:
            return []
        docs = [c.get("content", "") for c in candidates]
        results = self._reranker.rerank(query, docs, top_n=len(docs))
        ordered = []
        for item in results:
            chunk = dict(candidates[item.index])
            chunk["rerank_score"] = item.score
            ordered.append(chunk)
        return ordered

    # ------------------------------------------------------------------
    # 조건부 인접 청크 확장 (Phase 1 설계 2-4)
    # ------------------------------------------------------------------
    def _maybe_expand(self, contexts: list[dict], trace: dict) -> list[dict]:
        """최상위 청크가 참조 표현/분할 청크면 이웃을 가져와 예산 내로 재구성한다."""
        if not contexts:
            return contexts
        top = contexts[0]
        content = top.get("content", "")
        is_split = bool(top.get("clause_range"))
        has_reference = bool(_REFERENCE_RE.search(content))
        if not (is_split or has_reference):
            return contexts

        doc_id = top.get("doc_id")
        idx = top.get("chunk_index")
        if doc_id is None or idx is None:
            return contexts

        neighbors = self._store.get_adjacent(doc_id, max(0, idx - 1), idx + 1)
        seen = {c.get("chunk_index") for c in contexts}
        extra = [n for n in neighbors if n.get("chunk_index") not in seen]
        if not extra:
            return contexts

        # 예산 유지: rerank 상위(top_k - 추가분) + 이웃, chunk 순서 보존
        keep = self._top_k - len(extra)
        merged = contexts[: max(1, keep)] + extra
        merged = merged[: self._top_k]
        trace["expanded"] = True
        trace["expanded_neighbors"] = len(extra)
        logger.info("인접 청크 확장: 이웃 %d개 추가", len(extra))
        return merged
