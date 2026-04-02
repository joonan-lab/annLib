"""설정 페이지 — 단계별 API 가이드 + OS별 안내 + 즉시 저장"""

import platform
import subprocess
import sys
from pathlib import Path

import streamlit as st

from annlib import config
from annlib.core.api_validator import validate_llm

st.set_page_config(page_title="설정 | annlib", page_icon="⚙️", layout="wide")

# ──────────────────────────────────────────────────────────────
# OS 감지 (전역)
# ──────────────────────────────────────────────────────────────
SYSTEM = platform.system()   # "Darwin" | "Windows" | "Linux"
IS_MAC = SYSTEM == "Darwin"
IS_WIN = SYSTEM == "Windows"

OS_LABEL = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(SYSTEM, SYSTEM)
OS_ICON  = {"Darwin": "🍎", "Windows": "🪟", "Linux": "🐧"}.get(SYSTEM, "💻")


# ──────────────────────────────────────────────────────────────
# 헬퍼 함수
# ──────────────────────────────────────────────────────────────

def _chromium_installed() -> bool:
    """Playwright Chromium 설치 여부 확인 (OS별 경로)."""
    if IS_WIN:
        bases = [Path.home() / "AppData" / "Local" / "ms-playwright"]
        exe_name = "chrome.exe"
    elif IS_MAC:
        bases = [
            Path.home() / "Library" / "Caches" / "ms-playwright",
            Path.home() / ".cache" / "ms-playwright",  # 구버전 fallback
        ]
        exe_name = "chrome"
    else:  # Linux
        bases = [Path.home() / ".cache" / "ms-playwright"]
        exe_name = "chrome"

    return any(
        base.exists() and any(base.rglob(exe_name))
        for base in bases
    )


def _obsidian_installed() -> bool:
    """Obsidian 설치 여부 확인 (OS별 경로)."""
    if IS_MAC:
        return Path("/Applications/Obsidian.app").exists()
    if IS_WIN:
        paths = [
            Path(r"C:\Program Files\Obsidian\Obsidian.exe"),
            Path.home() / "AppData" / "Local" / "Obsidian" / "Obsidian.exe",
            Path.home() / "AppData" / "Local" / "Programs" / "obsidian" / "Obsidian.exe",
        ]
        return any(p.exists() for p in paths)
    return False  # Linux는 수동 확인 유도


def _guess_vault_path() -> Path:
    """OS별 기본 Vault 경로를 제안합니다."""
    if IS_WIN:
        # Windows: Documents 폴더 위치는 레지스트리 or 환경변수로 확인
        import os
        docs = Path(os.environ.get("USERPROFILE", Path.home())) / "Documents"
    else:
        docs = Path.home() / "Documents"

    candidates = [
        docs / "ObsidianVault",
        docs / "Obsidian",
        Path.home() / "ObsidianVault",
    ]
    for p in candidates:
        if p.exists():
            return p
    return docs / "ObsidianVault"


def _path_display(p: Path) -> str:
    """경로를 OS별로 읽기 좋게 표시합니다."""
    return str(p).replace("/", "\\") if IS_WIN else str(p)


# ──────────────────────────────────────────────────────────────
# 페이지 헤더
# ──────────────────────────────────────────────────────────────
st.title("⚙️ 설정")

col_os, col_desc = st.columns([1, 5])
with col_os:
    st.info(f"{OS_ICON} **{OS_LABEL}**", icon=None)
with col_desc:
    st.caption("각 항목을 입력하고 [저장] 버튼을 누르면 `~/.annlib/config.json`에 즉시 반영됩니다.")

cfg = config.load()

# 진행 상태 바
def _is_done(key: str) -> bool:
    return bool(cfg.get(key, ""))

steps_done = sum([_is_done("llm_api_key"), _is_done("vault_path"), _chromium_installed()])
st.progress(steps_done / 3, text=f"필수 설정 완료 {steps_done}/3")
if steps_done == 3:
    st.success("모든 설정이 완료되었습니다. **annlib run** 으로 대시보드를 시작하세요.")

st.divider()


