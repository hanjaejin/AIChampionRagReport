# Phase 3 진행사항 요약 — Supabase 스키마 + 데이터 적재

> 작성일: 2026-07-03

## 1. 수행 내용
- Supabase(pgvector) 스키마 설계·적용 (`rag_documents`, `rag_chunks` + RPC 2개 + 인덱스 5개 + RLS)
- 적재 파이프라인을 **모듈 4개로 분리** 구현: `config`(비밀값), `embeddings`(임베딩 Provider), `vector_store`(Supabase), `ingest`(오케스트레이션)
- CLI 진입점 `load_to_supabase.py` — `ingest.ingest_markdown`을 재사용(업로드 탭과 동일 파이프라인)
- TDD: `config` 6개 + `ingest` 5개 테스트 (가짜 임베더/스토어로 네트워크 없이 검증)
- **실제 Supabase 적재 + 검색 통합 검증 완료**

## 2. 주요 결정사항 (ADR 후보)
| 결정 | 근거 |
| --- | --- |
| 테이블명 `rag_` 네임스페이스 사용 | 프로젝트에 이전 실습 테이블(`documents` 59행, `documents_test` 53행)이 존재 — **내가 만들지 않은 데이터라 삭제 없이** 충돌 회피 |
| `documents`/`chunks` 2테이블 분리 (문서 1행 : 청크 N행) | 문서 수준 메타데이터 중복 저장 방지, 재업로드 시 cascade 삭제 용이 |
| 벡터 검색을 RPC(`match_rag_chunks`)로 노출 | PostgREST는 벡터 연산 직접 불가. `filter_content_type`으로 표 전용 검색 지원 |
| `content`/`embed_text` 컬럼 분리 (Phase 1 R7) + 임베딩은 `embed_text`로 생성 | "보여줄 텍스트"와 "검색용 텍스트" 분리 |
| BM25용 `fts tsvector`(generated) + GIN 인덱스 선반영 | Phase 6 하이브리드 검색 시 마이그레이션 불필요. 한국어 형태소기 부재로 `simple` 사용 |
| 임베딩 Provider·VectorStore를 **생성자 주입 + Protocol**로 설계 | UI 키 입력 정책 + 폐쇄망 전환(BGE/자체 pgvector 교체) 대비 |
| 재업로드 정책: **같은 파일명은 삭제 후 재적재**(교체) | `source_filename` 유니크 인덱스, `replaced` 플래그로 사용자에게 표시 |
| HNSW 인덱스 구성(현 규모에선 완전탐색과 차이 미미) | 학습 목적 + 문서 증가 대비. 레포트에 이 사실 명시 |

## 3. 산출물
| 파일 | 역할 |
| --- | --- |
| `sql/schema.sql` | pgvector 확장, rag_documents/rag_chunks, 인덱스 5종, RPC 2종, RLS |
| `config.py` | 비밀값 로더 (우선순위 UI > st.secrets > .env), `Settings.require()` |
| `embeddings.py` | `EmbeddingProvider` Protocol + `OpenAIEmbeddingProvider`(토큰 사용량 누적) |
| `vector_store.py` | `VectorStore` Protocol + `SupabaseVectorStore`(적재·검색·재업로드) |
| `ingest.py` | 청킹→임베딩→적재 오케스트레이션 + `IngestReport` |
| `load_to_supabase.py` | CLI (기본 개인정보지침.md, `--dry-run` 지원) |
| `requirements.txt` | 의존성 목록 |
| `tests/test_config.py`, `tests/test_ingest.py` | 단위 테스트 11건 |

## 4. 실측 검증 결과 (실제 Supabase)
| 항목 | 값 |
| --- | --- |
| 적재 문서 | 개인정보보호 지침 (제2024-23호) |
| 청크 수 / 임베딩 완료 | 94 / 94 (전량 임베딩) |
| 유형별 | preamble 1, article 71, deleted 8, table 14 |
| "제4장" 중복 chapter_seq | 2개로 구분 ✅ |
| 임베딩 토큰 / 비용 | 33,217토큰 ≈ **$0.00066** (text-embedding-3-small) |
| 적재 소요 | 6.7초 |

**검색 품질 검증(match_rag_chunks RPC):**
| 질의 | Top-1 결과 | 유사도 |
| --- | --- | --- |
| 개인정보가 유출되면 어떻게 신고하나요? | 제35조(개인정보 유출 등의 신고) | 0.620 |
| 개인정보 보호책임자는 누구인가요? | 제28조(분야별 책임자 지정) | 0.633 |
| 개인정보파일 보유기간 기준표를 보여줘 | **별표1(보유기간 책정 기준표)** | **0.729** |
| 파기 관리대장 서식 (표 필터) | 별표3(파기 관리대장) | 0.487 |

→ **R9 표 이중 인덱싱 실증**: 표 겨냥 질의에서 별표가 관련 조문보다 높은 순위(0.729)로 1위. 규칙 기반 캡션이 검색에 유효함을 확인.

## 5. 이슈 및 해결
| 이슈 | 처리 |
| --- | --- |
| 기존 `documents`/`chunks` 이름 충돌 | ✅ `rag_` 네임스페이스로 분리 (기존 데이터 무손상) |
| ⚠️ 기존 `documents`(59행)·`documents_test`(53행) **RLS 비활성화** | **미해결 — 사용자 결정 필요**. anon 키로 전체 행 접근 가능한 상태. 우리 테이블(rag_*)은 RLS 활성화 완료. 아래 6절 참고 |
| pgvector 삽입 시 벡터 포맷 | `_to_pgvector()`로 `[..]` 리터럴 문자열 변환하여 해결 |

## 6. 사용자 확인 필요 (보안)
기존 두 테이블의 RLS가 꺼져 있습니다. 사용 안 하면 삭제하거나, 유지하려면 아래 SQL로 RLS를 켜세요(정책 없이 켜면 anon 접근이 전면 차단됨 — 앱이 service_role로 접근하면 무관):
```sql
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents_test ENABLE ROW LEVEL SECURITY;
```

## 7. 다음 Phase 준비사항
- Phase 4: `ChatProvider` 추상화(OpenRouter/Gemini) + `naive_rag.py`. 검색은 `SupabaseVectorStore.match()` 재사용
- 챗 키(OpenRouter/Gemini)는 `.env`에 없음 → 설계대로 UI 입력 또는 CLI 테스트 시 임시 환경변수로 주입
- `doc_id = e78cefad-f1f7-4fb5-8d1f-8cdd8d58433d` (적재된 지침 문서)
