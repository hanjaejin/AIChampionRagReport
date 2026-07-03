# file: tests/test_chunker.py
"""chunker 모듈 테스트.

Phase 1 설계 문서(docs/design/phase1_architecture_chunking.md)의
청킹 규칙 R1~R9를 검증한다. 마크다운 헤딩 불신 원칙에 따라
테스트 샘플에도 헤딩 표기 불일치를 의도적으로 포함한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from chunker import Chunk, ChunkingError, RegulationChunker

# ---------------------------------------------------------------------------
# 테스트 샘플: 개인정보지침.md의 구조적 특징을 축소 재현
#  - 헤딩 불일치 (제3조만 ### 헤딩)
#  - 삭제 조문 (제16조)
#  - 장 번호 중복 (제4장 2회)
#  - 별표(표) + 셀 내 <br>
# ---------------------------------------------------------------------------
SAMPLE_DOC = """개인정보보호 지침

제정 2010. 08. 01.

개정 2016.08.12. 제2016-35호

전부개정 2024.06.27. 제2024-23호


### 제1장 총칙

제1조(목적) 이 지침은 개인정보의 안전한 처리와 보호에 필요한 사항을 정하는 것을 목적으로 한다.

제2조(적용 범위) ① 이 지침은 모든 부서에 적용한다.

② 다른 사규에서 특별히 정한 경우를 제외하고는 이 지침에 따른다.

### 제3조(용어 정의) 이 지침에서 사용하는 용어의 뜻은 다음과 같다.

1. "정보주체"란 정보의 주체가 되는 사람을 말한다.

### 제2장 개인정보 처리기준

### 제1절 개인정보의 처리

제4조(처리 원칙) 개인정보는 처리목적에 필요한 최소한의 범위에서 수집한다.

### 제16조(주민등록번호 이외의 회원가입 방법 제공) 삭제

### 제4장 개인정보파일의 관리

제70조(등록) 개인정보파일은 지체 없이 등록한다.

### 제4장 보칙

제71조(재검토) 이 지침은 3년마다 타당성을 재검토한다.

## [별표 1](제47조 관련)

개인정보파일 보유기간 책정 기준표