# ──────────────────────────────────────────────────────────────
# STEP 1 — LLM API
# ──────────────────────────────────────────────────────────────
with st.expander(
    f"{'✅' if _is_done('llm_api_key') else '1️⃣'}  LLM API 키 설정  *(필수)*",
    expanded=not _is_done("llm_api_key"),
):
    st.markdown("논문 요약과 RAG 질문에 사용할 AI 서비스를 선택하세요.")

    st.info("💡 **학생 권장**: Google Gemini는 Google 계정만 있으면 **무료**로 사용할 수 있습니다.", icon=None)

    provider = st.radio(
        "서비스 선택",
        options=["gemini", "openai", "claude"],
        format_func=lambda x: {
            "gemini": "Google Gemini 1.5 Flash  —  ✅ 무료 (Google 계정만 필요)",
            "openai": "OpenAI GPT-4o-mini  —  크레딧 필요",
            "claude": "Anthropic Claude Haiku  —  크레딧 필요",
        }[x],
        index=["gemini", "openai", "claude"].index(cfg.get("llm_provider") or "gemini"),
        horizontal=False,
        key="provider_radio",
    )

    with st.container(border=True):
        guides = {
            "gemini": (
                "**Google Gemini API 키 발급 방법** (무료, 신용카드 불필요)\n\n"
                "1. [aistudio.google.com](https://aistudio.google.com) 접속\n"
                "2. 평소 쓰는 **Google 계정으로 로그인**\n"
                "3. 왼쪽 메뉴 **Get API key** 클릭\n"
                "4. **Create API key** 버튼 클릭 → 프로젝트 선택\n"
                "5. 생성된 키(`AIza...`)를 복사하여 아래에 붙여넣기\n\n"
                "> 무료 티어 기준 분당 15회, 하루 1,500회 요청 가능 — 수업 사용에 충분합니다."
            ),
            "openai": (
                "**OpenAI API 키 발급 방법** (크레딧 필요, ChatGPT Plus와 별개)\n\n"
                "1. [platform.openai.com](https://platform.openai.com) 접속 → 회원가입/로그인\n"
                "2. 우측 상단 프로필 아이콘 → **API keys** 클릭\n"
                "3. **+ Create new secret key** 버튼 클릭 → 이름 입력 후 생성\n"
                "4. 생성된 키(`sk-...`)를 **즉시 복사** (창을 닫으면 다시 볼 수 없음)\n\n"
                "> ⚠️ ChatGPT Plus/Pro 구독과 별개로 크레딧을 충전해야 합니다."
            ),
            "claude": (
                "**Anthropic Claude API 키 발급 방법** (크레딧 필요, Claude.ai 구독과 별개)\n\n"
                "1. [console.anthropic.com](https://console.anthropic.com) 접속 → 회원가입/로그인\n"
                "2. 왼쪽 메뉴 **API Keys** 클릭\n"
                "3. **+ Create Key** 버튼 클릭 → 키 이름 입력 후 생성\n"
                "4. 생성된 키(`sk-ant-api03-...`)를 복사하여 아래에 붙여넣기\n\n"
                "> ⚠️ Claude Max/Pro 구독과 별개로 크레딧을 충전해야 합니다."
            ),
        }
        st.markdown(guides[provider])

    llm_api_key = st.text_input(
        "API 키 붙여넣기",
        value=cfg.get("llm_api_key", "") if cfg.get("llm_provider") == provider else "",
        type="password",
        placeholder={"openai": "sk-...", "gemini": "AIza...", "claude": "sk-ant-..."}[provider],
        key="llm_key_input",
    )

    col_save, col_test = st.columns(2)
    with col_save:
        if st.button("저장", key="save_llm", type="primary", use_container_width=True):
            if llm_api_key:
                config.save({"llm_provider": provider, "llm_api_key": llm_api_key})
                st.success("저장되었습니다.")
                st.rerun()
            else:
                st.warning("API 키를 입력해 주세요.")
    with col_test:
        if st.button("연결 테스트 후 저장", key="test_llm", use_container_width=True):
            with st.spinner("연결 확인 중..."):
                result = validate_llm(provider, llm_api_key)
            if result.ok:
                config.save({"llm_provider": provider, "llm_api_key": llm_api_key})
                st.success("연결 성공! 저장되었습니다.")
                st.rerun()
            else:
                st.error(f"연결 실패: {result.message}")


