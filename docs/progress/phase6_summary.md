# Phase 6 진행사항 요약 — Modular RAG (라우팅 + 하이브리드 + 인접 확장)

> 작성일: 2026-07-03

## 1. 수행 내용
- 하이브리드 검색 RPC(`hybrid_search_rag_chunks`) 추가·적용: BM25(tsvector) + 벡터 RRF 융합
- VectorStore에 3개 메서드 추가: `hybrid_search`, `get_by_article`(직접 조회), `get_adjacent`(인접)
- `router.py`: 규칙(1단) + LLM(2단) 2단 라우터 (DIRECT/TABLE/SEMANTIC)
- `modular_rag.py`: 라우팅→경로별 검색→(rerank)→조건부 인접 확장→생성
- TDD: router 6 + modular 6 = 12개 테스트
- **실제 서비스로 3경로 + 인접 확장 검증 완료**

## 2. 주요 결정사항 (ADR 후보)
| 결정 | 근거 |
| --- | --- |
| 2단 라우팅(규칙 우선, LLM 폴백) | 조번호/별표/서식 키워드는 규칙으로 무료·즉시 분류. 모호한 경우만 LLM 호출로 비용 절감 |
| DIRECT 경로는 **rerank 생략, 메타데이터 직접 조회** | 조번호 명시 질문은 벡터 검색보다 정확 조회가 항상 우월. 부수 효과로 토큰 대폭 절감 |
| 하이브리드는 SQL 내 RRF 융합(rrf_k=50) | BM25·벡터 각각의 순위를 결합. 앱단 융합보다 1회 왕복으로 효율적 |
| 인접 확장은 **조건부**(최상위가 분할청크 or 참조표현 시에만) | 무조건 확장은 컨텍스트 오염. 최종 top_k 예산 유지 + 중복 제거 |
| DIRECT 조회 실패 시 하이브리드 폴백 | 존재하지 않는 조번호 질문에도 답을 시도(사용자 경험) |

## 3. 산출물
| 파일 | 역할 |
| --- | --- |
| `router.py` | `QueryRouter` 2단 라우터 + `RouteDecision` + `Route` enum |
| `modular_rag.py` | Modular RAG 파이프라인 (경로별 검색 + 조건부 인접 확장) |
| `vector_store.py`(수정) | hybrid_search / get_by_article / get_adjacent 추가 |
| `sql/schema.sql`(수정) | hybrid_search_rag_chunks RPC 추가 |
| `prompts.py`(수정) | 라우팅 분류 프롬프트 추가 |
| `tests/test_modular_rag.py` | 단위 테스트 12건 |

## 4. 실측 검증 결과 (실제 서비스, 3경로)
| 질문 | 경로(계층) | Top-1 근거 | 입력 토큰 | 시간 |
| --- | --- | --- | --- | --- |
| 제36조 내용 알려줘 | DIRECT(rule) | 제36조 직접 조회 | **518** | 6.3s |
| 파기 관리대장 서식 보여줘 | TABLE(rule) | 별표3(파기 관리대장) | 1767 | 4.7s |
| 개인정보 보호책임자는 어떤 역할을? | SEMANTIC(llm) | 제29조(역할 및 책임) | 1599 | 10.8s |

**핵심 관찰(레포트 소재):**
- **라우팅의 비용 효과**: DIRECT 경로는 518토큰으로, 후보 20개를 회수하는 SEMANTIC(1599토큰)의 1/3. 조번호 질문에서 라우팅이 정확도·비용 모두 이득.
- TABLE 경로가 표 5종을 정확히 회수하고 별표3을 1위로 → 표 전용 필터 유효.
- 하이브리드 검색 실측: "개인정보 유출 신고"에 제35조·제33조 + 별표4/5(신고서 서식) 동시 포착(키워드+의미 결합 효과).

## 5. 이슈 및 해결
| 이슈 | 처리 |
| --- | --- |
| 한국어 tsvector가 형태소 분석 없음(simple) | RRF에서 벡터가 보완. Phase 7에서 키워드-only vs 하이브리드 비교로 효과 정량화 |
| 인접 확장이 3개 검증 질의에서 미발동 | 정상(조건부). 최상위가 참조표현/분할청크일 때만 발동 — 단위 테스트로 발동/미발동 모두 검증 |

## 6. 다음 Phase 준비사항
- **3개 파이프라인(Naive/Advanced/Modular) 모두 완성** → Phase 7 비교·평가로 진입
- Phase 7: 지표 계산(Recall@k, MRR, nDCG, faithfulness, 지연, 비용) + 오류 분석(E1/E2/E3) + Streamlit 3탭 앱(업로드/비교/대시보드)
- 벤치마크 QA 세트(골드 라벨 = article_no) 구성 필요
- 세 파이프라인 공통 반환 타입 `RagAnswer` 확보 → 비교 로직 단순화 가능
