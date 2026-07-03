# Phase 7 진행사항 요약 — 평가 프레임워크 + Streamlit 3탭 앱

> 작성일: 2026-07-03

## 1. 수행 내용
- 벤치마크 QA 세트(22문항) 구성 — 실제 조문 목록 기반, 골드 라벨=조번호/별표
- 평가 프레임워크(`evaluation/` 패키지) 구현:
  - `metrics.py`: Recall@k, MRR, nDCG@k (순수 함수)
  - `pricing.py`: 토큰/호출 → USD 비용
  - `judge.py`: LLM-as-judge (faithfulness/correctness)
  - `error_analysis.py`: 오류 3단 분류(E1/E2/E3)
  - `benchmark.py` / `runner.py`: QA 로딩 + 파이프라인 실행·집계
- `pipeline_factory.py`: 3개 파이프라인 공유 조립(CLI/러너/앱 공통)
- `compare_app.py`: Streamlit 3탭 앱(문서 업로드 / RAG 비교 / 평가 대시보드)
- TDD: metrics 9 + pricing 5 + error_analysis 6 + runner 6 = 26개 테스트 추가 (누적 75개)

## 2. 주요 결정사항 (ADR 후보)
| 결정 | 근거 |
| --- | --- |
| 골드 라벨 = 조번호(article_no)/별표 | 청킹 방식이 바뀌어도 QA 세트 재사용. E1/E2는 LLM 없이 자동 판정(비용 0) |
| 심판은 생성과 **다른 모델**로 분리(예: 생성 gpt-4o-mini, 심판 gpt-4o) | Phase 0 Q6 자기채점 순환 회피 |
| GeminiProvider **thinking 기본 비활성화**(thinking_budget=0) | gemini-2.5-flash가 사고에 출력 토큰을 소진해 JSON이 잘리는 문제 해결 + 토큰 회계 정확화 |
| 비용에서 심판 토큰 제외 | 심판은 평가 도구일 뿐 운영 비용이 아님 |
| 앱 키는 사이드바 password 입력 → session_state | UI 입력 키 정책. 업로드 탭은 UPLOAD_PASSWORD로 보호(설정 시) |
| 대시보드는 문항 수 슬라이더 + 심판 on/off | 비용·시간 통제(전체 실행 강제 안 함) |

## 3. 산출물
| 파일 | 역할 |
| --- | --- |
| `data/benchmark_qa.json` | 벤치마크 22문항(의미/표/직접, 격식/구어체 혼합) |
| `evaluation/metrics.py` | 검색 지표(순수 함수) |
| `evaluation/pricing.py` | 비용 계산(단가 근사, 조정 가능) |
| `evaluation/judge.py` | LLM 심판(코드펜스 파싱 강건화) |
| `evaluation/error_analysis.py` | E1/E2/E3 분류 |
| `evaluation/benchmark.py` / `runner.py` | QA 로딩 + 실행·집계(실패 격리) |
| `pipeline_factory.py` | 3파이프라인 공유 조립 |
| `compare_app.py` | Streamlit 3탭 앱 |
| `tests/test_metrics.py` 등 4종 | 단위 테스트 26건 |

## 4. 검증 결과
- **단위 테스트 75개 전부 통과** (지표·비용·오류분류·러너 포함)
- **Streamlit 앱 headless 부팅 확인**: HTTP 200, `/_stcore/health` = ok (3탭 렌더 정상)
- **평가 파이프라인 실서비스 부분 검증**: q21(제36조 직접 조회) 경로가 임베딩 없이 전 구간(라우팅→직접조회→생성→gpt-4o 심판) 통과, faithfulness=1.0/correctness=1.0/OK 판정 → 심판·오류분류·비용 계산의 실동작 확인

## 5. 이슈 및 리스크 (검증이 드러낸 실제 문제)
| 이슈 | 상태 |
| --- | --- |
| ⚠️ OpenAI 임베딩 크레딧 소진(insufficient_quota 429) | ✅ **해결(2026-07-03)**: 임베딩을 Gemini(`gemini-embedding-001`, 1536차원)로 전환하고 전체 코퍼스 재임베딩. OpenAI 의존 제거로 전체 벤치마크 실행 가능해짐. 3파이프라인 end-to-end 재검증 완료 |
| Gemini 무료 티어 5회/분 제한 | 배치 평가엔 부적합. 심판/생성은 OpenRouter 권장(대시보드 기본값 반영) |
| Gemini thinking으로 JSON 잘림 | ✅ 해결(thinking_budget=0) |
| 심판 JSON 코드펜스 | ✅ 해결(펜스 제거 파싱) |
| 임베딩/챗 레이트리밋 재시도 미구현 | 배치 안정화를 위해 지수 백오프 재시도는 향후 개선 과제로 기록 |

## 5-b. 전체 벤치마크 실행 결과 (2026-07-03 추가 실행)
Gemini 임베딩 전환 후 전체 22문항×3파이프라인+심판(gpt-4o) 실행 완료.
상세·해석은 `docs/benchmark_report.md`, 원시 데이터는 `docs/benchmark_results.json`.

| 파이프라인 | Recall@5 | MRR | nDCG@5 | Faithful | 지연(중앙) | 질의당 비용 |
| --- | --- | --- | --- | --- | --- | --- |
| Naive | 1.000 | 1.000 | 1.000 | 0.977 | 4.7s | $0.00042 |
| Advanced | 0.977 | 0.932 | 0.932 | 0.977 | 7.1s | $0.00249 |
| Modular | 0.977 | 0.977 | 0.966 | 0.977 | 5.7s | $0.00244 |

**핵심 발견:** ① 쉬운 의미 질의에선 Naive가 동급 정확도에 6배 저렴 ② 조번호 질의에선
Modular 직접조회가 정확·토큰 1/3, Advanced rerank는 오히려 악화(MRR 0.75) ③ 답변 품질은
3개 동일(0.977) → 차이는 검색에서 발생 ④ 지연 평균은 q15 레이트리밋 이상치(2761s)로
오염 → 중앙값 사용. 전부 OK(E1/E2/E3=0)는 벤치마크가 쉬웠다는 방증.

**버그 수정:** nDCG가 분할 조문(같은 조번호 2청크)에서 중복 계산돼 1.0 초과 → 조번호 단위
중복 제거로 수정(`metrics.dedupe_labels`, 테스트 추가). API 재호출 없이 저장 데이터로 재계산.

## 6. 다음 Phase 준비사항
- **OpenAI 크레딧 충전 후** 대시보드에서 전체 벤치마크(22문항×3) 실행 → 실측 지표를 최종 레포트(Phase 11)에 반영
- Phase 8: GitHub 배포 구조 + Streamlit Cloud 배포(requirements.txt·.env.example·.gitignore·README, secrets 설정, 업로드 잠금)
- Phase 9~11: ADR, 레포트 목차, 최종 문서(매뉴얼/레포트/README)
