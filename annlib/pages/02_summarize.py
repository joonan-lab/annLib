"""논문 요약 페이지 — 검색 결과 또는 PDF 직접 업로드"""

import asyncio
import io
import re
from pathlib import Path

import streamlit as st

from annlib import config
from annlib.core.notebooklm_client import is_logged_in
from annlib.core.obsidian import save_paper_note

# ── 헬퍼 함수 (탭보다 먼저 정의) ──────────────────────────────

def _extract_pdf_meta(uploaded_file) -> dict:
    """업로드된 PDF 또는 BytesIO에서 텍스트와 메타데이터를 추출합니다."""
    try:
        from PyPDF2 import PdfReader
        uploaded_file.seek(0)
        data = uploaded_file.read()
        reader = PdfReader(io.BytesIO(data))
        uploaded_file.seek(0)

        meta    = reader.metadata or {}
        title   = str(meta.get("/Title",  "")).strip()
        authors = str(meta.get("/Author", "")).strip()

        pages = reader.pages[:30]
        text  = "\n".join(p.extract_text() or "" for p in pages)

        if not title and text:
            first_line = text.strip().split("\n")[0][:120]
            title = first_line if len(first_line) > 10 else ""

        years = re.findall(r'\b(19[5-9]\d|20[0-2]\d)\b', text[:2000])
        year  = int(years[0]) if years else 2024

        doi_m = re.search(r'10\.\d{4,}/\S+', text[:3000])
        doi   = doi_m.group(0).rstrip(".,;)") if doi_m else ""

        return {"title": title, "authors": authors, "year": year, "doi": doi, "text": text}
    except Exception:
        return {"title": "", "authors": "", "year": 2024, "doi": "", "text": ""}


def _split_authors(authors_str: str) -> list[str]:
    if not authors_str:
        return []
    sep = ";" if ";" in authors_str else ","
    return [a.strip() for a in authors_str.split(sep) if a.strip()]


def _render_summary_options(prefix: str):
    """요약 방식 선택 UI (두 탭 공통)."""
    nlm_available = is_logged_in()
    mode_options = ["llm"]
    mode_labels  = {
        "llm": f"🤖 LLM 직접 요약  ({cfg.get('llm_provider', '미설정').upper()})"
    }
    if nlm_available:
        mode_options.append("notebooklm")
        mode_labels["notebooklm"] = "📓 Google NotebookLM"
    else:
        st.caption("NotebookLM을 사용하려면 설정 페이지에서 `notebooklm login`을 완료하세요.")

    st.session_state[f"mode_{prefix}"] = st.radio(
        "요약 방식",
        options=mode_options,
        format_func=lambda x: mode_labels[x],
        horizontal=True,
        key=f"radio_mode_{prefix}",
    )

    if st.session_state[f"mode_{prefix}"] == "notebooklm":
        col1, col2 = st.columns(2)
        with col1:
            st.session_state[f"podcast_{prefix}"] = st.checkbox(
                "🎙️ 팟캐스트 생성", key=f"chk_podcast_{prefix}",
                help="논문 내용을 MP3 오디오로 생성합니다. 약 3-5분 소요."
            )
        with col2:
            st.session_state[f"keep_{prefix}"] = st.checkbox(
                "📓 NotebookLM 소스 유지", key=f"chk_keep_{prefix}",
            )


