"""PageIndex RAG — 계층적 트리 기반 논문 인덱싱 및 질문 답변"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------

@dataclass
class TreeNode:
    title: str
    content: str
    children: list["TreeNode"] = field(default_factory=list)
    source_file: str = ""
    citation: str = ""   # "Kim et al. (2017), Nature"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "content": self.content[:500],
            "children": [c.to_dict() for c in self.children],
            "source": self.source_file,
        }


@dataclass
class PageIndex:
    roots: list[TreeNode] = field(default_factory=list)
    source_count: int = 0


@dataclass
class RAGReference:
    title: str
    section: str
    excerpt: str


@dataclass
class RAGResult:
    answer: str
    references: list[RAGReference] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 인덱스 빌드
# ---------------------------------------------------------------------------

def build_index(md_files: list[Path], cfg: dict) -> PageIndex:
    """
    Obsidian Papers/ 폴더의 Markdown 파일들을 읽어
    PageIndex 트리 구조로 인덱싱합니다.
    """
    index = PageIndex()

    for md_file in md_files:
        if md_file.stem.startswith("_"):
            continue  # _Index.md 등 제외

        try:
            content = md_file.read_text(encoding="utf-8")
            root = _parse_markdown_to_tree(content, md_file.stem)
            index.roots.append(root)
        except Exception:
            continue

    index.source_count = len(index.roots)
    return index


def _citation_from_frontmatter(content: str) -> str:
    """YAML frontmatter에서 '1저자 et al. (연도), 저널명' 형식 문자열을 만듭니다."""
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return ""
    fm = fm_match.group(1)

    year = ""
    m = re.search(r'^year:\s*(\d+)', fm, re.MULTILINE)
    if m:
        year = m.group(1)

    authors_raw = ""
    m = re.search(r'^authors:\s*"(.+?)"', fm, re.MULTILINE)
    if m:
        authors_raw = m.group(1)

    journal = ""
    m = re.search(r'^journal:\s*"(.+?)"', fm, re.MULTILINE)
    if m:
        journal = m.group(1).strip()

    # 1저자 성(last name) 추출
    first = authors_raw.split(",")[0].split("외")[0].strip()
    last_name = first.split()[-1] if first else "Unknown"
    et_al = " et al." if ("외" in authors_raw or "," in authors_raw) else ""

    year_part = f" ({year})" if year else ""
    journal_part = f", {journal}" if journal else ""
    return f"{last_name}{et_al}{year_part}{journal_part}"


def _parse_markdown_to_tree(content: str, filename: str) -> TreeNode:
    """Markdown을 헤딩 기반 트리로 파싱합니다."""
    citation = _citation_from_frontmatter(content)

    # frontmatter 제거
    content = re.sub(r"^---.*?---\n", "", content, flags=re.DOTALL)

    lines = content.split("\n")
    root = TreeNode(title=filename, content="", source_file=filename, citation=citation)
    current_h2: TreeNode | None = None
    current_h3: TreeNode | None = None
    buffer: list[str] = []

    def flush(node: TreeNode, buf: list[str]) -> None:
        node.content = "\n".join(buf).strip()
        buf.clear()

    for line in lines:
        if line.startswith("## "):
            if current_h2:
                flush(current_h2, buffer)
            current_h2 = TreeNode(
                title=line[3:].strip(),
                content="",
                source_file=filename,
            )
            root.children.append(current_h2)
            current_h3 = None
        elif line.startswith("### ") and current_h2:
            if current_h3:
                flush(current_h3, buffer)
            elif buffer:
                flush(current_h2, buffer)
            current_h3 = TreeNode(
                title=line[4:].strip(),
                content="",
                source_file=filename,
            )
            current_h2.children.append(current_h3)
        else:
            buffer.append(line)

    # 버퍼 마무리
    if current_h3:
        flush(current_h3, buffer)
    elif current_h2:
        flush(current_h2, buffer)
    else:
        flush(root, buffer)

    return root


# ---------------------------------------------------------------------------
# 인덱스 쿼리
# ---------------------------------------------------------------------------

def query_index(index: PageIndex, question: str, cfg: dict) -> RAGResult:
    """
    PageIndex에서 질문과 관련된 섹션을 LLM 추론으로 찾아 답변합니다.
    """
    provider = cfg.get("llm_provider", "openai")
    api_key = cfg.get("llm_api_key", "")

    if not api_key:
        raise ValueError("LLM API 키가 설정되지 않았습니다.")

    # 1단계: 관련 논문 선택
    relevant_roots = _select_relevant_papers(index, question, provider, api_key)

    if not relevant_roots:
        return RAGResult(answer="관련 논문을 찾지 못했습니다.")

    # 2단계: 관련 섹션 추출
    relevant_sections = _select_relevant_sections(relevant_roots, question, provider, api_key)

    # 3단계: 최종 답변 생성
    answer = _generate_answer(question, relevant_sections, provider, api_key)

    references = [
        RAGReference(
            title=sec["paper"],
            section=sec["section"],
            excerpt=sec["content"][:300],
        )
        for sec in relevant_sections
    ]

    return RAGResult(answer=answer, references=references)


def _select_relevant_papers(
    index: PageIndex,
    question: str,
    provider: str,
    api_key: str,
) -> list[TreeNode]:
    """논문 목록 중 질문과 관련된 논문을 선택합니다."""
    paper_list = "\n".join(
        f"{i+1}. {root.title}: {root.content[:200]}"
        for i, root in enumerate(index.roots)
    )

    prompt = f"""다음 논문 목록에서 아래 질문에 답하는 데 관련된 논문 번호를 JSON으로 응답하세요.

