"""NotebookLM 클라이언트 래퍼 — notebooklm-py 기반

CREATE_NOTEBOOK RPC가 Google 내부 API 변경으로 현재 비작동 상태.
대신 전용 작업 노트북(workspace)을 재사용하는 방식으로 우회.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

WORKSPACE_TITLE = "[annlib] 작업 공간"


def is_logged_in() -> bool:
    """notebooklm login 인증 파일이 존재하는지 확인합니다."""
    from notebooklm.paths import get_storage_path
    return get_storage_path().exists()


async def _get_or_prompt_workspace(client) -> str:
    """
    '[annlib] 작업 공간' 노트북 ID를 반환합니다.
    없으면 config에서 읽거나 첫 번째 노트북을 fallback으로 사용합니다.
    """
    from annlib import config as cfg_module

    # 1. config에 저장된 workspace_notebook_id 확인
    saved_id = cfg_module.get("notebooklm_workspace_id", "")
    if saved_id:
        return saved_id

    # 2. 기존 노트북 목록에서 전용 노트북 탐색
    notebooks = await client.notebooks.list()
    for nb in notebooks:
        if nb.title == WORKSPACE_TITLE:
            cfg_module.save({"notebooklm_workspace_id": nb.id})
            return nb.id

    # 3. 없으면 첫 번째 노트북 사용 (fallback)
    if notebooks:
        nb = notebooks[0]
        cfg_module.save({"notebooklm_workspace_id": nb.id})
        return nb.id

    raise RuntimeError(
        "사용 가능한 NotebookLM 노트북이 없습니다.\n"
        "notebooklm.google.com 에서 노트북을 하나 만들어 주세요."
    )


@dataclass
class NotebookLMSummary:
    summary: str
    notebook_id: str
    source_title: str
    podcast_path: Optional[Path] = None


async def summarize_with_notebooklm(
    title: str,
    text: str,
    generate_podcast: bool = False,
    podcast_lang: str = "ko",
    keep_notebook: bool = False,   # 이 구현에서는 소스 삭제 여부로 해석
) -> NotebookLMSummary:
    """
    논문 텍스트를 NotebookLM 작업 노트북에 소스로 추가하고 요약을 가져옵니다.

    1. 작업 노트북 ID 확보 (기존 노트북 재사용)
    2. 텍스트 소스 추가
    3. 요약 질문 (chat)
    4. (선택) 팟캐스트 생성
    5. 소스 삭제 (keep_notebook=False)
    """
    from notebooklm import NotebookLMClient
    from notebooklm.exceptions import AuthError

    try:
        client = await NotebookLMClient.from_storage()
        async with client:
            notebook_id = await _get_or_prompt_workspace(client)

            # 2. 텍스트 소스 추가 (최대 50만자)
            content = text[:500_000]
            source = await client.sources.add_text(
                notebook_id,
                title=title[:100],
                content=content,
                wait=True,
            )
            source_id = source.id

            try:
                # 3. 요약 질문 — 이 소스만 대상으로
                summary_prompt = (
                    "방금 추가된 논문의 핵심 기여, 방법론, 주요 결과, 한계점을 "
                    "각각 2-3문장으로 한국어로 요약해 주세요."
                )
                chat_resp = await client.chat.ask(
                    notebook_id,
                    summary_prompt,
                    source_ids=[source_id],
                )
                summary_text = chat_resp.answer

                # 4. 팟캐스트 생성 (선택)
                podcast_path = None
                if generate_podcast:
                    podcast_path = await _generate_podcast(
                        client, notebook_id, title, podcast_lang,
                        source_ids=[source_id],
                    )

                return NotebookLMSummary(
                    summary=summary_text,
                    notebook_id=notebook_id,
                    source_title=title,
                    podcast_path=podcast_path,
                )

            finally:
                # 5. 소스 삭제 (작업 노트북을 깨끗하게 유지)
                if not keep_notebook:
                    try:
                        await client.sources.delete(notebook_id, source_id)
                    except Exception:
                        pass

    except AuthError as e:
        raise RuntimeError(
            "NotebookLM 로그인이 만료되었습니다.\n"
            "터미널에서 `notebooklm login` 을 다시 실행해 주세요."
        ) from e


async def _generate_podcast(
    client,
    notebook_id: str,
    title: str,
    lang: str,
    source_ids: list[str] | None = None,
) -> Optional[Path]:
    """팟캐스트 오디오를 생성하고 저장합니다."""
    try:
        status = await client.artifacts.generate_audio(
            notebook_id,
            source_ids=source_ids,
            language=lang,
        )

        audio_artifact = await client.artifacts.wait_for_audio(
            notebook_id,
            task_id=status.task_id,
            timeout=300,
        )

        podcast_dir = Path.home() / ".annlib" / "podcasts"
        podcast_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title[:50])
        dest = podcast_dir / f"{safe_name}.mp3"

        audio_bytes = await client.artifacts.download_audio(audio_artifact)
        dest.write_bytes(audio_bytes)
        return dest

    except Exception:
        return None


def get_workspace_info() -> dict:
    """저장된 workspace 노트북 정보를 반환합니다."""
    from annlib import config as cfg_module
    return {
        "notebook_id": cfg_module.get("notebooklm_workspace_id", ""),
        "title": WORKSPACE_TITLE,
    }


def reset_workspace() -> None:
    """저장된 workspace ID를 초기화합니다 (다음 실행 시 재탐색)."""
    from annlib import config as cfg_module
    cfg_module.save({"notebooklm_workspace_id": ""})
