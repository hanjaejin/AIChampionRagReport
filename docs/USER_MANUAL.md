# 사용자 매뉴얼 — 규정 문서 RAG 비교 시스템

> 이 매뉴얼은 **비개발자도 따라 할 수 있도록** 설치부터 실행까지 단계별로 설명합니다.
> 막히는 부분은 마지막 "자주 묻는 질문/문제 해결"을 먼저 확인하세요.
>
> **🔗 설치 없이 바로 쓰기: https://aichampion-rag.streamlit.app/**
> (사이드바에 본인 API 키 입력 → ② RAG 비교 탭에서 질문. 아래 4장 참고)

---

## 0. 이 시스템이 하는 일 (1분 이해)

규정 문서(예: 개인정보보호 지침)를 넣어두면, 질문에 대해 **관련 조문을 찾아 근거와 함께
답변**합니다. 같은 질문을 3가지 방식(Naive / Advanced / Modular)으로 처리해 **어느 방식이
더 정확하고 저렴한지 비교**할 수 있습니다.

> 비유: 도서관 사서 3명에게 같은 질문을 하고, 누가 더 정확하고 빠르게 답하는지 겨루는 것.

---

## 1. 준비물 (API 키)

아래 서비스의 API 키가 필요합니다. 앱에서는 **사이드바에 직접 입력**하므로 코드에
넣을 필요가 없습니다.

| 서비스 | 용도 | 발급처 |
| --- | --- | --- |
| **Supabase** | 문서·벡터 저장 | supabase.com (프로젝트 URL + service key) |
| **Gemini** | 임베딩 + 챗 | ai.google.dev |
| **OpenRouter** | 챗(gpt-4o-mini 등) | openrouter.ai |
| **Cohere** | 재정렬(rerank) | cohere.com |

> OpenAI 키는 선택입니다(임베딩을 OpenAI로 쓸 때만).

---

## 2. 설치 (한 번만)

### 2-1. 사전 요구사항
- Python 3.11 이상 ([python.org](https://www.python.org)에서 설치)
- 터미널(Windows PowerShell / macOS·Linux 터미널)

### 2-2. 코드 내려받기 & 의존성 설치
```bash
git clone https://github.com/<사용자>/<레포>.git
cd <레포>
pip install -r requirements.txt
```

### 2-3. 환경변수 설정
```bash
cp .env.example .env
```
편집기로 `.env`를 열어 Supabase URL/키 등을 채웁니다. (LLM 키는 앱에서 입력해도 됩니다.)

### 2-4. 데이터베이스 준비 (한 번만)
1. Supabase 대시보드 → **SQL Editor** 열기
2. 프로젝트의 [`sql/schema.sql`](../sql/schema.sql) 내용을 전체 복사해 붙여넣고 **Run**
3. 테이블 `rag_documents`, `rag_chunks` 가 생성되면 완료

---

## 3. 문서 넣기 (적재)

### 방법 A — 앱에서 (권장, 쉬움)
1. 앱 실행: `streamlit run compare_app.py`
2. 브라우저가 열리면 왼쪽 사이드바에 **API 키 입력**
3. **① 문서 업로드** 탭 → md 파일 선택
4. **청킹 미리보기**(청크 수·유형) 확인 → "✅ 임베딩 후 Supabase에 적재" 클릭
5. 진행 막대가 끝나면 적재 완료(청크 수·소요시간 표시)

### 방법 B — 명령어로
```bash
python load_to_supabase.py                 # 기본: 개인정보지침.md
python load_to_supabase.py 다른규정.md      # 다른 문서
python load_to_supabase.py --dry-run       # 청킹만 미리보기(적재 안 함)
```

---

## 4. 앱 사용법

```bash
streamlit run compare_app.py
```
왼쪽 사이드바에서 **API 키**와 **Provider**(챗/임베딩)를 선택한 뒤, 3개 탭을 사용합니다.

### 탭 ① 문서 업로드
- md 규정 문서를 올려 벡터 DB에 적재 (3장 참조)
- 공개 배포 시 관리자 비밀번호가 걸려 있을 수 있음

### 탭 ② RAG 비교
- 질문 입력 → **비교 실행** → Naive/Advanced/Modular 답변이 **나란히** 표시
- 각 답변 아래 토큰·지연·검색 근거(조문) 확인 가능

### 탭 ③ 평가 대시보드
- **실행 문항 수** 슬라이더로 벤치마크 규모 선택
- **LLM 심판** 체크 시 답변 품질(faithfulness/correctness)까지 측정(비용↑)
- **벤치마크 실행** → 지표 표·막대그래프·오류 분포 확인

---

## 5. 벤치마크(성능 비교) 실행 — 명령어

앱 없이 전체 성능 비교를 돌리려면:
```bash
python run_benchmark.py                 # 검색 지표·비용·지연(심판 없음, 저렴)
python run_benchmark.py --judge         # 답변 품질까지(심판 포함, 비용↑)
python run_benchmark.py --limit 6       # 앞 6문항만(빠른 확인)
```
결과는 `docs/benchmark_results.md`(요약표)와 `docs/benchmark_results.json`(원시)에 저장됩니다.
해석은 [`docs/benchmark_report.md`](benchmark_report.md) 참고.

---

## 6. 자주 묻는 질문 / 문제 해결 (FAQ)

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| `insufficient_quota` (OpenAI) | 크레딧 소진 | 임베딩 Provider를 **Gemini**로 선택(사이드바/`--embedding gemini`) 또는 OpenAI 충전 |
| `429 RESOURCE_EXHAUSTED` (Gemini) | 무료 티어 분당 요청 제한 | 잠시 후 재시도(재시도 내장). 대량 실행은 유료 티어 또는 OpenRouter 챗 사용 |
| 업로드 시 "청킹 실패" | 규정 형식이 아닌 파일 | 장/절/조(제N조) 구조의 md인지 확인 |
| 검색 결과가 이상함 | 적재 임베딩과 질의 임베딩 Provider 불일치 | **적재와 질의를 같은 Provider**로(둘 다 Gemini 등). 바꿨다면 재적재 |
| 앱이 "키가 없습니다" | 사이드바 키 미입력 | 해당 키 입력 후 재실행 |
| 표(별표) 질문이 잘 안 됨 | — | Modular 파이프라인/표 라우팅이 유리 |
| Supabase 연결 오류 | URL/키 오타, 스키마 미생성 | `.env` 확인, `sql/schema.sql` 실행 여부 확인 |
| Streamlit 앱이 안 뜸 | 포트 충돌 | `streamlit run compare_app.py --server.port 8502` |

---

## 7. 안전 수칙
- API 키는 **저장·공유 금지**. 앱은 세션 메모리에만 보관합니다.
- 각 서비스 콘솔에서 **지출 한도**를 설정해 예기치 않은 비용을 막으세요.
- 민감 문서는 공개 배포 전 대외 공개 가능 여부를 확인하세요([배포 가이드](DEPLOYMENT.md) 체크리스트).

---

## 8. 더 알아보기
- 전체 개요·빠른시작: [README.md](../README.md)
- 성능 비교 해석: [benchmark_report.md](benchmark_report.md)
- 최종 레포트: [FINAL_REPORT.md](FINAL_REPORT.md)
- 배포: [DEPLOYMENT.md](DEPLOYMENT.md)
