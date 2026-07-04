# file: tests/test_advanced_rag.py
"""advanced_rag + query_rewriter + reranker(reorder) 테스트 (가짜 의존성)."""

from __future__ import annotations

from advanced_rag import AdvancedRAG
from chat_providers import ChatResult
from query_rewriter import QueryRewriter
from reranker import RerankResult


class FakeEmbedder:
    model = "fake-embed"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class FakeStore:
    """20개 후보를 돌려주고 match_count를 기록."""

    def __init__(self) -> None:
        self.last_match_count: int | None = None
        # 의도적으로 관련 낮은 것이 앞에 오도록 구성(rerank가 재정렬해야 함)
        self.candidates = [
            {"content": f"조문{i} 내용", "article_no": f"제{i}조",
             "article_title": f"제목{i}", "content_type": "article", "doc_id": "doc-x"}
            for i in range(20)
        ]

    def match(self, query_embedding, match_count=5, doc_id=None, content_type=None):
        self.last_match_count = match_count
        return self.candidates[:match_count]


class FakeReranker:
    """마지막 후보일수록 높은 점수를 주도록 뒤집어 재정렬(재정렬 검증용)."""

    def __init__(self) -> None:
        self.last_docs: list[str] | None = None

    def rerank(self, query, documents, top_n):
        self.last_docs = documents
        n = len(documents)
        ordered = sorted(
            (RerankResult(index=i, score=(i + 1) / n) for i in range(n)),
            key=lambda r: r.score, reverse=True,
        )
        return ordered[:top_n]


class FakeChat:
    model = "fake-chat"

    def __init__(self, text="답변입니다.") -> None:
        self._text = text
        self.last_user: str | None = None
        self.calls = 0

    def complete(self, user, system=None, temperature=0.0, max_tokens=1024):
        self.calls += 1
        self.last_user = user
        return ChatResult(text=self._text, input_tokens=50, output_tokens=10,
                          model=self.model)


# ── query_rewriter ────────────────────────────────────────────
def test_rewriter_returns_rewritten_query() -> None:
    chat = FakeChat(text="개인정보 유출 시 통지 및 신고 의무")
    result = QueryRewriter(chat).rewrite("유출되면 뭐해야 돼?")
    assert result.rewritten == "개인정보 유출 시 통지 및 신고 의무"
    assert result.original == "유출되면 뭐해야 돼?"
    assert result.input_tokens == 50


def test_rewriter_falls_back_to_original_on_empty() -> None:
    result = QueryRewriter(FakeChat(text="   ")).rewrite("원 질문")
    assert result.rewritten == "원 질문"


# ── advanced_rag ──────────────────────────────────────────────
def _make(**kwargs):
    store, chat, reranker = FakeStore(), FakeChat(), FakeReranker()
    rag = AdvancedRAG(
        embedder=FakeEmbedder(), store=store, chat=chat, reranker=reranker,
        rewriter=QueryRewriter(FakeChat(text="재작성된 질의")),
        retrieve_k=20, top_k=5, **kwargs,
    )
    return rag, store, chat, reranker


def test_retrieves_wide_then_reranks_narrow() -> None:
    rag, store, _, reranker = _make()
    result = rag.answer("질문")
    assert store.last_match_count == 20          # 넓게 회수
    assert len(result.contexts) == 5             # rerank로 좁힘
    assert reranker.last_docs is not None
    assert len(reranker.last_docs) == 20         # 20개를 rerank에 넘김


def test_candidate_labels_prefixed_with_doc_key_map() -> None:
    """다중 문서 평가 시 candidate_labels가 문서 단축키로 접두된다."""
    rag, _, _, _ = _make(doc_key_map={"doc-x": "법률"})
    result = rag.answer("질문")
    assert all(label.startswith("법률:") for label in result.trace["candidate_labels"])


def test_rerank_reorders_context() -> None:
    rag, _, chat, _ = _make()
    result = rag.answer("질문")
    # FakeReranker는 마지막 후보(제19조)를 최상위로 올린다
    assert result.contexts[0]["article_no"] == "제19조"


def test_min_score_filtering() -> None:
    # 임계치 0.9 이상만 통과 → 상위 소수만 남아야 함(top_k보다 적을 수 있음)
    rag, _, _, _ = _make(min_rerank_score=0.9)
    result = rag.answer("질문")
    assert all(c["rerank_score"] >= 0.9 for c in result.contexts)
    assert len(result.contexts) < 5


def test_tokens_sum_rewrite_and_generation() -> None:
    rag, _, _, _ = _make()
    result = rag.answer("질문")
    # 재작성(50/10) + 생성(50/10) 합산
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert result.pipeline == "advanced"
    assert "rewritten_query" in result.trace


def test_generation_uses_reranked_context() -> None:
    rag, _, chat, _ = _make()
    rag.answer("질문")
    # 생성 프롬프트에 최상위 재정렬 문맥(제19조)이 포함되어야 함
    assert "조문19 내용" in chat.last_user
