<p align="center">
  <h1 align="center">dochan (독한)</h1>
  <p align="center">
    <strong>독한 native 문서 파서 — AI/LLM 최적 Markdown 변환</strong>
  </p>
  <p align="center">
    The toughest Korean document parser. HWP/HWPX/Office → Markdown, JSON, Plain Text.
  </p>
  <p align="center">
    <a href="https://pypi.org/project/dochan/"><img src="https://img.shields.io/pypi/v/dochan?color=blue&cacheSeconds=60" alt="PyPI"></a>
    <a href="https://pypi.org/project/dochan/"><img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
    <a href="https://github.com/illuwa/dochan/stargazers"><img src="https://img.shields.io/github/stars/illuwa/dochan?style=social" alt="GitHub Stars"></a>
  </p>
</p>

---

## What is dochan?

**dochan**(독한)은 한글(HWP/HWPX)과 Office 문서를 native로 파싱하여 AI/LLM이 바로 사용할 수 있는 Markdown으로 변환하는 Python 파서입니다.

- `doc` (문서) + `한` (韓, 한국) = **dochan** — "독한 파서"라는 더블 미닝
- HWP 5.0 바이너리 + HWPX(OWPML) XML + Office OOXML/legacy binary 1차 지원
- 155개 실문서로 검증, 평균 96.5점, 공개가능한 문서로 계속 학습시켜 개선할 예정

```python
from dochan import Dochan

doc = Dochan("공문서.hwp")
print(doc.to_markdown())
```

## Features

| 기능 | 설명 |
|------|------|
| **HWP + HWPX + Office** | HWP/HWPX, Office OOXML(.docx/.pptx/.xlsx), legacy Office(.doc/.ppt/.xls)를 native parser로 파싱 |
| **Markdown 출력** | 제목, 표, 서식(bold/italic), 수식까지 AI가 바로 쓸 수 있는 Markdown |
| **표 파싱** | 셀 병합, 중첩 표, 좌표 배치 지원 |
| **서식 보존** | CharShape 기반 bold/italic/글자크기 → TextRun 연결 |
| **제목 자동 감지** | Style 이름 + 글자 크기 기반 heading 레벨 판별 |
| **수식 LaTeX** | HWP 수식 스크립트 → LaTeX 기본 변환 |
| **JSON / Plain Text** | Markdown 외 구조화 JSON, 플레인 텍스트 출력 |
| **OCR (선택)** | Tesseract 연동, 이미지 속 텍스트 추출 |
| **CLI** | `dochan convert 문서.hwp` 한 줄로 변환 |
| **배치 처리** | 디렉토리 단위 병렬 변환 |
| **보안** | Zip Bomb, XXE, Path Traversal, 메모리 폭발 방어 |

## Installation

```bash
pip install dochan
```

OCR 기능이 필요한 경우:
```bash
pip install dochan[ocr]
brew install tesseract tesseract-lang  # macOS
```

## Quick Start

### Python API

```python
from dochan import Dochan

# HWP, HWPX, DOC, PPT, XLS, DOCX, PPTX, XLSX
doc = Dochan("보고서.hwp")

# AI/LLM용 Markdown
markdown = doc.to_markdown()

# 구조화 JSON
json_str = doc.to_json()

# 플레인 텍스트
text = doc.to_plain_text()

# 요소별 접근
for table in doc.find_all('table'):
    print(f"표: {table.row_count}행 x {table.col_count}열")

for eq in doc.find_all('equation'):
    print(f"수식: {eq.latex}")

# 메타데이터
print(doc.metadata)
```

### CLI