def _run_summarize(papers, source: str, texts: list | None = None, key_prefix: str = ""):
    """논문 목록을 순차 요약하고 Obsidian에 저장합니다."""
    from annlib.core.pdf_fetcher import fetch_pdf
    from annlib.core.notebooklm import summarize_paper

    mode    = st.session_state.get(f"mode_{key_prefix}", "llm")
    podcast = st.session_state.get(f"podcast_{key_prefix}", False)
    keep    = st.session_state.get(f"keep_{key_prefix}", False)
    results = []

    for idx, paper in enumerate(papers):
        with st.status(f"처리 중: {paper.title[:55]}…", expanded=True) as status:

            # 콘텐츠 준비
            if texts:
                content = texts[idx]
                st.write("✅ PDF 텍스트 준비됨")
            else:
                st.write("📥 PDF 수집 중…")
                try:
                    content = asyncio.run(fetch_pdf(paper))
                    st.write("✅ PDF 수집 완료")
                except Exception as e:
                    st.write(f"⚠️ PDF 수집 실패 ({e}), 초록으로 대체합니다.")
                    content = paper.abstract or ""

            # 요약
            label = "📓 NotebookLM 요약 중…" if mode == "notebooklm" \
                    else f"🤖 {cfg.get('llm_provider','').upper()} 요약 중…"
            st.write(label)
            try:
                summary = summarize_paper(
                    paper, content, cfg,
                    mode=mode,
                    generate_podcast=podcast,
                    keep_notebook=keep,
                )
                st.write("✅ 요약 완료")
            except Exception as e:
                st.write(f"❌ 요약 실패: {e}")
                status.update(label=f"실패: {paper.title[:45]}", state="error")
                continue

            # Obsidian 저장
            st.write("💾 Obsidian 저장 중…")
            try:
                note_path = save_paper_note(paper, summary, cfg["vault_path"], source=source)
                st.write(f"✅ 저장: `{note_path.name}`")
                results.append((paper, note_path))
                status.update(label=f"완료: {paper.title[:45]}", state="complete")
            except Exception as e:
                st.write(f"❌ 저장 실패: {e}")
                status.update(label=f"저장 실패: {paper.title[:45]}", state="error")

    if results:
        st.success(f"{len(results)}편 완료!")
        st.balloons()

        podcast_dir = Path.home() / ".annlib" / "podcasts"
        if podcast_dir.exists() and any(podcast_dir.glob("*.mp3")):
            st.info(f"🎙️ 팟캐스트 저장 위치: `{podcast_dir}`")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("더 검색하기", key=f"more_{key_prefix}"):
                st.switch_page("pages/01_search.py")
        with col2:
            if st.button("RAG 질문하기 →", key=f"rag_{key_prefix}"):
                st.switch_page("pages/03_rag.py")


# ── 페이지 ──────────────────────────────────────────────────────

st.set_page_config(page_title="논문 요약 | annlib", page_icon="📝", layout="wide")
st.title("📝 논문 요약")

cfg = config.load()

if not cfg.get("vault_path"):
    st.warning("Vault 경로가 설정되지 않았습니다. 설정 페이지를 먼저 완료해 주세요.")
    st.stop()

tab_search, tab_pdf, tab_folder = st.tabs([
    "🔍 검색 결과 요약",
    "📄 PDF 직접 업로드",
    "📁 폴더 일괄 처리",
])


# ══════════════════════════════════════════════════════════════
# TAB 1 — 검색 결과 요약
# ══════════════════════════════════════════════════════════════
with tab_search:
    selected: dict = st.session_state.get("selected_papers", {})

    if not selected:
        st.info("먼저 **논문 검색** 페이지에서 논문을 선택해 주세요.")
        if st.button("검색 페이지로 이동", key="go_search"):
            st.switch_page("pages/01_search.py")
    else:
        st.markdown(f"**{len(selected)}편** 논문을 요약합니다.")
        for p in selected.values():
            st.markdown(f"- {p.title} ({p.year})")

        st.divider()
        _render_summary_options("search")

        if st.button("요약 시작", type="primary", use_container_width=True, key="run_search"):
            _run_summarize(list(selected.values()), source="openalex", key_prefix="search")
            st.session_state["selected_papers"] = {}


