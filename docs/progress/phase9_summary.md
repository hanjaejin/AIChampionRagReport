# Phase 9 진행사항 요약 — ADR(의사결정 기록) 초안 생성

> 작성일: 2026-07-03

## 1. 수행 내용
- `adr-decision-log` 스킬의 코레일유통 표준 ADR 양식(맥락-결정-대안-근거-트레이드오프) 적용
- Phase 1~8 주요 결정을 ADR 10건 + L3 quick-log로 정리, 카테고리 접두어(SYS/ML/DATA/PROC/SEC) 및 L1/L2/L3 분류
- ADR 인덱스(`docs/decisions/README.md`) 작성

## 2. 작성한 ADR 목록
| ADR | 제목 | 레벨 | 상태 |
| --- | --- | --- | --- |
| DATA-001 | 구조 기반 청킹 전략(장/절/조 + 별표 이중 인덱싱) | L1 | ✅ 승인 |
| SYS-001 | 벡터 저장소 Supabase(pgvector) | L1 | ✅ 승인 |
| SYS-002 | Provider 추상화 계층(폐쇄망 전환 대비) | L1 | ✅ 승인 |
| ML-001 | 임베딩 OpenAI text-embedding-3-small | L1 | 🔄 대체됨 |
| ML-002 | 임베딩 Gemini 전환(ML-001 대체) | L1 | ✅ 승인 |
| ML-003 | 3-RAG 비교 + 공정 비교 원칙 | L1 | ✅ 승인 |
| ML-004 | 평가 프레임워크(심판 분리 + E1/E2/E3) | L2 | ✅ 승인 |
| PROC-001 | 챗 Provider 이중화 + Cohere Rerank | L2 | ✅ 승인 |
| PROC-002 | TDD / Tidy First 개발 방식 | L2 | ✅ 승인 |
| SEC-001 | API 키 사용자 입력 + 배포 보안 | L2 | ✅ 승인 |
| quick-log/2026-07 | L3 구현 결정 5건(네임스페이스·thinking·인덱스·재업로드·토큰계수) | L3 | ✅ 기록 |

## 3. 주요 결정사항 (메타)
| 결정 | 근거 |
| --- | --- |
| OpenAI→Gemini 임베딩 전환을 **ML-001 폐기 + ML-002 대체**의 2개 ADR로 기록 | "폐기된 ADR도 삭제하지 않는다" 원칙 — 당시 판단 근거 보존이 조직 지식 |
| 청킹/저장소/추상화/비교설계를 L1으로 분류 | 아키텍처급 결정(팀장 승인 대상) |
| 평가·Provider이중화·TDD·보안을 L2 | 프로세스·도구 결정 |

## 4. 산출물
| 파일 | 역할 |
| --- | --- |
| `docs/decisions/README.md` | ADR 인덱스 |
| `docs/decisions/ADR-*.md` (10건) | 결정별 ADR 초안 |
| `docs/decisions/quick-log/2026-07.md` | L3 빠른 기록 5건 |

## 5. 이슈 및 해결
- 없음. (각 Phase 요약의 "주요 결정사항"과 plan.md 설계 변경 이력을 원천 자료로 활용)

## 6. 다음 Phase 준비사항
- Phase 10: 최종 레포트 목차(배경-목표-설계-구현-실험-결과-인사이트-향후계획)
- Phase 11: 사용자 매뉴얼·최종 레포트·README 최종본 — ADR과 진행요약이 레포트 "설계/의사결정" 절의 원천
- (권장) 전체 벤치마크 실행으로 실측 지표 확보 후 레포트 반영