| 보유기간 | 대상 개인정보 파일 |
| --- | --- |
| 영 구 | 영구보존이 필요한 개인정보파일<br>중요 파일 |
| 1년 | 단순 보고용 파일 |
"""


@pytest.fixture()
def result():
    """SAMPLE_DOC 청킹 결과 (기본 설정)."""
    return RegulationChunker().chunk(SAMPLE_DOC)


def _by_article(chunks: list[Chunk], article_no: str) -> list[Chunk]:
    return [c for c in chunks if c.article_no == article_no]


# ---------------------------------------------------------------------------
# R1: 1조 = 1청크
# ---------------------------------------------------------------------------
def test_article_becomes_single_chunk(result) -> None:
    chunks = _by_article(result.chunks, "제1조")
    assert len(chunks) == 1
    assert chunks[0].content_type == "article"
    assert "안전한 처리와 보호" in chunks[0].content
    assert chunks[0].article_title == "목적"


# ---------------------------------------------------------------------------
# 마크다운 헤딩 불신 원칙: ### 붙은 조문도 동일하게 인식, 본문에 # 미포함
# ---------------------------------------------------------------------------
def test_heading_marker_not_trusted_and_stripped(result) -> None:
    chunks = _by_article(result.chunks, "제3조")
    assert len(chunks) == 1
    assert "#" not in chunks[0].content
    assert chunks[0].article_title == "용어 정의"


# ---------------------------------------------------------------------------
# R4: 삭제 조문은 content_type='deleted'
# ---------------------------------------------------------------------------
def test_deleted_article(result) -> None:
    chunks = _by_article(result.chunks, "제16조")
    assert len(chunks) == 1
    assert chunks[0].content_type == "deleted"


# ---------------------------------------------------------------------------
# R5: 제·개정 연혁 preamble 청크 + 문서 메타데이터 추출
# ---------------------------------------------------------------------------
def test_preamble_and_doc_metadata(result) -> None:
    preambles = [c for c in result.chunks if c.content_type == "preamble"]
    assert len(preambles) == 1
    assert "전부개정" in preambles[0].content

    assert result.metadata.doc_title == "개인정보보호 지침"
    assert result.metadata.doc_version == "제2024-23호"
    assert result.metadata.revision_date == date(2024, 6, 27)


# ---------------------------------------------------------------------------
# R6: 장/절은 청크가 아니라 메타데이터
# ---------------------------------------------------------------------------
def test_chapter_and_section_metadata(result) -> None:
    chunk = _by_article(result.chunks, "제4조")[0]
    assert chunk.chapter_no == "제2장"
    assert chunk.chapter_title == "개인정보 처리기준"
    assert chunk.section_no == "제1절"
    assert chunk.section_title == "개인정보의 처리"
    # 장/절 헤더 자체가 독립 청크로 만들어지면 안 된다
    assert all("총칙" != c.content.strip() for c in result.chunks)


# ---------------------------------------------------------------------------
# 장 번호 중복 대응: 같은 "제4장"이라도 chapter_seq는 달라야 한다
# ---------------------------------------------------------------------------
def test_duplicate_chapter_gets_distinct_seq(result) -> None:
    c70 = _by_article(result.chunks, "제70조")[0]
    c71 = _by_article(result.chunks, "제71조")[0]
    assert c70.chapter_no == c71.chapter_no == "제4장"
    assert c70.chapter_seq != c71.chapter_seq
    assert c70.chapter_title == "개인정보파일의 관리"
    assert c71.chapter_title == "보칙"


# ---------------------------------------------------------------------------
# R3: 1별표 = 1청크, 별표 메타데이터(annex_no, related_articles)
# ---------------------------------------------------------------------------
def test_annex_single_chunk_with_metadata(result) -> None:
    tables = [c for c in result.chunks if c.content_type == "table"]
    assert len(tables) == 1
    t = tables[0]
    assert t.annex_no == 1
    assert t.related_articles == ("제47조",)
    assert "| 보유기간 |" in t.content  # 원본 표는 content에 유지


# ---------------------------------------------------------------------------
# R9: 표 청크의 embed_text는 자연어 캡션 (마크다운 표 기호 미포함)
# ---------------------------------------------------------------------------
def test_table_embed_text_uses_caption_not_pipes(result) -> None:
    t = [c for c in result.chunks if c.content_type == "table"][0]
    assert "|" not in t.embed_text
    assert "---" not in t.embed_text
    assert "별표 1" in t.embed_text
    assert "개인정보파일 보유기간 책정 기준표" in t.embed_text
    assert "제47조" in t.embed_text
    assert "보유기간" in t.embed_text  # 열 헤더가 캡션에 포함
    assert t.table_caption is not None


# ---------------------------------------------------------------------------
# R7: 일반 청크의 embed_text = 브레드크럼 + 본문
# ---------------------------------------------------------------------------
def test_breadcrumb_in_embed_text(result) -> None:
    chunk = _by_article(result.chunks, "제4조")[0]
    assert chunk.embed_text.startswith(
        "[제2장 개인정보 처리기준 > 제1절 개인정보의 처리 > 제4조(처리 원칙)]"
    )
    assert "최소한의 범위" in chunk.embed_text


# ---------------------------------------------------------------------------
# R8: <br> 정규화
# ---------------------------------------------------------------------------
def test_br_normalized(result) -> None:
    assert all("<br>" not in c.content for c in result.chunks)


# ---------------------------------------------------------------------------
# R2: 긴 조문은 항(①) 단위 분할 + 조 헤더 반복 + clause_range
# ---------------------------------------------------------------------------
def test_long_article_split_by_clause() -> None:
    long_doc = (
        "장문 규정 샘플\n\n"
        "제1장 총칙\n\n"
        "제5조(보호조치) 개인정보처리자는 다음 각 항의 조치를 하여야 한다.\n\n"
        "① 관리적 조치로서 내부 관리계획의 수립과 시행, 개인정보 취급자에 대한 "
        "정기적인 교육과 감독을 포함한 조치를 빠짐없이 이행하여야 한다.\n\n"
        "② 기술적 조치로서 접근권한의 관리, 접근통제시스템의 설치, 개인정보의 "
        "암호화와 보안프로그램의 설치 및 갱신 조치를 이행하여야 한다.\n\n"
        "③ 물리적 조치로서 전산실과 자료보관실 등의 접근통제 조치를 이행하여야 한다.\n"
    )
    # 글자 수를 토큰 수로 간주하는 계수기를 주입해 분할을 강제한다 (결정적 테스트)
    chunker = RegulationChunker(token_counter=len, max_tokens=150)
    chunks = [c for c in chunker.chunk(long_doc).chunks if c.article_no == "제5조"]

    assert len(chunks) >= 2  # 분할되었다
    for c in chunks:
        assert c.content.startswith("제5조(보호조치)")  # 조 헤더 반복
        assert c.clause_range is not None
    # 마지막 분할 청크에 마지막 항이 포함된다
    assert "③" in chunks[-1].clause_range or "③" in chunks[-1].content


# ---------------------------------------------------------------------------
# R2 확장: 항(①)이 없고 호(1. 2. …)만 있는 긴 조문은 호 단위로 분할
# (실제 지침의 제3조(용어 정의)가 이 사례 — 22개 호, 약 1,000토큰)
# ---------------------------------------------------------------------------
def test_long_article_without_clauses_splits_by_items() -> None:
    doc = (
        "용어 규정 샘플\n\n"
        "제1장 총칙\n\n"
        "제3조(용어 정의) 이 지침에서 사용하는 용어의 뜻은 다음과 같다.\n\n"
        '1. "정보주체"란 처리되는 정보에 의하여 알아볼 수 있는 사람으로서 '
        "그 정보의 주체가 되는 사람을 말한다.\n\n"
        '2. "개인정보"란 살아 있는 개인에 관한 정보로서 성명, 주민등록번호 및 '
        "영상 등을 통하여 개인을 알아볼 수 있는 정보를 말한다.\n\n"
        '3. "가명처리"란 개인정보의 일부를 삭제하거나 일부 또는 전부를 대체하는 '
        "방법으로 특정 개인을 알아볼 수 없도록 처리하는 것을 말한다.\n"
    )
    chunker = RegulationChunker(token_counter=len, max_tokens=150)
    chunks = [c for c in chunker.chunk(doc).chunks if c.article_no == "제3조"]

    assert len(chunks) >= 2  # 호 단위로 분할되었다
    for c in chunks:
        assert c.content.startswith("제3조(용어 정의)")  # 조 헤더 반복
        assert c.clause_range is not None
        assert "호" in c.clause_range  # 항이 아닌 호 기반 범위 표기


# ---------------------------------------------------------------------------
# 조문 패턴이 전혀 없는 파일 → ChunkingError (업로드 탭 오류 처리 대비)
# ---------------------------------------------------------------------------
def test_no_article_pattern_raises() -> None:
    with pytest.raises(ChunkingError):
        RegulationChunker().chunk("이 파일은 규정 문서가 아닙니다.\n그냥 메모입니다.\n")


# ---------------------------------------------------------------------------
# chunk_index는 0부터 연속
# ---------------------------------------------------------------------------
def test_chunk_index_sequential(result) -> None:
    assert [c.chunk_index for c in result.chunks] == list(range(len(result.chunks)))


# ---------------------------------------------------------------------------
# 통합 테스트: 실제 개인정보지침.md 전체 청킹
# ---------------------------------------------------------------------------
REAL_DOC = Path(__file__).resolve().parents[1] / "개인정보지침.md"


@pytest.mark.skipif(not REAL_DOC.exists(), reason="실제 지침 문서가 없는 환경")
def test_real_document_integration() -> None:
    result = RegulationChunker().chunk(REAL_DOC.read_text(encoding="utf-8"))
    chunks = result.chunks

    # 예상 규모 (Phase 1 설계 3-4: 약 100~130청크, 여유 범위로 검증)
    assert 80 <= len(chunks) <= 200

    # 4가지 content_type 모두 존재
    types = {c.content_type for c in chunks}
    assert types == {"article", "table", "deleted", "preamble"}

    # 별표는 14개
    assert len([c for c in chunks if c.content_type == "table"]) == 14

    # 골드 라벨 키가 될 조문 존재 확인
    assert _by_article(chunks, "제36조")

    # "제4장" 중복이 서로 다른 chapter_seq로 구분된다
    seqs = {c.chapter_seq for c in chunks if c.chapter_no == "제4장"}
    assert len(seqs) == 2

    # 문서 메타데이터
    assert result.metadata.doc_version == "제2024-23호"
    assert result.metadata.revision_date == date(2024, 6, 27)

    # 빈 청크 없음
    assert all(c.content.strip() for c in chunks)
