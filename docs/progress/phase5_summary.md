# Phase 5 진행사항 요약 — Advanced RAG (쿼리 재작성 + Cohere Rerank)

> 작성일: 2026-07-03

## 1. 수행 내용
- `Reranker` 프로토콜 + `CohereReranker` 구현 (다국어 모델, 한국어 지원)
- `QueryRewriter`: ChatProvider 재사용, 구어체→규정 용어 재작성 (실패 시 원 질문 폴백)
- 공유 프롬프트에 `REWRITE_SYSTEM_PROMPT` 추가
- `advanced_rag.py`: 쿼리 재작성 → 넓은 검색(top-20) → Cohere Rerank(top-5) → 점수 임계치 필터 → 생성
- TDD: rewriter 2 + advanced 6 = 8개 테스트
- **실제 Cohere API + LLM + Supabase로 Naive vs Advanced 비교 검증 완료**

## 2. 주요 결정사항 (ADR 후보)
| 결정 | 근거 |
| --- | --- |
| rerank는 **원 질문 기준**, 검색은 **재작성 질의 기준** | 재작성은 재현율(넓게 회수)에, rerank는 사용자 의도 정밀 정렬에 유리. 역할 분리로 재작성 오류가 최종 순위를 오염시키지 않음 |
| RagAnswer 토큰 = **파이프라인 전체 합계**(재작성+생성) | 파이프라인별 비용을 공정하게 비교하려면 모든 LLM 호출 합산이 맞음. 단계별 분해는 trace에 보존 |
| 검색 후 필터링 = rerank 점수 임계치 방식 | "검색 후 압축"을 결정적·설명가능하게 구현. 임계치는 설정값(min_rerank_score) |
| `rerank-multilingual-v3.0` 기본 | 한국어 규정 문체 지원 확인. 실측에서 상대 순위가 유효 |
| 재작성기·재정렬기를 각각 별도 모듈로 분리 | 단일 책임. Modular RAG(Phase 6)에서 재사용 |

## 3. 산출물
| 파일 | 역할 |
| --- | --- |
| `reranker.py` | `Reranker` 프로토콜 + `CohereReranker` + `RerankResult` |
| `query_rewriter.py` | `QueryRewriter` + `RewriteResult` (폴백 포함) |
| `advanced_rag.py` | Advanced RAG 파이프라인 |
| `prompts.py`(수정) | 쿼리 재작성 프롬프트 추가 |
| `tests/test_advanced_rag.py` | 단위 테스트 8건 |

## 4. 실측 검증 결과 — Naive vs Advanced (같은 구어체 질문)
질문: **"직원 실수로 고객 정보가 새어나가면 회사가 뭘 해야 하나요?"**

| 파이프라인 | 검색 근거(Top-5) | 출력 토큰 | 시간 | 평가 |
| --- | --- | --- | --- | --- |
| Naive | 제49·31·28·46·41조 | 14 | 4.3s | 구어체 '새어나가면'이 '유출' 조문에 매칭 실패 → 빈약한 답변 |
| Advanced | **제33·35의2·34·49·38조** | 331 | 7.7s | 재작성('유출 시 대응 조치·의무') + rerank로 **제33조(유출 통지)를 1위**로 → 정확·상세 |

**핵심 관찰(레포트 소재):** 동일 질문에서 Naive는 관련 조문(제33조)을 아예 못 찾았고, Advanced는 찾았다. 쿼리 재작성이 재현율을, rerank가 정밀도를 각각 개선한 교과서적 사례. 비용(토큰·시간)은 늘지만 정확도가 오른 **트레이드오프**가 정량으로 드러남.

Cohere rerank 단독 검증: "개인정보 유출 시 조치" 질의에서 "유출 시 72시간 통지"=0.811, "직원 교육 계획"=0.000으로 명확히 분리.

## 5. 이슈 및 해결 / 리스크
| 항목 | 내용 |
| --- | --- |
| ⚠️ rerank 절대 점수가 낮음(0.01~0.006대) | 한국어 규정 문체에서 Cohere 절대 점수가 낮게 나옴. **상대 순위는 유효**하나 고정 임계치(예 0.9) 필터는 전부 탈락시킴. → `min_rerank_score` 기본 0.0(필터 off) 유지, Phase 7에서 임계치 튜닝 또는 상대 컷 방식 검토 |
| 재작성 폴백 | 빈 응답 시 원 질문 사용하도록 처리 |

## 6. 다음 Phase 준비사항
- Phase 6(Modular RAG): 라우팅(규칙+LLM 2단) + 하이브리드 검색(BM25 tsvector + 벡터, RRF) + 조건부 인접 청크 확장
- BM25용 RPC 함수(하이브리드/키워드 검색)를 스키마에 추가 필요 → `apply_migration`
- 조번호 직접 조회 경로: `article_no` 인덱스 활용
- reranker/rewriter는 Phase 5 것 재사용
