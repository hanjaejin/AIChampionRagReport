# file: evaluation/__init__.py
"""RAG 파이프라인 정량 평가 프레임워크.

모듈:
    metrics        : 검색 지표(Recall@k, MRR, nDCG) — 순수 함수
    pricing        : 토큰→비용 계산
    judge          : LLM 심판(faithfulness, correctness)
    error_analysis : 오류 3단 분류(E1/E2/E3)
    benchmark      : QA 세트 로딩
    runner         : 파이프라인을 QA 세트에 실행해 결과 수집
"""
