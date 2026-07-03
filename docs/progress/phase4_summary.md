# Phase 4 진행사항 요약 — Provider 추상화 + Naive RAG

> 작성일: 2026-07-03

## 1. 수행 내용
- `ChatProvider` 프로토콜 + 두 구현체(`OpenRouterProvider`, `GeminiProvider`) 작성 — **서로 다른 SDK**로 구현해 추상화 가치 실증
- 3개 파이프라인 공유 프롬프트 모듈(`prompts.py`) 작성 (공정 비교 원칙: 동일 답변 템플릿)
- `naive_rag.py`: 기본형 RAG(retrieve→generate) 구현
- TDD: `naive_rag` 5개 테스트 (가짜 임베더/스토어/챗)
- **실제 LLM + 실제 Supabase로 두 Provider end-to-end 검증 완료**

## 2. 주요 결정사항 (ADR 후보)
| 결정 | 근거 |
| --- | --- |
| `OpenRouterProvider`=openai SDK(호환), `GeminiProvider`=google-genai(네이티브) | 두 개의 진짜 다른 구현을 한 인터페이스 뒤에 둠 → 추상화 교육 효과 + 폐쇄망(vLLM) 확장 근거 |
| `ChatProvider.complete(user, system, temperature, max_tokens)` 단일 턴 시그니처 | 답변 생성뿐 아니라 Phase 5 쿼리 재작성·Phase 6 라우팅도 단일 턴이라 재사용 가능 |
| 답변 프롬프트를 `prompts.py`에 집중 | 파이프라인별 임의 변형 방지(공정 비교). 근거 조문 인용·미검색 시 "찾을 수 없음" 규칙 포함 |
| `temperature=0.0` 기본 | 결정적 생성으로 비교 재현성 확보 |
| `RagAnswer` 공통 반환 타입(question/answer/contexts/토큰/시간/trace) | 3개 파이프라인이 같은 타입을 반환해야 Phase 7 비교·평가가 단순해짐 |
| 기본 모델: OpenRouter `openai/gpt-4o-mini`, Gemini `gemini-2.5-flash` | 실측으로 동작 확인. 비교 실험 회차 내에서는 동일 모델로 고정(공정성) |

## 3. 산출물
| 파일 | 역할 |
| --- | --- |
| `chat_providers.py` | `ChatProvider` 프로토콜 + OpenRouter/Gemini 구현 + `ChatResult` |
| `prompts.py` | 공유 시스템/사용자 프롬프트, 문맥 조립 |
| `naive_rag.py` | Naive RAG 파이프라인 + `RagAnswer` |
| `tests/test_naive_rag.py` | 단위 테스트 5건 |

## 4. 실측 검증 결과 (실제 LLM + Supabase)
질문: "개인정보가 유출되었을 때 정보주체에게 통지해야 하는 시기와 항목은?"

| Provider | 검색 근거(공통) | 입력/출력 토큰 | 시간 | 정확도 |
| --- | --- | --- | --- | --- |
| OpenRouter (gpt-4o-mini) | 제33·34·35·38·36조 | 1867/189 | 5.1s | 72시간 규칙·통지 항목 정확, 제33조 인용 |
| Gemini (2.5-flash) | 제33·34·35·38·36조 | 1860/332 | 6.1s | 72시간 + 예외(제33조②)·입증책임까지 더 상세 |

**관찰(레포트 소재):** 검색 근거가 동일한데 답변 상세도가 다름 → 순수 **생성 모델 차이**가 드러남(검색은 공통이므로 변수 통제 성공). Gemini가 예외 조항까지 포괄해 출력 토큰이 약 1.75배.

## 5. 이슈 및 해결
| 이슈 | 처리 |
| --- | --- |
| Gemini SDK 버전 혼란(google-generativeai vs google-genai) | 신 SDK `google-genai` 채택, `types.GenerateContentConfig`로 system/temperature 전달 |
| 두 SDK의 사용량 필드명 상이 | ChatResult로 정규화(input_tokens/output_tokens) |

## 6. 다음 Phase 준비사항
- Phase 5(Advanced RAG): 쿼리 재작성(ChatProvider 재사용) + Cohere Rerank + 검색 후 압축
- `cohere` 패키지 설치 필요, `COHERE_API_KEY`는 `.env`에 존재
- 검색은 top-20으로 넓힌 뒤 rerank 5로 좁히는 구조 → `SupabaseVectorStore.match(match_count=20)` 활용
