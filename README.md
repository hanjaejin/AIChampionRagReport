# 📚 규정 문서 RAG 아키텍처 비교 (Naive · Advanced · Modular)

동일한 한국어 규정 문서를 대상으로 **3가지 RAG(Retrieval-Augmented Generation)
아키텍처를 모두 구축**하고 정확도·속도·비용을 **정량 비교**하는 오픈소스 프로젝트입니다.
사내 "AI 챔피언 고급과정" 실습 산출물이며, 대상 문서는 장/절/조 계층 + 별표(표)가
혼재된 개인정보보호 지침입니다.

![python](https://img.shields.io/badge/Python-3.11%2B-blue)
![streamlit](https://img.shields.io/badge/UI-Streamlit-red)
![pgvector](https://img.shields.io/badge/VectorDB-Supabase%20pgvector-3ecf8e)
![tests](https://img.shields.io/badge/tests-81%20passing-brightgreen)

> ⚠️ 데모는 방문자가 **자신의 API 키를 입력**해 사용합니다(앱 소유자 키 비용 도용 방지).

## ✨ 주요 기능

- **3개 RAG 파이프라인**을 동일 조건(임베딩·청크·컨텍스트 예산·프롬프트 고정)으로 비교
- **구조 기반 청킹**: 장/절/조 계층 인식, 조=청크, 표(별표)는 자연어 캡션으로 이중 인덱싱
- **평가 프레임워크**: Recall@k · MRR · nDCG · faithfulness · 지연 · 비용 + 오류 3단 분류(E1/E2/E3)
- **Streamlit 3탭 앱**: ① 문서 업로드 ② RAG 비교 ③ 평가 대시보드
- **Provider 추상화**: 챗(OpenRouter/Gemini)·임베딩(Gemini/OpenAI)·rerank(Cohere)를
  교체 가능 → 폐쇄망(온프레미스) 전환 대비

## 🏗️ 3가지 아키텍처

| 단계 | ① Naive | ② Advanced | ③ Modular |
| --- | --- | --- | --- |
| 쿼리 전처리 | 없음 | 쿼리 재작성(LLM) | 라우팅(조번호/표/의미) |
| 검색 | 벡터 top-5 | 벡터 top-20 | 하이브리드(BM25+벡터, RRF) |
| 재정렬 | 없음 | Cohere Rerank | Cohere Rerank |
| 추가 | — | 검색 후 필터 | 조건부 인접 청크 확장 |

## 🧰 기술 스택

- 벡터 저장소: **Supabase (pgvector)** — HNSW 인덱스, RRF 하이브리드 검색 RPC
- 임베딩: **Gemini `gemini-embedding-001`** (1536차원, 문서/질의 비대칭 task_type)
  — `OpenAIEmbeddingProvider`도 선택 가능
- 챗: **OpenRouter** + **Google Gemini** 이중 지원(공통 `ChatProvider` 인터페이스)
- 재정렬: **Cohere Rerank** (다국어)
- 앱/배포: **Streamlit** + **Streamlit Community Cloud**

## 🚀 빠른 시작

```bash
# 1) 의존성 설치
pip install -r requirements.txt

# 2) 환경변수 설정
cp .env.example .env    # 편집기로 열어 키 입력 (Supabase, Gemini, OpenRouter, Cohere)

# 3) Supabase 스키마 생성
#    Supabase 대시보드 SQL Editor에 sql/schema.sql 붙여넣어 실행

# 4) 문서 적재 (기본: 개인정보지침.md → Gemini 임베딩 → Supabase)
python load_to_supabase.py

# 5) 앱 실행
streamlit run compare_app.py
```

테스트: `pytest -q`

## 📁 폴더 구조

```
├── compare_app.py          # Streamlit 3탭 앱(업로드/비교/대시보드)
├── chunker.py              # 구조 기반 청킹(장/절/조 + 별표)
├── ingest.py               # 적재 파이프라인(청킹→임베딩→저장)
├── load_to_supabase.py     # 문서 적재 CLI
├── config.py               # 비밀값 로더(UI > st.secrets > .env)
├── embeddings.py           # EmbeddingProvider(Gemini/OpenAI)
├── chat_providers.py       # ChatProvider(OpenRouter/Gemini)
├── reranker.py             # Reranker(Cohere)
├── vector_store.py         # Supabase(pgvector) 저장/검색
├── prompts.py              # 공유 프롬프트(생성/재작성/라우팅/심판)
├── naive_rag.py / advanced_rag.py / modular_rag.py   # 3개 파이프라인
├── router.py               # Modular 2단 라우터
├── query_rewriter.py       # 쿼리 재작성
├── pipeline_factory.py     # 파이프라인 공유 조립
├── evaluation/             # 지표·비용·심판·오류분석·러너
├── sql/schema.sql          # pgvector 스키마 + RPC + 인덱스
├── data/benchmark_qa.json  # 벤치마크 QA(골드=조번호)
├── tests/                  # 단위 테스트(79개)
└── docs/                   # 설계·진행요약·배포·매뉴얼·레포트
```

## 📊 배포

Streamlit Community Cloud 무료 배포 및 민감정보 체크리스트는
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) 참고.

## 🔒 폐쇄망(온프레미스) 대체

학습용으로 클라우드를 쓰지만, Provider 추상화 덕분에 운영 배포 시 구현체만 교체하면 됩니다:
Supabase→자체 PostgreSQL+pgvector, Gemini/OpenAI 임베딩→BGE-M3/KURE,
OpenRouter/Gemini 챗→vLLM(EXAONE 등), Cohere→BGE-reranker.

## 📄 문서 (전체 색인)

생성된 모든 문서를 용도별로 정리했습니다.

### 🚀 시작하기 · 사용
| 문서 | 설명 |
| --- | --- |
| [docs/USER_MANUAL.md](docs/USER_MANUAL.md) | **사용자 매뉴얼** — 설치부터 실행·벤치마크까지 비개발자용 단계별 안내 + FAQ/문제해결 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | **배포 가이드** — GitHub + Streamlit Cloud 배포 절차, 민감정보 제거 체크리스트, 데모 보호 |

### 📊 성능 비교 (핵심 산출물)
| 문서 | 설명 |
| --- | --- |
| [docs/benchmark_report.md](docs/benchmark_report.md) | **벤치마크 종합 보고서** — 3개 RAG 장단점, 상황별 추천(택시 비유), 5대 발견, 한계·인사이트 |
| [docs/benchmark_results.md](docs/benchmark_results.md) | 벤치마크 자동 요약표(지표·오류분포) |
| [docs/benchmark_results.json](docs/benchmark_results.json) | 벤치마크 원시 결과(문항별 상세) |
| [docs/FINAL_REPORT.md](docs/FINAL_REPORT.md) | **최종 레포트** — 배경-목표-설계-구현-실험-결과-인사이트-향후계획 통합본(제출용) |

### 🏗️ 설계 · 의사결정
| 문서 | 설명 |
| --- | --- |
| [docs/design/phase1_architecture_chunking.md](docs/design/phase1_architecture_chunking.md) | **아키텍처·청킹 설계** — 3파이프라인 비교, 청킹 규칙 R1~R9, 메타데이터 스키마, 오류분석 |
| [docs/report_outline.md](docs/report_outline.md) | 최종 레포트 목차 설계(원천 자료 매핑) |
| [docs/decisions/README.md](docs/decisions/README.md) | **ADR 인덱스** — 의사결정 기록 11건 목록 |
| [docs/decisions/ADR-DATA-001.md](docs/decisions/ADR-DATA-001.md) | ADR: 구조 기반 청킹 전략(표 이중 인덱싱) — L1 |
| [docs/decisions/ADR-SYS-001.md](docs/decisions/ADR-SYS-001.md) | ADR: 벡터 저장소 Supabase(pgvector) — L1 |
| [docs/decisions/ADR-SYS-002.md](docs/decisions/ADR-SYS-002.md) | ADR: Provider 추상화 계층(폐쇄망 대비) — L1 |
| [docs/decisions/ADR-ML-001.md](docs/decisions/ADR-ML-001.md) | ADR: 임베딩 OpenAI(대체됨) — L1 |
| [docs/decisions/ADR-ML-002.md](docs/decisions/ADR-ML-002.md) | ADR: 임베딩 Gemini 전환 — L1 |
| [docs/decisions/ADR-ML-003.md](docs/decisions/ADR-ML-003.md) | ADR: 3-RAG 비교 + 공정 비교 원칙 — L1 |
| [docs/decisions/ADR-ML-004.md](docs/decisions/ADR-ML-004.md) | ADR: 평가 프레임워크(심판 분리·E1/E2/E3) — L2 |
| [docs/decisions/ADR-PROC-001.md](docs/decisions/ADR-PROC-001.md) | ADR: 챗 Provider 이중화 + Cohere Rerank — L2 |
| [docs/decisions/ADR-PROC-002.md](docs/decisions/ADR-PROC-002.md) | ADR: TDD / Tidy First 개발 방식 — L2 |
| [docs/decisions/ADR-SEC-001.md](docs/decisions/ADR-SEC-001.md) | ADR: API 키 사용자 입력 + 배포 보안 — L2 |
| [docs/decisions/quick-log/2026-07.md](docs/decisions/quick-log/2026-07.md) | L3 빠른 결정 기록 5건 |

### 📆 단계별 진행 기록 (Phase 0~10)
| 문서 | 설명 |
| --- | --- |
| [docs/progress/phase0_summary.md](docs/progress/phase0_summary.md) | Phase 0 — 요구사항 재정의·리스크 진단 |
| [docs/progress/phase1_summary.md](docs/progress/phase1_summary.md) | Phase 1 — 아키텍처·청킹 설계 |
| [docs/progress/phase2_summary.md](docs/progress/phase2_summary.md) | Phase 2 — 청킹 모듈(TDD) |
| [docs/progress/phase3_summary.md](docs/progress/phase3_summary.md) | Phase 3 — Supabase 스키마·적재 |
| [docs/progress/phase4_summary.md](docs/progress/phase4_summary.md) | Phase 4 — Provider 추상화·Naive RAG |
| [docs/progress/phase5_summary.md](docs/progress/phase5_summary.md) | Phase 5 — Advanced RAG |
| [docs/progress/phase6_summary.md](docs/progress/phase6_summary.md) | Phase 6 — Modular RAG |
| [docs/progress/phase7_summary.md](docs/progress/phase7_summary.md) | Phase 7 — 평가 프레임워크·앱·벤치마크 |
| [docs/progress/phase8_summary.md](docs/progress/phase8_summary.md) | Phase 8 — 배포 구조 |
| [docs/progress/phase9_summary.md](docs/progress/phase9_summary.md) | Phase 9 — ADR 생성 |
| [docs/progress/phase10_summary.md](docs/progress/phase10_summary.md) | Phase 10 — 최종 레포트 목차 |

### 🗂️ 기타
| 문서 | 설명 |
| --- | --- |
| [plan.md](plan.md) | 전체 프로젝트 계획 · Phase 체크리스트 · 설계 변경 이력 |
| [sql/schema.sql](sql/schema.sql) | DB 스키마(pgvector·RPC·인덱스·RLS) |
| [data/benchmark_qa.json](data/benchmark_qa.json) | 벤치마크 QA 세트(22문항, 골드=조번호) |

## ⚠️ 무료 티어 참고

Streamlit Cloud(잠자기 모드), Gemini(분당 요청 제한), Supabase(용량 제한)의
제약이 있습니다. 자세한 내용은 배포 가이드를 참고하세요.

## 라이선스

MIT (실습 프로젝트).
