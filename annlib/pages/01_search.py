"""논문 검색 페이지 — OpenAlex API (키워드 / 제목 / 저자 / DOI)"""

import streamlit as st

st.set_page_config(page_title="논문 검색 | annlib", page_icon="🔍", layout="wide")
st.title("🔍 논문 검색")

from annlib.core.openalex import search_papers, Paper

# ── 검색 모드 선택 ──────────────────────────────────────────────
mode_labels = {
    "keyword": "🔎 키워드",
    "title":   "📄 논문 제목",
    "author":  "👤 저자명",
    "doi":     "🔗 DOI",
}
mode_hints = {
    "keyword": "transformer attention mechanism",
    "title":   "Attention Is All You Need",
    "author":  "Yoshua Bengio",
    "doi":     "10.48550/arXiv.1706.03762",
}
mode_help = {
    "keyword": "제목·초록·키워드 전체에서 검색합니다.",
    "title":   "논문 제목에 포함된 단어로 검색합니다.",
    "author":  "저자 이름으로 검색합니다. (영문 권장)",
    "doi":     "DOI를 입력하면 해당 논문 한 편을 바로 가져옵니다.",
}

search_mode = st.radio(
    "검색 방식",
    options=list(mode_labels.keys()),
    format_func=lambda x: mode_labels[x],
    horizontal=True,
    key="search_mode",
)
st.caption(mode_help[search_mode])

# ── 검색 폼 ────────────────────────────────────────────────────
with st.form("search_form"):
    query = st.text_input(
        "검색어",
        placeholder=mode_hints[search_mode],
        key="query_input",
    )

    # DOI 모드는 추가 필터 불필요
    if search_mode != "doi":
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            year_from = st.number_input(
                "출판 연도 (이후)", min_value=1900, max_value=2030, value=2020
            )
        with col2:
            oa_only = st.checkbox("오픈 액세스만", value=False)
        with col3:
            per_page = st.selectbox("결과 수", [10, 20, 50], index=0)
        with col4:
            sort_by = st.selectbox(
                "정렬",
                ["cited_by_count:desc", "publication_date:desc"],
                format_func=lambda x: {
                    "cited_by_count:desc": "인용 수 높은 순",
                    "publication_date:desc": "최신 순",
                }[x],
            )
    else:
        year_from, oa_only, per_page, sort_by = 1900, False, 1, "cited_by_count:desc"

    submitted = st.form_submit_button("검색", type="primary", use_container_width=True)

# ── 검색 실행 ──────────────────────────────────────────────────
if submitted:
    if not query.strip():
        st.warning("검색어를 입력해 주세요.")
    else:
        with st.spinner(f"{mode_labels[search_mode]} 검색 중..."):
            try:
                papers = search_papers(
                    query=query.strip(),
                    search_mode=search_mode,
                    year_from=year_from,
                    oa_only=oa_only,
                    per_page=per_page,
                    sort=sort_by,
                )
            except Exception as e:
                st.error(f"검색 오류: {e}")
                papers = []

        if not papers:
            st.info("검색 결과가 없습니다. 검색어를 바꿔보세요.")
        else:
            st.success(f"{len(papers)}편 검색됨")
            st.session_state["search_results"] = papers
            st.session_state["search_query"] = query

# ── 결과 표시 ──────────────────────────────────────────────────
if "search_results" in st.session_state:
    papers: list[Paper] = st.session_state["search_results"]

    if "selected_papers" not in st.session_state:
        st.session_state["selected_papers"] = {}

    st.divider()

    for paper in papers:
        with st.container(border=True):
            col_info, col_btn = st.columns([5, 1])
            with col_info:
                st.markdown(f"**{paper.title}**")
                st.caption(
                    f"{paper.citation_str}  ·  "
                    f"인용 {paper.cited_by_count:,}회  ·  "
                    f"{'🔓 오픈 액세스' if paper.is_oa else '🔒 구독 전용'}"
                )
                if paper.doi:
                    st.caption(f"DOI: `{paper.doi}`")
                if paper.abstract:
                    with st.expander("초록 보기"):
                        st.write(paper.abstract[:800] + ("…" if len(paper.abstract) > 800 else ""))
            with col_btn:
                uid = paper.doi or paper.title
                already = uid in st.session_state["selected_papers"]
                if already:
                    if st.button("✓ 선택됨", key=f"sel_{uid}", use_container_width=True):
                        del st.session_state["selected_papers"][uid]
                        st.rerun()
                else:
                    if st.button("선택", key=f"sel_{uid}", type="primary", use_container_width=True):
                        st.session_state["selected_papers"][uid] = paper
                        st.rerun()

    # ── 선택 논문 요약 바 ──────────────────────────────────────
    selected = st.session_state.get("selected_papers", {})
    if selected:
        st.divider()
        with st.container(border=True):
            st.markdown(f"**선택된 논문 {len(selected)}편**")
            for p in selected.values():
                st.markdown(f"- {p.title} ({p.year})")
            if st.button("요약 페이지로 이동 →", type="primary", use_container_width=True):
                st.switch_page("pages/02_summarize.py")
