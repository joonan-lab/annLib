"""CLI 엔트리포인트 — annlib run / annlib setup"""

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from annlib import __version__
from annlib import config

console = Console()

APP_PATH = Path(__file__).parent / "app.py"


@click.group()
@click.version_option(__version__, prog_name="annlib")
def main():
    """annlib — 대학원 수업용 논문 관리 올인원 대시보드"""
    pass


@main.command()
@click.option("--port", default=8501, help="Streamlit 포트 (기본: 8501)")
def run(port: int):
    """대시보드를 실행합니다."""
    cfg = config.load()

    if not cfg.get("vault_path"):
        console.print(
            Panel(
                "[yellow]설정이 완료되지 않았습니다.[/yellow]\n"
                "[dim]먼저 [bold]annlib setup[/bold] 을 실행해 주세요.[/dim]",
                title="annlib",
            )
        )
        sys.exit(1)

    console.print(
        Panel(
            f"[green]대시보드 시작 중...[/green]\n"
            f"[dim]브라우저에서 http://localhost:{port} 가 열립니다.[/dim]",
            title="annlib v" + __version__,
        )
    )

    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run",
            str(APP_PATH),
            "--server.port", str(port),
            "--server.headless", "false",
            "--browser.gatherUsageStats", "false",
        ],
        check=True,
    )


@main.command()
def setup():
    """초기 설정 마법사를 실행합니다."""
    console.print(
        Panel(
            "[bold cyan]annlib 설정 마법사[/bold cyan]\n"
            "[dim]API 키와 Obsidian Vault 경로를 설정합니다.[/dim]",
            title="annlib setup",
        )
    )

    cfg = config.load()

    # 1. LLM 프로바이더
    console.print("\n[bold]1. LLM 프로바이더 선택[/bold]")
    console.print("  [cyan]1[/cyan] OpenAI (GPT-4o)")
    console.print("  [cyan]2[/cyan] Google Gemini")
    console.print("  [cyan]3[/cyan] Anthropic Claude")
    choice = Prompt.ask("선택", choices=["1", "2", "3"], default="1")
    provider_map = {"1": "openai", "2": "gemini", "3": "claude"}
    provider = provider_map[choice]

    api_key = Prompt.ask(
        f"\n{provider.upper()} API 키",
        default=cfg.get("llm_api_key", ""),
        password=True,
    )

    # 2. NotebookLM API 키
    console.print("\n[bold]2. NotebookLM 설정[/bold]")
    notebooklm_key = Prompt.ask(
        "NotebookLM API 키 (없으면 Enter 건너뜀)",
        default=cfg.get("notebooklm_api_key", ""),
        password=True,
    )

    # 3. OpenAlex 이메일 (polite pool)
    console.print("\n[bold]3. OpenAlex 이메일 [dim](선택, 더 빠른 API 응답)[/dim][/bold]")
    email = Prompt.ask(
        "이메일",
        default=cfg.get("openalex_email", ""),
    )

    # 4. Obsidian Vault 경로
    console.print("\n[bold]4. Obsidian Vault 경로[/bold]")
    default_vault = _guess_vault_path()
    vault_path = Prompt.ask(
        "Vault 경로",
        default=str(default_vault) if default_vault else "",
    )

    if vault_path:
        vault = Path(vault_path).expanduser()
        vault.mkdir(parents=True, exist_ok=True)
        (vault / "Papers").mkdir(exist_ok=True)
        (vault / "RAG_Results").mkdir(exist_ok=True)
        console.print(f"[green]Vault 폴더 준비 완료:[/green] {vault}")

    # 5. Obsidian 설치 확인
    console.print("\n[bold]5. Obsidian 설치 확인[/bold]")
    _check_obsidian()

    # 6. Playwright Chromium 설치
    console.print("\n[bold]6. Playwright Chromium 설치[/bold]")
    if Confirm.ask("Playwright Chromium을 설치하시겠어요? (PDF 자동 수집에 필요)", default=True):
        console.print("[dim]설치 중...[/dim]")
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            console.print("[green]Chromium 설치 완료[/green]")
        else:
            console.print(f"[red]설치 실패:[/red] {result.stderr}")

    # 저장
    config.save({
        "llm_provider": provider,
        "llm_api_key": api_key,
        "notebooklm_api_key": notebooklm_key,
        "openalex_email": email,
        "vault_path": vault_path,
    })

    console.print(
        Panel(
            "[green]설정 완료![/green]\n\n"
            "이제 [bold]annlib run[/bold] 으로 대시보드를 시작하세요.",
            title="완료",
        )
    )


@main.command("install-skills")
def install_skills():
    """CC 스킬을 ~/.claude/skills/ 에 설치합니다."""
    skills_src = Path(__file__).parent.parent / "skills"
    skills_dst = Path.home() / ".claude" / "skills"

    if not skills_src.exists():
        console.print("[red]스킬 파일을 찾을 수 없습니다.[/red]")
        sys.exit(1)

    skills_dst.mkdir(parents=True, exist_ok=True)

    installed = []
    for skill_dir in sorted(skills_src.iterdir()):
        if not skill_dir.is_dir():
            continue
        dst = skills_dst / skill_dir.name
        if dst.exists():
            import shutil
            shutil.rmtree(dst)
        import shutil
        shutil.copytree(skill_dir, dst)
        installed.append(skill_dir.name)

    if installed:
        console.print(
            Panel(
                "[green]스킬 설치 완료![/green]\n\n"
                + "\n".join(f"  ✅ /{s}" for s in installed)
                + "\n\nClaude Code 에서 바로 사용할 수 있습니다.",
                title="annlib install-skills",
            )
        )
    else:
        console.print("[yellow]설치할 스킬이 없습니다.[/yellow]")


def _guess_vault_path() -> Path | None:
    """OS별로 일반적인 Obsidian Vault 위치를 탐색합니다."""
    candidates = [
        Path.home() / "Documents" / "ObsidianVault",
        Path.home() / "ObsidianVault",
        Path.home() / "Documents" / "Obsidian",
        Path.home() / "Obsidian",
    ]
    for p in candidates:
        if p.exists():
            return p
    # 없으면 기본 경로 제안
    return Path.home() / "Documents" / "ObsidianVault"


def _check_obsidian():
    import platform
    system = platform.system()

    # 설치 여부 간단 체크 (앱 번들 경로)
    installed = False
    if system == "Darwin":
        installed = Path("/Applications/Obsidian.app").exists()
    elif system == "Windows":
        installed = (
            Path(r"C:\Program Files\Obsidian\Obsidian.exe").exists()
            or Path.home().joinpath("AppData/Local/Obsidian/Obsidian.exe").exists()
        )

    if installed:
        console.print("[green]Obsidian 설치 확인됨[/green]")
    else:
        console.print(
            "[yellow]Obsidian이 설치되지 않은 것 같습니다.[/yellow]\n"
            "  macOS:   https://github.com/obsidianmd/obsidian-releases/releases\n"
            "  Windows: https://obsidian.md/download\n"
            "[dim]설치 후 annlib setup 을 다시 실행하지 않아도 됩니다.[/dim]"
        )
