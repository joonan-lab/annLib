"""Obsidian Vault — Markdown 노트 생성 및 저장

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 annlib 논문 노트 Markdown 규칙 (v1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

파일명 규칙:
  {연도}_{제목_앞60자}.md
  예) 2017_Attention_Is_All_You_Need.md
  - 특수문자·공백은 _ 로 치환
  - 입력 경로: Vault/Papers/

YAML Frontmatter 필드:
  title        : 논문 제목 (필수)
  authors      : 저자 문자열 (필수)
  year         : 출판 연도 int (없으면 0)
  doi          : DOI 문자열 (없으면 "")
  source       : "openalex" | "pdf_upload" | "manual"
  tags         : 키워드 리스트
  is_oa        : true | false
  cited_by     : 인용 횟수 int
  summary_date : 요약 생성 날짜 (YYYY-MM-DD)

본문 섹션 순서 (고정):
  # 제목
  메타 정보 블록
  ## 핵심 기여
  ## 방법론
  ## 주요 결과
  ## 한계점
  ## 관련 논문 / 키워드
  ## 개념
  --- (구분선)
  생성 서명

인덱스:
  Papers/_Index.md 에 자동 등록 (중복 방지)
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

from annlib.core.openalex import Paper
from annlib.core.notebooklm import PaperSummary


# ──────────────────────────────────────────────────────────────
# Vault 인덱스 캐시 — {정규화된_제목: 파일명(확장자 없음)}
# ──────────────────────────────────────────────────────────────

def _build_vault_index(papers_dir: Path) -> dict[str, str]:
    """
    기존 Papers/ 폴더의 .md 파일을 스캔하여
    {정규화 제목: 파일명(stem)} 딕셔너리를 반환합니다.
    """
    index: dict[str, str] = {}
    for md in papers_dir.glob("*.md"):
        if md.stem.startswith("_"):
            continue
        # 파일명에서 연도_ 접두사 제거 후 정규화
        stem = re.sub(r'^\d{4}_', '', md.stem)
        normalized = _normalize(stem)
        index[normalized] = md.stem
        # 원본 파일명도 등록
        index[_normalize(md.stem)] = md.stem
    return index


def _normalize(text: str) -> str:
    """비교용 정규화: 소문자, 특수문자 제거, 공백 통일."""
    return re.sub(r'[^a-z0-9가-힣]+', ' ', text.lower()).strip()


def _make_wikilinks(
    text: str,
    vault_index: dict[str, str],
    min_match_ratio: float = 0.6,
) -> str:
    """
    텍스트 내 단어/구절이 기존 논문 제목과 일치하면
    [[파일명|원본텍스트]] 위키링크로 교체합니다.

    min_match_ratio: 제목 단어 중 몇 %가 일치해야 링크로 인정할지
    """
    if not text or not vault_index:
        return text

    lines = text.split("\n")
    result = []

    for line in lines:
        # 이미 위키링크가 있는 줄은 건너뜀
        if "[[" in line:
            result.append(line)
            continue

        for norm_title, stem in vault_index.items():
            # 정규화된 제목 단어들
            title_words = norm_title.split()
            if len(title_words) < 2:
                continue  # 너무 짧은 제목은 오탐 위험

            # 줄에서 제목 단어들이 얼마나 등장하는지 확인
            line_norm = _normalize(line)
            matched   = sum(1 for w in title_words if w in line_norm)
            ratio     = matched / len(title_words)

            if ratio >= min_match_ratio:
                # 원본 대소문자 보존하면서 링크로 교체
                display = re.sub(r'^\d{4}_', '', stem).replace("_", " ")
                link    = f"[[{stem}|{display}]]"
                # 줄에 처음 등장하는 관련 구절을 링크로 교체 (1회만)
                escaped = re.escape(norm_title.replace(" ", ".{0,3}"))
                line = re.sub(
                    escaped, link, line,
                    count=1, flags=re.IGNORECASE,
                ) if re.search(escaped, line, re.IGNORECASE) else line + f" {link}"
                break  # 줄당 하나의 링크만

        result.append(line)

    return "\n".join(result)


# ──────────────────────────────────────────────────────────────
# 통합 노트 저장 (OpenAlex 검색 또는 PDF 업로드 공통 사용)
# ──────────────────────────────────────────────────────────────

def save_paper_note(
    paper: Paper,
    summary: PaperSummary,
    vault_path: str,
    source: str = "openalex",    # "openalex" | "pdf_upload" | "manual"
) -> Path:
    """논문 요약을 Obsidian Papers/ 폴더에 Markdown으로 저장합니다."""
    vault = Path(vault_path).expanduser()
    papers_dir = vault / "Papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    filename = _safe_filename(f"{paper.year}_{paper.title[:60]}") + ".md"
    dest = papers_dir / filename

    # 저장 전에 기존 논문 인덱스 빌드 (위키링크 자동 연결용)
    vault_index = _build_vault_index(papers_dir)

    content = _render_paper_note(paper, summary, source, vault_index)
    dest.write_text(content, encoding="utf-8")
    _update_index(vault, paper, filename)
    return dest


def _render_paper_note(
    paper: Paper,
    summary: PaperSummary,
    source: str,
    vault_index: dict[str, str] | None = None,
) -> str:
    """논문 노트 Markdown을 렌더링합니다 (규칙 고정)."""
    keywords = summary.keywords or paper.concepts or []
    concepts = ", ".join(paper.concepts) if paper.concepts else "없음"

    # 관련 논문 — Vault에 있는 논문은 [[위키링크]]로 변환
    related_items = summary.related_papers or []
    if vault_index and related_items:
        linked = []
        for item in related_items:
            norm = _normalize(item)
            # 정확 매칭 먼저
            if norm in vault_index:
                stem    = vault_index[norm]
                display = re.sub(r'^\d{4}_', '', stem).replace("_", " ")
                linked.append(f"- [[{stem}|{display}]]")
            else:
                # 부분 매칭: 아이템 단어 중 60% 이상 제목에 포함
                matched_stem = None
                best_ratio   = 0.0
                item_words   = norm.split()
                for t_norm, t_stem in vault_index.items():
                    if len(item_words) == 0:
                        continue
                    ratio = sum(1 for w in item_words if w in t_norm) / len(item_words)
                    if ratio > best_ratio:
                        best_ratio   = ratio
                        matched_stem = t_stem
                if best_ratio >= 0.6 and matched_stem:
                    display = re.sub(r'^\d{4}_', '', matched_stem).replace("_", " ")
                    linked.append(f"- [[{matched_stem}|{display}]] *(관련: {item})*")
                else:
                    linked.append(f"- {item}")
        related = "\n".join(linked) if linked else "없음"
    else:
        related = "\n".join(f"- {r}" for r in related_items) or "없음"
    doi_link = f"[{paper.doi}](https://doi.org/{paper.doi})" if paper.doi else "없음"
    oa_str   = "예" if paper.is_oa else "아니오"

    source_label = {
        "openalex":   "OpenAlex 검색",
        "pdf_upload": "PDF 직접 업로드",
        "manual":     "수동 입력",
    }.get(source, source)

    return f"""---
