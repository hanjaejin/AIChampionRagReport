# file: tests/test_config.py
"""config 모듈 테스트 — 비밀값 우선순위(UI > st.secrets > .env) 검증."""

from __future__ import annotations

import config


def test_override_wins_over_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "env-value")
    got = config.get_secret("OPENAI_API_KEY", overrides={"OPENAI_API_KEY": "ui-value"})
    assert got == "ui-value"


def test_env_used_when_no_override(monkeypatch) -> None:
    monkeypatch.setenv("SOME_TEST_KEY", "env-value")
    assert config.get_secret("SOME_TEST_KEY") == "env-value"


def test_missing_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("DEFINITELY_MISSING_KEY", raising=False)
    assert config.get_secret("DEFINITELY_MISSING_KEY") is None


def test_empty_override_falls_back_to_env(monkeypatch) -> None:
    """UI 입력이 빈 문자열이면 무시하고 env로 폴백한다."""
    monkeypatch.setenv("OPENAI_API_KEY", "env-value")
    got = config.get_secret("OPENAI_API_KEY", overrides={"OPENAI_API_KEY": ""})
    assert got == "env-value"


def test_load_settings_maps_fields(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    settings = config.load_settings(overrides={"COHERE_API_KEY": "ui-cohere"})
    assert settings.supabase_url == "https://x.supabase.co"
    assert settings.cohere_api_key == "ui-cohere"


def test_require_raises_on_missing(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    settings = config.load_settings()
    try:
        settings.require("openrouter_api_key")
    except config.MissingSecretError as exc:
        assert "openrouter_api_key" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("MissingSecretError가 발생해야 한다")
