# 배포 가이드 (GitHub + Streamlit Community Cloud)

> 이 문서는 프로젝트를 GitHub 공개 레포로 올리고 Streamlit Community Cloud에
> 무료 배포해 공개 데모 URL을 얻는 절차를 안내합니다.

## 0. 배포 전 민감정보 제거 체크리스트 ⚠️

커밋/푸시 **전에** 반드시 확인하세요. 한 번 커밋된 비밀은 git 히스토리에 영구 잔존합니다.

- [ ] `.env` 가 커밋 대상이 아닌지 확인 (`git status`에 안 보여야 함 — `.gitignore`로 차단됨)
- [ ] `.streamlit/secrets.toml` 이 커밋 대상이 아닌지 확인 (차단됨)
- [ ] 코드에 하드코딩된 키가 없는지 검색:
      `grep -rInE "sk-|AIza|eyJ|api[_-]?key" --include="*.py" .` (결과 없어야 정상)
- [ ] `개인정보지침.md`(대상 문서)의 **대외 공개 가능 여부 확인**.
      비공개 사내 문서라면 커밋하지 말고 `.gitignore`에 추가하거나 가공본으로 대체.
      (공개 규정이면 그대로 두어도 무방)
- [ ] Supabase의 이전 실습 테이블(`documents`, `documents_test`)이 남아 있다면
      RLS 활성화 또는 삭제(별도 정리 — 이 프로젝트 `rag_*` 테이블과 무관)
- [ ] 커밋 후 GitHub 웹에서 파일 목록을 눈으로 재확인

## 1. GitHub 공개 레포로 올리기

```bash
git init
git add .
git commit -m "규정 문서 RAG 아키텍처 비교 프로젝트"
git branch -M main
git remote add origin https://github.com/<사용자>/<레포>.git
git push -u origin main
```

`.gitignore` 가 `.env`·`secrets.toml`·`__pycache__` 등을 자동 제외합니다.

## 2. Supabase 준비

1. Supabase 프로젝트 생성(또는 기존 사용).
2. SQL Editor에 [`sql/schema.sql`](../sql/schema.sql) 전체를 붙여넣어 실행
   (테이블 `rag_documents`/`rag_chunks`, RPC, 인덱스, RLS 생성).
3. 문서 적재: 로컬에서 `python load_to_supabase.py` 실행
   (또는 배포된 앱의 **① 문서 업로드 탭**에서 업로드).

## 3. Streamlit Community Cloud 배포

1. https://share.streamlit.io 에 GitHub 계정으로 로그인.
2. **New app** → 레포/브랜치 선택, **Main file path** = `compare_app.py`.
3. **Advanced settings > Secrets** 에 [`.streamlit/secrets.toml.example`](../.streamlit/secrets.toml.example)
   내용을 참고해 최소한 `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `UPLOAD_PASSWORD` 입력.
4. **Deploy** → `https://<앱이름>.streamlit.app` 공개 URL 발급.
5. 레포에 push하면 자동 재배포됩니다.

의존성은 [`requirements.txt`](../requirements.txt)로 자동 설치됩니다.

## 4. 공개 데모 보호

| 위험 | 대응 |
| --- | --- |
| 앱 소유자 LLM 키 비용 도용 | LLM 키를 secrets에 넣지 말고 **방문자가 사이드바에서 직접 입력**하게 함(기본 설계) |
| 공유 Supabase 데이터 오염 | `UPLOAD_PASSWORD` 설정 → 업로드 탭이 비밀번호 요구 |
| 방문자의 과도한 호출 | 각 LLM 콘솔에서 지출 한도(spending limit) 설정 |

## 5. 무료 티어 제약 (README에도 안내)

- **Streamlit Cloud**: 메모리 약 1GB, 일정 시간 미사용 시 잠자기(재접속 시 수십 초 웨이크업).
- **Gemini 무료 티어**: 분당 요청 제한(예: 챗 5 RPM). 전체 벤치마크처럼 다량 호출 시
  레이트리밋 가능 → 유료 티어 또는 OpenRouter 챗 사용 권장. 임베딩 Provider는
  재시도(지수 백오프)를 내장.
- **Supabase 무료 티어**: 용량/일시정지 정책 확인.
