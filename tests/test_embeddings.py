# file: tests/test_embeddings.py
"""임베딩 Provider 테스트 — 가짜 클라이언트로 로직·재시도 검증."""

from __future__ import annotations

import pytest

from embeddings import GeminiEmbeddingProvider, OpenAIEmbeddingProvider


# ── OpenAI ────────────────────────────────────────────────────
class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = self

    def create(self, model, input, dimensions):
        class _Usage:
            total_tokens = 10 * len(input)

        class _Item:
            def __init__(self, i): self.embedding = [float(i)] * dimensions

        class _Resp:
            data = [_Item(i) for i in range(len(input))]
            usage = _Usage()

        return _Resp()


def test_openai_embed_batches_and_tracks_tokens() -> None:
    provider = OpenAIEmbeddingProvider(
        api_key="x", dimension=3, batch_size=2, client=_FakeOpenAIClient()
    )
    vecs = provider.embed(["a", "b", "c"])
    assert len(vecs) == 3
    assert all(len(v) == 3 for v in vecs)
    assert provider.total_tokens == 30  # 3건 x 10


# ── Gemini ────────────────────────────────────────────────────
class _FakeEmbedding:
    def __init__(self, dim): self.values = [0.1] * dim


class _FakeGeminiModels:
    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.calls = 0

    def embed_content(self, model, contents, config):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

        class _Resp:
            embeddings = [_FakeEmbedding(config.output_dimensionality) for _ in contents]

        return _Resp()


class _FakeGeminiClient:
    def __init__(self, fail_times=0):
        self.models = _FakeGeminiModels(fail_times)


def test_gemini_embed_returns_vectors() -> None:
    client = _FakeGeminiClient()
    provider = GeminiEmbeddingProvider(
        api_key="x", dimension=1536, batch_size=2, client=client
    )
    vecs = provider.embed(["a", "b", "c"])
    assert len(vecs) == 3
    assert all(len(v) == 1536 for v in vecs)
    assert client.models.calls == 2  # 3건을 2건+1건 배치로


def test_gemini_retries_on_rate_limit(monkeypatch) -> None:
    monkeypatch.setattr("retry_util.time.sleep", lambda s: None)  # 대기 스킵
    client = _FakeGeminiClient(fail_times=2)  # 2회 429 후 성공
    provider = GeminiEmbeddingProvider(
        api_key="x", batch_size=10, client=client, max_retries=4
    )
    vecs = provider.embed(["a"])
    assert len(vecs) == 1
    assert client.models.calls == 3  # 2회 실패 + 1회 성공


def test_gemini_reraises_after_max_retries(monkeypatch) -> None:
    monkeypatch.setattr("retry_util.time.sleep", lambda s: None)
    client = _FakeGeminiClient(fail_times=10)
    provider = GeminiEmbeddingProvider(api_key="x", client=client, max_retries=3)
    with pytest.raises(RuntimeError):
        provider.embed(["a"])
