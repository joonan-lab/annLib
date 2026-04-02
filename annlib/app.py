"""Streamlit 메인 앱"""

import streamlit as st

st.set_page_config(
    page_title="annlib",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📚 annlib")
st.markdown(
    "대학원 수업용 논문 관리 대시보드입니다.  \n"
    "왼쪽 사이드바에서 메뉴를 선택하세요."
)

st.info(
    "처음 사용하신다면 **설정** 페이지에서 API 키와 Obsidian Vault 경로를 설정해 주세요.",
    icon="ℹ️",
)

# 빠른 상태 요약
from annlib import config

cfg = config.load()

col1, col2, col3 = st.columns(3)
with col1:
    vault = cfg.get("vault_path", "")
    st.metric("Obsidian Vault", "연결됨" if vault else "미설정")
with col2:
    provider = cfg.get("llm_provider", "")
    st.metric("LLM 프로바이더", provider.upper() if provider else "미설정")
with col3:
    # 저장된 논문 수 카운트
    paper_count = 0
    if vault:
        from pathlib import Path
        paper_count = len(list(Path(vault).joinpath("Papers").glob("*.md")))
    st.metric("저장된 논문", f"{paper_count}편")
