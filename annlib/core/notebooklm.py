"""NotebookLM 연동 — 논문 요약 생성"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

from annlib.core.openalex import Paper

PDF_OR_TEXT = Union[Path, str]


@dataclass
class PaperSummary:
    title: str
    key_contribution: str
    methodology: str
    results: str
    limitations: str
    related_papers: list[str]
    keywords: list[str]
    raw_text: str = ""


def summarize_paper(
    paper: Paper,
    content: PDF_OR_TEXT,
    cfg: dict,
    mode: str = "llm",              # "llm" | "notebooklm"
    generate_podcast: bool = False,
    keep_notebook: bool = False,
) -> PaperSummary:
    """
    논문을 요약합니다.

    mode:
      - "llm"         : 설정된 LLM API 직접 호출 (OpenAI/Gemini/Claude)
      - "notebooklm"  : notebooklm-py로 Google NotebookLM에 업로드 후 요약
    """
    # 텍스트 준비
    if isinstance(content, Path):
        from annlib.core.pdf_fetcher import extract_text_from_pdf
        text = extract_text_from_pdf(content)
    else:
        text = content

    if mode == "notebooklm":
        return _summarize_via_notebooklm_py(
            paper, text, generate_podcast=generate_podcast, keep_notebook=keep_notebook
        )

    # LLM 모드 — 컨텍스트 길이 제한
    text = text[:12000] if len(text) > 12000 else text
    return _summarize_with_llm(paper, text, cfg)


def _summarize_via_notebooklm_py(
    paper: Paper,
    text: str,
    generate_podcast: bool = False,
    keep_notebook: bool = False,
) -> PaperSummary:
    """notebooklm-py를 통해 Google NotebookLM으로 요약합니다."""
    import asyncio
    from annlib.core.notebooklm_client import summarize_with_notebooklm

    result = asyncio.run(
        summarize_with_notebooklm(
            title=paper.title,
            text=text,
            generate_podcast=generate_podcast,
            keep_notebook=keep_notebook,
        )
    )

    # NotebookLM 응답을 PaperSummary 구조로 파싱
    raw = result.summary
    return _parse_notebooklm_response(paper, raw, result.podcast_path)


def _build_prompt(paper: Paper, text: str) -> str:
    abstract_hint = f"\n\n[초록]\n{paper.abstract}" if paper.abstract else ""
    content_hint = f"\n\n[본문 발췌]\n{text}" if text and not text.startswith("[초록 없음]") else ""

    return f"""다음 학술 논문을 한국어로 요약해 주세요.

[논문 정보]
제목: {paper.title}
저자: {paper.authors_str}
연도: {paper.year}
{abstract_hint}{content_hint}

