# 최종 레포트 — 규정 문서 RAG 아키텍처 비교

> **AI 챔피언 고급과정** 실습 제출용 · 작성: 코레일유통 IT · 2026-07-03
> 대상 문서: 코레일유통 개인정보보호 지침(제2024-23호)

---

## 초록 (Executive Summary)

동일한 한국어 규정 문서를 대상으로 **Naive / Advanced / Modular** 3가지 RAG 아키텍처를
구축하고 22문항 벤치마크로 정량 비교했다. 핵심 결론은 **"절대 강자는 없다"** 이다.
쉬운 의미 질의에서는 Naive가 동급 정확도(Recall/MRR/nDCG=1.0)에 **6배 저렴**했고, "제N조"
같은 조번호 질의에서는 Modular의 직접조회가 정확하고 **토큰을 1/3로** 절감했다. 답변 품질은
세 방식 모두 동일(faithfulness 0.977)하여, 성능 차이는 **생성이 아니라 검색**에서 났다.
특히 임베딩 모델을 OpenAI→Gemini로 바꾸자 판도가 뒤집혀, **"파이프라인 복잡화보다 임베딩
점검이 먼저"** 라는 교훈을 얻었다. 산출물은 실행 가능한 코드, 3탭 Streamlit 앱, 평가
프레임워크, 공개 배포 구조, 그리고 11건의 ADR이다.

---

## 1. 배경

### 1.1 문제 정의
사내 규정 문서는 장/절/조 계층 + 항/호/목 + 별표(표)가 혼재하고, 조문이 서로를 참조한다.
"개인정보 유출 시 어떻게 신고하나?" 같은 질문에 담당자가 매번 문서를 뒤지는 것은 비효율적이다.

### 1.2 RAG란
RAG(검색증강생성)는 **먼저 관련 문서를 찾고(검색), 그 근거로 답을 생성**하는 방식이다.
LLM 단독은 근거 없이 그럴듯한 오답(환각)을 낼 수 있으나, RAG는 실제 조문을 근거로 제시한다.
> 비유: 사서가 질문을 듣고 관련 책을 찾아준 뒤, 그 책을 근거로 답을 정리해 주는 것.

### 1.3 조직 맥락과 제약
우리 조직은 폐쇄망이 원칙이나, 학습 목적상 클라우드(Supabase/Gemini/OpenRouter/Cohere)를
사용했다. 대신 **운영 배포 시 로컬 대체안**(8장)과 **보안 조치**(3.5·[ADR-SEC-001](decisions/ADR-SEC-001.md))를
함께 설계했다. 상세 리스크 진단은 [Phase 0 요약](progress/phase0_summary.md) 참고.

## 2. 목표
1. Naive/Advanced/Modular 3개 RAG를 **동일 조건**으로 구축·비교
2. 산출물: 실행 코드 + 성능 비교 레포트 + 사용자 매뉴얼 + 공개 데모
3. 성공 기준: **실행 가능성 · 비교 가능성(공정성) · 재현성**

## 3. 설계

### 3.1 전체 아키텍처
두 흐름으로 구성된다.
- **적재:** md 문서 → 구조 청킹 → 임베딩(Gemini) → Supabase(pgvector) 저장
- **질의:** 질문 → (파이프라인별 처리) → 근거 조문 검색 → LLM 답변 생성

### 3.2 문서 구조 분석
실사 결과 **마크다운 헤딩 불일치**(일부 조문만 `###`), **"제4장" 번호 중복**, **표 셀 내
`<br>` 노이즈**를 확인했다. → 헤딩을 믿지 않고 **정규식 텍스트 패턴**으로 청킹하기로 결정.

### 3.3 청킹 전략 ([ADR-DATA-001](decisions/ADR-DATA-001.md))
- 1조=1청크(긴 조문은 항/호 단위 분할 + 조 헤더 반복)
- 1별표=1청크, **표는 자연어 캡션으로 임베딩**(마크다운 기호 노이즈 제거) — 이중 인덱싱
- `content`(답변용 원문)와 `embed_text`(검색용) 분리
- 삭제 조문 포함, "제4장" 중복은 등장 순번(`chapter_seq`)으로 구분
- 상세: [Phase 1 설계 문서](design/phase1_architecture_chunking.md)

