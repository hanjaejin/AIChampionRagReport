-- file: sql/schema.sql
-- 규정 문서 RAG 비교 프로젝트 — Supabase(pgvector) 스키마
--
-- Phase 1 설계(docs/design/phase1_architecture_chunking.md)의 메타데이터 스키마와
-- Phase 2 chunker.py의 Chunk dataclass 필드를 1:1 대응시킨다.
--
-- ※ 테이블명 prefix 'rag_' 사용 이유:
--   이 Supabase 프로젝트에는 이전 실습의 documents/documents_test 테이블이 이미 존재한다.
--   기존 데이터를 건드리지 않기 위해 본 프로젝트 테이블은 rag_ 네임스페이스로 분리한다.
--
-- 적용 방법(택1):
--   1) Supabase 대시보드 > SQL Editor 에 붙여넣기 실행
--   2) load_to_supabase.py 실행 전에 psql / MCP apply_migration 으로 적용
--
-- 임베딩 모델: OpenAI text-embedding-3-small → 1536차원

-- ── 1. 확장 활성화 ────────────────────────────────────────────
create extension if not exists vector;      -- pgvector: 벡터 유사도 검색

-- ── 2. 문서 테이블 (원문 1건 = 1행) ───────────────────────────
create table if not exists rag_documents (
    doc_id          uuid primary key default gen_random_uuid(),
    doc_title       text not null,
    doc_version     text,                    -- 예: 제2024-23호
    revision_date   date,                    -- 문서 수준 최신 개정일
    source_filename text,                    -- 업로드 원본 파일명 (재업로드 감지 키)
    content_hash    text,                    -- 원문 SHA-256 (동일 내용 재업로드 판별)
    chunk_count     int  not null default 0,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- 재업로드 정책: 같은 파일명은 1건만 유지 (교체 시 기존 삭제 후 재적재)
create unique index if not exists rag_documents_source_filename_key
    on rag_documents (source_filename);

-- ── 3. 청크 테이블 (청크/임베딩/메타데이터) ───────────────────
create table if not exists rag_chunks (
    id                bigint generated always as identity primary key,
    doc_id            uuid not null references rag_documents(doc_id) on delete cascade,
    chunk_index       int  not null,                 -- 문서 내 순번(인접 청크 확장 조회 키)
    content_type      text not null
        check (content_type in ('article', 'table', 'deleted', 'preamble')),

    -- 본문(R7): 답변 제시용 원문 / 임베딩 입력 분리
    content           text not null,                 -- 사람에게 보여줄 원문
    embed_text        text not null,                 -- 임베딩에 넣은 텍스트(브레드크럼/캡션 포함)
    embedding         vector(1536),                  -- text-embedding-3-small

    -- 계층 메타데이터
    chapter_seq       int,                           -- 장 등장 순번("제4장" 중복 대응 유니크 키)
    chapter_no        text,
    chapter_title     text,
    section_no        text,
    section_title     text,
    article_no        text,                          -- 평가 골드 라벨 매칭 키
    article_title     text,
    clause_range      text,                          -- R2 분할 시 항/호 범위
    annex_no          int,                           -- 별표 번호(표 청크)
    related_articles  text[] not null default '{}',  -- 별표↔조 상호참조
    table_caption     text,                          -- R9 캡션 원문(표 청크)

    token_count       int,
    embedding_version text,                           -- 모델 교체 시 재임베딩 대상 식별

    -- BM25 하이브리드 검색(Phase 6)용 전문검색 벡터.
    -- 한국어 형태소 분석기가 기본 제공되지 않으므로 'simple'(공백/구두점 토큰화) 사용.
    fts tsvector generated always as (to_tsvector('simple', content)) stored,

    created_at        timestamptz not null default now(),

    unique (doc_id, chunk_index)
);

-- ── 4. 인덱스 전략 ────────────────────────────────────────────
-- HNSW: 근사 최근접 이웃. 현재 문서 규모(약 94청크)에선 완전탐색과 속도차가 거의 없으나
--        학습 목적 + 문서 증가 대비로 구성한다(레포트에 이 사실 명시).
create index if not exists rag_chunks_embedding_hnsw
    on rag_chunks using hnsw (embedding vector_cosine_ops);

-- GIN: BM25 전문검색(Phase 6 하이브리드)
create index if not exists rag_chunks_fts_gin
    on rag_chunks using gin (fts);

-- 조번호 직접 조회(Modular RAG 라우팅) / 유형 필터(표 전용 검색) / 문서 조인
create index if not exists rag_chunks_article_no_idx   on rag_chunks (article_no);
create index if not exists rag_chunks_content_type_idx on rag_chunks (content_type);
create index if not exists rag_chunks_doc_id_idx        on rag_chunks (doc_id);

-- ── 5. 벡터 유사도 검색 RPC ───────────────────────────────────
-- Supabase 클라이언트(PostgREST)는 벡터 연산을 직접 못 하므로 RPC 함수로 노출한다.
-- 코사인 유사도 = 1 - 코사인 거리(<=>). filter_content_type 로 표 전용 검색 등 지원.
create or replace function match_rag_chunks(
    query_embedding      vector(1536),
    match_count          int  default 5,
    filter_doc_id        uuid default null,
    filter_content_type  text default null
)
returns table (
    id               bigint,
    doc_id           uuid,
    chunk_index      int,
    content_type     text,
    content          text,
    article_no       text,
    article_title    text,
    chapter_no       text,
    chapter_title    text,
    section_no       text,
    annex_no         int,
    related_articles text[],
    similarity       float
)
language sql stable
as $$
    select
        c.id, c.doc_id, c.chunk_index, c.content_type, c.content,
        c.article_no, c.article_title, c.chapter_no, c.chapter_title,
        c.section_no, c.annex_no, c.related_articles,
        1 - (c.embedding <=> query_embedding) as similarity
    from rag_chunks c
    where c.embedding is not null
      and (filter_doc_id is null or c.doc_id = filter_doc_id)
      and (filter_content_type is null or c.content_type = filter_content_type)
    order by c.embedding <=> query_embedding
    limit match_count;
$$;

-- ── 6. 인접 청크 직접 조회 RPC (Modular RAG 인접 확장, Phase 6) ─
-- 특정 문서에서 chunk_index 범위로 청크를 가져온다(벡터 검색 없이).
create or replace function get_adjacent_rag_chunks(
    p_doc_id     uuid,
    p_from_index int,
    p_to_index   int
)
returns table (
    id           bigint,
    chunk_index  int,
    content_type text,
    content      text,
    article_no   text
)
language sql stable
as $$
    select c.id, c.chunk_index, c.content_type, c.content, c.article_no
    from rag_chunks c
    where c.doc_id = p_doc_id
      and c.chunk_index between p_from_index and p_to_index
    order by c.chunk_index;
$$;

-- ── 6-b. 하이브리드 검색 RPC (Modular RAG, Phase 6) ───────────
-- BM25(tsvector) + 벡터 검색을 각각 수행한 뒤 RRF(Reciprocal Rank Fusion)로 융합한다.
-- rrf_score = Σ weight / (rrf_k + rank). 키워드·의미 검색의 장점을 결합.
create or replace function hybrid_search_rag_chunks(
    query_text          text,
    query_embedding     vector(1536),
    match_count         int   default 5,
    rrf_k               int   default 50,
    full_text_weight    float default 1.0,
    semantic_weight     float default 1.0,
    filter_doc_id       uuid  default null
)
returns table (
    id bigint, doc_id uuid, chunk_index int, content_type text, content text,
    article_no text, article_title text, chapter_no text, chapter_title text,
    section_no text, annex_no int, related_articles text[], rrf_score float
)
language sql stable
as $$
    with full_text as (
        select c.id,
               row_number() over (
                   order by ts_rank_cd(c.fts, plainto_tsquery('simple', query_text)) desc
               ) as rank_ix
        from rag_chunks c
        where c.fts @@ plainto_tsquery('simple', query_text)
          and (filter_doc_id is null or c.doc_id = filter_doc_id)
        order by rank_ix
        limit least(match_count * 4, 40)
    ),
    semantic as (
        select c.id,
               row_number() over (order by c.embedding <=> query_embedding) as rank_ix
        from rag_chunks c
        where c.embedding is not null
          and (filter_doc_id is null or c.doc_id = filter_doc_id)
        order by rank_ix
        limit least(match_count * 4, 40)
    )
    select
        c.id, c.doc_id, c.chunk_index, c.content_type, c.content,
        c.article_no, c.article_title, c.chapter_no, c.chapter_title,
        c.section_no, c.annex_no, c.related_articles,
        coalesce(1.0 / (rrf_k + full_text.rank_ix), 0.0) * full_text_weight
        + coalesce(1.0 / (rrf_k + semantic.rank_ix), 0.0) * semantic_weight as rrf_score
    from full_text
    full outer join semantic on full_text.id = semantic.id
    join rag_chunks c on c.id = coalesce(full_text.id, semantic.id)
    order by rrf_score desc
    limit match_count;
$$;

-- ── 7. RLS(행 수준 보안) ──────────────────────────────────────
-- 정책을 만들지 않아 anon/authenticated 는 접근 불가, service_role 만 우회 접근.
-- 공개 데모에서 앱은 service_role 키로 서버측 접근하고, 업로드는 앱 비밀번호로 보호(Phase 8).
alter table rag_documents enable row level security;
alter table rag_chunks    enable row level security;