# ──────────────────────────────────────────────────────────────
# STEP 2 — OpenAlex 이메일 (선택)
# ──────────────────────────────────────────────────────────────
with st.expander(
    f"{'✅' if _is_done('openalex_email') else '2️⃣'}  OpenAlex 이메일 *(선택)*",
    expanded=False,
):
    st.markdown(
        "OpenAlex는 무료 학술 논문 검색 API입니다. "
        "이메일을 등록하면 **polite pool**로 배정되어 응답 속도가 빨라집니다.\n\n"
        "대학 이메일 주소를 입력하세요."
    )
    email = st.text_input(
        "이메일",
        value=cfg.get("openalex_email", ""),
        placeholder="yourname@university.ac.kr",
        key="email_input",
    )
    if st.button("저장", key="save_email", use_container_width=True):
        config.save({"openalex_email": email})
        st.success("저장되었습니다.")
        st.rerun()


# ──────────────────────────────────────────────────────────────
# STEP 3 — Obsidian 설치 + Vault 경로
# ──────────────────────────────────────────────────────────────
with st.expander(
    f"{'✅' if _is_done('vault_path') else '3️⃣'}  Obsidian 설정  *(필수)*",
    expanded=not _is_done("vault_path"),
):
    obsidian_ok = _obsidian_installed()

    # ── Obsidian 설치 안내 ──
    if not obsidian_ok:
        st.warning(f"Obsidian이 설치되어 있지 않습니다. ({OS_LABEL})")
        with st.container(border=True):
            if IS_MAC:
                st.markdown(
                    "**macOS — Obsidian 설치 방법**\n\n"
                    "1. [obsidian.md/download](https://obsidian.md/download) 접속\n"
                    "2. **Download for macOS** 클릭 → `.dmg` 파일 다운로드\n"
                    "3. `.dmg` 파일 열기 → Obsidian 아이콘을 **Applications** 폴더로 드래그\n"
                    "4. Launchpad 또는 Spotlight(`⌘ Space`)에서 **Obsidian** 실행\n"
                    "5. **새 보관함(Vault) 만들기** → 이름과 저장 위치 설정\n"
                    "6. 아래에 그 경로를 입력하세요."
                )
            elif IS_WIN:
                st.markdown(
                    "**Windows — Obsidian 설치 방법**\n\n"
                    "1. [obsidian.md/download](https://obsidian.md/download) 접속\n"
                    "2. **Download for Windows** 클릭 → `.exe` 설치 파일 다운로드\n"
                    "3. 다운로드한 `.exe` 파일 실행 → 설치 진행\n"
                    "   - *'Windows의 PC 보호'* 경고 창이 뜨면 **추가 정보 → 실행** 클릭\n"
                    "4. 시작 메뉴에서 **Obsidian** 실행\n"
                    "5. **새 보관함(Vault) 만들기** → 이름과 저장 위치 설정\n"
                    "6. 아래에 그 경로를 입력하세요.\n\n"
                    "> 💡 경로 예시: `C:\\Users\\홍길동\\Documents\\ObsidianVault`"
                )
            else:
                st.markdown(
                    "**Linux — Obsidian 설치 방법**\n\n"
                    "1. [obsidian.md/download](https://obsidian.md/download) 접속\n"
                    "2. **AppImage** 또는 **.deb** 파일 다운로드\n"
                    "3. AppImage: `chmod +x Obsidian.AppImage && ./Obsidian.AppImage`\n"
                    "4. .deb: `sudo dpkg -i obsidian_*.deb`"
                )
    else:
        st.success(f"Obsidian 설치 확인됨 ({OS_LABEL})")

    st.markdown("---")
    st.markdown("**Vault 폴더 경로**")
    st.caption("Obsidian에서 만든 Vault 폴더의 경로를 입력하세요. 폴더가 없으면 자동으로 생성됩니다.")

    default_hint = _guess_vault_path()
    vault_path = st.text_input(
        "Vault 경로",
        value=cfg.get("vault_path", ""),
        placeholder=_path_display(default_hint),
        key="vault_input",
    )

    if vault_path:
        p = Path(vault_path).expanduser()
        if p.exists():
            st.caption(f"폴더 확인됨: `{_path_display(p)}`")
        else:
            st.caption(f"저장 시 자동 생성됩니다: `{_path_display(p)}`")

    if st.button("저장", key="save_vault", type="primary", use_container_width=True):
        if vault_path:
            p = Path(vault_path).expanduser()
            p.mkdir(parents=True, exist_ok=True)
            (p / "Papers").mkdir(exist_ok=True)
            (p / "RAG_Results").mkdir(exist_ok=True)
            config.save({"vault_path": str(p)})  # 절대경로로 저장
            st.success(f"Vault 저장 완료: `{_path_display(p)}`")
            st.rerun()
        else:
            st.warning("경로를 입력해 주세요.")


