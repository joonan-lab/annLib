---
name: review-start
description: 리뷰 논문 연구 프로젝트를 시작합니다. 폴더 구조, CLAUDE.md, 질문 트리를 초기화합니다.
---

# /review-start

주제를 받아 리뷰 프로젝트를 초기화합니다.

## 실행 절차

### 1. 주제 확인
ARGUMENTS 가 있으면 그것을 주제로 사용합니다.
없으면 사용자에게 한 줄로 물어봅니다: "리뷰할 주제를 입력해 주세요 (예: maternal germline de novo mutations)"

### 2. 프로젝트 초기화
```bash
python -m annlib.review.project init "<주제>"
```
출력에서 `PROJECT_DIR=` 값을 읽습니다.

### 3. 사용자에게 안내
다음 내용을 마크다운으로 출력합니다:

```
## ✅ 프로젝트 생성 완료

**주제**: {주제}
**경로**: {PROJECT_DIR}

### 생성된 구조
{PROJECT_DIR}/
├── CLAUDE.md           ← 프로젝트 컨텍스트
├── papers/             ← 논문 노트 저장 위치
├── questions/
│   └── question-tree.md  ← 질문 계층 트리
└── themes/             ← 논문 간 테마 묶음

### 다음 단계
논문을 추가하세요:
  /review-add 10.1038/nature24018        ← DOI로 추가
  /review-add "maternal age mutation"   ← 키워드로 검색
  /review-add @논문.pdf                  ← PDF 직접 추가
```

### 4. 경로 이동 안내
터미널에서 `cd {PROJECT_DIR}` 하거나,
Claude Code에서 해당 폴더를 열면 이후 명령어가 자동으로 프로젝트를 인식합니다.
