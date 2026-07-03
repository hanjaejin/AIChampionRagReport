# Phase 8 진행사항 요약 — GitHub 배포 구조 + Streamlit Cloud 배포

> 작성일: 2026-07-03

## 1. 수행 내용
- 배포용 파일 작성: `.env.example`, `.streamlit/config.toml`, `.streamlit/secrets.toml.example`, `LICENSE`(MIT)
- `README.md` 초안 작성(소개·아키텍처·기술스택·빠른시작·폴더구조·폐쇄망 대체·무료티어 안내)
- `docs/DEPLOYMENT.md` 작성: GitHub 푸시 + Streamlit Cloud 배포 절차 + **민감정보 제거 체크리스트** + 공개 데모 보호
- `.gitignore` 검증 및 민감정보 스캔 수행

## 2. 주요 결정사항 (ADR 후보)
| 결정 | 근거 |
| --- | --- |
| 폴더 구조는 **평면(root) + evaluation/ 패키지 유지** (src/ 재편 안 함) | 학습 프로젝트 규모에 적합, 기존 import/테스트 안정성 유지. README에 구조 문서화 |
| LLM 키는 secrets에 넣지 않고 방문자 입력, Supabase만 소유자 secrets | 공개 데모의 키 비용 도용 원천 차단 |
| 업로드 탭 `UPLOAD_PASSWORD` 보호 | 공유 Supabase 데이터 오염 방지 |
| `개인정보지침.md`는 커밋하되 **공개 여부 확인을 체크리스트로 강제** | 공개 규정일 가능성이 높으나 미확인. 사용자 최종 판단 항목으로 명시 |
| git init/push는 **사용자 승인 후** 수행 | 외부 공개는 되돌리기 어려운 작업 → 자동 실행하지 않음 |

## 3. 산출물
| 파일 | 역할 |
| --- | --- |
| `README.md` | GitHub 배포용 README 초안(Phase 11에서 최종화) |
| `.env.example` | 환경변수 템플릿(실제 키 없음) |
| `.streamlit/config.toml` | 앱 테마·업로드 크기 제한 |
| `.streamlit/secrets.toml.example` | Streamlit Cloud secrets 템플릿 |
| `docs/DEPLOYMENT.md` | 배포 절차 + 민감정보 체크리스트 + 데모 보호 |
| `LICENSE` | MIT |

## 4. 검증 결과 (민감정보 제거 체크리스트 일부 자동 검증)
- ✅ `.py` 파일 내 하드코딩된 키 스캔: **0건** (`sk-`, `sk-or-v1-`, `AIzaSy`, `eyJhbGci` 패턴)
- ✅ `.gitignore`가 `.env`·`.streamlit/secrets.toml` 커밋 차단 확인(`git check-ignore`)
- ✅ `.env.example`·`secrets.toml.example`에 실제 값 없음(플레이스홀더만)

## 5. 이슈 및 사용자 확인 필요
| 항목 | 내용 |
| --- | --- |
| `개인정보지침.md` 공개 여부 | 미확인(Phase 0 Q1). 비공개면 커밋 제외 필요 — 체크리스트에 명시 |
| 기존 `documents`/`documents_test` RLS 비활성화 | Supabase 정리 항목(별도, rag_* 무관) — 체크리스트에 명시 |
| git init/push | 사용자 승인 후 진행(현재 미실행). 레포 URL 확정 시 절차대로 푸시 |

## 6. 다음 Phase 준비사항
- Phase 9: Phase 1~8 주요 결정을 ADR(L1/L2/L3)로 정리 — 각 요약의 "주요 결정사항"과 plan.md 설계 변경 이력이 원천 자료
- Phase 10: 최종 레포트 목차
- Phase 11: 사용자 매뉴얼·최종 레포트·README 최종본
- (권장) OpenAI 의존 제거로 전체 벤치마크 실행 가능 → 실측 지표를 Phase 11 레포트에 반영
