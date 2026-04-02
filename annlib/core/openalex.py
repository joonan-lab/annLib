"""OpenAlex API 클라이언트"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

import requests

from annlib import config

OPENALEX_BASE = "https://api.openalex.org"
TIMEOUT = 15


@dataclass
class Paper:
    title: str
    doi: str
    year: int
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    cited_by_count: int = 0
    is_oa: bool = False
    pdf_url: Optional[str] = None
    openalex_id: str = ""
    concepts: list[str] = field(default_factory=list)
    journal: str = ""

    @property
    def authors_str(self) -> str:
        if not self.authors:
            return "저자 미상"
        if len(self.authors) <= 3:
            return ", ".join(self.authors)
        return f"{self.authors[0]} 외 {len(self.authors) - 1}명"

    @property
    def citation_str(self) -> str:
        """1저자 et al. (연도) 저널명 형식."""
        if not self.authors:
            first = "저자 미상"
        else:
            # 성(last name)만 추출
            first = self.authors[0].split()[-1]
        suffix = " et al." if len(self.authors) > 1 else ""
        year_part = f" ({self.year})" if self.year else ""
        journal_part = f" {self.journal}" if self.journal else ""
        return f"{first}{suffix}{year_part}{journal_part}"

    @property
    def safe_filename(self) -> str:
        name = f"{self.year}_{self.title[:60]}"
        return re.sub(r'[\\/:*?"<>|]', "_", name)


def _headers() -> dict[str, str]:
    email = config.get("openalex_email")
    if email:
        return {"User-Agent": f"annlib/0.1 (mailto:{email})"}
    return {"User-Agent": "annlib/0.1"}


def _parse_paper(item: dict) -> Paper:
    # 저자 이름 추출
    authors = [
        authorship.get("author", {}).get("display_name", "")
        for authorship in item.get("authorships", [])
    ]
    authors = [a for a in authors if a]

    # 초록 (inverted index → 텍스트 복원)
    abstract = ""
    inv_index = item.get("abstract_inverted_index")
    if inv_index:
        try:
            positions: dict[str, list[int]] = {}
            for word, pos_list in inv_index.items():
                for pos in pos_list:
                    positions[pos] = word
            abstract = " ".join(positions[i] for i in sorted(positions))
        except Exception:
            abstract = ""

    # PDF URL (best OA location)
    pdf_url = None
    oa_locations = item.get("open_access", {})
    best_oa = item.get("best_oa_location") or {}
    pdf_url = best_oa.get("pdf_url")

    # 개념/키워드
    concepts = [
        c.get("display_name", "")
        for c in item.get("concepts", [])
        if c.get("score", 0) > 0.3
    ][:5]

    doi = item.get("doi", "") or ""
    doi = doi.replace("https://doi.org/", "")

    # 저널명
    primary_loc = item.get("primary_location") or {}
    source = primary_loc.get("source") or {}
    journal = source.get("display_name", "") or ""

    return Paper(
        title=item.get("display_name", "제목 없음"),
        doi=doi,
        year=item.get("publication_year") or 0,
        authors=authors,
        abstract=abstract,
        cited_by_count=item.get("cited_by_count", 0),
        is_oa=item.get("open_access", {}).get("is_oa", False),
        pdf_url=pdf_url,
        openalex_id=item.get("id", ""),
        concepts=concepts,
        journal=journal,
    )


def search_papers(
    query: str,
    search_mode: str = "keyword",   # keyword | title | author | doi
    year_from: int = 2000,
    oa_only: bool = False,
    per_page: int = 10,
    sort: str = "cited_by_count:desc",
) -> list[Paper]:
    """
    OpenAlex works 엔드포인트로 논문을 검색합니다.

    search_mode:
      - keyword : 제목·초록·전문 전체 검색 (기본)
      - title   : 제목만 검색
      - author  : 저자명 검색
      - doi     : DOI 직접 조회 (단일 결과)
    """
    # DOI 직접 조회
    if search_mode == "doi":
        doi_clean = query.strip().replace("https://doi.org/", "")
        paper = fetch_by_doi(doi_clean)
        return [paper] if paper else []

    filters = [f"publication_year:>{year_from - 1}"]
    if oa_only:
        filters.append("is_oa:true")

    params: dict = {
        "sort": sort,
        "per-page": per_page,
        "select": (
            "id,display_name,doi,publication_year,authorships,"
            "abstract_inverted_index,cited_by_count,open_access,"
            "best_oa_location,concepts,primary_location"
        ),
    }

    if search_mode == "title":
        # 제목 필드만 검색
        filters.append(f"title.search:{query}")
        params["filter"] = ",".join(filters)
    elif search_mode == "author":
        # 저자 display_name 검색 — filter로 처리
        filters.append(f"authorships.author.display_name.search:{query}")
        params["filter"] = ",".join(filters)
    else:
        # keyword: 전문 검색 (search 파라미터)
        params["search"] = query
        params["filter"] = ",".join(filters)

    resp = requests.get(
        f"{OPENALEX_BASE}/works",
        params=params,
        headers=_headers(),
        timeout=TIMEOUT,
    )
    resp.raise_for_status()

    results = resp.json().get("results", [])
    return [_parse_paper(item) for item in results]


def fetch_by_doi(doi: str) -> Optional[Paper]:
    """DOI로 단일 논문을 가져옵니다."""
    encoded = quote(doi, safe="")
    resp = requests.get(
        f"{OPENALEX_BASE}/works/https://doi.org/{encoded}",
        headers=_headers(),
        timeout=TIMEOUT,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _parse_paper(resp.json())
