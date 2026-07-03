# file: load_to_supabase.py
"""문서를 Supabase에 적재하는 CLI 진입점.

사용법:
    python load_to_supabase.py                  # 기본: 개인정보지침.md
    python load_to_supabase.py 다른규정.md
    python load_to_supabase.py --dry-run        # 청킹만, 임베딩/적재 없이 미리보기

키/접속정보는 .env(또는 환경변수)에서 로드하며 하드코딩하지 않는다.
실제 적재 로직은 ingest.ingest_markdown 을 재사용한다(업로드 탭과 동일 파이프라인).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from chunker import ChunkingError, RegulationChunker
from config import MissingSecretError, load_settings
from ingest import ingest_markdown
from pipeline_factory import DEFAULT_EMBEDDING_PROVIDER, build_embedder
from vector_store import SupabaseVectorStore

logger = logging.getLogger(__name__)

DEFAULT_DOC = "개인정보지침.md"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="규정 문서를 Supabase(pgvector)에 적재")
    parser.add_argument(
        "path", nargs="?", default=DEFAULT_DOC, help=f"적재할 md 파일 (기본: {DEFAULT_DOC})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="청킹 결과만 출력하고 임베딩·적재는 건너뜀",
    )
    parser.add_argument(
        "--embedding",
        choices=["gemini", "openai"],
        default=DEFAULT_EMBEDDING_PROVIDER,
        help=f"임베딩 Provider (기본: {DEFAULT_EMBEDDING_PROVIDER})",
    )
    return parser.parse_args(argv)


def _print_progress(frac: float, msg: str) -> None:
    print(f"[{int(frac * 100):3d}%] {msg}")


def run(argv: list[str] | None = None) -> int:
    """CLI 실행 본체.

    Args:
        argv: 명령행 인자(테스트 주입용, 기본은 sys.argv).

    Returns:
        프로세스 종료 코드(0 성공, 1 실패).
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)

    doc_path = Path(args.path)
    if not doc_path.exists():
        logger.error("파일을 찾을 수 없습니다: %s", doc_path)
        return 1
    text = doc_path.read_text(encoding="utf-8")

    # --dry-run: 외부 서비스 없이 청킹 미리보기
    if args.dry_run:
        try:
            result = RegulationChunker().chunk(text)
        except ChunkingError as exc:
            logger.error("청킹 실패: %s", exc)
            return 1
        from collections import Counter

        counts = Counter(c.content_type for c in result.chunks)
        print(f"문서: {result.metadata.doc_title} / {result.metadata.doc_version}")
        print(f"총 청크: {len(result.chunks)}  유형별: {dict(counts)}")
        return 0

    try:
        settings = load_settings()
        settings.require("supabase_url", "supabase_service_key")
        # 문서 적재이므로 RETRIEVAL_DOCUMENT task_type 사용(Gemini)
        embedder = build_embedder(
            settings, args.embedding, task_type="RETRIEVAL_DOCUMENT"
        )
    except MissingSecretError as exc:
        logger.error("%s", exc)
        return 1

    store = SupabaseVectorStore(
        url=settings.supabase_url, service_key=settings.supabase_service_key
    )

    try:
        report = ingest_markdown(
            text,
            source_filename=doc_path.name,
            embedder=embedder,
            store=store,
            progress=_print_progress,
        )
    except ChunkingError as exc:
        logger.error("청킹 실패(규정 문서 형식 아님): %s", exc)
        return 1

    action = "교체" if report.replaced else "신규"
    print("\n===== 적재 완료 =====")
    print(f"문서       : {report.doc_title} ({action})")
    print(f"doc_id     : {report.doc_id}")
    print(f"청크 수    : {report.chunk_count}  유형별: {report.type_counts}")
    print(f"임베딩 토큰: {report.embedding_tokens:,}  모델: {report.embedding_version}")
    print(f"소요 시간  : {report.elapsed_sec:.1f}초")
    return 0


if __name__ == "__main__":
    sys.exit(run())
