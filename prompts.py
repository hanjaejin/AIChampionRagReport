# file: prompts.py
"""3개 RAG 파이프라인이 공유하는 답변 생성 프롬프트.

공정 비교 원칙(Phase 1): 세 파이프라인은 동일한 답변 프롬프트 템플릿을 쓴다.
이 모듈에 프롬프트를 모아 파이프라인별로 임의 변형되지 않도록 강제한다.
"""

from __future__ import annotations

from typing import Any

# 규정 QA 어시스턴트 시스템 프롬프트
ANSWER_SYSTEM_PROMPT = (
    "당신은 대한민국 공공기관의 사내 규정 문서를 안내하는 정확한 AI 어시스턴트입니다.\n"
    "아래 [참고 문맥]에 제공된 조문/별표 내용에만 근거하여 한국어로 답변하세요.\n\n"
    "규칙:\n"
    "1. 반드시 참고 문맥에 있는 내용만 사용하고, 추측하거나 없는 내용을 지어내지 마세요.\n"
    "2. 답변 근거가 된 조문 번호(예: 제35조)나 별표 번호(예: 별표 1)를 문장에 명시하세요.\n"
    "3. 참고 문맥에서 답을 찾을 수 없으면 '제공된 규정에서 해당 내용을 찾을 수 없습니다'라고 답하세요.\n"
    "4. 삭제된 조문에 대한 질문이면 해당 조문이 삭제되었음을 알려주세요.\n"
    "5. 간결하고 명확하게, 필요하면 항목으로 나눠 설명하세요."
)


# 쿼리 재작성 시스템 프롬프트 (Advanced/Modular RAG)
REWRITE_SYSTEM_PROMPT = (
    "당신은 대한민국 공공기관 사내 규정 검색을 돕는 질의 재작성기입니다.\n"
    "사용자의 구어체·모호한 질문을 규정 문서(조/항/별표) 검색에 적합한 형태로 다시 씁니다.\n\n"
    "규칙:\n"
    "1. 규정 용어로 정규화하세요(예: '유출되면 뭐해야 돼' → '개인정보 유출 시 통지 및 신고 의무').\n"
    "2. 검색 재현율을 높이도록 핵심 동의어·상위 개념을 함께 넣으세요.\n"
    "3. 새로운 사실을 지어내지 말고, 질문의 의도를 보존하세요.\n"
    "4. 설명 없이 재작성된 검색 질의 한 줄만 출력하세요."
)


def build_rewrite_prompt(question: str) -> str:
    """쿼리 재작성용 사용자 프롬프트를 만든다.

    Args:
        question: 원 질문.

    Returns:
        재작성기에 전달할 사용자 메시지.
    """
    return f"원 질문: {question}\n\n재작성된 검색 질의:"


# 라우팅 분류 시스템 프롬프트 (Modular RAG 2단 라우팅의 LLM 폴백)
ROUTE_SYSTEM_PROMPT = (
    "당신은 규정 문서 질의를 검색 경로로 분류하는 분류기입니다.\n"
    "질문을 다음 두 유형 중 하나로만 분류하고, 라벨 한 단어만 출력하세요.\n\n"
    "- TABLE: 서식·양식·별표·대장·기준표 등 '표' 형태 자료를 찾는 질문\n"
    "- SEMANTIC: 그 외 조문 내용·의미를 묻는 일반 질문\n\n"
    "출력은 반드시 TABLE 또는 SEMANTIC 중 하나여야 합니다."
)


def build_route_prompt(question: str) -> str:
    """라우팅 분류용 사용자 프롬프트를 만든다.

    Args:
        question: 원 질문.

    Returns:
        분류기에 전달할 사용자 메시지.
    """
    return f"질문: {question}\n\n분류(TABLE 또는 SEMANTIC):"


# LLM 심판(faithfulness/correctness) 시스템 프롬프트
JUDGE_SYSTEM_PROMPT = (
    "당신은 규정 QA 답변을 평가하는 엄격한 심판입니다.\n"
    "주어진 [질문], [답변], [참고 문맥]을 보고 두 점수를 매기세요.\n\n"
    "- faithfulness(충실도): 답변의 모든 주장이 참고 문맥으로 뒷받침되는가? "
    "문맥에 없는 내용을 지어냈으면 낮게. (0.0~1.0)\n"
    "- correctness(정확성): 답변이 질문에 정확하고 충분히 답했는가? (0.0~1.0)\n\n"
    "반드시 아래 JSON 형식으로만 답하세요(설명 금지):\n"
    '{"faithfulness": 0.0, "correctness": 0.0, "rationale": "간단한 근거"}'
)


def build_judge_prompt(question: str, answer: str, chunks: list[dict[str, Any]]) -> str:
    """심판용 사용자 프롬프트를 만든다.

    Args:
        question: 원 질문.
        answer: 평가 대상 답변.
        chunks: 답변이 사용한 참고 문맥.

    Returns:
        심판 LLM에 전달할 사용자 메시지.
    """
    context = format_context(chunks) if chunks else "(문맥 없음)"
    return (
        f"[질문]\n{question}\n\n[답변]\n{answer}\n\n"
        f"[참고 문맥]\n{context}\n\n[평가 JSON]"
    )


def format_context(chunks: list[dict[str, Any]]) -> str:
    """검색된 청크 목록을 프롬프트용 문맥 문자열로 조립한다.

    Args:
        chunks: 검색 결과 청크 dict 목록. 각 dict는 최소 'content'를 포함하며
            'article_no', 'annex_no' 등 라벨 필드를 선택적으로 가진다.

    Returns:
        번호가 매겨진 문맥 블록 문자열.
    """
    blocks: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        label = _chunk_label(chunk)
        blocks.append(f"[문맥 {i}] {label}\n{chunk.get('content', '').strip()}")
    return "\n\n".join(blocks)


def _chunk_label(chunk: dict[str, Any]) -> str:
    """청크의 출처 라벨을 만든다 (예: '제35조(개인정보 유출 등의 신고)')."""
    if chunk.get("article_no"):
        title = chunk.get("article_title") or ""
        return f"{chunk['article_no']}({title})" if title else str(chunk["article_no"])
    if chunk.get("annex_no"):
        return f"별표 {chunk['annex_no']}"
    return "규정 본문"


def build_answer_prompt(question: str, chunks: list[dict[str, Any]]) -> str:
    """질문과 검색 문맥으로 사용자 프롬프트를 만든다.

    Args:
        question: 사용자 질문.
        chunks: 검색된 문맥 청크 목록.

    Returns:
        LLM에 전달할 사용자 메시지 문자열.
    """
    context = format_context(chunks) if chunks else "(검색된 문맥 없음)"
    return (
        f"[참고 문맥]\n{context}\n\n"
        f"[질문]\n{question}\n\n"
        "[답변] 위 참고 문맥에 근거하여 근거 조문/별표 번호를 밝히며 답변하세요."
    )