title: "{_escape_yaml(paper.title)}"
authors: "{_escape_yaml(paper.authors_str)}"
year: {paper.year or 0}
journal: "{_escape_yaml(paper.journal or '')}"
doi: "{paper.doi or ''}"
source: {source}
tags: [{", ".join(keywords)}]
is_oa: {str(paper.is_oa).lower()}
cited_by: {paper.cited_by_count}
summary_date: {date.today().isoformat()}
---

# {paper.title}

| 항목 | 내용 |
|------|------|
| **저자** | {paper.authors_str} |
| **연도** | {paper.year or "미상"} |
| **DOI** | {doi_link} |
| **출처** | {source_label} |
| **오픈 액세스** | {oa_str} |
| **인용** | {paper.cited_by_count:,}회 |

---

## 핵심 기여

{summary.key_contribution or "—"}

## 방법론

{summary.methodology or "—"}

## 주요 결과

{summary.results or "—"}

## 한계점

{summary.limitations or "—"}

## 관련 논문 / 키워드

{related}

## 개념

{concepts}

---

*annlib 자동 생성 · {source_label} · {date.today().isoformat()}*
"""


# ──────────────────────────────────────────────────────────────
# RAG 결과 저장
# ──────────────────────────────────────────────────────────────

def save_rag_result(
    question: str,
    result: "RAGResult",
    vault_path: str,
    followups: list[str] | None = None,
    cross_refs: list[dict] | None = None,
) -> Path:
    """RAG 질문 결과를 Obsidian RAG_Results/ 폴더에 저장합니다."""
    vault = Path(vault_path).expanduser()
    rag_dir = vault / "RAG_Results"
    rag_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    filename = f"{today}_{_safe_filename(question[:50])}.md"
    dest = rag_dir / filename

    # 참고 논문 — Vault 논문은 위키링크로
    vault_index = _build_vault_index(vault / "Papers")
    refs_md = ""
    for ref in (result.references or []):
        norm = _normalize(ref.title)
        stem = vault_index.get(norm)
        if not stem:
            # 부분 매칭
            for t_norm, t_stem in vault_index.items():
                words = norm.split()
                if words and sum(1 for w in words if w in t_norm) / len(words) >= 0.6:
                    stem = t_stem
                    break
        if stem:
            display = re.sub(r'^\d{4}_', '', stem).replace("_", " ")
            title_link = f"[[{stem}|{display}]]"
        else:
            title_link = ref.title
        refs_md += f"\n#### {title_link}\n\n> {ref.excerpt}\n\n*섹션: {ref.section}*\n"

    # 후속 질문
    followup_md = ""
    if followups:
        followup_md = "\n".join(f"- {q}" for q in followups)

    # 다른 논문과의 연관성
    cross_md = ""
    if cross_refs:
        for cr in cross_refs:
            stem = vault_index.get(_normalize(cr.get("title", "")))
            if stem:
                display = re.sub(r'^\d{4}_', '', stem).replace("_", " ")
                link = f"[[{stem}|{display}]]"
            else:
                link = cr.get("title", "")
            cross_md += f"\n- {link}: {cr.get('relevance', '')}\n"

    dest.write_text(
        f"""---
