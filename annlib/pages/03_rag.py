"""RAG 질문 페이지 — Obsidian Vault 또는 기존 NotebookLM 노트북 대상"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import streamlit as st

from annlib import config
from annlib.core.notebooklm_client import is_logged_in
from annlib.core.obsidian import save_rag_result, load_rag_result


# ── 헬퍼 함수 ──────────────────────────────────────────────────

def _call_llm(prompt: str, cfg: dict) -> str:
    """설정된 LLM으로 단일 프롬프트를 호출합니다."""
    provider = cfg.get("llm_provider", "openai")
    api_key = cfg.get("llm_api_key", "")
    if not api_key:
        raise ValueError("LLM API 키가 설정되지 않았습니다.")

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return resp.choices[0].message.content

    elif provider == "gemini":
        from google import genai
        client = genai.Client(api_key=api_key)
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        ).text

    elif provider == "claude":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    raise ValueError(f"지원하지 않는 LLM: {provider}")


def _generate_followups(question: str, answer: str, cfg: dict) -> list[str]:
    """답변을 바탕으로 후속 질문 3개를 생성합니다."""
    prompt = f"""다음 질문과 답변을 읽고, 더 깊이 탐구할 수 있는 후속 질문 3개를 한국어로 작성해 주세요.

질문: {question}

답변:
{answer[:2000]}

응답 형식 (JSON):
{{"followups": ["후속 질문1", "후속 질문2", "후속 질문3"]}}"""

    try:
        raw = _call_llm(prompt, cfg)
        m = __import__("re").search(r"\{.*\}", raw, __import__("re").DOTALL)
        if m:
            data = json.loads(m.group())
            return data.get("followups", [])
    except Exception:
        pass
    return []


def _generate_cross_refs(
    question: str,
    answer: str,
    paper_titles: list[str],
    cfg: dict,
) -> list[dict]:
    """답변과 관련된 다른 논문들과의 연관성을 분석합니다."""
    if not paper_titles:
        return []

    titles_text = "\n".join(f"- {t}" for t in paper_titles[:30])
    prompt = f"""다음 질문과 답변을 읽고, 아래 논문 목록 중 관련된 논문과 그 연관성을 JSON으로 응답해 주세요.

질문: {question}

답변 요약:
{answer[:1000]}

논문 목록:
{titles_text}