```bash
# Markdown 변환 (stdout)
dochan convert 문서.hwp

# 파일로 저장
dochan convert 문서.hwp -o output.md

# JSON 출력
dochan convert 문서.hwpx --format json

# Word DOCX 변환
dochan convert 문서.docx

# Legacy Word DOC 변환
dochan convert 문서.doc

# PowerPoint PPTX 변환
dochan convert 발표.pptx

# Legacy PowerPoint PPT 변환
dochan convert 발표.ppt

# Excel XLSX 변환
dochan convert 표.xlsx

# Legacy Excel XLS 변환
dochan convert 표.xls

# 디렉토리 일괄 변환
dochan batch input_dir/ output_dir/ --format markdown --workers 4

# 문서 정보
dochan info 문서.hwp
```

### OCR (이미지 속 텍스트 추출)

```python
doc = Dochan("이미지포함문서.hwpx", ocr=True)
print(doc.to_markdown())  # 이미지 속 텍스트도 포함
```

## Output Examples

### Input: 한글 공문서 (.hwp)

### Output: Markdown

```markdown
# **사내 규정집**

| 연번 | 내용 | 일자 |
| --- | --- | --- |
| 1 | 제정 | 2020. 3. 1. |
| 2 | 개정 | 2024. 9.15. |

### **제1장 총칙**

**제1조(목적)** 이 규정은 회사 직원의 복무에 관한 사항을 정함을
목적으로 한다.
```

## Supported Elements

| 요소 | HWP | HWPX | DOC | PPT | XLS | DOCX | PPTX | XLSX |
|------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 텍스트 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 표 (단순) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 표 (셀 병합) | ✅ | ✅ | ⬜ | ⬜ | ✅ | ✅ | ✅ | ✅ |
| 표 (중첩 텍스트) | ✅ | ✅ | ⬜ | ⬜ | — | ✅ | ⬜ | — |
| 서식 (bold/italic) | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ✅ | ⬜ | ⬜ |
| 제목 감지 | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | — |
| 스타일 상속 | ⬜ | ⬜ | ⬜ | — | — | ✅ | — | — |
| 수식 | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| 공유 수식 | — | — | — | — | ✅ | — | — | ✅ |
| 이미지 참조 | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| 이미지 대체 텍스트 | ⬜ | ⬜ | ⬜ | ⬜ | — | ✅ | ✅ | — |
| 이미지 OCR | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| 머리글/바닥글 | ✅ | ✅ | ⬜ | — | — | ✅ | — | — |
| 각주/미주 | ✅ | ✅ | ⬜ | — | — | ✅ | — | — |
| 주석/코멘트 | ⬜ | ⬜ | ⬜ | — | — | ✅ | — | ✅ |
| 변경 추적 | ⬜ | ⬜ | ⬜ | — | — | ✅ | — | — |
| 컨트롤/스마트 태그 텍스트 | ⬜ | ⬜ | ⬜ | — | — | ✅ | — | — |
| 텍스트박스 텍스트 | ⬜ | ⬜ | ⬜ | ⬜ | — | ✅ | ✅ | — |
| 필드 결과 텍스트 | ⬜ | ⬜ | ✅ | ✅ | — | ✅ | — | — |
| 여러 슬라이드 | — | — | — | ✅ | — | — | ✅ | — |
| 레이아웃 상속 텍스트 | — | — | — | ⬜ | — | — | ✅ | — |
| 발표자 노트 | — | — | — | ⬜ | — | — | ✅ | — |
| 읽기 순서 | ✅ | ✅ | ⬜ | ⬜ | — | ⬜ | ✅ | — |
| 그룹 도형 | — | — | — | ⬜ | — | — | ✅ | — |
| 차트 제목/데이터 | — | — | ⬜ | ⬜ | ⬜ | ⬜ | ✅ | ⬜ |
| 여러 시트 | — | — | — | — | ✅ | — | — | ✅ |
| sharedStrings | — | — | — | — | ✅ | — | — | ✅ |
| Boolean/error/formula cached value | — | — | — | — | ✅ | — | — | ✅ |
| rich text 문자열 | — | — | — | — | ⬜ | — | — | ✅ |
| 날짜/숫자 서식 | — | — | ⬜ | ⬜ | ✅ | ⬜ | ⬜ | ✅ |
| 빈 행/열 좌표 보존 | — | — | ⬜ | — | ✅ | — | — | ✅ |
| 하이퍼링크 | ⬜ | ⬜ | ⬜ | ⬜ | ✅ | ✅ | ✅ | ✅ |
| 하이퍼링크 URL | ⬜ | ⬜ | ⬜ | ⬜ | ✅ | ✅ | ✅ | ✅ |
| 내부 하이퍼링크 | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ✅ | ✅ | ✅ |
| 내부 북마크 | ⬜ | ⬜ | ⬜ | — | — | ✅ | — | — |
| 암호화 문서 | ⬜ | — | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