### 3.4 데이터 모델 ([ADR-SYS-001](decisions/ADR-SYS-001.md))
`rag_documents`(문서) : `rag_chunks`(청크) 2테이블 + RPC 3종(벡터/하이브리드/인접) +
인덱스(HNSW·GIN·조번호) + RLS. 스키마: [`sql/schema.sql`](../sql/schema.sql)

### 3.5 Provider 추상화 ([ADR-SYS-002](decisions/ADR-SYS-002.md))
`ChatProvider`·`EmbeddingProvider`·`Reranker`·`VectorStore` 4개 인터페이스. 구현체만
교체하면 폐쇄망 전환 가능. API 키는 생성자 주입(UI 입력 지원).

### 3.6 3개 파이프라인 설계 비교
| 단계 | Naive | Advanced | Modular |
| --- | --- | --- | --- |
| 쿼리 전처리 | 없음 | 재작성(LLM) | 라우팅(조번호/표/의미) |
| 검색 | 벡터 top-5 | 벡터 top-20 | 하이브리드(BM25+벡터 RRF) |
| 재정렬 | 없음 | Cohere Rerank | Cohere Rerank |
| 추가 | — | 검색 후 필터 | 조건부 인접 청크 확장 |

### 3.7 평가 설계 ([ADR-ML-004](decisions/ADR-ML-004.md))
검색 지표(Recall@k/MRR/nDCG) + 답변 품질(LLM 심판, **생성과 다른 모델**로 자기채점 회피) +
비용·지연 + **오류 3단 분류**(E1 검색/E2 재정렬/E3 생성). 골드 라벨=조번호라 E1/E2는 자동 판정.

## 4. 구현

### 4.1 개발 방식 ([ADR-PROC-002](decisions/ADR-PROC-002.md))
TDD(Red→Green→Refactor) + Tidy First. 외부 서비스는 의존성 주입 + 가짜로 대체.
최종 **81개 테스트** 통과.

### 4.2~4.6 모듈
- 청킹: [`chunker.py`](../chunker.py) (실측 94청크: article 71/table 14/deleted 8/preamble 1)
- 적재: [`ingest.py`](../ingest.py)·[`load_to_supabase.py`](../load_to_supabase.py) (CLI·업로드 탭 공유)
- Provider: [`chat_providers.py`](../chat_providers.py)·[`embeddings.py`](../embeddings.py)·[`reranker.py`](../reranker.py)
- 파이프라인: [`naive_rag.py`](../naive_rag.py)·[`advanced_rag.py`](../advanced_rag.py)·[`modular_rag.py`](../modular_rag.py)
- 앱: [`compare_app.py`](../compare_app.py) (3탭, API 키 사용자 입력)
- 각 Phase 상세: [progress/](progress/)

## 5. 실험

### 5.1 벤치마크 QA
22문항([`data/benchmark_qa.json`](../data/benchmark_qa.json)) — 의미(18)/표(2)/직접(2),
격식·구어체 혼합. 골드 라벨=조번호/별표.

### 5.2 실험 설정 (공정 비교, [ADR-ML-003](decisions/ADR-ML-003.md))
고정: 동일 청크·임베딩(Gemini)·챗(gpt-4o-mini)·**최종 5청크 예산**·답변 프롬프트.
심판=gpt-4o(분리). 비용 단가는 근사치([`evaluation/pricing.py`](../evaluation/pricing.py)).

## 6. 결과

### 6.1 종합 지표 (전체 해석: [benchmark_report.md](benchmark_report.md))
| 파이프라인 | Recall@5 | MRR | nDCG@5 | Faithful | 지연(중앙) | 질의당 비용 |
| --- | --- | --- | --- | --- | --- | --- |
| **Naive** | **1.000** | **1.000** | **1.000** | 0.977 | 4.7s | **$0.00042** |
| Advanced | 0.977 | 0.932 | 0.932 | 0.977 | 7.1s | $0.00249 |
| Modular | 0.977 | 0.977 | 0.966 | 0.977 | 5.7s | $0.00244 |

