# annlib

**대학원생을 위한 논문 관리 올인원 대시보드**

논문 검색 → PDF 수집 → AI 요약 → Obsidian 저장 → RAG 질문까지  
하나의 Streamlit 대시보드에서 처리합니다.

> Google 계정만 있으면 바로 시작할 수 있습니다 (Gemini 무료 티어 기본 지원).

---

## 설치

```bash
pip install annlib
```

> Python 3.10 이상 필요

## 빠른 시작

```bash
# 1. 초기 설정 (API 키, Obsidian Vault 경로, 브라우저 설치 확인)
annlib setup

# 2. 대시보드 실행
annlib run
```

브라우저에서 `http://localhost:8501` 이 자동으로 열립니다.

---

## 주요 기능

| 페이지 | 기능 |
|--------|------|
| ⚙️ 설정 | API 키 등록, Vault 경로, Obsidian/Playwright 설치 안내 |
| 🔍 논문 검색 | OpenAlex API — 키워드 / 논문 제목 / 저자 / DOI 검색 |
| 📝 논문 요약 | PDF 수집 + LLM 요약 + Obsidian 노트 자동 저장 |
| 🧠 RAG 질문 | 수집한 논문 전체에 자연어 질문 (PageIndex 기반) |

### 📝 논문 요약 — 3가지 입력 방식

1. **검색 결과 요약** — OpenAlex 검색 후 선택한 논문을 바로 요약
2. **PDF 직접 업로드** — PDF 파일을 직접 올려서 요약
3. **📁 폴더 일괄 처리** — 로컬 폴더의 PDF를 한 번에 처리  
   - 이미 Vault에 저장된 논문은 자동 제외  
   - 파일별 중복 확인 + 선택/해제 가능

### 🧠 RAG 질문

- 답변 후 **후속 질문 버튼** 자동 생성 (클릭하면 바로 재질문)
- 다른 논문과의 연관성 자동 분석
- 질문 기록 자동 저장 (Obsidian RAG_Results 폴더)

---

## PDF 수집 방식 (자동 폴백)

1. OpenAlex 제공 PDF URL 직접 다운로드
2. Playwright → arXiv 자동 탐색
3. Playwright → PubMed Central 자동 탐색
4. fallback: 초록 텍스트로 요약

---

## 지원 LLM

| 제공사 | 모델 | 비고 |
|--------|------|------|
| **Google Gemini** | gemini-2.5-flash | **기본 권장 — 무료 티어 사용 가능** |
| OpenAI | gpt-4o-mini | API 크레딧 필요 |
| Anthropic Claude | claude-haiku-4-5 | API 크레딧 필요 |

---

## 요구사항

- Python 3.10+
- [Obsidian](https://obsidian.md/) — 노트 확인용 (annlib setup 에서 설치 안내)
- Chrome 또는 Chromium — PDF 자동 수집용 (없으면 Playwright Chromium 자동 설치)

---

## 설정 파일 위치

```
~/.annlib/config.json   # API 키, Vault 경로 등 (자동 생성)
```

---

## 라이선스

MIT
