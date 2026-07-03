# file: tests/test_retry_util.py
"""retry_util 테스트 — 일시 오류(429/503) 재시도 검증."""

from __future__ import annotations

import pytest

import retry_util


def test_is_retryable_covers_transient() -> None:
    assert retry_util.is_retryable(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert retry_util.is_retryable(RuntimeError("503 UNAVAILABLE high demand"))
    assert retry_util.is_retryable(RuntimeError("502 Bad Gateway"))
    assert not retry_util.is_retryable(RuntimeError("401 Unauthorized"))
    assert not retry_util.is_retryable(ValueError("잘못된 입력"))


def test_retry_succeeds_after_transient(monkeypatch) -> None:
    monkeypatch.setattr("retry_util.time.sleep", lambda s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("503 UNAVAILABLE")
        return "ok"

    assert retry_util.retry_call(flaky, max_retries=5) == "ok"
    assert calls["n"] == 3


def test_retry_reraises_non_retryable(monkeypatch) -> None:
    monkeypatch.setattr("retry_util.time.sleep", lambda s: None)

    def auth_error():
        raise RuntimeError("401 Unauthorized")

    with pytest.raises(RuntimeError, match="401"):
        retry_util.retry_call(auth_error, max_retries=5)


def test_retry_exhausts(monkeypatch) -> None:
    monkeypatch.setattr("retry_util.time.sleep", lambda s: None)

    def always_503():
        raise RuntimeError("503 high demand")

    with pytest.raises(RuntimeError, match="503"):
        retry_util.retry_call(always_503, max_retries=3)
