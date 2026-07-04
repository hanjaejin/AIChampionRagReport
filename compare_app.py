# file: compare_app.py
"""Streamlit 비교 앱 — 3탭(문서 업로드 / RAG 비교 / 평가 대시보드).

실행:
    streamlit run compare_app.py

API 키는 사이드바에서 사용자가 직접 입력하며 세션 메모리(st.session_state)에만
보관한다(저장·로깅 없음). 우선순위: UI 입력 > st.secrets > .env (config.py).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from chat_providers import OpenRouterProvider
from config import MissingSecretError, load_settings
from evaluation.benchmark import build_doc_key_map, load_benchmark
from evaluation.judge import LLMJudge
from evaluation.runner import run_benchmark, summarize
from ingest import ingest_markdown
from pipeline_factory import build_chat, build_components, build_pipelines

st.set_page_config(page_title="규정 RAG 비교", page_icon="📚", layout="wide")

# 사이드바에서 입력받을 LLM 키(환경변수명)와 라벨
_KEY_FIELDS = [
    ("OPENAI_API_KEY", "OpenAI (임베딩)"),
    ("OPENROUTER_API_KEY", "OpenRouter (챗)"),
    ("GEMINI_API_KEY", "Google Gemini (챗)"),
    ("COHERE_API_KEY", "Cohere (Rerank)"),
]


# ──────────────────────────────────────────────────────────────
# 사이드바: API 키 입력 + Provider 선택
# ──────────────────────────────────────────────────────────────
def _sidebar() -> dict:
    st.sidebar.header("🔑 API 키 입력")
    st.sidebar.caption(
        "키는 이 세션 메모리에만 보관되며 저장·로깅되지 않습니다. "
        "미입력 시 서버의 .env/secrets 값을 사용합니다."
    )
    overrides: dict[str, str] = {}
    for env_name, label in _KEY_FIELDS:
        value = st.sidebar.text_input(label, type="password", key=f"key_{env_name}")
        if value:
            overrides[env_name] = value

    st.sidebar.divider()
    provider = st.sidebar.radio(
        "챗 Provider", ["openrouter", "gemini"], key="provider",
        help="3개 파이프라인이 공유하는 답변 생성 모델의 Provider",
    )
    embedding_provider = st.sidebar.radio(
        "임베딩 Provider", ["gemini", "openai"], key="embedding_provider",
        help="질의/문서 임베딩 Provider (OpenRouter는 임베딩 미지원). "
        "적재와 질의는 동일 Provider여야 벡터 공간이 일치합니다.",
    )
    return {
        "overrides": overrides,
        "provider": provider,
        "embedding_provider": embedding_provider,
    }


def _get_settings(overrides: dict):
    return load_settings(overrides=overrides)


# ──────────────────────────────────────────────────────────────
# 탭 ①: 문서 업로드 (청킹 미리보기 → 임베딩 → 적재)
# ──────────────────────────────────────────────────────────────
def _tab_upload(settings, cfg) -> None:
    st.header("① 문서 업로드")
    st.write(
        "국가계약법령(법률·시행령·시행규칙)과 유사한 장/절/조 + 별표(표) 구조의 "
        "마크다운 규정 문서를 업로드하면, 청킹 미리보기 후 임베딩·Supabase 적재를 수행합니다."
    )

    # 공개 데모 보호: 관리자 비밀번호(secrets의 UPLOAD_PASSWORD가 설정된 경우에만 요구)
    from config import get_secret

    admin_pw = get_secret("UPLOAD_PASSWORD", cfg["overrides"])
    if admin_pw:
        entered = st.text_input("업로드 관리자 비밀번호", type="password")
        if entered != admin_pw:
            st.info("업로드는 관리자 비밀번호가 필요합니다.")
            return

    uploaded = st.file_uploader("규정 문서(.md) 업로드", type=["md", "markdown", "txt"])
    if not uploaded:
        return
    text = uploaded.read().decode("utf-8")

    # 청킹 미리보기(임베딩 비용 발생 전 확인)
    from chunker import ChunkingError, RegulationChunker

    try:
        preview = RegulationChunker().chunk(text)
    except ChunkingError as exc:
        st.error(f"청킹 실패: {exc}")
        return

    from collections import Counter

    counts = Counter(c.content_type for c in preview.chunks)
    st.success(
        f"청킹 미리보기: **{len(preview.chunks)}개 청크** "
        f"(문서: {preview.metadata.doc_title} / {preview.metadata.doc_version or '버전 미상'})"
    )
    st.write("유형별:", dict(counts))
    with st.expander("청크 샘플 5개 보기"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "type": c.content_type,
                        "라벨": c.article_no or (f"별표{c.annex_no}" if c.annex_no else "-"),
                        "embed_text(앞 60자)": c.embed_text[:60],
                    }
                    for c in preview.chunks[:5]
                ]
            ),
            use_container_width=True,
        )

    if not st.button("✅ 임베딩 후 Supabase에 적재", type="primary"):
        return
    from pipeline_factory import build_embedder
    from vector_store import SupabaseVectorStore

    try:
        settings.require("supabase_url", "supabase_service_key")
        # 문서 적재이므로 RETRIEVAL_DOCUMENT
        embedder = build_embedder(
            settings, cfg.get("embedding_provider", "gemini"),
            task_type="RETRIEVAL_DOCUMENT",
        )
    except MissingSecretError as exc:
        st.error(str(exc))
        return

    store = SupabaseVectorStore(
        url=settings.supabase_url, service_key=settings.supabase_service_key
    )
    bar = st.progress(0.0, text="시작")
    try:
        report = ingest_markdown(
            text, source_filename=uploaded.name, embedder=embedder, store=store,
            progress=lambda f, m: bar.progress(f, text=m),
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"적재 실패: {type(exc).__name__}: {exc}")
        return

    st.success(f"적재 완료 — {'교체' if report.replaced else '신규'}")
    st.json(
        {
            "문서": report.doc_title,
            "청크 수": report.chunk_count,
            "유형별": report.type_counts,
            "임베딩 토큰": report.embedding_tokens,
            "소요(초)": round(report.elapsed_sec, 1),
        }
    )


# ──────────────────────────────────────────────────────────────
# 탭 ②: RAG 비교 (3개 파이프라인 나란히)
# ──────────────────────────────────────────────────────────────
def _tab_compare(settings, cfg) -> None:
    st.header("② RAG 비교")
    st.write("질문을 입력하면 Naive / Advanced / Modular 3개 파이프라인 결과를 나란히 비교합니다.")

    question = st.text_input("질문", value="수의계약을 할 수 있는 경우는 언제인가요?")
    if not st.button("비교 실행", type="primary"):
        return
    try:
        components = build_components(
            settings, provider=cfg["provider"],
            embedding_provider=cfg["embedding_provider"],
        )
    except MissingSecretError as exc:
        st.error(str(exc))
        return

    pipelines = build_pipelines(components)
    cols = st.columns(3)
    labels = {"naive": "① Naive", "advanced": "② Advanced", "modular": "③ Modular"}
    for col, (name, pipeline) in zip(cols, pipelines.items()):
        with col:
            st.subheader(labels[name])
            with st.spinner("실행 중…"):
                try:
                    ans = pipeline.answer(question)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"{type(exc).__name__}: {exc}")
                    continue
            st.markdown(ans.answer)
            st.caption(
                f"토큰 {ans.input_tokens}+{ans.output_tokens} · {ans.elapsed_sec:.1f}s"
                + (f" · 경로:{ans.trace.get('route')}" if ans.trace.get("route") else "")
            )
            with st.expander("검색 근거"):
                for c in ans.contexts:
                    label = c.get("article_no") or (
                        f"별표{c.get('annex_no')}" if c.get("annex_no") else "-"
                    )
                    st.write(f"- **{label}** {c.get('article_title', '')}")


# ──────────────────────────────────────────────────────────────
# 탭 ③: 평가 대시보드 (벤치마크 → 지표·오류·비용)
# ──────────────────────────────────────────────────────────────
def _tab_dashboard(settings, cfg) -> None:
    st.header("③ 평가 대시보드")
    items = load_benchmark()
    st.write(f"벤치마크 QA {len(items)}문항 · 골드 라벨은 '문서단축키:조번호' 기준(예: 법률:제1조)")

    col1, col2 = st.columns(2)
    subset_n = col1.slider("실행 문항 수", 1, len(items), min(5, len(items)))
    use_judge = col2.checkbox("LLM 심판(faithfulness/correctness) 사용", value=False,
                              help="켜면 문항마다 심판 LLM을 1회 더 호출합니다(비용↑).")

    st.warning(
        "벤치마크 실행은 문항 × 3파이프라인 만큼 LLM/임베딩을 호출해 비용·시간이 듭니다.",
        icon="⚠️",
    )
    if not st.button("벤치마크 실행", type="primary"):
        return
    try:
        components = build_components(
            settings, provider=cfg["provider"],
            embedding_provider=cfg["embedding_provider"],
        )
    except MissingSecretError as exc:
        st.error(str(exc))
        return

    doc_key_map = build_doc_key_map(components.store.list_documents())
    pipelines = build_pipelines(components, doc_key_map=doc_key_map)
    judge = None
    if use_judge:
        # 자기채점 방지: 생성과 다른 모델을 심판으로
        judge_model = "openai/gpt-4o" if cfg["provider"] == "openrouter" else None
        try:
            judge = LLMJudge(build_chat(settings, "openrouter", judge_model))
        except MissingSecretError:
            st.warning("심판용 OpenRouter 키가 없어 심판 없이 진행합니다.")

    bar = st.progress(0.0, text="시작")
    results = run_benchmark(
        pipelines, items[:subset_n], judge=judge,
        rerank_model=components.rerank_model,
        progress=lambda f, m: bar.progress(f, text=m),
        doc_key_map=doc_key_map,
    )
    summary = summarize(results)

    # 요약 표
    st.subheader("파이프라인별 요약")
    rows = []
    for name, agg in summary.items():
        rows.append(
            {
                "파이프라인": name,
                "Recall@5": round(agg["recall@k"], 3),
                "MRR": round(agg["mrr"], 3),
                "nDCG@5": round(agg["ndcg@k"], 3),
                "Hit율": round(agg["hit_rate"], 3),
                "Faithful": round(agg["faithfulness"], 3) if agg["faithfulness"] is not None else "-",
                "Correct": round(agg["correctness"], 3) if agg["correctness"] is not None else "-",
                "평균지연(s)": round(agg["avg_latency_sec"], 2),
                "총비용($)": round(agg["total_cost_usd"], 5),
            }
        )
    summary_df = pd.DataFrame(rows).set_index("파이프라인")
    st.dataframe(summary_df, use_container_width=True)

    # 검색 지표 막대그래프
    st.subheader("검색 지표 비교")
    st.bar_chart(summary_df[["Recall@5", "MRR", "nDCG@5"]])

    # 오류 분포
    st.subheader("오류 분류 분포 (E1 검색 / E2 재정렬 / E3 생성)")
    err_rows = []
    for name, agg in summary.items():
        row = {"파이프라인": name}
        row.update(agg["error_dist"])
        err_rows.append(row)
    err_df = pd.DataFrame(err_rows).set_index("파이프라인").fillna(0)
    st.bar_chart(err_df)

    # 상세 결과
    with st.expander("문항별 상세 결과"):
        detail = pd.DataFrame(
            [
                {
                    "질문ID": r.item_id, "파이프라인": r.pipeline, "정답": ",".join(r.gold),
                    "Recall": round(r.recall, 2), "MRR": round(r.mrr, 2),
                    "오류": r.error_class, "경로": r.route or "-",
                    "토큰": r.input_tokens + r.output_tokens,
                    "비용$": round(r.cost_usd, 6),
                }
                for r in results
            ]
        )
        st.dataframe(detail, use_container_width=True)


# ──────────────────────────────────────────────────────────────
# 첫 화면 사용 설명서
# ──────────────────────────────────────────────────────────────
def _usage_guide() -> None:
    """앱 상단에 사용법을 안내하는 설명서(펼침 기본)."""
    with st.expander("📖 화면 사용 설명서 — 처음이라면 먼저 읽어주세요", expanded=True):
        st.markdown(
            """
