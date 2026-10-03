<p align="center">
  <h1 align="center">dochan (독한)</h1>
  <p align="center">
    <strong>독한 native 문서 파서 — AI/LLM 최적 Markdown 변환</strong>
  </p>
  <p align="center">
    The toughest Korean document parser. HWP/HWPX/Office/PDF → Markdown, JSON, Plain Text.
  </p>
  <p align="center">
    <a href="https://pypi.org/project/dochan/"><img src="https://img.shields.io/pypi/v/dochan?color=blue&cacheSeconds=60" alt="PyPI"></a>
    <a href="https://pypi.org/project/dochan/"><img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
    <a href="https://github.com/illuwa/dochan/stargazers"><img src="https://img.shields.io/github/stars/illuwa/dochan?style=social" alt="GitHub Stars"></a>
  </p>
    <p align="center"><strong>Current stable version: 1.14.0</strong></p>
</p>

---

## What is dochan?

**dochan**(독한)은 한글(HWP/HWPX)과 Office 문서를 native로 파싱하여 AI/LLM이 바로 사용할 수 있는 Markdown으로 변환하는 Python 파서입니다.

- `doc` (문서) + `한` (韓, 한국) = **dochan** — "독한 파서"라는 더블 미닝
- HWP 5.0 바이너리 + HWPX(OWPML) XML + Office OOXML/legacy binary + PDF(텍스트·표·읽기 순서) 네이티브 지원
- 동일 문서 HWP/HWPX/PDF 80쌍과 공개 HWP/HWPX 7,188개 회귀 코퍼스로 검증(2026-08 기준), 공개가능한 문서로 계속 학습시켜 개선할 예정
- 공개 OOXML fixture 50개의 고정 SHA-256 corpus와 형식별 회귀 테스트로 지속 검증

```python
from dochan import Dochan

doc = Dochan("공문서.hwp")
print(doc.to_markdown())
```

## Features

| 기능 | 설명 |
|------|------|
| **HWP + HWPX + Office + PDF** | HWP/HWPX, Office OOXML(.docx/.pptx/.xlsx), legacy Office(.doc/.ppt/.xls), PDF(.pdf)를 native parser로 파싱 |
| **PDF 텍스트·표 추출** | CTM(그래픽 상태) 기반 좌표 레이아웃으로 문단·읽기 순서를 복원하고, 벡터 괘선으로 표(병합 셀·셀 안 중첩 표·페이지에 걸친 표 포함)를 재구성. 줄바꿈으로 갈라진 한글 어절은 문자 통계 모델로 공백을 복원. 괘선 없는 표는 `pdf_text_tables=True` 옵션(실험적)으로 텍스트 정렬 기반 추정. 반복 머리글/바닥글, 주석(코멘트), 내부·외부 링크, 세로쓰기, LZW·TIFF predictor, 표준 암호화(빈 암호·사용자 암호) 지원. 스캔 PDF 는 이미지 추출+OCR 로 처리 |
| **legacy Office 구조 해석** | `.doc`·`.ppt`·`.xls` 를 Microsoft 공개 명세대로 해석해 서식·병합 셀·중첩 표·각주·주석·변경 추적·그림·하이퍼링크·노트·차트·수식(Equation 3.0)을 복원 |
| **암호화 문서** | OOXML(Standard/Agile), DOC·XLS(XOR·RC4·CryptoAPI), PPT(RC4 CryptoAPI), PDF(사용자 암호), HWP 배포용 문서. 암호는 `password=`, CLI `--password-stdin` 또는 `DOCHAN_PASSWORD` 로만 받는다 |
| **차트** | DOCX·PPTX·XLSX·XLS·PPT·HWPX 차트의 제목·종류·축 제목·데이터를 표로 |
| **Markdown 출력** | 제목, 표, 서식(bold/italic), 수식까지 AI가 바로 쓸 수 있는 Markdown |
| **표 파싱** | 셀 병합, 중첩 표, 좌표 배치 지원 |
| **서식 보존** | CharShape 기반 bold/italic/글자크기 → TextRun 연결 |
| **제목 자동 감지** | Style 이름 + 글자 크기 기반 heading 레벨 판별 |
| **수식 LaTeX** | HWP 수식 스크립트, DOCX·PPTX OMML, DOC·PPT MathType(MTEF) → LaTeX |
| **JSON / Plain Text** | Markdown 외 구조화 JSON, 플레인 텍스트 출력 |
| **OCR (선택)** | Tesseract 연동, 이미지 속 텍스트 추출 |
| **CLI** | `dochan convert 문서.hwp` 한 줄로 변환 |
| **배치 처리** | 디렉토리 단위 병렬 변환 |
| **보안** | Zip Bomb, XXE, Path Traversal, 메모리 폭발 방어 |