# ══════════════════════════════════════════════════════════════
# TAB 2 — PDF 직접 업로드
# ══════════════════════════════════════════════════════════════
with tab_pdf:
    st.markdown(
        "PDF 파일을 업로드하면 텍스트를 추출하고 동일한 형식의 Markdown 노트를 생성합니다."
    )

    uploaded_files = st.file_uploader(
        "PDF 파일 선택 (복수 가능)",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
    )

    if uploaded_files:
        st.divider()
        st.subheader("논문 정보 확인")
        st.caption("PDF에서 자동 추출된 정보를 확인하고 필요하면 수정하세요.")

        paper_metas = []
        for i, f in enumerate(uploaded_files):
            with st.expander(f"📄 {f.name}", expanded=(i == 0)):
                meta = _extract_pdf_meta(f)

                col1, col2 = st.columns(2)
                with col1:
                    title   = st.text_input("제목",   value=meta["title"],   key=f"title_{i}")
                    authors = st.text_input("저자",   value=meta["authors"], key=f"authors_{i}")
                with col2:
                    year = st.number_input("연도", value=meta["year"],
                                           min_value=1900, max_value=2030, key=f"year_{i}")
                    doi  = st.text_input("DOI (선택)", value=meta["doi"],   key=f"doi_{i}")

                paper_metas.append({
                    "file": f, "text": meta["text"],
                    "title": title, "authors": authors, "year": year, "doi": doi,
                })

        st.divider()
        _render_summary_options("pdf")

        if st.button("요약 시작", type="primary", use_container_width=True, key="run_pdf"):
            from annlib.core.openalex import Paper

            papers = []
            texts  = []
            for m in paper_metas:
                papers.append(Paper(
                    title=m["title"] or m["file"].name,
                    doi=m["doi"],
                    year=int(m["year"]),
                    authors=_split_authors(m["authors"]),
                    is_oa=False,
                ))
                texts.append(m["text"])

            _run_summarize(papers, source="pdf_upload", texts=texts, key_prefix="pdf")