# ──────────────────────────────────────────────────────────────
# STEP 4 — 브라우저 설정 (Chrome 또는 Chromium)
# ──────────────────────────────────────────────────────────────
def _chrome_installed() -> bool:
    """시스템에 Chrome이 설치되어 있는지 확인합니다."""
    if IS_MAC:
        return Path("/Applications/Google Chrome.app").exists()
    if IS_WIN:
        paths = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
        return any(p.exists() for p in paths)
    return False


browser_ready = _chromium_installed() or (
    _chrome_installed() and cfg.get("browser_channel") == "chrome"
)

with st.expander(
    f"{'✅' if browser_ready else '4️⃣'}  PDF 자동 수집 브라우저 설정  *(필수)*",
    expanded=not browser_ready,
):
    st.markdown(
        "arXiv, PubMed 등에서 PDF를 자동 수집하려면 브라우저가 필요합니다.  \n"
        "이미 **Chrome이 설치되어 있다면** 그것을 그대로 사용할 수 있습니다."
    )

    # Chrome 설치 여부에 따라 옵션 구성
    chrome_ok = _chrome_installed()
    chromium_ok = _chromium_installed()

    if chrome_ok:
        st.success(f"Google Chrome 감지됨 ({OS_LABEL})")
    if chromium_ok:
        st.success("Playwright Chromium 설치됨")

    st.markdown("**사용할 브라우저를 선택하세요**")
    saved_channel = cfg.get("browser_channel", "chrome" if chrome_ok else "chromium")

    browser_choice = st.radio(
        "브라우저",
        options=["chrome", "chromium"],
        format_func=lambda x: {
            "chrome":   f"{'✅ ' if chrome_ok else '❌ '}Google Chrome  {'(이미 설치됨, 추가 설치 불필요)' if chrome_ok else '— 미설치'}",
            "chromium": f"{'✅ ' if chromium_ok else '⬜ '}Playwright Chromium  {'(설치됨)' if chromium_ok else '— 별도 설치 필요'}",
        }[x],
        index=0 if saved_channel == "chrome" else 1,
        key="browser_choice",
    )

    if st.button("브라우저 설정 저장", type="primary", use_container_width=True):
        if browser_choice == "chrome" and not chrome_ok:
            st.error("Chrome이 설치되어 있지 않습니다. 먼저 Chrome을 설치해 주세요.")
        else:
            config.save({"browser_channel": browser_choice})
            st.success(f"{'Chrome' if browser_choice == 'chrome' else 'Chromium'} 사용으로 저장되었습니다.")
            st.rerun()

    # Chrome 미설치 시 안내
    if not chrome_ok:
        with st.container(border=True):
            st.markdown("**Chrome 설치 방법**")
            if IS_MAC:
                st.markdown("1. [google.com/chrome](https://www.google.com/chrome) 접속\n2. **Chrome 다운로드** 클릭 → `.dmg` 설치")
            elif IS_WIN:
                st.markdown("1. [google.com/chrome](https://www.google.com/chrome) 접속\n2. **Chrome 다운로드** 클릭 → `.exe` 설치")

    # Chromium 설치 섹션
    if browser_choice == "chromium" and not chromium_ok:
        st.divider()
        st.markdown("**Playwright Chromium 설치**")

        if IS_WIN:
            st.info("설치 중 Windows Defender 경고가 뜨면 **허용**을 클릭하세요.", icon="ℹ️")
        elif IS_MAC:
            st.info(
                "설치 후 처음 실행 시 보안 경고가 뜰 수 있습니다.  \n"
                "시스템 설정 → 개인 정보 보호 및 보안 → **허용** 클릭",
                icon="ℹ️",
            )

        if st.button("Chromium 자동 설치", use_container_width=True):
            with st.spinner("설치 중... (1~3분 소요)"):
                r = subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    capture_output=True, text=True,
                )
            if r.returncode == 0:
                st.success("Chromium 설치 완료!")
                config.save({"browser_channel": "chromium"})
                st.rerun()
            else:
                st.error("자동 설치 실패. 터미널에서 직접 실행해 주세요:")
                st.code(
                    "python -m playwright install chromium",
                    language="batch" if IS_WIN else "bash",
                )
                if IS_WIN:
                    st.caption("시작 메뉴 → `cmd` 검색 → 명령 프롬프트 실행 후 위 명령어 입력")