## Installation

```bash
pip install dochan
```

OCR 기능이 필요한 경우(Python 3.10 이상):
```bash
pip install "dochan[ocr]"
brew install tesseract tesseract-lang  # macOS
```

## Quick Start

### Python API

```python
from dochan import Dochan

# HWP, HWPX, DOC, PPT, XLS, DOCX, PPTX, XLSX, PDF
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

# 문서 속 이미지 바이너리를 파일로 저장 (<파일이름>-image-NNN.<확장자>)
doc.save_images("images/")

# 암호화 문서 (키워드 전용; 암호 값은 오류·로그에 남지 않는다)
doc = Dochan("암호문서.docx", password="비밀번호")

# HWP/HWPX 변경 추적: preserve(기본, 모든 텍스트) · final(삭제 제외) · original(삽입 제외)
doc = Dochan("검토본.hwpx", revision_mode="final")
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

# PDF 텍스트 추출
dochan convert 문서.pdf

# 이미지 바이너리도 함께 저장
dochan convert 문서.docx -o 문서.md --images-dir images/

# 암호화 문서: 표준 입력 첫 줄 또는 DOCHAN_PASSWORD (명령줄 인자로는 받지 않는다)
echo "$PASSWORD" | dochan convert 암호문서.xlsx --password-stdin

# PDF 괘선 없는 표 복원(실험적)
dochan convert 문서.pdf --pdf-text-tables

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

| 요소 | HWP | HWPX | DOC | PPT | XLS | DOCX | PPTX | XLSX | PDF |
|------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 텍스트 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 표 (단순) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 표 (셀 병합) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 표 (중첩 텍스트) | ✅ | ✅ | ✅ | — | — | ✅ | — | — | ⬜ |
| 서식 (bold/italic) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 제목 감지 | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | ✅ |
| 스타일 상속 | — | — | ✅ | ✅ | — | ✅ | ✅ | — | — |
| 수식 | ✅ | ✅ | ✅¹ | ✅¹ | ✅² | ✅ | ✅ | ✅ | ⬜ |
| 공유 수식 | — | — | — | — | ✅ | — | — | ✅ | — |
| 이미지 참조 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 이미지 대체 텍스트 | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | — |
| 표/그림 캡션 | ✅ | ✅ | ✅³ | — | — | ✅³ | — | — | — |
| 이미지 OCR | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 머리글/바닥글 | ✅ | ✅ | ✅ | — | — | ✅ | — | — | ✅ |
| 각주/미주 | ✅ | ✅ | ✅ | — | — | ✅ | — | — | ⬜ |
| 주석/코멘트 | ✅ | ✅ | ✅ | — | — | ✅ | — | ✅ | ✅ |
| 변경 추적 | ⬜ | ⬜ | ✅ | — | — | ✅ | — | — | — |
| 컨트롤/스마트 태그 텍스트 | ✅ | ✅ | ✅ | — | — | ✅ | — | — | — |
| 텍스트박스/도형 텍스트 | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | — |
| 필드 결과 텍스트 | ✅ | ✅ | ✅ | ✅ | — | ✅ | — | — | — |
| 여러 슬라이드 | — | — | — | ✅ | — | — | ✅ | — | — |
| 레이아웃 상속 텍스트 | — | — | — | ✅ | — | — | ✅ | — | — |
| 발표자 노트 | — | — | — | ✅ | — | — | ✅ | — | — |
| 읽기 순서 | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | ✅ |
| 그룹 도형 | — | — | — | ✅ | — | — | ✅ | — | — |
| 페이지 번호 provenance | — | — | — | — | — | — | — | — | ✅ |
| 현대 PDF(1.5+) xref/객체 스트림 | — | — | — | — | — | — | — | — | ✅ |
| 표준 암호화(RC4/AES, 빈·사용자 암호) | — | — | — | — | — | — | — | — | ✅ |
| 차트 제목/데이터 | ✅⁷ | ✅ | ⬜ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| 여러 시트 | — | — | — | — | ✅ | — | — | ✅ | — |
| sharedStrings | — | — | — | — | ✅ | — | — | ✅ | — |
| Boolean/error/formula cached value | — | — | — | — | ✅ | — | — | ✅ | — |
| rich text 문자열 | — | — | — | — | ✅ | — | — | ✅ | — |
| 날짜/숫자 서식 | — | — | — | — | ✅⁶ | — | — | ✅⁶ | — |
| 빈 행/열 좌표 보존 | — | — | ✅ | — | ✅ | — | — | ✅ | — |
| 하이퍼링크 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ |
| 하이퍼링크 URL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 내부 하이퍼링크 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 내부 북마크 | ✅ | ✅ | ✅ | — | — | ✅ | — | — | ✅ |
| 암호화 문서 | ✅⁴ | — | ✅⁵ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

✅ 지원 &nbsp; ⬜ 미지원 &nbsp; — 해당 없음 (형식에 그 구조가 없음)

✅ 는 단위 테스트와 실물 문서 검증을 모두 통과한 칸에만 붙인다. 칸마다 검증 표본·수치·남은 한계는
[`docs/SUPPORT_NOTES.md`](docs/SUPPORT_NOTES.md) 와 `docs/benchmarks/` 에 있다. 주요 범위 제한:

1. DOC·PPT 수식은 내장 Equation 3.0(MathType MTEF v2/v3/v5) 개체를 LaTeX 로 바꾼다. 공개 실물 변환율은 DOC 42/54, PPT 13/18 이고 변환하지 못한 식은 미리보기 그림으로 남는다.
2. XLS 수식은 BIFF8 과, BIFF5 의 셀 참조·공유식을 해석한다. 같은 문서의 XLSX 와 비교한 1,070 수식 중 1,059개(98.97%)가 일치하며, 데이터 표(`TABLE(행입력,열입력)`, 공개 90셀)와 DDE 링크(`서비스|토픽!항목`, 공개 1,399셀)도 수식으로 낸다. OLE 링크 항목과 해석하지 못한 BIFF5 이름·3D 참조·배열은 수식 대신 캐시 값만 낸다.
3. 캡션은 Caption 스타일·SEQ 필드 문단이 최상위 흐름에서 표·그림 바로 앞/뒤에 있을 때만 결합한다. DOC 의 위쪽 캡션은 합성 문서로만 검증했다.
4. HWP 는 배포용 문서를 복호화한다. 열기 암호로 보호된 HWP 는 명확한 오류로 거부한다.
5. DOC 의 XOR 난독화는 공개 실물 표본이 없어 합성 문서로만 검증했다(RC4·RC4 CryptoAPI 는 실물 검증).
6. XLS·XLSX 숫자 서식은 Excel 이 저장한 표시값으로 검증했다. 공개 분수 표 3,540셀이 공백 정규화 후 모두 같고(고정 분모 2,124/2,124, 가변 분모 1,416/1,416 — Excel 처럼 부동소수 연분수의 수렴분수만 쓴다. 분모 4자리 이상 서식은 짧은 분수로 나눠떨어지는 값만 검증했다), 경계 사례 위주의 `TEXT()` 캐시 832행 중 755행이 정확히 같다(과학 표기 248/248행, 분수 리터럴 190/190행, General·텍스트 구역 34행, 날짜·경과 시간·백분율 18행 추가 일치). General·서식 없는 숫자는 Excel 정밀도인 15자리 유효숫자로 반올림해 표시한다(`0.30000000000000004` → `0.3`). dochan 계약으로 지수 자리가 -10 이하이거나 15 이상인 수는 `1.23456789012346E+19` 처럼 지수로 낸다(Excel 셀의 약 11글자 폭 규칙은 따르지 않는다). 표시 문자열만 내며 원래의 17자리 정밀도와 XLSX 원문 표기는 출력에 남지 않는다. 문자열·논리값에는 텍스트 구역의 `@`와 리터럴을 적용한다. 회계 서식의 0 구역 `-`, 음수 구역의 문자와 괄호, 쉼표 배율(`#,##0,`), 필수 0 자리는 Excel 과 같게 낸다. 과학 표기는 공학 가수 자리, 지수의 `0`·`#`·`?` 자리, `E-`의 양수 부호 생략, 가수와 지수 사이의 리터럴을 처리한다. 색만 다른 음수 구역(`#,##0;[Red]#,##0`)은 Markdown 에 색이 없으므로 Excel 과 달리 `-` 를 붙이고, 부호 문자나 괄호가 있거나 음수 구역에만 리터럴이 있는 구역(`△`, `(…)`, `" €"`)은 그 표기를 그대로 낸다. 연·월·일이 있는 날짜와 시각은 ISO·24시간으로 정규화하고, 한 자리 숫자 토큰의 부분 날짜(`d`, `m/d`, `m"月"d"日"`, `d "days" h`)는 리터럴을 포함한 Excel 토큰 표시로 낸다(두 자리 토큰 `dd`·`mm/dd` 와 연 토큰이 있는 서식은 이전처럼 ISO). 1900 날짜 체계의 일련번호 0·60은 일 토큰에서 각각 0·29일로 표시한다. `?` 자리 공백과 `*` 채움은 내지 않는다(과학 표기와, 색·통화·리터럴이 붙어 자리별로 그리는 분수 서식은 Excel `TEXT()` 와 같게 `?` 자리를 공백으로 낸다 — 기본 `# ?/?` 꼴은 공백을 생략한다). `AM/PM`·`A/P`는 24시간 시각으로 바꾸고, 한 글자 연·월·일 토큰과 백분율의 천 단위 쉼표를 처리한다. 요일·월 이름 토큰은 기존 ISO 표시를 유지하며 이름 자체를 표시하지 않는다. 네 자리 이상 초 소수와 일부 미지원 조합은 원시 값으로 남는다. 분수 서식의 정수부·자리 사이 리터럴·정수 자리 뒤 `_` 패딩의 가분수는 공개 Excel 캐시와 대조해 처리한다. 캐시로 검증되지 않은 정수부 없는 가분수는 기존 대분수 표시를 유지하고, 분수 뒤 `%`는 백분율 배율을 적용하지 않은 기존 표시로 둔다. `#/#`·`##/##`의 Excel 표시값은 미검증이다.
7. HWP 차트는 GSO OLE 중 `OOXMLChartContents` 캐시를 읽는다. 공개 차트 38/38개가 XML 원문의 계열 값 순서·제목·종류와 일치했고, HWP/HWPX 짝 28/28문서에서 표와 앞뒤 문단 위치가 일치했다. 내장 `Excel.Chart.8` 차트 8참조(5문서)는 독립 BIFF 판독의 시트 셀 값과 8/8 일치한다(분산형은 X·Y 점 단위 대조, 차트 내부 캐시가 시트와 다른 1개는 시트 값을 따른다). 공개 차트 문서 46개 중 OOXML 35개·Excel 5개를 지원하며, 구형 한컴 `Contents` 차트 7문서 33참조는 한컴 공개 차트 명세(개정 1.2)가 있으나 아직 구현하지 않았다. 실물 OLE 33개에는 `OlePres000`이 없고 지정된 HWPX 짝에도 차트 XML이 없어, 요청된 독립 값 검증은 진행할 수 없다.

