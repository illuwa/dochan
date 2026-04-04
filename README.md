<p align="center">
  <h1 align="center">dochan (독한)</h1>
  <p align="center">
    <strong>독한 HWP/HWPX 파서 — AI/LLM 최적 Markdown 변환</strong>
  </p>
  <p align="center">
    The toughest Korean document parser. HWP/HWPX → Markdown, JSON, Plain Text.
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

**dochan**(독한)은 한글(HWP/HWPX) 문서를 파싱하여 AI/LLM이 바로 사용할 수 있는 Markdown으로 변환하는 Python 파서입니다.

- `doc` (문서) + `한` (韓, 한국) = **dochan** — "독한 파서"라는 더블 미닝
- HWP 5.0 바이너리 + HWPX(OWPML) XML 이중 지원
- 155개 실문서로 검증, 평균 96.5점, 공개가능한 문서로 계속 학습시켜 개선할 예정

```python
from dochan import Dochan

doc = Dochan("공문서.hwp")
print(doc.to_markdown())
```

## Features

| 기능 | 설명 |
|------|------|
| **HWP + HWPX** | 바이너리(.hwp)와 XML(.hwpx) 모두 자동 감지 파싱 |
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

# HWP 또는 HWPX — 자동 감지
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

| 요소 | HWP (바이너리) | HWPX (XML) |
|------|:-:|:-:|
| 텍스트 | ✅ | ✅ |
| 표 (단순) | ✅ | ✅ |
| 표 (셀 병합) | ✅ | ✅ |
| 표 (중첩) | ✅ | ✅ |
| 서식 (bold/italic) | ✅ | ✅ |
| 제목 감지 | ✅ | ✅ |
| 수식 | ✅ | ✅ |
| 이미지 참조 | ✅ | ✅ |
| 이미지 OCR | ✅ | ✅ |
| 머리글/바닥글 | ✅ | ✅ |
| 각주/미주 | ✅ | ✅ |
| 암호화 문서 | ⬜ | — |

✅ 지원 &nbsp; ⬜ 미지원 &nbsp; — 해당 없음

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
- **입력 검증**: FileHeader/스트림명/바이너리 바운드 체크

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
