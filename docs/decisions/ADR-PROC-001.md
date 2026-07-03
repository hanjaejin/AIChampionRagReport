# ADR-PROC-001: 챗 Provider 이중화(OpenRouter/Gemini) + Cohere Rerank

## 메타데이터
- **번호:** ADR-PROC-001
- **날짜:** 2026-07-03
- **작성자:** 한재진 (코레일유통 IT)
- **레벨:** L2
- **상태:** ✅ 승인
- **관련 ADR:** ADR-SYS-002(추상화)
- **관련 프로젝트:** 규정 문서 RAG 아키텍처 비교

## 1. 맥락 (Context)
답변 생성 LLM을 하나의 벤더에 종속시키면 장애·요금·정책 변화에 취약하다. 실습 목표에도
"OpenRouter + Gemini 이중 지원"이 포함된다. 재정렬(rerank)도 별도 Provider가 필요하다.

## 2. 결정 (Decision)
**채택:** 챗은 `ChatProvider` 뒤에서 `OpenRouterProvider`(openai SDK)와
`GeminiProvider`(google-genai SDK)를 선택 가능. 재정렬은 `CohereReranker`
(rerank-multilingual-v3.0). 한 실험 회차 내에서는 동일 챗 모델로 고정(공정 비교).

## 3. 대안 검토
| 대안 | 장점 | 단점 | 탈락 이유 |
| --- | --- | --- | --- |
| 단일 벤더 | 단순 | 종속·장애 리스크 | 이중화 목표 미충족 |
| 로컬 LLM(vLLM) | 폐쇄망 정합 | 인프라 필요 | 학습 일정상 운영 대안으로 기록 |
| rerank 자체구현(코사인) | 무료 | 품질↓ | 전용 rerank 대비 열위 |
| **OpenRouter+Gemini + Cohere** | 유연·다국어 | Provider별 특성 차이 | **← 채택** |

## 4. 근거 (Rationale)
1. **이중화 실증:** 동일 질문에서 두 Provider가 같은 청크를 검색하고 답변 상세도만 차이(gpt-4o-mini 189토큰 vs Gemini 332토큰) → 순수 생성 모델 비교 가능
2. **rerank 효과:** "유출 시 조치"에 관련 문서 0.811 vs 무관 0.000으로 명확 분리
3. **키 주입식**(ADR-SYS-002)이라 UI 입력 키로 즉시 전환

## 5. 결과 및 트레이드오프
**긍정적 결과:** 벤더 장애/요금 대응 유연, 모델 간 비교 데이터 확보
**부정적 결과 / 위험:** Gemini 무료 티어 RPM 제한, rerank 절대점수 낮음(상대순위로 사용)
**수용 기준:** 두 Provider·rerank 실서비스 동작 확인(충족)

## 6. 이후 업데이트
| 날짜 | 내용 | 작성자 |
| --- | --- | --- |
| 2026-07-03 | 배치 평가엔 OpenRouter 권장(Gemini 무료 RPM 제한) 정책 반영 | 한재진 |