> Legacy Office(.doc/.ppt/.xls)도 외부 변환 엔진 없이 native 로 읽습니다. `.doc` 와 `.ppt` 는 Microsoft 공개 명세 [MS-DOC]·[MS-PPT] 에 따라 문서 구조(글자 서식과 스타일, 셀 병합·중첩 표, 각주·주석·머리글/바닥글, 텍스트박스, 슬라이드·노트·마스터 상속, 도형 트리와 읽기 순서 등)를 해석해 DOCX·PPTX 와 같은 형태로 내고, 구조를 해석할 수 없는 문서는 이전의 텍스트 추출 경로로 처리합니다. `.xls` 는 BIFF8 해석을 넓혀 [MS-XLS] 함수 표에 기반한 수식 문자열, rich text, 내부 링크, 그림, 차트를 읽습니다. 세 형식 모두 공용 OfficeArt 파서로 그림과 대체 텍스트를 꺼내고, `.doc`·`.ppt` 에 내장된 OLE 차트(Excel·MS Graph)는 OOXML 차트와 같은 표로, Equation 3.0 수식은 LaTeX 로 바꿉니다. 암호화된 문서는 `.doc`·`.xls` 의 XOR·RC4·RC4 CryptoAPI 와 `.ppt` 의 RC4 CryptoAPI 를 `password=` 로 열 수 있으며, 항목별 지원 범위와 검증 한계는 위 표와 각주에 적었습니다.

