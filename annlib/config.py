"""설정 관리 — ~/.annlib/config.json"""

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".annlib"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "llm_provider": "gemini", # openai | gemini | claude
    "llm_api_key": "",
    "notebooklm_api_key": "",
    "vault_path": "",
    "openalex_email": "",     # OpenAlex polite pool용 이메일 (선택)
    "browser_channel": "",              # chrome | chromium (PDF 수집용)
    "notebooklm_workspace_id": "",      # NotebookLM 작업 노트북 ID
}


def load() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open() as f:
            data = json.load(f)
        return {**DEFAULTS, **data}
    return dict(DEFAULTS)


def save(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    merged = {**load(), **data}
    with CONFIG_FILE.open("w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)


def get(key: str, fallback: Any = "") -> Any:
    return load().get(key, fallback)
