# file: evaluation/benchmark.py
"""벤치마크 QA 세트 로딩.

골드 라벨은 조번호(article_no) 또는 별표(별표N) 문자열.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_QA_PATH = Path(__file__).resolve().parents[1] / "data" / "benchmark_qa.json"


@dataclass
class QAItem:
    """벤치마크 질의 1건.

    Attributes:
        id: 질의 식별자.
        question: 질문 텍스트.
        gold: 정답 라벨 집합(조번호/별표).
        category: 질의 유형(semantic/table/direct).
        style: 질문 문체(formal/colloquial/direct).
    """

    id: str
    question: str
    gold: set[str]
    category: str = ""
    style: str = ""


def load_benchmark(path: str | Path | None = None) -> list[QAItem]:
    """QA 세트 JSON을 로드해 QAItem 목록으로 반환한다.

    Args:
        path: QA JSON 경로(미지정 시 data/benchmark_qa.json).

    Returns:
        QAItem 목록.

    Raises:
        FileNotFoundError: 파일이 없을 때.
    """
    path = Path(path) if path else DEFAULT_QA_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        QAItem(
            id=item["id"],
            question=item["question"],
            gold=set(item["gold"]),
            category=item.get("category", ""),
            style=item.get("style", ""),
        )
        for item in data["items"]
    ]
