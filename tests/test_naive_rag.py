# file: tests/test_naive_rag.py
"""naive_rag 테스트 — 가짜 임베더/스토어/챗으로 retrieve→generate 흐름 검증."""

from __future__ import annotations

from chat_providers import ChatResult
from naive_rag import NaiveRAG


class FakeEmbedder:
    model = "fake-embed"

    def __init__(self) -> None:
        self.total_tokens = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.total_tokens += 1
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class FakeStore:
    """고정 청크를 돌려주고 호출 인자를 기록하는 가짜 스토어."""

    def __init__(self) -> None:
        self.last_match_count: int | None = None
        self.chunks = [
            {"content": "제35조 내용: 유출 시 신고한다.", "article_no": "제35조",
             "article_title": "개인정보 유출 등의 신고", "content_type": "article"},
            {"content": "제33조 내용: 통지 시기.", "article_no": "제33조",
             "article_title": "유출 통지", "content_type": "article"},
        ]

    def match(self, query_embedding, match_count=5, doc_id=None, content_type=None):
        self.last_match_count = match_count
        return self.chunks[:match_count]


class FakeChat:
    """받은 프롬프트를 기록하고 고정 답변을 돌려주는 가짜 챗."""

    model = "fake-chat"

    def __init__(self) -> None:
        self.last_system: str | None = None
        self.last_user: str | None = None

    def complete(self, user, system=None, temperature=0.0, max_tokens=1024):
        self.last_system = system
        self.last_user = user
        return ChatResult(text="제35조에 따라 신고합니다.", input_tokens=100,
                          output_tokens=20, model=self.model)


def _make(top_k: int = 5) -> tuple[NaiveRAG, FakeStore, FakeChat]:
    store, chat = FakeStore(), FakeChat()
    rag = NaiveRAG(embedder=FakeEmbedder(), store=store, chat=chat, top_k=top_k)
    return rag, store, chat


def test_retrieves_top_k() -> None:
    rag, store, _ = _make(top_k=2)
    rag.answer("유출되면 어떻게 신고하나요?")
    assert store.last_match_count == 2


def test_context_passed_to_chat() -> None:
    rag, _, chat = _make()
    rag.answer("유출 신고 방법은?")
    # 검색된 조문 내용이 사용자 프롬프트(문맥)에 포함되어야 한다
    assert "제35조 내용" in chat.last_user
    assert "유출 신고 방법은?" in chat.last_user
    # 시스템 프롬프트가 전달되어야 한다
    assert chat.last_system is not None


def test_answer_fields_populated() -> None:
    rag, _, _ = _make()
    result = rag.answer("유출 신고 방법은?")
    assert result.answer == "제35조에 따라 신고합니다."
    assert result.question == "유출 신고 방법은?"
    assert len(result.contexts) == 2
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert result.model == "fake-chat"
    assert result.elapsed_sec >= 0.0


def test_temperature_zero_for_fair_comparison() -> None:
    """비교 공정성: 기본 temperature=0.0 (결정적 생성)."""
    captured = {}

    class RecordingChat(FakeChat):
        def complete(self, user, system=None, temperature=0.0, max_tokens=1024):
            captured["temperature"] = temperature
            return super().complete(user, system, temperature, max_tokens)

    store, chat = FakeStore(), RecordingChat()
    NaiveRAG(embedder=FakeEmbedder(), store=store, chat=chat).answer("질문")
    assert captured["temperature"] == 0.0