응답 형식 (JSON, 최대 5개):
{{"cross_refs": [{{"title": "논문 제목", "relevance": "연관성 설명 (1문장)"}}]}}"""

    try:
        raw = _call_llm(prompt, cfg)
        m = __import__("re").search(r"\{.*\}", raw, __import__("re").DOTALL)
        if m:
            data = json.loads(m.group())
            return data.get("cross_refs", [])
    except Exception:
        pass
    return []


def _clean_excerpt(text: str) -> str:
    """마크다운 테이블, H1, 구분선을 제거하고 순수 텍스트만 반환합니다."""
    lines = []
    for line in text.splitlines():
        # 테이블 행 (|로 시작)
        if line.strip().startswith("|"):
            continue
        # H1 제목 (#으로 시작)
        if line.startswith("# "):
            continue
        # 구분선
        if re.match(r"^[-*]{3,}$", line.strip()):
            continue
        # annlib 서명 줄
        if line.strip().startswith("*annlib"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _paper_display_name(stem: str) -> str:
    """파일명 stem → 사람이 읽기 좋은 제목."""
    return re.sub(r"^\d{4}_", "", stem).replace("_", " ")


async def _load_notebooks():
    from notebooklm import NotebookLMClient
    client = await NotebookLMClient.from_storage()
    async with client:
        return await client.notebooks.list()


async def _query_notebooks(
    notebook_ids: list[str],
    nb_titles: dict[str, str],
    question: str,
) -> list[tuple[str, str]]:
    """여러 NotebookLM 노트북에 동일한 질문을 순차 전송합니다."""
    from notebooklm import NotebookLMClient
    results = []

    client = await NotebookLMClient.from_storage()
    async with client:
        for nb_id in notebook_ids:
            try:
                resp = await client.chat.ask(nb_id, question)
                if resp.answer:
                    results.append((nb_titles[nb_id], resp.answer))
            except Exception as e:
                results.append((nb_titles[nb_id], f"*오류: {e}*"))

    return results


# ── 페이지 설정 ────────────────────────────────────────────────

st.set_page_config(page_title="RAG 질문 | annlib", page_icon="🧠", layout="wide")
st.title("🧠 RAG 질문")
st.caption("수집된 논문 전체를 대상으로 자연어로 질문하세요.")

cfg = config.load()
nlm_ok = is_logged_in()

# ── RAG 소스 선택 ──────────────────────────────────────────────
source_options = []
source_labels  = {}

vault_path = cfg.get("vault_path", "")
md_files = []
if vault_path:
    md_files = [f for f in (Path(vault_path) / "Papers").glob("*.md")
                if not f.stem.startswith("_")]
    if md_files:
        source_options.append("obsidian")
        source_labels["obsidian"] = f"📁 Obsidian Vault ({len(md_files)}편)"

if nlm_ok:
    source_options.append("notebooklm")
    source_labels["notebooklm"] = "📓 NotebookLM 기존 노트북"

if not source_options:
    st.info(
        "사용 가능한 논문 소스가 없습니다.\n\n"
        "- **논문 요약** 페이지에서 논문을 먼저 저장하거나\n"
        "- **설정** 페이지에서 NotebookLM 로그인을 완료하세요."
    )
    st.stop()

rag_source = st.radio(
    "질문할 논문 소스",
    options=source_options,
    format_func=lambda x: source_labels[x],
    horizontal=True,
    key="rag_source",
)

st.divider()

# ══════════════════════════════════════════════════════════════
# A. Obsidian Vault 모드 (PageIndex)
# ══════════════════════════════════════════════════════════════
if rag_source == "obsidian":
    from annlib.core.pageindex import build_index, query_index

    col_info, col_btn = st.columns([4, 1])
    with col_info:
        st.markdown(f"**{len(md_files)}편** 논문이 인덱싱 대상입니다.")
    with col_btn:
        rebuild = st.button("인덱스 재빌드", use_container_width=True)

    if "rag_index" not in st.session_state or rebuild:
        with st.spinner("인덱스 빌드 중..."):
            try:
                st.session_state["rag_index"] = build_index(md_files, cfg)
                st.success(f"인덱스 준비 완료 — {len(md_files)}편")
            except Exception as e:
                st.error(f"인덱스 빌드 실패: {e}")
                st.stop()

    # 후속 질문 버튼 클릭 시 실행할 질문을 버튼 렌더링 전에 캡처
    exec_question = st.session_state.pop("_run_rag_question", None)
    if exec_question:
        st.session_state["q_obsidian"] = exec_question

    question = st.text_input(
        "질문",
        placeholder="attention mechanism을 비교한 논문들의 핵심 차이는?",
        key="q_obsidian",
    )

    button_clicked = st.button("질문하기", type="primary", disabled=not question, key="ask_obsidian")
    effective_q = exec_question or (question if button_clicked else None)

    # ── 쿼리 실행 ──────────────────────────────────────────────
    if effective_q:
        with st.spinner("탐색 중..."):
            try:
                result = query_index(st.session_state["rag_index"], effective_q, cfg)
            except Exception as e:
                st.error(f"오류: {e}")
                result = None

        if result:
            paper_titles = [r.title for r in st.session_state["rag_index"].roots]
            followups: list[str] = []
            cross_refs: list[dict] = []
            with st.spinner("후속 질문 및 연관성 분석 중..."):
                try:
                    followups = _generate_followups(effective_q, result.answer, cfg)
                except Exception:
                    pass
                try:
                    cross_refs = _generate_cross_refs(
                        effective_q, result.answer, paper_titles, cfg
                    )
                except Exception:
                    pass

            # 결과를 session_state에 저장 (후속 질문 버튼 rerun 후에도 유지)
            st.session_state["_rag_result"] = {
                "question": effective_q,
                "result": result,
                "followups": followups,
                "cross_refs": cross_refs,
            }

            try:
                save_rag_result(
                    effective_q, result, vault_path,
                    followups=followups, cross_refs=cross_refs,
                )
            except Exception:
                pass

    # ── 결과 표시 (session_state에서 항상 렌더링) ──────────────
    cached = st.session_state.get("_rag_result")
    if cached:
        result   = cached["result"]
        followups  = cached["followups"]
        cross_refs = cached["cross_refs"]

        st.subheader("답변")
        st.markdown(result.answer)

        if followups:
            st.divider()
            st.subheader("후속 질문 제안")
            cols = st.columns(len(followups))
            for i, fq in enumerate(followups):
                with cols[i]:
                    if st.button(fq, key=f"fq_{i}", use_container_width=True):
                        st.session_state["_run_rag_question"] = fq
                        st.rerun()

        if cross_refs:
            st.divider()
            st.subheader("다른 논문과의 연관성")
            for cr in cross_refs:
                st.markdown(f"- **{cr.get('title', '')}**: {cr.get('relevance', '')}")

        if result.references:
            st.divider()
            st.subheader("참고 논문")
            by_paper: dict[str, list] = {}
            for ref in result.references:
                by_paper.setdefault(ref.title, []).append(ref)

            PRIORITY = ["핵심 기여", "방법론", "주요 결과", "한계점"]
            for paper_stem, refs in by_paper.items():
                with st.container(border=True):
                    st.markdown(f"**{_paper_display_name(paper_stem)}**")
                    best = next(
                        (r for p in PRIORITY for r in refs if r.section == p),
                        refs[0],
                    )
                    excerpt = _clean_excerpt(best.excerpt)
                    if excerpt:
                        st.caption(best.section)
                        st.markdown(excerpt)


# ══════════════════════════════════════════════════════════════
# B. NotebookLM 기존 노트북 모드
# ══════════════════════════════════════════════════════════════
elif rag_source == "notebooklm":

    # 노트북 목록 로드 (캐시)
    if "nlm_notebooks" not in st.session_state:
        with st.spinner("NotebookLM 노트북 목록 불러오는 중..."):
            try:
                st.session_state["nlm_notebooks"] = asyncio.run(_load_notebooks())
            except Exception as e:
                st.error(f"노트북 목록 로드 실패: {e}")
                st.stop()

    notebooks = st.session_state["nlm_notebooks"]
    st.markdown(f"NotebookLM에 **{len(notebooks)}개** 노트북이 있습니다.")

    # 노트북 선택
    nb_options = {nb.id: nb.title for nb in notebooks}
    selected_ids = st.multiselect(
        "질문할 노트북 선택 (복수 선택 가능)",
        options=list(nb_options.keys()),
        format_func=lambda x: nb_options[x],
        default=list(nb_options.keys())[:5],  # 기본: 최근 5개
        key="nlm_selected",
    )

    if st.button("목록 새로고침", use_container_width=False):
        del st.session_state["nlm_notebooks"]
        st.rerun()

    st.divider()

    question = st.text_input(
        "질문",
        placeholder="single cell RNA sequencing 관련 논문들의 공통 방법론은?",
        key="q_nlm",
    )

    if st.button("질문하기", type="primary",
                 disabled=not (question and selected_ids), key="ask_nlm"):
        with st.spinner(f"{len(selected_ids)}개 노트북에 질문 중..."):
            try:
                answers = asyncio.run(
                    _query_notebooks(selected_ids, nb_options, question)
                )
            except Exception as e:
                st.error(f"오류: {e}")
                answers = []

        if answers:
            combined_answer = "\n\n---\n\n".join(
                f"**{t}**\n\n{a}" for t, a in answers
            )

            for nb_title, answer in answers:
                with st.expander(f"📓 {nb_title}", expanded=True):
                    st.markdown(answer)

            # 후속 질문 생성
            followups: list[str] = []
            with st.spinner("후속 질문 생성 중..."):
                try:
                    followups = _generate_followups(question, combined_answer, cfg)
                except Exception:
                    pass

            if followups:
                st.divider()
                st.subheader("후속 질문 제안")
                for fq in followups:
                    st.markdown(f"- {fq}")

            # Obsidian 저장
            if vault_path:
                try:
                    from annlib.core.pageindex import RAGResult
                    dummy = RAGResult(answer=combined_answer, references=[])
                    note_path = save_rag_result(
                        question, dummy, vault_path,
                        followups=followups,
                    )
                    st.caption(f"Obsidian 저장: `{note_path.name}`")
                except Exception:
                    pass


# ── 최근 질문 기록 ──────────────────────────────────────────────
if vault_path:
    rag_dir = Path(vault_path) / "RAG_Results"
    past = sorted(rag_dir.glob("*.md"), reverse=True)[:5] if rag_dir.exists() else []
    if past:
        st.divider()
        st.subheader("최근 질문 기록")
        for p in past:
            with st.expander(f"🗂 {p.stem}"):
                try:
                    rec = load_rag_result(p)
                    st.markdown(f"**질문:** {rec['question']}")
                    st.markdown("**답변:**")
                    st.markdown(rec["answer"])
                    if rec["followups"] and rec["followups"] != "없음":
                        st.markdown("**후속 질문:**")
                        st.markdown(rec["followups"])
                    if rec["cross_refs"] and rec["cross_refs"] != "없음":
                        st.markdown("**연관 논문:**")
                        st.markdown(rec["cross_refs"])
                    if rec["refs"] and rec["refs"] != "없음":
                        st.markdown("**참고 논문:**")
                        st.markdown(rec["refs"])
                except Exception as e:
                    st.caption(f"로드 실패: {e}")