✅ 지원 &nbsp; ⬜ 미지원 &nbsp; — 해당 없음

> Legacy Office(.doc/.ppt/.xls)는 현재 OLE/BIFF native 기반의 기초 구조 복원 단계입니다. `.doc`는 WordDocument FIB 텍스트 범위, 0Table/1Table CLX piece table, compressed piece flag, UTF-16/cp1252 compressed 본문 선택, legacy layout 문자와 soft line/page break 정규화, quoted/unquoted/internal HYPERLINK field 표시 텍스트/URL 및 일반 field 결과 텍스트, single-byte smart quote/dash 문장부호, legacy bullet/numbered/parenthesized numbered/alpha/roman outline list marker, legacy checkbox/checklist marker, underline-style heading, 한국어 제목/소제목 label, section break, 명시적 heading/list/table/key-value form 및 전각 콜론 key-value 신호, Word cell marker 및 tab/pipe-delimited/Markdown-style pipe/고정폭 공백·전각 공백 정렬 표 구조를 복원하고, `.ppt`는 slide/notes/comments container, 중첩 notes/comments container의 직전 슬라이드 연결, quoted/unquoted/internal HYPERLINK field 표시 텍스트/URL 및 일반 field 결과 텍스트, cp1252 byte text 문장부호, legacy layout 문자와 soft line/page break 정규화, legacy bullet/numbered/parenthesized numbered/alpha/roman outline list marker, legacy checkbox/checklist marker, underline-style heading, 한국어 제목/소제목 label, tab/pipe-delimited/Markdown-style pipe/고정폭 공백·전각 공백 정렬 표와 key-value form/전각 콜론 key-value 구조, 반복 텍스트 라인, TextHeaderAtom title/center-title/body 신호를 반영하며, `.xls`는 BIFF sheet/table/merged-cell/cell 타입, HEADER/FOOTER 시트 문단과 제어 코드 정규화, cp1252 compressed 문자열 문장부호, BIFF2/3/4 LABEL 셀, BIFF INTEGER 정수 셀, legacy NUMBER 숫자 셀, legacy BOOLERR boolean/error 셀, legacy BLANK 빈 좌표, rich-text/SST CONTINUE shared string, RSTRING rich-text label 셀, 문자열 중간에서 끊긴 SST CONTINUE, HLINK URL, NOTE 코멘트 작성자, DIMENSION used-range, ROW/COLINFO 행·열 범위, BLANK/MULBLANK 빈 좌표, RK/MULRK 압축 숫자, FORMAT/XF 기반 날짜·퍼센트·통화 서식, 이름 정의 대상 문단, RPN 수식·범위·절대/혼합/다른 시트 참조/이름 정의 참조 flag·operand class variant·문자열/boolean/error literal·단항/퍼센트/괄호·지수·IF/AND/OR/NOT/COUNT/ROUND/TRUE/FALSE/가변/다중 인자 고정 함수·비교·문자열 결합 토큰, FORMULA cached boolean/표준 error/blank 결과, SHRFMLA 공유 수식 템플릿/상대 참조 보정과 STRING/legacy STRING/legacy byte STRING 후속 레코드 기반 문자열 수식 결과를 복원합니다.

## Architecture