# ──────────────────────────────────────────────────────────────
# STEP 5 — NotebookLM
# ──────────────────────────────────────────────────────────────
with st.expander("5️⃣  NotebookLM 로그인", expanded=False):
    from annlib.core.notebooklm_client import is_logged_in

    nlm_ok = is_logged_in()

    if nlm_ok:
        st.success("NotebookLM 로그인 상태 — 사용 가능")
        st.caption("논문 요약 페이지에서 **NotebookLM 요약** 방식을 선택할 수 있습니다.")

        from annlib.core.notebooklm_client import get_workspace_info, reset_workspace
        ws = get_workspace_info()
        if ws["notebook_id"]:
            st.info(f"작업 노트북 ID: `{ws['notebook_id'][:16]}…`")
            if st.button("작업 노트북 초기화 (다음 요약 시 재탐색)", use_container_width=True):
                reset_workspace()
                st.success("초기화되었습니다.")
                st.rerun()
        else:
            st.caption("첫 요약 시 자동으로 작업 노트북을 탐색합니다.")
    else:
        st.warning("NotebookLM에 로그인되어 있지 않습니다.")
        st.markdown(
            "NotebookLM은 Google 계정으로 로그인하여 사용합니다.  \n"
            "API 키 없이 무료로 사용 가능합니다."
        )
        with st.container(border=True):
            st.markdown(
                "**로그인 방법**\n\n"
                "1. 터미널(Terminal / 명령 프롬프트)을 엽니다.\n"
                "2. 아래 명령어를 입력하고 Enter:\n"
            )
            st.code("notebooklm login", language="bash")
            st.markdown(
                "3. 브라우저가 열리면 Google 계정으로 로그인\n"
                "4. 로그인 완료 후 이 페이지를 새로고침하세요.\n\n"
            )
            if IS_WIN:
                st.caption("Windows: 시작 메뉴 → `cmd` 검색 → 명령 프롬프트")
            elif IS_MAC:
                st.caption("macOS: Spotlight(`⌘ Space`) → Terminal 검색")

        if st.button("새로고침 (로그인 완료 후)", use_container_width=True):
            st.rerun()


# ──────────────────────────────────────────────────────────────
# 현재 설정 요약
# ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("현재 설정 요약")

cfg = config.load()
c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("운영체제", f"{OS_ICON} {OS_LABEL}")
with c2:
    provider_label = {"openai": "OpenAI", "gemini": "Gemini", "claude": "Claude"}.get(
        cfg.get("llm_provider", ""), "미설정"
    )
    st.metric("LLM", provider_label)
with c3:
    st.metric("API 키", "설정됨" if cfg.get("llm_api_key") else "미설정")
with c4:
    vault = cfg.get("vault_path", "")
    st.metric("Vault", "연결됨" if vault else "미설정")
with c5:
    st.metric("Chromium", "설치됨" if _chromium_installed() else "미설치")
