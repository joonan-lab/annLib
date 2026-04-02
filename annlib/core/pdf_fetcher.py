"""PDF 수집 — 직접 다운로드 우선, Playwright fallback"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Union
from urllib.parse import urlparse

import httpx

from annlib.core.openalex import Paper

# PDF 저장 디렉토리
PDF_CACHE_DIR = Path.home() / ".annlib" / "pdf_cache"
PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

PDFResult = Union[Path, str]  # Path = PDF 파일, str = 텍스트 fallback


async def fetch_pdf(paper: Paper) -> PDFResult:
    """
    논문 PDF를 수집합니다.
    1순위: OpenAlex PDF URL 직접 다운로드
    2순위: Playwright → arXiv 탐색
    3순위: Playwright → PubMed Central 탐색
    fallback: 초록 텍스트 반환
    """

    # 캐시 확인
    cached = _cached_path(paper)
    if cached and cached.exists():
        return cached

    # 1순위: 직접 다운로드
    if paper.pdf_url:
        try:
            path = await _direct_download(paper.pdf_url, paper.safe_filename)
            if path:
                return path
        except Exception:
            pass

    # 2순위: Playwright arXiv
    arxiv_id = _extract_arxiv_id(paper.doi, paper.title)
    if arxiv_id:
        try:
            path = await _playwright_arxiv(arxiv_id, paper.safe_filename)
            if path:
                return path
        except Exception:
            pass

    # 3순위: Playwright PMC
    pmcid = await _lookup_pmcid(paper.doi)
    if pmcid:
        try:
            path = await _playwright_pmc(pmcid, paper.safe_filename)
            if path:
                return path
        except Exception:
            pass

    # fallback: 초록
    return paper.abstract or f"[초록 없음] {paper.title}"


def _cached_path(paper: Paper) -> Path | None:
    if not paper.safe_filename:
        return None
    return PDF_CACHE_DIR / f"{paper.safe_filename}.pdf"


async def _direct_download(url: str, filename: str) -> Path | None:
    dest = PDF_CACHE_DIR / f"{filename}.pdf"
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.get(url, headers={"User-Agent": "annlib/0.1"})
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type and not url.endswith(".pdf"):
            return None
        dest.write_bytes(resp.content)
    return dest


def _extract_arxiv_id(doi: str, title: str = "") -> str | None:
    """DOI 또는 제목에서 arXiv ID를 추출합니다."""
    # DOI에서 추출 (예: 10.48550/arXiv.2305.12345)
    if doi:
        m = re.search(r"arXiv[.:](\d{4}\.\d{4,5})", doi, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", doi, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


async def _lookup_pmcid(doi: str) -> str | None:
    """DOI → PubMed Central ID 변환"""
    if not doi:
        return None
    try:
        url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"ids": doi, "format": "json"})
            data = resp.json()
            records = data.get("records", [])
            if records and "pmcid" in records[0]:
                return records[0]["pmcid"].replace("PMC", "")
    except Exception:
        pass
    return None


def _browser_launch_kwargs() -> dict:
    """설정에서 browser_channel을 읽어 Playwright launch 파라미터를 반환합니다."""
    from annlib import config as cfg_module
    channel = cfg_module.get("browser_channel", "chromium")
    if channel == "chrome":
        return {"channel": "chrome", "headless": True}
    return {"headless": True}  # Chromium 기본


async def _playwright_arxiv(arxiv_id: str, filename: str) -> Path | None:
    """Playwright로 arXiv PDF를 다운로드합니다."""
    from playwright.async_api import async_playwright

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    dest = PDF_CACHE_DIR / f"{filename}.pdf"

    async with async_playwright() as p:
        browser = await p.chromium.launch(**_browser_launch_kwargs())
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                resp = await client.get(
                    pdf_url,
                    headers={"User-Agent": "Mozilla/5.0 annlib/0.1"},
                )
                if resp.status_code == 200 and "pdf" in resp.headers.get("content-type", ""):
                    dest.write_bytes(resp.content)
                    return dest
        finally:
            await browser.close()

    return None


async def _playwright_pmc(pmcid: str, filename: str) -> Path | None:
    """Playwright로 PubMed Central PDF를 다운로드합니다."""
    from playwright.async_api import async_playwright

    dest = PDF_CACHE_DIR / f"{filename}.pdf"

    async with async_playwright() as p:
        browser = await p.chromium.launch(**_browser_launch_kwargs())
        try:
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            await page.goto(f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/pdf/")

            pdf_links = await page.query_selector_all("a[href*='.pdf']")
            for link in pdf_links:
                href = await link.get_attribute("href")
                if href:
                    if not href.startswith("http"):
                        href = "https://www.ncbi.nlm.nih.gov" + href
                    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                        resp = await client.get(href)
                        if resp.status_code == 200:
                            dest.write_bytes(resp.content)
                            return dest
        except Exception:
            pass
        finally:
            await browser.close()

    return None


def extract_text_from_pdf(pdf_path: Path) -> str:
    """PDF 파일에서 텍스트를 추출합니다."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(str(pdf_path))
        texts = []
        for page in reader.pages[:30]:  # 최대 30페이지
            texts.append(page.extract_text() or "")
        return "\n".join(texts)
    except Exception as e:
        return f"[PDF 텍스트 추출 실패: {e}]"