## Architecture

```
dochan/
├── reader.py          # 통합 진입점 (Dochan 클래스; password=·revision_mode=·include_assets=)
├── cli.py             # CLI 도구 (convert·batch·info, --images-dir, --password-stdin)
├── batch.py           # 디렉토리 일괄 변환
├── conversion.py      # AssetRef 등 변환 계약
├── cfb.py             # [MS-CFB] OLE 복합 파일 리더 (HWP·DOC·PPT·XLS·내장 OLE 공용, 외부 의존성 없음)
├── crypto/            # 암호화 Office 문서 ([MS-OFFCRYPTO], 외부 의존성 없음)
│   ├── ooxml.py       #   OOXML Standard/Agile (EncryptionInfo + EncryptedPackage)
│   ├── legacy.py      #   DOC·XLS XOR·RC4·RC4 CryptoAPI
│   └── ppt.py         #   PPT CryptSession10Container
├── hwp/               # HWP 5.0 바이너리 파서
│   ├── header.py      #   FileHeader (256바이트)
│   ├── doc_info.py    #   DocInfo (서식/스타일/변경 추적 정보)
│   ├── section.py     #   섹션 (레코드 트리 → 모델)
│   ├── distdoc.py     #   배포용 문서 ViewText 복호화 (한컴 공개 명세)
│   ├── revisions.py   #   변경 추적 범위 투영
│   ├── forms.py       #   양식 개체·누름틀 표시 텍스트
│   ├── bin_data.py    #   BinData 이미지 연결
│   └── records/       #   개별 레코드 파서
├── hwpx/              # HWPX (OWPML) XML 파서
│   ├── parser.py
│   ├── charts.py      #   내장 차트 캐시
│   └── revisions.py   #   변경 추적 투영
├── ooxml/             # Office Open XML native 파서 (Strict 정규화 포함)
│   ├── package.py     #   안전한 ZIP/XML 패키지 유틸, Strict → Transitional
│   ├── docx.py        #   DOCX 문단/서식/표/캡션/차트
│   ├── pptx.py        #   PPTX 슬라이드/텍스트/표/수식/미디어
│   ├── xlsx.py        #   XLSX workbook/sheet/cell/차트
│   ├── charts.py      #   DOCX·PPTX·XLSX 공용 차트(종류·축 제목·캐시 없는 참조·chartEx)
│   └── math.py        #   OMML → LaTeX
├── office_binary/     # Legacy Office OLE native 파서 ([MS-DOC]/[MS-PPT]/[MS-XLS])
│   ├── doc.py         #   DOC 진입점 (구조 해석 실패 시 텍스트 경로)
│   ├── doc_binary.py  #   FIB·CLX·FKP·sprm·STSH
│   ├── doc_tables.py · doc_stories.py · doc_images.py · doc_captions.py · doc_structure.py
│   ├── ppt.py         #   PPT 진입점
│   ├── ppt_structure.py · ppt_text.py · ppt_shapes.py · ppt_render.py
│   ├── xls.py         #   XLS BIFF workbook/sheet/cell
│   ├── xls_formula.py · xls_ftab.py · xls_chart.py · xls_drawing.py · xls_hyperlink.py
│   ├── officeart.py   #   [MS-ODRAW] 공용 OfficeArt(BLIP·도형·속성)
│   ├── ole_objects.py #   내장 OLE 차트(Excel·MS Graph)·수식 개체
│   ├── mtef.py        #   MathType MTEF → LaTeX
│   ├── symbol_fonts.py#   Symbol·Wingdings 문자 대응
│   └── structure.py   #   legacy 텍스트 경로의 구조화
├── pdf/               # 네이티브 PDF 파서
│   ├── objects.py     #   객체 문법 파서
│   ├── filters.py     #   Flate/LZW/ASCIIHex/ASCII85 + PNG·TIFF predictor
│   ├── structure.py   #   xref/트레일러/페이지 트리/객체 스트림
│   ├── crypto.py      #   표준 보안 핸들러(RC4/AES, 사용자 암호 R2–R6)
│   ├── cmap.py · widths.py · core14.py  # ToUnicode·글리프 폭·표준 14 글꼴(Adobe AFM 폭)
│   ├── content.py     #   콘텐츠 스트림 해석(CTM·텍스트 좌표·세로쓰기)
│   ├── paths.py · tables.py · text_tables.py · pagination.py  # 괘선·표·페이지 걸침
│   ├── layout.py · spacing.py  # 줄 → 문단, 한글 줄바꿈 공백 모델
│   ├── running.py     #   반복 머리글/바닥글
│   ├── annotations.py #   주석(코멘트)·링크·내부 목적지
│   ├── notes.py       #   각주 휴리스틱
│   ├── images.py      #   이미지 XObject 추출
│   └── reader.py      #   PDFReader (페이지 → Document)
├── model/             # Document 모델 (Document·Section·Paragraph·Table·Image·Equation·HeaderFooter·Footnote·Comment)
├── output/            # 출력 포맷 (markdown.py·json_out.py·plain_text.py)
├── quality/           # 품질 검사·교차 검증
└── utils/             # 유틸리티
    ├── aes.py         #   FIPS-197 AES (표 기반, 외부 의존성 없음)
    ├── bounded_io.py  #   신뢰할 수 없는 OLE 스트림의 상한 읽기
    ├── image_export.py#   이미지 바이너리 저장
    ├── ocr.py         #   Tesseract OCR (선택, Python 3.10+)
    └── safe_decompress.py  # Zip Bomb 방어
```