아래 JSON 형식으로 정확히 응답해 주세요:
{{
  "key_contribution": "핵심 기여 (2-3문장)",
  "methodology": "방법론 설명 (2-3문장)",
  "results": "주요 결과 (2-3문장)",
  "limitations": "한계점 (1-2문장)",
  "related_papers": ["관련 논문 키워드 1", "관련 논문 키워드 2"],
  "keywords": ["키워드1", "키워드2", "키워드3"]
}}"""


def _summarize_with_notebooklm(paper: Paper, text: str, api_key: str) -> PaperSummary:
    """(deprecated) 공식 API 공개 전 stub — notebooklm-py로 대체됨"""
    raise NotImplementedError("notebooklm-py 방식을 사용하세요.")


def _parse_notebooklm_response(
    paper: Paper, raw: str, podcast_path=None
) -> PaperSummary:
    """
    NotebookLM chat 응답(자유 텍스트)을 PaperSummary로 변환합니다.
    섹션 헤딩이 없는 경우 전체를 key_contribution에 저장합니다.
    """
    import re

    sections = {
        "key_contribution": "",
        "methodology": "",
        "results": "",
        "limitations": "",
    }

    # "핵심 기여", "방법론", "주요 결과", "한계점" 섹션 추출 시도
    patterns = {
        "key_contribution": r"핵심\s*기여[:\s]+(.+?)(?=방법론|주요\s*결과|한계|$)",
        "methodology":      r"방법론[:\s]+(.+?)(?=핵심|주요\s*결과|한계|$)",
        "results":          r"주요\s*결과[:\s]+(.+?)(?=핵심|방법론|한계|$)",
        "limitations":      r"한계점?[:\s]+(.+?)(?=핵심|방법론|주요|$)",
    }

    matched_any = False
    for key, pattern in patterns.items():
        m = re.search(pattern, raw, re.DOTALL | re.IGNORECASE)
        if m:
            sections[key] = m.group(1).strip()
            matched_any = True

    if not matched_any:
        sections["key_contribution"] = raw.strip()

    return PaperSummary(
        title=paper.title,
        key_contribution=sections["key_contribution"],
        methodology=sections["methodology"],
        results=sections["results"],
        limitations=sections["limitations"],
        related_papers=[],
        keywords=paper.concepts,
        raw_text=raw,
    )


def _summarize_with_llm(paper: Paper, text: str, cfg: dict) -> PaperSummary:
    """설정된 LLM으로 요약합니다."""
    provider = cfg.get("llm_provider", "openai")
    api_key = cfg.get("llm_api_key", "")

    if not api_key:
        raise ValueError("LLM API 키가 설정되지 않았습니다. 설정 페이지에서 API 키를 입력해 주세요.")

    # 잘못된 키 형식 조기 감지
    if provider == "claude" and not api_key.startswith("sk-ant-api"):
        raise ValueError(
            "Claude API 키 형식이 올바르지 않습니다.\n"
            "올바른 형식: sk-ant-api003-...\n"
            "console.anthropic.com → API Keys 탭에서 새 키를 발급받으세요.\n"
            "(sk-ant-oat 로 시작하는 것은 OAuth 토큰으로 API 키가 아닙니다)"
        )
    if provider == "openai" and not api_key.startswith("sk-"):
        raise ValueError("OpenAI API 키 형식이 올바르지 않습니다. platform.openai.com에서 확인하세요.")
    if provider == "gemini" and not api_key.startswith("AIza"):
        raise ValueError("Gemini API 키 형식이 올바르지 않습니다. aistudio.google.com에서 확인하세요.")

    prompt = _build_prompt(paper, text)

    if provider == "openai":
        response_text = _call_openai(prompt, api_key)
    elif provider == "gemini":
        response_text = _call_gemini(prompt, api_key)
    elif provider == "claude":
        response_text = _call_claude(prompt, api_key)
    else:
        raise ValueError(f"지원하지 않는 LLM 프로바이더: {provider}")

    return _parse_response(paper, response_text)


def _call_openai(prompt: str, api_key: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "당신은 학술 논문 요약 전문가입니다. JSON 형식으로만 응답하세요."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    return response.choices[0].message.content


def _call_gemini(prompt: str, api_key: str) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"JSON 형식으로만 응답하세요.\n\n{prompt}",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )
    return response.text


def _call_claude(prompt: str, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": f"JSON 형식으로만 응답하세요.\n\n{prompt}",
            }
        ],
    )
    return response.content[0].text


def _parse_response(paper: Paper, response_text: str) -> PaperSummary:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        # JSON 블록 추출 시도
        import re
        m = re.search(r"\{.*\}", response_text, re.DOTALL)
        if m:
            data = json.loads(m.group())
        else:
            data = {}

    return PaperSummary(
        title=paper.title,
        key_contribution=data.get("key_contribution", "요약 실패"),
        methodology=data.get("methodology", ""),
        results=data.get("results", ""),
        limitations=data.get("limitations", ""),
        related_papers=data.get("related_papers", []),
        keywords=data.get("keywords", paper.concepts),
        raw_text=response_text,
    )
