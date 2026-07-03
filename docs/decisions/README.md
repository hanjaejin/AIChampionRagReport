# 의사결정 기록(ADR) 인덱스 — 규정 문서 RAG 비교 프로젝트

코레일유통 "AI 챔피언 고급과정" 실습. Phase 1~8의 주요 결정을 ADR로 기록한다.
양식: 맥락 → 결정 → 대안 → 근거 → 트레이드오프. 레벨 L1(아키텍처)/L2(프로세스)/L3(구현).

| ADR 번호 | 제목 | 날짜 | 상태 | 레벨 |
| --- | --- | --- | --- | --- |
| [ADR-DATA-001](ADR-DATA-001.md) | 구조 기반 청킹 전략(장/절/조 + 별표 이중 인덱싱) | 2026-07-03 | ✅ 승인 | L1 |
| [ADR-SYS-001](ADR-SYS-001.md) | 벡터 저장소로 Supabase(pgvector) 채택 | 2026-07-03 | ✅ 승인 | L1 |
| [ADR-SYS-002](ADR-SYS-002.md) | Provider 추상화 계층(폐쇄망 전환 대비) | 2026-07-03 | ✅ 승인 | L1 |
| [ADR-ML-001](ADR-ML-001.md) | 임베딩 모델로 OpenAI text-embedding-3-small | 2026-07-03 | 🔄 대체됨(ADR-ML-002) | L1 |
| [ADR-ML-002](ADR-ML-002.md) | 임베딩 모델 Gemini 전환(ADR-ML-001 대체) | 2026-07-03 | ✅ 승인 | L1 |
| [ADR-ML-003](ADR-ML-003.md) | 3-RAG 비교 아키텍처 + 공정 비교 원칙 | 2026-07-03 | ✅ 승인 | L1 |
| [ADR-ML-004](ADR-ML-004.md) | 평가 프레임워크(심판 분리 + E1/E2/E3 오류분류) | 2026-07-03 | ✅ 승인 | L2 |
| [ADR-PROC-001](ADR-PROC-001.md) | 챗 Provider 이중화 + Cohere Rerank | 2026-07-03 | ✅ 승인 | L2 |
| [ADR-PROC-002](ADR-PROC-002.md) | TDD / Tidy First 개발 방식 | 2026-07-03 | ✅ 승인 | L2 |
| [ADR-SEC-001](ADR-SEC-001.md) | API 키 사용자 입력 + Streamlit Cloud 배포 보안 | 2026-07-03 | ✅ 승인 | L2 |
| [quick-log/2026-07.md](quick-log/2026-07.md) | L3 구현 결정 모음(네임스페이스·thinking·인덱스 등) | 2026-07-03 | ✅ 기록 | L3 |