외부 출처와 의존성은 [`docs/THIRD_PARTY.md`](docs/THIRD_PARTY.md) 에 정리돼 있다.

## Security

dochan은 신뢰할 수 없는 문서도 안전하게 처리합니다:

- **Zip Bomb 방어**: raw zlib 출력 200MB(HWP 본문은 문서당 누적 200MB, 손상 스트림은 실제 해제한 양만 차감), OOXML/HWPX XML part 32MB, 일반 part 100MB, archive 합계 512MB 상한
- **XXE·엔티티 증폭 차단**: 모든 XML 을 표준 라이브러리 위 자체 안전 파서로 읽는다. DOCTYPE·엔티티 선언은 파싱 전에 거부하고(Python 3.9 의
  expat 2.2.8 처럼 증폭 방어가 없는 판에서도 같은 동작), 깊이·요소 수·네임스페이스 선언에 상한을 둔다. 손상된 시트·VML 파트는 그 파트에만 오류를 남긴다
- **Path Traversal 방지**: 배치 처리 시 경로 탈출 차단
- **메모리 제한**: HWP 레코드 섹션당 100만·문서당 130만·DocInfo 20만 개(넘으면 그때까지 읽은 본문을 보존하고 오류를 남김), HWP·HWPX 문서당 서식 런 524,288·150,000개와 HWPX 문단·각주 150,000개(넘으면 이후 본문을 서식·하이퍼링크 없이 보존하고 WARN 1회), HWP·HWPX·DOCX·XLSX·XLS·PDF 문서당 표 셀 20만 개, HWP·DOCX 일반 구조 깊이 64, HWP·DOCX 표 깊이 32, PPTX 그룹 깊이 64 상한. PDF 는 페이지 콘텐츠 합계 64MB, 괘선 2만 개, 괘선 교차 검사 200만 회, 스트림 해제 200MB 추가 상한
- **입력 검증**: FileHeader/스트림명/OOXML 패키지명/바이너리 바운드 체크