# ══════════════════════════════════════════════════════════════
# TAB 3 — 폴더 일괄 처리
# ══════════════════════════════════════════════════════════════
with tab_folder:
    st.markdown(
        "로컬 폴더의 PDF 파일을 모두 스캔합니다. "
        "이미 Obsidian Vault에 저장된 논문은 자동으로 제외됩니다."
    )

    folder_input = st.text_input(
        "PDF 폴더 경로",
        placeholder="/Users/name/Downloads/papers  또는  C:\\Users\\name\\papers",
        key="folder_path_input",
        help="PDF 파일이 들어있는 폴더의 절대 경로를 입력하세요.",
    )

    scan_btn = st.button("🔍 폴더 스캔", disabled=not folder_input.strip(), key="scan_folder")

    if scan_btn or st.session_state.get("_folder_scanned"):
        folder_path = Path(folder_input.strip()).expanduser()

        if not folder_path.exists() or not folder_path.is_dir():
            st.error(f"폴더를 찾을 수 없습니다: `{folder_path}`")
            st.session_state.pop("_folder_scanned", None)
        else:
            # PDF 목록 스캔
            pdf_files = sorted(folder_path.glob("*.pdf"))
            if not pdf_files:
                st.warning("폴더에 PDF 파일이 없습니다.")
                st.session_state.pop("_folder_scanned", None)
            else:
                st.session_state["_folder_scanned"] = True

                # Vault 인덱스 빌드 (중복 체크용)
                vault_papers_dir = Path(cfg["vault_path"]) / "Papers"
                vault_stems: set[str] = set()
                if vault_papers_dir.exists():
                    for md in vault_papers_dir.glob("*.md"):
                        if not md.stem.startswith("_"):
                            norm = re.sub(r'[^a-z0-9가-힣]+', ' ',
                                          re.sub(r'^\d{4}_', '', md.stem).lower()).strip()
                            vault_stems.add(norm)

                def _is_duplicate(pdf_name: str) -> bool:
                    norm = re.sub(r'[^a-z0-9가-힣]+', ' ',
                                  pdf_name.replace(".pdf", "").lower()).strip()
                    # 정확 매칭
                    if norm in vault_stems:
                        return True
                    # 부분 매칭 (PDF 제목 단어 70% 이상 일치)
                    words = norm.split()
                    if len(words) < 2:
                        return False
                    for vs in vault_stems:
                        matched = sum(1 for w in words if w in vs)
                        if matched / len(words) >= 0.7:
                            return True
                    return False

                # 파일별 상태 분류
                new_pdfs = []
                dup_pdfs = []
                for p in pdf_files:
                    if _is_duplicate(p.name):
                        dup_pdfs.append(p)
                    else:
                        new_pdfs.append(p)

                st.markdown(
                    f"**총 {len(pdf_files)}개** PDF 발견 — "
                    f"🆕 신규 **{len(new_pdfs)}개** · "
                    f"✅ 이미 처리됨 **{len(dup_pdfs)}개**"
                )

                # 이미 처리된 파일 목록 (접힘)
                if dup_pdfs:
                    with st.expander(f"✅ 이미 Vault에 있는 파일 {len(dup_pdfs)}개 (건너뜀)"):
                        for p in dup_pdfs:
                            st.markdown(f"- `{p.name}`")

                if not new_pdfs:
                    st.info("모든 PDF가 이미 처리되었습니다.")
                else:
                    st.divider()
                    st.subheader(f"🆕 처리할 파일 선택 ({len(new_pdfs)}개)")

                    # 파일별 선택 체크박스
                    if "folder_selection" not in st.session_state:
                        st.session_state["folder_selection"] = {
                            str(p): True for p in new_pdfs
                        }

                    # 새 스캔이면 선택 초기화
                    if scan_btn:
                        st.session_state["folder_selection"] = {
                            str(p): True for p in new_pdfs
                        }

                    col_all, col_none = st.columns([1, 1])
                    with col_all:
                        if st.button("전체 선택", key="sel_all_folder"):
                            st.session_state["folder_selection"] = {
                                str(p): True for p in new_pdfs
                            }
                            st.rerun()
                    with col_none:
                        if st.button("전체 해제", key="sel_none_folder"):
                            st.session_state["folder_selection"] = {
                                str(p): False for p in new_pdfs
                            }
                            st.rerun()

                    for p in new_pdfs:
                        checked = st.checkbox(
                            p.name,
                            value=st.session_state["folder_selection"].get(str(p), True),
                            key=f"chk_folder_{p.name}",
                        )
                        st.session_state["folder_selection"][str(p)] = checked

                    selected_pdfs = [
                        p for p in new_pdfs
                        if st.session_state["folder_selection"].get(str(p), True)
                    ]

                    if selected_pdfs:
                        st.divider()
                        st.markdown(f"**{len(selected_pdfs)}개** 파일을 처리합니다.")
                        _render_summary_options("folder")

                        if st.button("요약 시작", type="primary",
                                     use_container_width=True, key="run_folder"):
                            from annlib.core.openalex import Paper

                            papers_to_run = []
                            texts_to_run  = []

                            for pdf_path in selected_pdfs:
                                with open(pdf_path, "rb") as f:
                                    raw = f.read()
                                buf = io.BytesIO(raw)
                                buf.seek = buf.seek  # type: ignore
                                meta = _extract_pdf_meta(buf)

                                papers_to_run.append(Paper(
                                    title=meta["title"] or pdf_path.stem,
                                    doi=meta["doi"],
                                    year=int(meta["year"]),
                                    authors=_split_authors(meta["authors"]),
                                    is_oa=False,
                                ))
                                texts_to_run.append(meta["text"])

                            _run_summarize(
                                papers_to_run,
                                source="pdf_upload",
                                texts=texts_to_run,
                                key_prefix="folder",
                            )
                            st.session_state.pop("_folder_scanned", None)
                            st.session_state.pop("folder_selection", None)
