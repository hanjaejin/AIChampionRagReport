# file: chunker.py
"""장/절/조 계층 + 별표(표) 혼재 규정 문서의 구조 기반 청킹 모듈.

Phase 1 설계 문서(docs/design/phase1_architecture_chunking.md)의
청킹 규칙 R1~R9를 구현한다.

핵심 원칙:
    - 마크다운 헤딩(#)은 신뢰하지 않는다. 실제 문서의 헤딩 표기가
      불일치하므로 정규식 텍스트 패턴으로만 구조 경계를 인식한다.
    - 모든 청크는 content(답변 제시용 원문)와 embed_text(임베딩 입력)를
      분리해서 갖는다 (R7). 표 청크의 embed_text는 자연어 캡션이다 (R9).
    - 토큰 계수기는 의존성 주입으로 받는다. 기본 구현은 휴리스틱이며,
      정확한 토큰 수는 임베딩 단계(Phase 3)에서 API 응답으로 확정된다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal

logger = logging.getLogger(__name__)

TokenCounter = Callable[[str], int]
ContentType = Literal["article", "table", "deleted", "preamble"]

# ── 구조 경계 인식 패턴 (마크다운 헤딩 불신 원칙: 텍스트 패턴만 사용) ──
_HEADING_MARK_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_CHAPTER_RE = re.compile(r"^(제\d+장)\s*(.*)$")
_SECTION_RE = re.compile(r"^(제\d+절)\s*(.*)$")
_ARTICLE_RE = re.compile(r"^(제\d+조(?:의\d+)?)\s*\(([^)]*)\)\s*(.*)$")
_ANNEX_RE = re.compile(r"^\[별표\s*(\d+)\]\s*(.*)$")
_ARTICLE_REF_RE = re.compile(r"제\d+조(?:의\d+)?")
_REVISION_LINE_RE = re.compile(r"^(제정|개정|전부개정|일부개정)\b")
_DATE_RE = re.compile(r"(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})")
_VERSION_RE = re.compile(r"제\d{4}-\d+호")
_CLAUSE_MARK_RE = re.compile(r"^[①-⑳]")
_ITEM_MARK_RE = re.compile(r"^(\d+)\.\s")
_TABLE_SEP_RE = re.compile(r"^\|[\s:\-|]+\|?$")
_ANNEX_REF_PAREN_RE = re.compile(r"\([^()]*관련\)")


class ChunkingError(ValueError):
    """규정 문서로 인식할 수 없는 입력에 대한 예외 (조문 패턴 부재 등)."""


def default_token_counter(text: str) -> int:
    """한글 텍스트의 토큰 수를 대략 추정한다 (2자당 약 1토큰 휴리스틱).

    Args:
        text: 토큰 수를 추정할 텍스트.

    Returns:
        추정 토큰 수 (최소 1).
    """
    return max(1, len(text) // 2)


@dataclass(frozen=True)
class DocumentMetadata:
    """문서 수준 메타데이터 (제·개정 연혁에서 추출).

    Attributes:
        doc_title: 문서 제목 (첫 비공백 줄).
        doc_version: 최신 개정 호수 (예: "제2024-23호"). 없으면 None.
        revision_date: 최신 개정일. 없으면 None.
    """

    doc_title: str
    doc_version: str | None
    revision_date: date | None


@dataclass(frozen=True)
class Chunk:
    """청크 1건 — Phase 1 메타데이터 스키마의 파이썬 표현.

    Attributes:
        content: 답변 제시용 원문 (R7).
        embed_text: 임베딩 입력 텍스트 — 브레드크럼+본문, 표는 캡션 (R7·R9).
        content_type: article | table | deleted | preamble.
        chunk_index: 문서 내 순번 (0부터, 인접 청크 확장의 조회 키).
        token_count: embed_text 기준 추정 토큰 수.
        chapter_seq: 장 등장 순번 (장 번호 중복 대응 유니크 키).
        chapter_no: 장 번호 표기 (예: "제4장").
        chapter_title: 장 제목.
        section_no: 절 번호 표기 (절 없는 장은 None).
        section_title: 절 제목.
        article_no: 조 번호 표기 (예: "제36조") — 평가 골드 라벨 키.
        article_title: 조 제목.
        clause_range: 항 분할 시 항 범위 (예: "①~③"), 미분할 시 None.
        annex_no: 별표 번호 (표 청크만).
        related_articles: 별표↔조 상호참조 (예: ("제47조",)).
        table_caption: R9 캡션 원문 (표 청크만).
    """

    content: str
    embed_text: str
    content_type: ContentType
    chunk_index: int
    token_count: int
    chapter_seq: int | None = None
    chapter_no: str | None = None
    chapter_title: str | None = None
    section_no: str | None = None
    section_title: str | None = None
    article_no: str | None = None
    article_title: str | None = None
    clause_range: str | None = None
    annex_no: int | None = None
    related_articles: tuple[str, ...] = ()
    table_caption: str | None = None


@dataclass(frozen=True)
class ChunkingResult:
    """청킹 결과: 문서 메타데이터 + 순서 있는 청크 목록."""

    metadata: DocumentMetadata
    chunks: list[Chunk]


@dataclass
class _Context:
    """파싱 중의 장/절 상태 (내부 전용)."""

    chapter_seq: int | None = None
    chapter_no: str | None = None
    chapter_title: str | None = None
    section_no: str | None = None
    section_title: str | None = None


class RegulationChunker:
    """장/절/조 + 별표 구조 규정 문서를 청크 목록으로 변환한다.

    Args:
        token_counter: 토큰 계수 함수 (기본: 휴리스틱 추정기).
        max_tokens: 조문 분할 임계 토큰 수 (R2, 기본 800).
    """

    def __init__(
        self,
        token_counter: TokenCounter | None = None,
        max_tokens: int = 800,
    ) -> None:
        self._count_tokens = token_counter or default_token_counter
        self._max_tokens = max_tokens

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------
    def chunk(self, text: str) -> ChunkingResult:
        """규정 문서 텍스트를 청킹한다.

        Args:
            text: 규정 문서 전문 (마크다운 허용).

        Returns:
            문서 메타데이터와 청크 목록을 담은 ChunkingResult.

        Raises:
            ChunkingError: 조문 패턴(제N조)이 하나도 없어 규정 문서로
                인식할 수 없는 경우 (업로드 탭 오류 처리용).
        """
        lines = self._normalize(text)
        boundary = self._first_boundary_index(lines)
        if boundary is None:
            raise ChunkingError(
                "조문 패턴(제N조)을 찾을 수 없습니다. "
                "장/절/조 구조의 규정 문서인지 확인하세요."
            )

        preamble_lines = lines[:boundary]
        metadata = self._parse_metadata(preamble_lines)
        protos: list[dict] = []

        preamble_text = _clean("\n".join(preamble_lines))
        if preamble_text:
            protos.append(
                {
                    "content": preamble_text,
                    "embed_text": f"[{metadata.doc_title} > 제·개정 연혁]\n{preamble_text}",
                    "content_type": "preamble",
                }
            )

        protos.extend(self._parse_body(lines[boundary:]))

        if not any(p["content_type"] in ("article", "deleted") for p in protos):
            raise ChunkingError("조문을 하나도 추출하지 못했습니다.")

        chunks = [
            Chunk(
                chunk_index=i,
                token_count=self._count_tokens(p["embed_text"]),
                **p,
            )
            for i, p in enumerate(protos)
        ]
        logger.info("청킹 완료: %s → 청크 %d건", metadata.doc_title, len(chunks))
        return ChunkingResult(metadata=metadata, chunks=chunks)

    # ------------------------------------------------------------------
    # 전처리 (R8)
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(text: str) -> list[str]:
        """개행 통일, <br> 치환, 헤딩 마크 제거를 수행한 줄 목록을 반환한다."""
        text = text.replace("\r\n", "\n")
        text = _BR_RE.sub(" ", text)
        return [_HEADING_MARK_RE.sub("", line).rstrip() for line in text.split("\n")]

    @staticmethod
    def _first_boundary_index(lines: list[str]) -> int | None:
        """장/절/조/별표 중 가장 먼저 나오는 구조 경계의 줄 번호를 찾는다."""
        has_article = False
        first: int | None = None
        for i, line in enumerate(lines):
            if _ARTICLE_RE.match(line):
                has_article = True
                if first is None:
                    first = i
            elif first is None and (
                _CHAPTER_RE.match(line)
                or _SECTION_RE.match(line)
                or _ANNEX_RE.match(line)
            ):
                first = i
        return first if has_article else None

    # ------------------------------------------------------------------
    # 문서 메타데이터 (R5)
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_metadata(preamble_lines: list[str]) -> DocumentMetadata:
        """머리말에서 제목·최신 개정 호수·개정일을 추출한다."""
        title = next((ln.strip() for ln in preamble_lines if ln.strip()), "제목 미상")
        version: str | None = None
        revision: date | None = None
        for line in preamble_lines:
            if not _REVISION_LINE_RE.match(line.strip()):
                continue
            if m := _DATE_RE.search(line):
                revision = date(int(m[1]), int(m[2]), int(m[3]))
            if m := _VERSION_RE.search(line):
                version = m.group()
        return DocumentMetadata(doc_title=title, doc_version=version, revision_date=revision)

    # ------------------------------------------------------------------
    # 본문 파싱: 장/절 상태를 유지하며 조문·별표 블록 수집
    # ------------------------------------------------------------------
    def _parse_body(self, lines: list[str]) -> list[dict]:
        protos: list[dict] = []
        ctx = _Context()
        chapter_count = 0
        article: dict | None = None  # 수집 중인 조문 블록
        annex: dict | None = None  # 수집 중인 별표 블록

        def flush() -> None:
            nonlocal article, annex
            if article is not None:
                protos.extend(self._emit_article(article))
                article = None
            if annex is not None:
                protos.append(self._emit_annex(annex))
                annex = None

        for line in lines:
            stripped = line.strip()
            if m := _CHAPTER_RE.match(stripped):
                flush()
                chapter_count += 1
                ctx = _Context(
                    chapter_seq=chapter_count,
                    chapter_no=m[1],
                    chapter_title=m[2].strip(),
                )
            elif m := _SECTION_RE.match(stripped):
                flush()
                ctx.section_no, ctx.section_title = m[1], m[2].strip()
            elif m := _ARTICLE_RE.match(stripped):
                flush()
                article = {
                    "ctx": _Context(**vars(ctx)),
                    "article_no": m[1],
                    "article_title": m[2].strip(),
                    "rest": m[3].strip(),
                    "body": [],
                }
            elif m := _ANNEX_RE.match(stripped):
                flush()
                annex = {"annex_no": int(m[1]), "heading": stripped, "body": []}
            elif article is not None:
                article["body"].append(line)
            elif annex is not None:
                annex["body"].append(line)
        flush()
        return protos

    # ------------------------------------------------------------------
    # 조문 청크 생성 (R1·R2·R4·R7)
    # ------------------------------------------------------------------
    def _emit_article(self, block: dict) -> list[dict]:
        ctx: _Context = block["ctx"]
        header = f"{block['article_no']}({block['article_title']})"
        header_line = f"{header} {block['rest']}".strip()
        body = _clean("\n".join(block["body"]))

        # R4: 본문 없이 "삭제"만 남은 조문
        if not body and block["rest"].startswith("삭제"):
            return [
                self._article_proto(ctx, block, header_line, clause_range=None, deleted=True)
            ]

        content = f"{header_line}\n{body}".strip() if body else header_line
        if self._count_tokens(content) <= self._max_tokens:
            return [
                self._article_proto(
                    ctx, block, content, clause_range=None, deleted=False
                )
            ]

        # R2: 항(①) 단위 분할 + 조 헤더 반복
        groups = self._split_clauses(header_line, body)
        if groups is None:
            logger.warning(
                "%s: %d토큰 초과이나 항(①)/호(1.) 구분이 없어 분할하지 않습니다.",
                header,
                self._max_tokens,
            )
            return [
                self._article_proto(ctx, block, content, clause_range=None, deleted=False)
            ]
        return [
            self._article_proto(ctx, block, text, clause_range=rng, deleted=False)
            for text, rng in groups
        ]

    def _split_clauses(
        self, header_line: str, body: str
    ) -> list[tuple[str, str]] | None:
        """본문을 항(①) 단위로, 항이 없으면 호(1.) 단위로 그리디 분할한다.

        항/호 표식이 모두 없으면 None을 반환한다 (분할 불가).
        """
        for mark_re, label in (
            (_CLAUSE_MARK_RE, _clause_label),
            (_ITEM_MARK_RE, _item_label),
        ):
            segmented = _segment_paragraphs(body, mark_re)
            if segmented is not None:
                intro, segments = segmented
                return self._group_segments(header_line, intro, segments, label)
        return None

    def _group_segments(
        self,
        header_line: str,
        intro: list[str],
        segments: list[str],
        label: Callable[[str], str],
    ) -> list[tuple[str, str]]:
        """세그먼트를 토큰 예산에 맞게 그리디 그룹핑하고 범위 라벨을 붙인다."""
        groups: list[list[str]] = []
        current: list[str] = []
        for segment in segments:
            candidate = "\n".join([header_line, *intro, *current, segment])
            if current and self._count_tokens(candidate) > self._max_tokens:
                groups.append(current)
                current = [segment]
            else:
                current.append(segment)
        groups.append(current)

        results: list[tuple[str, str]] = []
        for i, group in enumerate(groups):
            parts = [header_line, *intro, *group] if i == 0 else [header_line, *group]
            marks = [label(seg) for seg in group]
            rng = marks[0] if len(marks) == 1 else f"{marks[0]}~{marks[-1]}"
            results.append((_clean("\n".join(parts)), rng))
        return results

    @staticmethod
    def _article_proto(
        ctx: _Context,
        block: dict,
        content: str,
        clause_range: str | None,
        deleted: bool,
    ) -> dict:
        breadcrumb_parts = [
            f"{ctx.chapter_no} {ctx.chapter_title}".strip() if ctx.chapter_no else None,
            f"{ctx.section_no} {ctx.section_title}".strip() if ctx.section_no else None,
            f"{block['article_no']}({block['article_title']})",
        ]
        breadcrumb = "[" + " > ".join(p for p in breadcrumb_parts if p) + "]"
        return {
            "content": content,
            "embed_text": f"{breadcrumb}\n{content}",
            "content_type": "deleted" if deleted else "article",
            "chapter_seq": ctx.chapter_seq,
            "chapter_no": ctx.chapter_no,
            "chapter_title": ctx.chapter_title,
            "section_no": ctx.section_no,
            "section_title": ctx.section_title,
            "article_no": block["article_no"],
            "article_title": block["article_title"],
            "clause_range": clause_range,
        }

    # ------------------------------------------------------------------
    # 별표 청크 생성 (R3·R9)
    # ------------------------------------------------------------------
    def _emit_annex(self, block: dict) -> dict:
        heading: str = block["heading"]
        body = _clean("\n".join(block["body"]))
        related = tuple(dict.fromkeys(_ARTICLE_REF_RE.findall(heading)))
        title = self._annex_title(heading, block["body"])
        caption = self._build_caption(block["annex_no"], title, related, block["body"])
        content = f"{heading}\n{body}".strip()
        return {
            "content": content,
            "embed_text": caption,
            "content_type": "table",
            "annex_no": block["annex_no"],
            "related_articles": related,
            "table_caption": caption,
        }

    @staticmethod
    def _annex_title(heading: str, body_lines: list[str]) -> str:
        """별표 제목: 헤딩 잔여 텍스트 우선, 없으면 본문 첫 일반 줄."""
        rest = _ANNEX_RE.match(heading)[2]
        rest = _ANNEX_REF_PAREN_RE.sub("", rest).strip("() ").strip()
        if rest:
            return rest
        return next(
            (
                ln.strip()
                for ln in body_lines
                if ln.strip() and not ln.strip().startswith("|")
            ),
            "",
        )

    @staticmethod
    def _build_caption(
        annex_no: int,
        title: str,
        related: tuple[str, ...],
        body_lines: list[str],
    ) -> str:
        """R9 규칙 기반 자연어 캡션: 제목 + 관련 조문 + 표 열 헤더."""
        caption = f"별표 {annex_no}({title})" if title else f"별표 {annex_no}"
        if related:
            caption += f", {'·'.join(related)} 관련 서식"
        headers = _table_headers(body_lines)
        if headers:
            caption += f", 항목: {', '.join(headers)}"
        return caption


def _clause_label(segment: str) -> str:
    """항 세그먼트의 범위 라벨을 반환한다 (예: "①")."""
    return segment.strip()[0]


def _item_label(segment: str) -> str:
    """호 세그먼트의 범위 라벨을 반환한다 (예: "제3호")."""
    return f"제{_ITEM_MARK_RE.match(segment.strip())[1]}호"


def _segment_paragraphs(
    body: str, mark_re: re.Pattern[str]
) -> tuple[list[str], list[str]] | None:
    """본문을 표식(mark_re) 기준 세그먼트로 나눈다.

    Args:
        body: 조문 본문 텍스트.
        mark_re: 세그먼트 시작을 나타내는 줄 선두 패턴.

    Returns:
        (표식 이전 도입부 줄 목록, 표식 세그먼트 목록). 표식이 없으면 None.
    """
    intro: list[str] = []
    segments: list[str] = []
    for para in body.split("\n"):
        if mark_re.match(para.strip()):
            segments.append(para)
        elif segments:
            segments[-1] += "\n" + para
        else:
            intro.append(para)
    return (intro, segments) if segments else None


def _table_headers(body_lines: list[str]) -> list[str]:
    """마크다운 표의 첫 헤더 행에서 열 이름을 추출한다."""
    for i, line in enumerate(body_lines[:-1]):
        stripped = line.strip()
        if stripped.startswith("|") and _TABLE_SEP_RE.match(body_lines[i + 1].strip()):
            return [cell.strip() for cell in stripped.strip("|").split("|") if cell.strip()]
    return []


def _clean(text: str) -> str:
    """연속 빈 줄을 하나로 줄이고 앞뒤 공백을 제거한다."""
    return re.sub(r"\n{3,}", "\n\n", text).strip()