이 상한들은 입력량과 구조 수를 묶을 뿐 메모리 사용량의 상한은 아닙니다(예: 상한 근처의 HWP 무서식 문단 64만 개는 약 2.5GB 를 쓴다). 신뢰할 수 없는 문서는 프로세스 메모리 제한(컨테이너·ulimit 등) 아래에서 처리하기를 권장합니다.

## Contributing

기여를 환영합니다! Issues, Pull Requests 모두 열려 있습니다.

```bash
# 개발 환경 설정
git clone https://github.com/illuwa/dochan.git
cd dochan
python -m pip install "uv==0.12.3"
uv sync --locked --extra dev
uv run --locked --extra dev ruff check dochan scripts tests
uv run --locked --extra dev python -m pytest tests/
```

## Acknowledgments

> [kordoc](https://github.com/chrisryugj/kordoc)를 보고 자극받아 만들었습니다.

dochan은 다음 프로젝트와 자료를 기반으로 개발되었습니다:

**스펙 참조**
- [한글과컴퓨터](https://www.hancom.com/) — HWP 문서 파일 형식 5.0 공개 스펙 (revision 1.3, 2018)
- [OWPML (KS X 6101:2011)](https://www.kssn.net/) — HWPX 국가 표준

**오픈소스**
- [pdfplumber](https://github.com/jsvine/pdfplumber) — 품질 검증용 PDF 추출 (MIT)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — 이미지 텍스트 추출 (Apache 2.0)

XML 은 1.14.0 부터 lxml 대신 표준 라이브러리 `xml.parsers.expat`·`ElementTree` 위의 자체 안전 파서(`dochan/utils/safe_xml.py`)로 읽어 런타임 의존성이 없다(1.13.0 까지는 lxml, BSD).

**선행 연구** (공개 HWP 파서 프로젝트. dochan 의 구현 근거는 한컴 공개 명세와 실물 바이트 관찰이며, 이 프로젝트들의 코드는 쓰지 않는다. 과거 참고 이력은 [`docs/THIRD_PARTY.md`](docs/THIRD_PARTY.md) 에 기록)
- [hwplib](https://github.com/neolord0/hwplib) (Java)
- [hwp.js](https://github.com/niceeee/hwp.js)
- [pyhwp](https://github.com/mete0r/pyhwp) — Python HWP 파서 선구자

OLE2(CFB) 컨테이너는 1.8.0 부터 [MS-CFB] 명세로 자체 구현한 `dochan/cfb.py` 로 읽는다(이전 버전은 olefile 을 썼다).

## License

[MIT License](LICENSE)

본 소프트웨어는 한글과컴퓨터의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발되었습니다. 자세한 내용은 [NOTICE](NOTICE) 파일을 참조하세요.
