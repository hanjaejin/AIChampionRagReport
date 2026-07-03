# ADR-SYS-002: Provider 추상화 계층(폐쇄망 전환 대비)

## 메타데이터
- **번호:** ADR-SYS-002
- **날짜:** 2026-07-03
- **작성자:** 한재진 (코레일유통 IT)
- **레벨:** L1
- **상태:** ✅ 승인
- **관련 ADR:** ADR-ML-002, ADR-PROC-001
- **관련 프로젝트:** 규정 문서 RAG 아키텍처 비교

## 1. 맥락 (Context)
학습용으로 클라우드(OpenAI/OpenRouter/Gemini/Cohere/Supabase)를 쓰지만, 우리 조직은
폐쇄망이 원칙이다. 운영 배포 시 "코드 재작성"이 아니라 "구현체 교체"로 전환되어야 한다.
또한 챗 Provider 이중화(OpenRouter/Gemini)와 API 키 사용자 입력 정책을 지원해야 한다.

**핵심 제약 조건:**
- RAG 파이프라인 코드가 구체 Provider를 몰라야 함
- API 키를 런타임(UI 입력)에 주입 가능해야 함
- 폐쇄망 대체 구현으로 무중단 교체

## 2. 결정 (Decision)
**채택:** 4개 인터페이스(Protocol) 경계 정의 — `ChatProvider`, `EmbeddingProvider`,
`Reranker`, `VectorStore`. 모든 구현체는 **API 키를 생성자 주입**으로 받는다.
파이프라인은 인터페이스에만 의존한다.

## 3. 대안 검토
| 대안 | 장점 | 단점 | 탈락 이유 |
| --- | --- | --- | --- |
| SDK 직접 호출(추상화 없음) | 코드 단순 | 벤더 종속, UI 키 주입 불가 | 폐쇄망 전환 = 전면 재작성 |
| LangChain 등 프레임워크 | 추상화 제공 | 무게·블랙박스·버전 리스크 | 학습 투명성 저하 |
| **자체 Protocol 추상화** | 경량·명시적·주입식 | 인터페이스 유지 비용 | **← 채택** |

## 4. 근거 (Rationale)
1. **실증:** OpenRouter(openai SDK)와 Gemini(google-genai SDK)를 서로 다른 SDK로 구현하고 한 인터페이스 뒤에 둠 → 파이프라인 무변경
2. **키 주입:** 생성자 주입 덕분에 사용자가 UI에서 입력한 키를 그대로 사용(ADR-SEC-001)
3. **전환 지도 확보:** Supabase→자체 pgvector, Gemini/OpenAI→BGE-M3/KURE, OpenRouter→vLLM, Cohere→BGE-reranker

## 5. 결과 및 트레이드오프
**긍정적 결과:** 임베딩 Provider를 OpenAI→Gemini로 **파이프라인 무변경 전환**(ADR-ML-002가 실증)
**부정적 결과 / 위험:** 인터페이스 4종 유지 비용, 얇은 래퍼가 벤더 고유 기능 일부 은폐
**수용 기준:** Provider 교체 시 파이프라인/테스트 코드 무수정으로 동작

## 6. 이후 업데이트
| 날짜 | 내용 | 작성자 |
| --- | --- | --- |
| 2026-07-03 | 임베딩 OpenAI→Gemini 전환이 구현체 교체만으로 성공 → 추상화 가치 실증 | 한재진 |
