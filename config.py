# file: config.py
"""비밀값(API 키·접속 정보) 로딩 모듈.

우선순위: UI 입력(overrides) > Streamlit secrets(st.secrets) > 환경변수(.env).
이 우선순위 덕분에 로컬 개발(.env)과 Streamlit Cloud(st.secrets),
그리고 사용자가 앱에서 직접 키를 입력하는 방식이 코드 수정 없이 모두 동작한다.

LLM 키(OpenAI·OpenRouter·Gemini·Cohere)는 앱에서 사용자가 입력하므로
overrides 로 주입되고, Supabase 접속 정보는 앱 소유자가 st.secrets/.env 로 관리한다.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 프로세스 시작 시 .env 를 os.environ 으로 로드(멱등). 실제 값은 환경변수로만 흐른다.
load_dotenv()

# 필드명(파이썬) → 환경변수명(대문자) 매핑
_FIELD_TO_ENV: dict[str, str] = {
    "openai_api_key": "OPENAI_API_KEY",
    "supabase_url": "SUPABASE_URL",
    "supabase_service_key": "SUPABASE_SERVICE_KEY",
    "cohere_api_key": "COHERE_API_KEY",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "gemini_api_key": "GEMINI_API_KEY",
}


class MissingSecretError(RuntimeError):
    """필수 비밀값이 어느 소스에도 없을 때 발생한다."""


def _from_streamlit_secrets(env_name: str) -> str | None:
    """Streamlit secrets에서 값을 조회한다. secrets가 없으면 조용히 None.

    Args:
        env_name: 환경변수 이름(= secrets 키).

    Returns:
        값 문자열 또는 None (streamlit 미설치·secrets 파일 부재 포함).
    """
    try:
        import streamlit as st

        value = st.secrets.get(env_name)  # secrets 파일 없으면 예외 가능
        return str(value) if value else None
    except Exception:  # noqa: BLE001 - secrets 부재는 정상 폴백 경로
        return None


def get_secret(env_name: str, overrides: dict[str, str] | None = None) -> str | None:
    """단일 비밀값을 우선순위(overrides > st.secrets > env)로 조회한다.

    Args:
        env_name: 환경변수 이름(예: "OPENAI_API_KEY").
        overrides: UI 입력 등 최우선 소스. 빈 문자열은 무시하고 폴백한다.

    Returns:
        비밀값 문자열, 없으면 None.
    """
    if overrides:
        candidate = overrides.get(env_name)
        if candidate:  # 빈 문자열/None 은 폴백
            return candidate
    secret = _from_streamlit_secrets(env_name)
    if secret:
        return secret
    return os.environ.get(env_name) or None


@dataclass(frozen=True)
class Settings:
    """애플리케이션 비밀값 묶음.

    Attributes:
        openai_api_key: OpenAI 임베딩 키.
        supabase_url: Supabase 프로젝트 URL.
        supabase_service_key: Supabase service_role 키.
        cohere_api_key: Cohere Rerank 키.
        openrouter_api_key: OpenRouter 챗 키.
        gemini_api_key: Google Gemini 챗 키.
    """

    openai_api_key: str | None
    supabase_url: str | None
    supabase_service_key: str | None
    cohere_api_key: str | None
    openrouter_api_key: str | None
    gemini_api_key: str | None

    def require(self, *field_names: str) -> None:
        """지정한 필드가 모두 채워졌는지 검증한다.

        Args:
            *field_names: 필수 필드명(예: "openai_api_key").

        Raises:
            MissingSecretError: 비어 있는 필드가 하나라도 있을 때.
        """
        missing = [name for name in field_names if not getattr(self, name)]
        if missing:
            raise MissingSecretError(
                "다음 필수 비밀값이 없습니다: "
                + ", ".join(missing)
                + ". .env 또는 앱 키 입력을 확인하세요."
            )


def load_settings(overrides: dict[str, str] | None = None) -> Settings:
    """모든 비밀값을 우선순위에 따라 로드해 Settings로 반환한다.

    Args:
        overrides: UI 입력 등 최우선 소스(환경변수명 → 값).

    Returns:
        채워진 Settings 인스턴스(없는 값은 None).
    """
    return Settings(
        **{
            field: get_secret(env_name, overrides)
            for field, env_name in _FIELD_TO_ENV.items()
        }
    )