```
dochan/
├── reader.py          # 통합 진입점 (Dochan 클래스)
├── cli.py             # CLI 도구
├── hwp/               # HWP 5.0 바이너리 파서
│   ├── header.py      #   FileHeader (256바이트)
│   ├── doc_info.py    #   DocInfo (서식/스타일)
│   ├── section.py     #   섹션 (레코드 트리 → 모델)
│   └── records/       #   개별 레코드 파서
├── hwpx/              # HWPX (OWPML) XML 파서
│   └── parser.py
├── ooxml/             # Office Open XML native 파서
│   ├── package.py     #   안전한 ZIP/XML 패키지 유틸
│   ├── docx.py        #   DOCX 문단/서식/표 파서
│   ├── pptx.py        #   PPTX 슬라이드/텍스트/표 파서
│   └── xlsx.py        #   XLSX workbook/sheet/cell 파서
├── office_binary/     # Legacy Office OLE native 파서
│   ├── structure.py   #   legacy 텍스트 heading/table/list 구조화
│   ├── doc.py         #   DOC WordDocument 텍스트/기초 구조 파서
│   ├── ppt.py         #   PPT slide/text/기초 구조 파서
│   └── xls.py         #   XLS BIFF workbook/sheet/cell 파서
├── model/             # Document 모델
│   ├── document.py    #   Document, Section, Paragraph
│   ├── table.py       #   Table, Cell
│   └── equation.py    #   Equation (LaTeX 변환)
├── output/            # 출력 포맷
│   ├── markdown.py    #   Markdown (AI/LLM 최적)
│   ├── json_out.py    #   구조화 JSON
│   └── plain_text.py  #   플레인 텍스트
└── utils/             # 유틸리티
    ├── ocr.py         #   Tesseract OCR
    └── safe_decompress.py  # Zip Bomb 방어
```

## Security

dochan은 신뢰할 수 없는 문서도 안전하게 처리합니다:

- **Zip Bomb 방어**: zlib/ZIP 해제 크기 제한 (200MB)
- **XXE 차단**: XML 외부 엔티티 해석 비활성화
- **Path Traversal 방지**: 배치 처리 시 경로 탈출 차단
- **메모리 제한**: 표 크기 1M셀, 재귀 깊이 100 제한
- **입력 검증**: FileHeader/스트림명/OOXML 패키지명/바이너리 바운드 체크

## Contributing

기여를 환영합니다! Issues, Pull Requests 모두 열려 있습니다.

```bash
# 개발 환경 설정
git clone https://github.com/illuwa/dochan.git
cd dochan
pip install -e ".[dev]"
python -m pytest dochan/tests/
```

## Acknowledgments

> [kordoc](https://github.com/chrisryugj/kordoc)를 보고 자극받아 만들었습니다.

dochan은 다음 프로젝트와 자료를 기반으로 개발되었습니다:

**스펙 참조**
- [한글과컴퓨터](https://www.hancom.com/) — HWP 문서 파일 형식 5.0 공개 스펙 (revision 1.3, 2018)
- [OWPML (KS X 6101:2011)](https://www.kssn.net/) — HWPX 국가 표준

**오픈소스**
- [olefile](https://github.com/decalage2/olefile) — OLE2 파일 파싱 (Philippe Lagadec, BSD)
- [lxml](https://lxml.de/) — XML 파싱 (BSD)
- [pdfplumber](https://github.com/jsvine/pdfplumber) — 품질 검증용 PDF 추출 (MIT)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — 이미지 텍스트 추출 (Apache 2.0)

**선행 연구**
- [hwplib](https://github.com/neolord0/hwplib) (Java) — HWP 레코드 구조 참조
- [hwp.js](https://github.com/niceeee/hwp.js) — 레코드 트리 구축 참조
- [pyhwp](https://github.com/mete0r/pyhwp) — Python HWP 파서 선구자

## License

[MIT License](LICENSE)

본 소프트웨어는 한글과컴퓨터의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발되었습니다. 자세한 내용은 [NOTICE](NOTICE) 파일을 참조하세요.
