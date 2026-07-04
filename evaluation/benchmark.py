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


def build_doc_key_map(documents: list[dict]) -> dict[str, str]:
    """rag_documents 행 목록에서 doc_id → 문서 단축키 매핑을 만든다.

    여러 문서가 공존하면 조번호가 문서 간에 겹칠 수 있어(예: 법률/시행령
    모두 "제1조") 평가 시 문서 단위로 구분해야 한다. 파일명에 "시행규칙"/
    "시행령"이 포함되면 해당 종류로, 그 외에는 "법률"로 분류한다
    (국가계약법령 3종 기준 — 다른 문서 조합을 쓰면 이 규칙을 조정할 것).

    Args:
        documents: SupabaseVectorStore.list_documents() 반환값.

    Returns:
        doc_id → "법률"/"시행령"/"시행규칙" 매핑.
    """
    key_map: dict[str, str] = {}
    for doc in documents:
        filename = doc.get("source_filename") or ""
        if "시행규칙" in filename:
            key = "시행규칙"
        elif "시행령" in filename:
            key = "시행령"
        else:
            key = "법률"
        key_map[doc["doc_id"]] = key
    return key_map


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