**이 앱은?** 국가계약법령(법률·시행령·시행규칙)에 대한 질문을 **3가지 RAG 방식**
(Naive·Advanced·Modular)으로 답하고, 정확도·속도·비용을 비교합니다.

#### 1단계 · 왼쪽 사이드바에서 API 키 입력
- **Google Gemini**, **OpenRouter**, **Cohere** 키를 입력하세요.
  (키는 이 세션에만 보관되며 저장·로깅되지 않습니다.)
- 키가 없으면 각 서비스 사이트에서 무료로 발급받을 수 있습니다.

#### 2단계 · Provider 선택 (중요)
- **임베딩 Provider = `gemini`** 로 두세요. ⚠️ 저장된 문서가 Gemini로 임베딩돼 있어
  바꾸면 검색이 안 됩니다.
- **챗 Provider = `openrouter` 권장.** (Gemini 챗은 무료 과부하 시 503/오류가 날 수 있어요.)

#### 3단계 · 탭 사용
| 탭 | 하는 일 |
| --- | --- |
| **② RAG 비교** | 질문 입력 → **비교 실행** → 3개 방식 답변을 나란히 비교 (여기부터 시작 추천) |
| **③ 평가 대시보드** | 여러 질문으로 지표(정확도·비용) 자동 측정 |
| **① 문서 업로드** | 새 규정 문서(.md)를 벡터 DB에 적재 |

**예시 질문:** `수의계약을 할 수 있는 경우는 언제인가요?` · `제33조 내용 알려줘` ·
`입찰보증금은 언제 면제되나요?`

> 💡 **오류가 나면?** 대부분 특정 서비스의 일시 과부하(429/503)입니다. 잠시 후 다시
> 실행하거나, 챗 Provider를 OpenRouter로 바꿔보세요. 키 미입력 시 안내 메시지가 뜹니다.
            """
        )


# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────
def main() -> None:
    st.title("📚 규정 문서 RAG 아키텍처 비교")
    st.caption("Naive · Advanced · Modular RAG — 국가계약법령(법률·시행령·시행규칙) 대상")

    _usage_guide()

    cfg = _sidebar()
    settings = _get_settings(cfg["overrides"])

    tab1, tab2, tab3 = st.tabs(["① 문서 업로드", "② RAG 비교", "③ 평가 대시보드"])
    with tab1:
        _tab_upload(settings, cfg)
    with tab2:
        _tab_compare(settings, cfg)
    with tab3:
        _tab_dashboard(settings, cfg)


main()