### 6.2 오류 분석
3개 모두 22문항 전부 `OK`(E1/E2/E3=0). → 이 벤치마크가 상대적으로 쉬웠다는 방증.

### 6.3 카테고리별(핵심)
- **조번호 질의:** Advanced MRR 0.75(rerank가 정확한 조문을 밀어냄) vs **Modular 1.00**(직접조회).
  토큰도 Modular ~820 vs 나머지 ~2,000+ → **1/3 절감**
- **구어체 복수정답(q02):** Naive가 정답 2개 모두 회수, Advanced/Modular는 1개 놓침

### 6.4 비용·지연
Advanced/Modular는 rerank + 추가 LLM 호출로 **비용 6배**. Advanced 평균 지연은 q15
레이트리밋 이상치(2,761s)로 오염 → 중앙값(7.1s)으로 해석.

## 7. 인사이트

1. **복잡한 RAG ≠ 좋은 RAG.** 쉬운 질의에선 Naive가 정확·저렴. 파이프라인을 늘리기 전에
   **임베딩부터 점검**하라(OpenAI→Gemini 전환이 판도를 바꿈).
2. **rerank는 만능이 아니다.** 명확한 질의를 재배치해 손해를 줄 수 있다 → "언제 켤지"를 라우팅이 판단.
3. **직접조회의 가치.** "제N조"는 벡터검색보다 메타데이터 정확 조회가 항상 우월(정확·저비용).
4. **상황별 선택 가이드**(쉬운 설명·택시 비유): [benchmark_report.md 4장](benchmark_report.md)
   - 명확한 질의/대량 트래픽 → **Naive**
   - 조번호·표·다문서 → **Modular**
   - 구어체·약한 임베딩 → **Advanced/Modular**
   - 실무 권장: **계단식(escalation)** — 기본은 가볍게, 실패 시에만 고급 파이프라인 발동

## 8. 향후 계획

### 8.1 폐쇄망(온프레미스) 전환 로드맵
| 구성요소 | 클라우드 | 로컬 대체 |
| --- | --- | --- |
| 저장소 | Supabase | 자체 PostgreSQL + pgvector |
| 임베딩 | Gemini/OpenAI | BGE-M3, KURE |
| 챗 | OpenRouter/Gemini | vLLM(EXAONE 등) |
| rerank | Cohere | BGE-reranker-v2-m3 |

Provider 추상화 덕분에 **구현체 교체**만으로 전환 가능. 전환 후 **벤치마크 재실행**으로 회귀 확인.

### 8.2 개선 과제
- 레이트리밋 재시도 확대, 한국어 형태소 BM25, rerank 임계치 상대컷, 다문서 라우팅
- 어려운 질의(다중조문·모호·오탈자)로 벤치마크 확장 → Advanced/Modular 강점 검증

### 8.3 운영 적용
사내 규정 챗봇, 접근통제·감사로그 연계, 정기 개정 반영 파이프라인.

---

## 부록
- **A. 의사결정 기록(ADR):** [decisions/](decisions/) — 인덱스 [README](decisions/README.md), ADR 11건
- **B. DB 스키마:** [`sql/schema.sql`](../sql/schema.sql)
- **C. 벤치마크 데이터:** [`data/benchmark_qa.json`](../data/benchmark_qa.json), 결과 [benchmark_results.md](benchmark_results.md)
- **D. 재현 방법:** [README.md](../README.md), [DEPLOYMENT.md](DEPLOYMENT.md), [USER_MANUAL.md](USER_MANUAL.md)
- **E. 단계별 진행 기록:** [progress/](progress/) (Phase 0~10)
- **F. 용어집:** RAG(검색증강생성), 임베딩(텍스트→벡터), 벡터검색, rerank(재정렬),
  RRF(순위융합), HNSW(근사최근접 인덱스), faithfulness(답변의 근거 충실도)
