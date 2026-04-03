"""논문 추가 — DOI / 키워드 / PDF 경로를 받아 papers/ 에 저장"""
from __future__ import annotations

import asyncio
import io
import re
import sys
from pathlib import Path


def _from_doi(doi: str):
    from annlib.core.openalex import fetch_by_doi
    paper = fetch_by_doi(doi.strip())
    return paper, paper.abstract if paper else ""


def _from_keyword(keyword: str):
    from annlib.core.openalex import search_papers
    results = search_papers(keyword, search_mode="keyword", per_page=1)
    if not results:
        results = search_papers(keyword, search_mode="title", per_page=1)
    if not results:
        return None, ""
    paper = results[0]
    return paper, paper.abstract


def _from_pdf(pdf_path: Path):
    from annlib.core.openalex import Paper
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(str(pdf_path))
        meta = reader.metadata or {}
        title   = str(meta.get("/Title",  "")).strip()
        authors = str(meta.get("/Author", "")).strip()

        pages = reader.pages[:30]
        text  = "\n".join(p.extract_text() or "" for p in pages)

        if not title and text:
            first = text.strip().split("\n")[0][:120]
            title = first if len(first) > 10 else pdf_path.stem

        years = re.findall(r'\b(19[5-9]\d|20[0-2]\d)\b', text[:2000])
        year  = int(years[0]) if years else 2024

        doi_m = re.search(r'10\.\d{4,}/\S+', text[:3000])
        doi   = doi_m.group(0).rstrip(".,;)") if doi_m else ""

        author_list = [a.strip() for a in
                       (authors.split(";") if ";" in authors else authors.split(","))
                       if a.strip()]

        paper = Paper(
            title=title or pdf_path.stem,
            doi=doi, year=year, authors=author_list, is_oa=False,
        )
        return paper, text
    except Exception as e:
        print(f"PDF 파싱 오류: {e}", file=sys.stderr)
        return None, ""


def _save_note(paper, content: str, project_dir: Path) -> Path:
    """논문 노트를 project_dir/papers/ 에 저장합니다."""
    from annlib.core.obsidian import _render_paper_note, _escape_yaml
    from annlib.core.notebooklm import PaperSummary
    from datetime import date
    import re as _re

    # 빈 요약 객체로 저장 (요약은 나중에 Claude가 스킬 안에서 수행)
    summary = PaperSummary(
        key_contribution="",
        methodology="",
        main_findings="",
        limitations="",
        related_papers=[],
        keywords=[c for c in paper.concepts[:5]],
    )

    safe = re.sub(r'[\\/:*?"<>|]', "_", f"{paper.year}_{paper.title[:60]}")
    note_path = project_dir / "papers" / f"{safe}.md"

    # 초록 또는 PDF 텍스트 첫 500자를 본문으로
    body_text = (content[:500] + "…") if len(content) > 500 else content

    frontmatter = f"""---
title: "{_escape_yaml(paper.title)}"
authors: "{_escape_yaml(paper.authors_str)}"
year: {paper.year or 0}
journal: "{_escape_yaml(paper.journal or '')}"
doi: "{paper.doi or ''}"
source: review
tags: [{", ".join(paper.concepts[:5])}]
is_oa: {str(paper.is_oa).lower()}
cited_by: {paper.cited_by_count}
added: {date.today()}
---"""

    body = f"""
# {paper.title}

| 항목 | 내용 |
|------|------|
| **저자** | {paper.authors_str} |
| **연도** | {paper.year or "미상"} |
| **저널** | {paper.journal or "미상"} |
| **DOI** | {f'[{paper.doi}](https://doi.org/{paper.doi})' if paper.doi else '없음'} |
| **인용** | {paper.cited_by_count:,}회 |

## 초록 / 내용
{body_text}

## 핵심 기여
*(Claude가 /review-add 후 채웁니다)*

## 방법론
*(Claude가 /review-add 후 채웁니다)*

## 주요 결과
*(Claude가 /review-add 후 채웁니다)*

## 한계점
*(Claude가 /review-add 후 채웁니다)*

## L1 질문
*(Claude가 /review-add 후 채웁니다)*
"""

    note_path.write_text(frontmatter + body, encoding="utf-8")
    return note_path


def main():
    if len(sys.argv) < 2:
        print("사용법: python -m annlib.review.add <DOI | 키워드 | /path/to/file.pdf>")
        sys.exit(1)

    arg = " ".join(sys.argv[1:]).strip()

    # 프로젝트 탐색
    from annlib.review.project import find_project
    project_dir = find_project()
    if not project_dir:
        print("ERROR: 리뷰 프로젝트를 찾을 수 없습니다. 먼저 /review-start 를 실행하세요.")
        sys.exit(1)

    # 입력 유형 판별
    path = Path(arg)
    if path.exists() and arg.lower().endswith(".pdf"):
        paper, content = _from_pdf(path)
        source = "pdf"
    elif re.match(r'^10\.\d{4,}/', arg):
        paper, content = _from_doi(arg)
        source = "doi"
    else:
        paper, content = _from_keyword(arg)
        source = "keyword"

    if not paper:
        print("ERROR: 논문을 찾을 수 없습니다.")
        sys.exit(1)

    note_path = _save_note(paper, content, project_dir)

    print(f"NOTE_PATH={note_path}")
    print(f"TITLE={paper.title}")
    print(f"CITATION={paper.citation_str}")
    print(f"DOI={paper.doi}")
    print(f"ABSTRACT={paper.abstract[:300] if paper.abstract else content[:300]}")


if __name__ == "__main__":
    main()
