# 최종 레포트 목차 (제출용) — 규정 문서 RAG 아키텍처 비교

> "AI 챔피언 고급과정" 제출용 레포트의 목차 설계. 흐름: 배경 → 목표 → 설계 → 구현
> → 실험 → 결과 → 인사이트 → 향후계획. 각 절에 **원천 자료(source)**를 매핑해
> Phase 11에서 `docs/FINAL_REPORT.md`로 조립한다. (이 문서는 목차 설계이며 코드 없음)

## 표지 / 요약
- 제목, 작성자(코레일유통 IT), 과정명·기수, 제출일
- **초록(Executive Summary, 1쪽)**: 무엇을·왜·핵심 결과 1문단
  - source: 본 목차 완성 후 결과 수치로 마감

---

## 1. 배경 (Background)
1.1 문제 정의 — 사내 규정 문서 질의응답의 어려움(장/절/조+별표 구조, 조문 상호참조)
1.2 RAG란 무엇인가 — 비유 기반 개념(사서/도서관), 왜 LLM 단독이 아닌 RAG인가
1.3 조직 맥락과 제약 — 폐쇄망 원칙 vs 학습용 클라우드, 보안·개인정보 고려
   - source: `docs/progress/phase0_summary.md`(리스크 진단), ADR-SEC-001

## 2. 목표 (Objectives)
2.1 3개 RAG 아키텍처(Naive/Advanced/Modular) 구축 및 정량 비교
2.2 산출물 정의 — 코드 레포, 성능 비교 레포트, 사용자 매뉴얼, 공개 데모
2.3 성공 기준 — 실행 가능성, 비교 가능성(공정성), 재현성
   - source: `plan.md`(목표), ADR-ML-003(공정 비교 원칙)

## 3. 설계 (Design)
3.1 전체 아키텍처 개요 — 데이터 흐름 다이어그램(적재 파이프라인 + 질의 파이프라인)
3.2 문서 구조 분석 — 실사 결과(헤딩 불일치, 장 번호 중복, 별표 표)
3.3 청킹 전략 — 구조 기반 청킹 R1~R9, content/embed_text 분리, 표 이중 인덱싱
3.4 데이터 모델 — 청크 메타데이터 스키마, Supabase 2테이블·인덱스·RPC
3.5 Provider 추상화 — 4개 인터페이스와 폐쇄망 대체 지도
3.6 3개 파이프라인 설계 비교표 — 단계별 차이(전처리→검색→재정렬→생성)
3.7 평가 설계 — 지표 정의, LLM 심판 분리, 오류 3단 분류(E1/E2/E3)
   - source: `docs/design/phase1_architecture_chunking.md`, ADR-DATA-001·SYS-001·SYS-002·ML-003·ML-004

## 4. 구현 (Implementation)
4.1 개발 방식 — TDD/Tidy First, 테스트 구성(79개)
4.2 청킹 모듈 — 정규식 파싱, 실측 청크 통계(94청크 유형 분포)
4.3 적재 파이프라인 — 임베딩·저장 모듈화(CLI/업로드 탭 공유), 재업로드 정책
4.4 Provider 구현 — 챗(OpenRouter/Gemini), 임베딩(Gemini/OpenAI), rerank(Cohere)
4.5 Naive / Advanced / Modular 파이프라인 구현 요점
4.6 Streamlit 3탭 앱 — 업로드/비교/대시보드, API 키 사용자 입력
   - source: `docs/progress/phase2~7_summary.md`, ADR-PROC-001·PROC-002

## 5. 실험 (Experiments)
5.1 벤치마크 QA 세트 — 22문항 구성(의미/표/직접, 격식/구어체), 골드 라벨=조번호
5.2 실험 설정 — 고정 변수(임베딩·챗 모델·5청크 예산·프롬프트), 측정 지표·비용 단가
5.3 실행 절차 — 대시보드/러너, 심판 모델 분리
   - source: `data/benchmark_qa.json`, `evaluation/`, `docs/progress/phase7_summary.md`
   - ⚠️ **미완**: 전체 벤치마크 실측 실행 필요(결과 수치는 5.x·6장에 반영)

## 6. 결과 (Results)
6.1 검색 지표 비교 — 파이프라인별 Recall@5/MRR/nDCG (표+막대그래프)
6.2 답변 품질 — faithfulness/correctness (심판 기반)
6.3 비용·지연 — 질의당 토큰·비용·지연 비교
6.4 오류 분석 — E1/E2/E3 분포로 본 병목(파이프라인별)
6.5 정성 사례 — 구어체 질의에서 Advanced의 개선, 조번호 질의에서 Modular 직접조회 효율
   - source: 벤치마크 실행 결과(대시보드 export) — **실측 후 채움**
   - 기확보 정성 사례: phase4/5/6 summary(제33조 검색, 518토큰 직접조회 등)

## 7. 인사이트 (Insights)
7.1 언제 어떤 아키텍처가 유리한가 — 질의 유형별 권장
7.2 비용 대비 정확도 트레이드오프 — 도입 의사결정 가이드
7.3 한국어 규정 문서의 특수성 — 임베딩 문체 한계, tsvector 형태소 이슈, 표 처리
7.4 검증이 드러낸 실무 교훈 — 크레딧 소진 대응(임베딩 전환), Gemini thinking, rerank 절대점수
   - source: 각 phase summary "놓쳤을 수 있는 관점", ADR-ML-002

## 8. 향후 계획 (Future Work)
8.1 폐쇄망(온프레미스) 전환 로드맵 — Provider별 로컬 대체(BGE-M3/KURE, vLLM, 자체 pgvector)
8.2 개선 과제 — 레이트리밋 재시도 확대, 한국어 형태소 BM25, rerank 임계치·상대컷, 다문서 라우팅
8.3 운영 적용 시나리오 — 사내 규정 챗봇, 접근통제·감사로그 연계
   - source: ADR-SYS-002, phase6/7 summary

---

## 부록 (Appendix)
- A. ADR 전체 목록 — `docs/decisions/`
- B. 데이터베이스 스키마 — `sql/schema.sql`
- C. 벤치마크 QA 세트 — `data/benchmark_qa.json`
- D. 재현 방법 — `README.md`, `docs/DEPLOYMENT.md`
- E. 용어집 — RAG, 임베딩, 벡터검색, rerank, RRF, HNSW, faithfulness

---

## 그림·표 목록(작성 예정)
- [그림 1] 전체 아키텍처 데이터 흐름
- [그림 2] 3개 파이프라인 단계 비교 다이어그램
- [그림 3] 검색 지표 막대그래프 / [그림 4] 오류 E1/E2/E3 분포
- [표 1] 파이프라인 설계 비교 / [표 2] 지표 요약 / [표 3] 비용·지연 요약

## 작성 원칙
- 초보자 눈높이 + 비유, 결론엔 추론 과정 병기(왜 그렇게 판단했는지)
- 모든 수치는 실측 근거 명시, 비용 단가는 근사치임을 밝힘
- 클라우드 사용 절마다 폐쇄망 대체안 병기
