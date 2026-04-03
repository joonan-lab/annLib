"""Question Tree 관리 — 레벨별 질문 추가/읽기"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path


def append(project_dir: Path, level: int, questions: list[str], source: str = "") -> None:
    """question-tree.md 의 해당 레벨에 질문들을 추가합니다."""
    tree_path = project_dir / "questions" / "question-tree.md"
    if not tree_path.exists():
        print(f"ERROR: question-tree.md 없음: {tree_path}", file=sys.stderr)
        return

    content = tree_path.read_text(encoding="utf-8")
    tag = f"<!-- L{level}_END -->"

    stamp = f"`[{source}, {date.today()}]`" if source else f"`[{date.today()}]`"
    lines = "\n".join(f"<!-- L{level}_ITEM -->\n- {q}  {stamp}" for q in questions)

    if tag in content:
        content = content.replace(tag, f"{lines}\n{tag}")
    else:
        content += f"\n{lines}\n"

    tree_path.write_text(content, encoding="utf-8")
    # 수정 날짜 업데이트
    content = tree_path.read_text(encoding="utf-8")
    content = re.sub(
        r'\*최종 업데이트: .+?\*',
        f'*최종 업데이트: {date.today()}*',
        content,
    )
    tree_path.write_text(content, encoding="utf-8")


def read_level(project_dir: Path, level: int) -> list[str]:
    """특정 레벨의 질문 목록을 반환합니다."""
    tree_path = project_dir / "questions" / "question-tree.md"
    if not tree_path.exists():
        return []

    content = tree_path.read_text(encoding="utf-8")
    start = f"<!-- L{level}_START -->"
    end   = f"<!-- L{level}_END -->"

    m = re.search(re.escape(start) + r'(.*?)' + re.escape(end), content, re.DOTALL)
    if not m:
        return []

    block = m.group(1)
    return re.findall(r'^- (.+?)  `\[', block, re.MULTILINE)


def summary(project_dir: Path) -> dict:
    """레벨별 질문 개수를 요약합니다."""
    return {
        f"L{i}": len(read_level(project_dir, i))
        for i in range(1, 5)
    }


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    from annlib.review.project import find_project

    cmd  = sys.argv[1] if len(sys.argv) > 1 else "summary"
    proj = find_project()

    if not proj:
        print("ERROR: 프로젝트를 찾을 수 없습니다.")
        sys.exit(1)

    if cmd == "summary":
        for k, v in summary(proj).items():
            print(f"{k}: {v}개")

    elif cmd == "read":
        level = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        for q in read_level(proj, level):
            print(f"- {q}")

    elif cmd == "append":
        level = int(sys.argv[2])
        source = sys.argv[3] if len(sys.argv) > 3 else ""
        questions = sys.stdin.read().strip().splitlines()
        questions = [q.lstrip("- ").strip() for q in questions if q.strip()]
        append(proj, level, questions, source)
        print(f"L{level}에 {len(questions)}개 질문 추가됨")
