# file: retry_util.py
"""일시적 API 오류에 대한 공통 재시도 유틸.

레이트리밋(429)뿐 아니라 서버 과부하(503 UNAVAILABLE/overloaded), 일시적 5xx,
타임아웃 등 **재시도로 해결될 가능성이 높은 오류**에 지수 백오프로 재시도한다.
임베딩·rerank·챗 Provider가 공유한다.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 재시도 대상 오류의 문자열 표식(대소문자 무시)
_RETRYABLE_MARKERS = (
    "429",
    "rate limit",
    "too many",
    "resource_exhausted",
    "503",
    "500",
    "502",
    "504",
    "unavailable",
    "overloaded",
    "high demand",
    "temporarily",
    "timeout",
    "deadline",
    "try again",
)


def is_retryable(exc: Exception) -> bool:
    """예외 메시지에 재시도 가능 표식이 있는지 판별한다.

    Args:
        exc: 발생한 예외.

    Returns:
        재시도할 가치가 있으면 True.
    """
    text = str(exc).lower()
    return any(marker in text for marker in _RETRYABLE_MARKERS)


def retry_call(
    fn: Callable[[], T],
    *,
    max_retries: int = 4,
    base_delay: float = 2.0,
    what: str = "API 호출",
) -> T:
    """fn()을 호출하고, 일시적 오류면 지수 백오프로 재시도한다.

    Args:
        fn: 인자 없는 호출 가능 객체(실제 API 호출을 감쌈).
        max_retries: 최대 시도 횟수.
        base_delay: 첫 재시도 대기(초). 이후 2배씩 증가.
        what: 로그에 표시할 작업 이름.

    Returns:
        fn()의 반환값.

    Raises:
        Exception: 재시도 불가 오류이거나 최대 횟수를 소진한 경우 마지막 예외.
    """
    delay = base_delay
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 재시도 판단 후 재발생
            if attempt == max_retries - 1 or not is_retryable(exc):
                raise
            logger.warning(
                "%s 일시 오류(%s), %.0f초 후 재시도 (%d/%d)",
                what, type(exc).__name__, delay, attempt + 1, max_retries,
            )
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"{what} 재시도 소진")  # 도달 불가(방어)
