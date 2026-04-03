"""리뷰 프로젝트 초기화 및 관리"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path


# ── 프로젝트 초기화 ─────────────────────────────────────────────

def init(topic: str, base_dir: Path | None = None) -> Path:
    slug = re.sub(r'[^\w\s-]', '', topic.lower())
    slug = re.sub(r'[\s_]+', '-', slug).strip('-')[:60]
    project_dir = (base_dir or Path.cwd()) / slug

    for d in ["papers", "questions", "themes"]:
        (project_dir / d).mkdir(parents=True, exist_ok=True)

    _write_claude_md(project_dir, topic)
    _write_question_tree(project_dir, topic)

    print(f"PROJECT_DIR={project_dir.resolve()}")
    print(f"TOPIC={topic}")
    return project_dir


def _write_claude_md(project_dir: Path, topic: str) -> None:
    path = project_dir / "CLAUDE.md"
    if path.exists():
        return
    path.write_text(f"""# Review Project: {topic}

## 주제
{topic}

## 시작일
{date.today()}

## 현재 상태
- 논문 수: 0
- Q 레벨: L0

## 명령어
- `/review-add <DOI | 키워드 | @파일.pdf>` — 논문 추가 + L1 질문 생성
- `/review-map` — 논문 간 관계 맵핑 + L2 질문 생성
- `/review-ask <질문>` — RAG 질문 → 답변 + 다음 레벨 질문
- `/review-gap` — 빈틈·모순 분석 + L4 질문 생성

## 프로젝트 경로
{project_dir.resolve()}
""")


def _write_question_tree(project_dir: Path, topic: str) -> None:
    path = project_dir / "questions" / "question-tree.md"
    if path.exists():
        return
    path.write_text(f"""# Question Tree: {topic}

*최종 업데이트: {date.today()}*

---

## L1 — 논문별 핵심 질문
> 각 논문이 직접 답하는 질문 / 전제하지만 검증하지 않은 가정

<!-- L1_START -->
<!-- L1_END -->

---

## L2 — 논문 간 관계 질문
> 두 편 이상을 비교·대조할 때 생기는 질문

<!-- L2_START -->
<!-- L2_END -->

---

## L3 — 합성 질문
> /review-ask 반복을 통해 깊어지는 질문

<!-- L3_START -->
<!-- L3_END -->

---

## L4 — 빈틈 질문
> /review-gap 이 발견한 미답 영역

<!-- L4_START -->
<!-- L4_END -->
""")


# ── 프로젝트 탐색 ────────────────────────────────────────────────

def find_project(start: Path | None = None) -> Path | None:
    """현재 디렉토리 또는 상위에서 CLAUDE.md + papers/ 를 찾습니다."""
    p = (start or Path.cwd()).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "CLAUDE.md").exists() and (parent / "papers").exists():
            return parent
    return None


# ── 통계 업데이트 ────────────────────────────────────────────────

def update_stats(project_dir: Path) -> None:
    papers = list((project_dir / "papers").glob("*.md"))
    tree = (project_dir / "questions" / "question-tree.md").read_text()

    l1 = len(re.findall(r'<!-- L1_ITEM', tree))
    l2 = len(re.findall(r'<!-- L2_ITEM', tree))

    claude_md = project_dir / "CLAUDE.md"
    content = claude_md.read_text()
    content = re.sub(r'- 논문 수: \d+', f'- 논문 수: {len(papers)}', content)
    claude_md.write_text(content)


# ── CLI 진입점 ───────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "init":
        topic = " ".join(sys.argv[2:]).strip()
        if not topic:
            print("사용법: python -m annlib.review.project init <주제>")
            sys.exit(1)
        init(topic)

    elif cmd == "find":
        p = find_project()
        print(f"PROJECT_DIR={p}" if p else "NOT_FOUND")

    elif cmd == "stats":
        p = find_project()
        if p:
            update_stats(p)
            print(f"UPDATED {p}")
        else:
            print("NOT_FOUND")
