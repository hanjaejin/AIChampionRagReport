# file: tests/test_modular_rag.py
"""router + modular_rag 테스트 (가짜 의존성)."""

from __future__ import annotations

from chat_providers import ChatResult
from modular_rag import ModularRAG
from reranker import RerankResult
from router import QueryRouter, Route


# ── 라우터 ────────────────────────────────────────────────────
def test_router_direct_by_article_number() -> None:
    d = QueryRouter().route("제36조 내용 알려줘")
    assert d.route == Route.DIRECT
    assert d.article_no == "제36조"
    assert d.tier == "rule"


def test_router_direct_by_article_with_eui() -> None:
    d = QueryRouter().route("제35조의2는 무슨 내용이야?")
    assert d.route == Route.DIRECT
    assert d.article_no == "제35조의2"


def test_router_direct_by_annex() -> None:
    d = QueryRouter().route("별표 3 보여줘")
    assert d.route == Route.DIRECT
    assert d.annex_no == 3


def test_router_table_by_keyword() -> None:
    d = QueryRouter().route("파기 관리대장 서식이 궁금해")
    assert d.route == Route.TABLE
    assert d.tier == "rule"


def test_router_semantic_fallback_without_chat() -> None:
    d = QueryRouter().route("개인정보 보호책임자의 역할은?")
    assert d.route == Route.SEMANTIC


def test_router_llm_tier_used_when_rule_misses() -> None:
    class FakeChat:
        def complete(self, user, system=None, temperature=0.0, max_tokens=1024):
            return ChatResult(text="TABLE", input_tokens=10, output_tokens=1, model="f")

    d = QueryRouter(FakeChat()).route("보유기간 얼마나 되는지 목록으로 보고싶어")
    assert d.route == Route.TABLE
    assert d.tier == "llm"
    assert d.input_tokens == 10


# ── Modular RAG ───────────────────────────────────────────────
class FakeEmbedder:
    def embed(self, texts): return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class FakeChat:
    model = "fake-chat"

    def __init__(self): self.last_user = None
    def complete(self, user, system=None, temperature=0.0, max_tokens=1024):
        self.last_user = user
        return ChatResult(text="답변", input_tokens=50, output_tokens=10, model=self.model)


class FakeReranker:
    def rerank(self, query, documents, top_n):
        return [RerankResult(index=i, score=1.0 - i * 0.1) for i in range(min(top_n, len(documents)))]


class RecordingStore:
    """어떤 검색 메서드가 호출됐는지 기록하는 가짜 스토어."""

    def __init__(self, article_hits=None):
        self.called = []
        self._article_hits = article_hits or []
        self._semantic = [
            {"content": f"의미청크{i}", "article_no": f"제{i}조", "chunk_index": i,
             "doc_id": "d1", "content_type": "article"} for i in range(20)
        ]
        self._tables = [
            {"content": f"표{i}", "annex_no": i, "chunk_index": 50 + i,
             "doc_id": "d1", "content_type": "table"} for i in range(5)
        ]

    def get_by_article(self, article_no, doc_id=None):
        self.called.append(("get_by_article", article_no))
        return self._article_hits

    def match(self, query_embedding, match_count=5, doc_id=None, content_type=None):
        self.called.append(("match", content_type))
        return self._tables[:match_count] if content_type == "table" else self._semantic[:match_count]

    def hybrid_search(self, query_text, query_embedding, match_count=5, doc_id=None):
        self.called.append(("hybrid_search", None))
        return self._semantic[:match_count]

    def get_adjacent(self, doc_id, from_index, to_index):
        self.called.append(("get_adjacent", (from_index, to_index)))
        return [{"content": f"이웃{i}", "article_no": f"제{i}조", "chunk_index": i,
                 "doc_id": doc_id, "content_type": "article"}
                for i in range(from_index, to_index + 1)]


def _make(store, **kwargs):
    return ModularRAG(
        embedder=FakeEmbedder(), store=store, chat=FakeChat(),
        reranker=FakeReranker(), router=QueryRouter(),
        retrieve_k=20, top_k=5, **kwargs,
    )


def test_direct_route_uses_article_lookup() -> None:
    hits = [{"content": "제36조 원문", "article_no": "제36조", "chunk_index": 5,
             "doc_id": "d1", "content_type": "article"}]
    store = RecordingStore(article_hits=hits)
    result = _make(store).answer("제36조 내용 알려줘")
    assert ("get_by_article", "제36조") in store.called
    assert result.trace["route"] == "direct"
    assert result.contexts[0]["article_no"] == "제36조"


def test_direct_route_falls_back_to_hybrid_when_not_found() -> None:
    store = RecordingStore(article_hits=[])  # 조문 없음
    result = _make(store).answer("제999조 알려줘")
    assert any(c[0] == "hybrid_search" for c in store.called)  # 폴백
    assert result.trace.get("direct_fallback") is True


def test_table_route_filters_tables() -> None:
    store = RecordingStore()
    result = _make(store).answer("파기 관리대장 서식 보여줘")
    assert ("match", "table") in store.called
    assert result.trace["route"] == "table"


def test_semantic_route_uses_hybrid() -> None:
    store = RecordingStore()
    result = _make(store).answer("개인정보 보호책임자의 역할은?")
    assert any(c[0] == "hybrid_search" for c in store.called)
    assert result.trace["route"] == "semantic"


def test_candidate_labels_prefixed_with_doc_key_map() -> None:
    """다중 문서 평가 시 candidate_labels가 문서 단축키로 접두된다(SEMANTIC 경로)."""
    store = RecordingStore()
    result = _make(store, doc_key_map={"d1": "법률"}).answer("개인정보 보호책임자의 역할은?")
    assert all(label.startswith("법률:") for label in result.trace["candidate_labels"])


def test_direct_route_candidate_labels_prefixed_with_doc_key_map() -> None:
    """DIRECT 경로(get_by_article)도 doc_key_map으로 candidate_labels가 접두된다."""
    hits = [{"content": "제36조 원문", "article_no": "제36조", "chunk_index": 5,
             "doc_id": "d1", "content_type": "article"}]
    store = RecordingStore(article_hits=hits)
    result = _make(store, doc_key_map={"d1": "법률"}).answer("제36조 내용 알려줘")
    assert result.trace["candidate_labels"] == ["법률:제36조"]


def test_adjacent_expansion_triggers_on_reference_phrase() -> None:
    store = RecordingStore()
    store._semantic[0]["content"] = "전조의 규정에 따라 처리한다."  # 참조 표현
    store._semantic[0]["chunk_index"] = 10
    result = _make(store, expand_adjacent=True).answer("개인정보 보호책임자의 역할은?")
    assert any(c[0] == "get_adjacent" for c in store.called)
    assert result.trace.get("expanded") is True
    assert len(result.contexts) == 5  # 예산 유지


def test_no_adjacent_expansion_without_trigger() -> None:
    store = RecordingStore()  # 참조 표현 없음, 분할청크 아님
    _make(store, expand_adjacent=True).answer("개인정보 보호책임자의 역할은?")
    assert not any(c[0] == "get_adjacent" for c in store.called)
