# file: tests/test_benchmark.py
"""evaluation.benchmark 테스트 — QA 로딩 및 doc_key_map 생성."""

from __future__ import annotations

from evaluation.benchmark import build_doc_key_map


def test_build_doc_key_map_classifies_by_filename() -> None:
    documents = [
        {"doc_id": "a", "source_filename": "국가를당사자로하는계약에관한법률_제21418호_20260611.md"},
        {"doc_id": "b", "source_filename": "국가를당사자로하는계약에관한법률시행령_대통령령_제36338호_20260603.md"},
        {"doc_id": "c", "source_filename": "국가를당사자로하는계약에관한법률시행규칙_재정경제부령_제00001호_20260102.md"},
    ]
    key_map = build_doc_key_map(documents)
    assert key_map == {"a": "법률", "b": "시행령", "c": "시행규칙"}


def test_build_doc_key_map_empty_list() -> None:
    assert build_doc_key_map([]) == {}