date: {today}
question: "{_escape_yaml(question)}"
type: rag-result
tags: [rag-result]
---

# {question}

## 답변

{result.answer}

## 후속 질문 제안

{followup_md or "없음"}

## 다른 논문과의 연관성

{cross_md.strip() or "없음"}

## 참고 논문

{refs_md.strip() or "없음"}

---

*annlib RAG · {today}*
""",
        encoding="utf-8",
    )
    return dest


def load_rag_result(md_path: Path) -> dict:
    """저장된 RAG 결과 Markdown을 파싱하여 반환합니다."""
    text = md_path.read_text(encoding="utf-8")

    # frontmatter 제거
    body = re.sub(r'^---.*?---\n', '', text, flags=re.DOTALL).strip()

    def _extract_section(src: str, heading: str) -> str:
        pattern = rf'## {re.escape(heading)}\n+(.*?)(?=\n## |\Z)'
        m = re.search(pattern, src, re.DOTALL)
        return m.group(1).strip() if m else ""

    return {
        "filename": md_path.stem,
        "question": _extract_section(body, "질문") or re.sub(r'^# ', '', body.split('\n')[0]),
        "answer":      _extract_section(body, "답변"),
        "followups":   _extract_section(body, "후속 질문 제안"),
        "cross_refs":  _extract_section(body, "다른 논문과의 연관성"),
        "refs":        _extract_section(body, "참고 논문"),
        "raw":         body,
    }


# ──────────────────────────────────────────────────────────────
# 인덱스 관리
# ──────────────────────────────────────────────────────────────

def _update_index(vault: Path, paper: Paper, filename: str) -> None:
    """Papers/_Index.md 에 논문을 추가합니다 (중복 방지)."""
    index_path = vault / "Papers" / "_Index.md"

    if not index_path.exists():
        index_path.write_text(
            "# 논문 인덱스\n\nannlib으로 관리되는 논문 목록입니다.\n\n"
            "| 제목 | 저자 | 연도 | 출처 | DOI |\n"
            "|------|------|------|------|-----|\n",
            encoding="utf-8",
        )

    existing = index_path.read_text(encoding="utf-8")
    uid = paper.doi or paper.title
    if uid and uid in existing:
        return

    row = (
        f"| [[{filename[:-3]}\\|{paper.title[:45]}]] "
        f"| {paper.authors_str} "
        f"| {paper.year or '미상'} "
        f"| {paper.doi or '-'} |\n"
    )
    index_path.write_text(existing + row, encoding="utf-8")


# ──────────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")


def _escape_yaml(value: str) -> str:
    return value.replace('"', '\\"')