질문: {question}

논문 목록:
{paper_list}

응답 형식: {{"relevant": [1, 3, 5]}}
최대 5개까지 선택하세요."""

    response = _call_llm(prompt, provider, api_key)

    try:
        data = json.loads(response)
        indices = [i - 1 for i in data.get("relevant", [])]
        return [index.roots[i] for i in indices if 0 <= i < len(index.roots)]
    except Exception:
        return index.roots[:3]  # 파싱 실패 시 상위 3개


def _select_relevant_sections(
    roots: list[TreeNode],
    question: str,
    provider: str,
    api_key: str,
) -> list[dict[str, str]]:
    """선택된 논문에서 관련 섹션을 추출합니다."""
    sections = []

    for root in roots:
        for child in root.children:
            if child.content.strip():
                sections.append({
                    "paper": root.title,
                    "citation": root.citation,
                    "section": child.title,
                    "content": child.content,
                })
            for grandchild in child.children:
                if grandchild.content.strip():
                    sections.append({
                        "paper": root.title,
                        "citation": root.citation,
                        "section": f"{child.title} > {grandchild.title}",
                        "content": grandchild.content,
                    })

    if not sections:
        return [{"paper": r.title, "citation": r.citation, "section": "전체", "content": r.content} for r in roots]

    section_list = "\n".join(
        f"{i+1}. [{s['paper']}] {s['section']}: {s['content'][:150]}..."
        for i, s in enumerate(sections)
    )

    prompt = f"""다음 섹션 목록에서 아래 질문에 답하는 데 가장 관련된 섹션 번호를 JSON으로 응답하세요.

질문: {question}

섹션 목록:
{section_list}

응답 형식: {{"relevant": [1, 2, 4]}}
최대 5개까지 선택하세요."""

    response = _call_llm(prompt, provider, api_key)

    try:
        data = json.loads(response)
        indices = [i - 1 for i in data.get("relevant", [])]
        return [sections[i] for i in indices if 0 <= i < len(sections)]
    except Exception:
        return sections[:5]


def _display_title(stem: str) -> str:
    """파일명 stem을 사람이 읽기 좋은 제목으로 변환합니다."""
    return re.sub(r"^\d{4}_", "", stem).replace("_", " ").strip(", ")


def _generate_answer(
    question: str,
    sections: list[dict[str, str]],
    provider: str,
    api_key: str,
) -> str:
    """추출된 섹션을 바탕으로 최종 답변을 생성합니다."""
    # 논문별 citation 문자열 수집 (중복 제거)
    seen: dict[str, str] = {}  # paper stem → citation
    for s in sections:
        stem = s["paper"]
        if stem not in seen:
            seen[stem] = s.get("citation") or _display_title(stem)

    context = "\n\n".join(
        f"[{seen[s['paper']]}] {s.get('section', '')}\n{s['content']}"
        for s in sections
    )

    # 인용 키 예시 (첫 번째 논문)
    example_cit = next(iter(seen.values()), "Kim et al. (2017), Nature")

    prompt = f"""다음 논문 섹션들을 참고하여 아래 질문에 한국어로 답변해 주세요.

질문: {question}

참고 자료:
{context}

【인용 규칙 — 반드시 준수】
- 인용할 때는 참고 자료 앞의 대괄호 키를 그대로 복사하세요.
  올바른 예: "~로 나타났다 [{example_cit}]."
- 같은 논문을 여러 섹션에서 참고해도 키는 하나만 씁니다.
- 키 뒤에 숫자, 섹션명, 쉼표+숫자를 절대 추가하지 마세요.
  잘못된 예: [{example_cit}, 1], [{example_cit}, 핵심 기여]
- 파일명(언더스코어 포함)은 절대 쓰지 마세요."""

    answer = _call_llm(prompt, provider, api_key)

    # 참고문헌 목록 (중복 없이 논문별 1줄)
    unique_refs = list(dict.fromkeys(seen.values()))
    refs = "\n".join(f"- {c}" for c in unique_refs)
    return f"{answer}\n\n**참고문헌**\n{refs}"


# ---------------------------------------------------------------------------
# LLM 호출 (공통)
# ---------------------------------------------------------------------------

def _call_llm(prompt: str, provider: str, api_key: str) -> str:
    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return resp.choices[0].message.content

    elif provider == "gemini":
        from google import genai
        client = genai.Client(api_key=api_key)
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        ).text

    elif provider == "claude":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    raise ValueError(f"지원하지 않는 LLM: {provider}")
