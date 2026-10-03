# dochan의 외부 의존성과 자료 출처

이 목록은 2026-10-03에 로컬 저장소, 설치된 패키지의 메타데이터와 라이선스,
원본 표준 자료를 확인한 결과다. dochan의 자체 코드는 MIT로 배포하지만 외부
패키지와 사실 데이터의 고지는 각각 유지한다. 이번 정리는 외부 구현 코드를
새로 열람하거나 번역하지 않았다. 과거 개발 전체의 출처를 입증하는 감사는 아니다.

## 런타임과 선택 의존성

선언 기준은 `pyproject.toml`이다. 1.14.0 부터 런타임 의존성은 없다.

| 구분 | 프로젝트와 선언 | 쓰임 | 확인한 고지와 범위 |
| --- | --- | --- | --- |
| 필수 | 없음(1.14.0 부터). 1.13.0 까지는 [lxml](https://lxml.de/) `>=4.9`(BSD-3-Clause)였다. | XML 은 표준 라이브러리 expat·ElementTree 위의 `dochan/utils/safe_xml.py` 로 읽는다. | 표준 라이브러리만 쓴다. |
| OCR 선택 | [pytesseract](https://github.com/madmaze/pytesseract), `>=0.3; python_version >= '3.10'`이다. | 사용자가 설치한 Tesseract를 호출한다. | 설치된 0.3.13의 고지는 Apache-2.0이다. Tesseract 실행파일은 dochan 소스에 포함하지 않는다. |
| OCR 선택 | [Pillow](https://github.com/python-pillow/Pillow), `>=12.3; python_version >= '3.10'`이다. | OCR 입력 이미지를 처리한다. | 검증 인터프리터의 11.3.0 메타데이터는 MIT-CMU다. 이 버전은 현재 OCR extra의 최소 버전보다 낮으므로 12.3 배포물의 전체 고지 검증을 대신하지 않는다. 이미지 코덱 고지도 배포물에 따라 별도로 확인한다. |

일반 문서 파싱은 Python 3.9 이상을 지원한다. OCR extra는 Python 3.10 이상에만
설치하도록 선언되어 있다. Python 3.9에 기존 OCR 패키지가 설치되어 있는 사실을
3.9 OCR 지원 보장으로 해석하지 않는다. 표준 라이브러리 `zlib`, `hashlib` 등을
사용하며 AES 구현은 저장소의 `dochan/utils/aes.py`를 재사용한다.

OLE 컨테이너는 [MS-CFB] 명세와 원시 바이트 관찰에 근거한 자체
`dochan/cfb.py`로 읽는다. `olefile`은 런타임 의존성에서 제거했으며,
`scripts/compare_cfb_olefile.py`가 로컬에 설치된 경우에만 호출하는 선택적 비교
정답지다. dochan 패키지에 해당 소스나 라이브러리를 동봉하지 않는다.

`dochan/quality/cross_validator.py`는 검증을 요청할 때 `pdfplumber`를 선택적으로
import하고, `dochan/quality/batch_validate.py`는 `opendataloader_pdf`를 선택적으로
호출한다. 이 어댑터 코드는 dochan 패키지 안에 있으므로 “검증 코드도 배포하지
않는다”는 설명은 정확하지 않다. 외부 엔진 자체를 복사하거나 필수 의존성으로
선언하지 않았으며 기본 파서 경로는 이 도구들을 호출하지 않는다. 이 작업에서는
해당 코드를 수정하지 않았다. 외부 엔진 연동까지 제거할지는 별도 범위로 남긴다.

## 소스에 포함한 외부 사실 데이터

| 데이터 | 원본 출처와 고지 | 생성 경로와 산출물 |
| --- | --- | --- |
| Core 14 AFM의 글리프 이름·폭·내장 인코딩이다. | Adobe의 `Core14_AFMs.zip`과 `MustRead.html` 허가문을 사용한다. 저작권 고지 보존, 허가문 원문 유지, 수정 사실 표시 조건이 있다. Apache PDFBox에도 같은 원본 데이터가 보존되어 있으나 구현 코드를 입력으로 쓰지 않는다. | `scripts/generate_pdf_core14.py`가 AFM 디렉터리를 읽어 `dochan/pdf/core14_metrics.py`를 생성한다. 14개 AFM의 줄바꿈 정규화 SHA-256은 `SOURCE_SHA256`에 기록한다. 원 ZIP 해시는 생성기 docstring에 유지한다. |
| Adobe Glyph List와 ITC Zapf Dingbats Glyph List의 Unicode 대응표다. | [Adobe agl-aglfn](https://github.com/adobe-type-tools/agl-aglfn)의 `glyphlist.txt`, `zapfdingbats.txt`, `LICENSE.md`를 직접 읽는다. Copyright 2002–2019 Adobe, BSD-3-Clause 조건과 면책문을 보존한다. | 같은 생성기가 Core 14에 필요한 항목을 추출한다. `AGL_SOURCE_SHA256`에 세 원본 파일의 바이트 해시를 기록한다. fontTools의 코드·대응표·라이선스 파일은 입력으로 사용하지 않는다. |
| Adobe CID→Unicode 사실 표다. | [Adobe mapping-resources-pdf의 pdf2unicode](https://github.com/adobe-type-tools/mapping-resources-pdf/tree/master/pdf2unicode)에서 `Adobe-CNS1-UCS2`, `Adobe-GB1-UCS2`, `Adobe-Japan1-UCS2`, `Adobe-KR-UCS2`, `Adobe-Korea1-UCS2`를 읽는다. 원본마다 다른 Adobe 저작권 연도(1990–2019·2020·2023)와 BSD-3-Clause 고지, 원본별 SHA-256은 `NOTICE`에 기록했다. | `scripts/generate_pdf_cid2unicode.py`가 유효한 CID 대응만 추출해 `dochan/pdf/cid_unicode_data.py`를 생성한다. 원본 CMap과 외부 구현 코드는 배포하지 않는다. |
| Adobe PDF 인코딩 CMap의 코드 공간과 코드→CID 사실 표다. | [Adobe cmap-resources](https://github.com/adobe-type-tools/cmap-resources)의 CNS1·GB1·Japan1·Korea1 컬렉션에 있는 61개 CMap 원본을 읽는다. BSD-3-Clause 고지, 원본별 저작권 줄과 SHA-256은 `NOTICE`에 기록했다. | `scripts/generate_pdf_predefined_cmaps.py`가 해시를 검증하고 범위를 압축해 `dochan/pdf/predefined_cmap_data.py`를 생성한다. 원본 CMap과 외부 구현 코드는 배포하지 않는다. |
| Excel 함수 식별자·이름·인자 수의 Ftab 사실 표다. | [Microsoft [MS-XLS] 2.5.198.17](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-xls/00b5dd7d-51ca-4938-b7b7-483fe0e5933b)의 표를 사용한다. 이는 일반 MIT 데이터가 아니라 Microsoft Open Specifications의 구현 목적 문서·스키마·샘플 배포 허가에 따른 자료로 기록되어 있다. 저장소 `NOTICE`의 Microsoft 고지를 유지한다. | `scripts/generate_xls_ftab.py`가 추출한 `ftab-table.json`을 읽어 `dochan/office_binary/xls_ftab.py`를 생성한다. 입력 SHA-256은 `f30365f746837d0ce65b6ebc4ffb7210d223e8fa62b5b76a373c29ca4db2813d`다. 재생성 검사에서 373개 함수와 210개 고정 인자 수가 일치했다. |

Adobe 고지 전체는 `NOTICE`와 생성 모듈 머리말에 들어 있다. AFM과 AGL 원본 파일은
배포하지 않는다. 이번 변경에서 fontTools MIT 블록만 제거했으며, Adobe 고지는
원본 `LICENSE.md`의 줄바꿈으로 다시 생성했다. 폭 4,172개·Unicode 글리프 653개·인코딩
5개의 JSON 및 압축 데이터는 변경 전과 바이트 단위로 동일하다.

Microsoft 원문 공지 전체는 로컬 Ftab HTML에 포함되어 있지 않아 이번 오프라인
작업에서 재확인하지 못했다. 위 분류는 기존 `NOTICE`와 생성기의 출처 기록을
유지한 것이며 모든 특허·상표 사용 권한을 확인했다는 뜻은 아니다.

## 배포용 HWP 재구현의 근거와 한계

`dochan/hwp/distdoc.py`의 기존 함수 본문은 열람하지 않았다. AST로 모듈 docstring과
함수 시그니처만 확인한 뒤 파일을 새로 작성했다. 기존 테스트·호출부·실물 프로브는
출력 계약과 회귀 검증에 사용했다. 다른 프로젝트의 구현은 열람하지 않았다.

dochan으로 한컴의 「한글문서파일형식 배포용 문서 revision 1.2」와 「한글문서파일형식
5.0 revision 1.3」을 직접 텍스트 추출했다. 전자는 1절과 2.1~2.4절에서 256바이트
레코드, seed, 반복 난수 배열, XOR, 키 위치, AES-128-ECB를 규정한다. 후자는
3.2.1절의 압축 플래그, 4.1절의 레코드 헤더, 4.2.13절의 배포용 레코드를 제공한다.

2.2절은 MS Visual C의 `srand`와 `rand`를 지정하지만 `214013`, `2531011`, 32비트
상태 및 상위 비트 반환 규칙의 수치 정의를 싣지 않았다. 이 구현은 해당 난수열에
대한 알려진 호환 규칙을 직접 수식으로 작성했다. 같은 매개변수(법 2^32, 곱수 214013,
증분 2531011, 상태의 16~30비트 반환)는 선형 합동 생성기의 널리 쓰이는 매개변수 표
(예: 위키백과 “Linear congruential generator”)에 Microsoft Visual C/C++ 항목으로 실려 있다.
`srand(1)` 직후 처음 다섯 값 41, 18467, 6334, 26500, 19169를 테스트로 고정했다.
한컴 명세의 일차 문서가 아니므로 “모든 상수가 한컴 명세에 있다”고 주장하지 않는다.
공개 65섹션에서 복호화 후 CRC32와 원문 길이가 모두 일치한 것은 호환성 근거다.

명세의 횟수 식 `(rand() & 0x0F + 1)`은 C 연산자 우선순위대로 읽으면 `rand() & 0x10`이
된다. 이 구현은 문장의 뜻(1~16회)에 맞는 `(rand() & 0x0F) + 1`로 해석했고, 공개 실물은
이 해석에서만 복호화된다. 2.3절대로 offset은 XOR 전에 seed로 구하고 256바이트 전체를
XOR한다(결과의 앞 4바이트는 쓰지 않는다). 테스트 픽스처(`tests/conftest.py`)의 난수
배열 생성기는 같은 절을 다른 표현으로 따로 작성한 정답지이며, 구현과 결과를 대조한다.

명세에는 압축 뒤 CRC32·ISIZE의 두 16바이트 정렬 블록이나 연속 8바이트 배치가
명시되어 있지 않다. 전자는 공개 64섹션, 후자는 공개 1섹션에서 직접 검증했다.
길이 없는 임의 trailer를 허용하지 않고 실제 배치와 영 패딩을 검사한다. trailer가
없는 AES 정렬 데이터는 기존 합성 테스트 계약을 유지한다. 이 한계를 포함한 검증 결과는
[`2026-10-02-license-clean-real-docs.md`](benchmarks/2026-10-02-license-clean-real-docs.md)에 있다.

따라서 이번 결과는 함수 본문을 읽지 않고 수행한 재구현과 동작 검증으로 한정한다.
과거 참조 이력을 지우거나, 저장소 전체의 법적 클린룸 절차가 입증되었다고 선언하지 않는다.
과거 이력: 커밋 `8b5b0cd`까지의 `distdoc.py`와 테스트 설명은 pyhwp(AGPL-3.0)·hwplib
구현을 참고했다고 기록되어 있었다. 이 구현은 `ec42aeb`(1.7.0 포함)에서 위 재작성으로
대체됐고, 테스트 픽스처의 난수 배열 생성기와 설명은 그 다음 변경에서 명세 기준으로 다시 썼다.

## 검증 자료와 외부 정답지

| 자료·도구 | 사용 범위 | 배포 경계 |
| --- | --- | --- |
| Apache POI와 Apache Tika의 공개 문서 코퍼스다. | 문서 내용·개수·암호·해시 등 테스트 기대값과 legacy/OOXML 짝을 정답 근거로 사용한다. 프로젝트의 Apache-2.0 표시는 개별 문서의 모든 권리를 자동 보증하지 않는다. | 코퍼스는 외부 디렉터리에서 읽으며 dochan 패키지나 tests에 복사하지 않는다. 구현 코드는 생성 입력으로 쓰지 않는다. |
| LibreOffice의 공개 문서 코퍼스다. | 호환성 및 손상 입력 사례로 사용한다. 로컬 원본에는 MPL·LGPL·GPL 고지 파일이 함께 있으므로 모든 표본에 단일 라이선스를 임의 부여하지 않는다. | 해당 코드와 코퍼스를 dochan에 넣지 않는다. 외부 변환 엔진을 런타임에 추가하지 않는다. |
| pdf.js의 PDF 코퍼스다. | PDF 구조·주석·암호·글꼴 검증에 사용한다. 프로젝트의 Apache-2.0 고지와 별개로 PDF별 출처가 있을 수 있다. | 공개 PDF는 외부 경로에서 읽는다. pdf.js의 파서 코드는 가져오지 않는다. |
| xlrd 정답지다. | `probe_xls_*` 스크립트가 별도 인터프리터에서 셀·수식 캐시를 비교한다. | xlrd 소스나 라이브러리를 dochan에 넣지 않는다. 이번 Python 3.9 환경에는 설치되어 있지 않아 해당 설치본의 고지는 재검증하지 않았다. |
| [olefile](https://github.com/decalage2/olefile) 정답지다. | 선택적 로컬 비교 스크립트가 컨테이너 목록·스트림·변환 출력을 대조한다. 런타임과 일반 테스트에는 필요하지 않다. | 설치된 0.47의 `LICENSE.txt`는 BSD-2-Clause 조건과 PIL 유래 허가문을 함께 담고 있다. 라이브러리를 별도 배포할 때 두 고지를 보존하며 dochan에는 동봉하지 않는다. |
| PDFium·Poppler·pdfplumber·Open Dataloader다. | 독립 PDF 글리프 좌표나 추출 텍스트를 비교하는 검증 도구다. | 도구 바이너리를 동봉하지 않는다. 패키지 안에 남아 있는 선택적 검증 어댑터는 앞 절에 구분해 기록했다. |
| pikepdf/qpdf·pypdf·openpyxl이다. | 합성 암호화 입력의 생성 이력이나 문서 작성기의 관찰 결과로 언급된다. | 생성된 테스트 바이트와 기대값이 남아 있으나 해당 프로젝트의 구현 코드를 포함했다는 근거는 해당 주석에 없다. |
| 한컴의 공개 명세와 HWP 공개 코퍼스다. | 명세·원시 바이트·CRC·길이로 구현과 복호화를 검증한다. | 원본 문서를 배포하지 않으며 한컴 명세 사용 고지는 기존 `NOTICE`에 유지한다. |

내부 문서 쌍은 집계 수치로만 보고하며 파일명·내용을 이 목록에 기록하지 않는다.

## 코드 주석과 docstring의 프로젝트명 조사

현재 추적 파일과 이번 신규 Python 파일을 AST 및 tokenize로 조사했다. 이름이
들어간 import·문자열 상수와 문서의 설명은 주석/docstring 목록과 구분했다. YAML·TOML
설정에도 대상 이름을 검색했다. 검색 대상에는 요청한 pyhwp, hwplib, pdf.js, POI,
LibreOffice, xlrd, msoffcrypto, fontTools, pdfminer, PyMuPDF 외에 PDFBox, Tika,
PDFium, Poppler, pdfplumber, Open Dataloader, pikepdf/qpdf, pypdf, openpyxl 등을 포함했다.

“구현 참고”는 코드 복제를 확정하는 말이 아니다. 주석이 구현이나 상수 대조를
명시하면 보수적으로 분류하고, 문서·정답·이슈만 언급하면 “기대값 근거·호환성 비교”로
분류했다. 기존 주석은 이번 파일 소유권 밖이므로 수정하지 않았다.

53개 일치 위치를 파일 38개로 묶었다. 다음 줄 번호는 이번 변경 후 상태다(그 뒤 `tests/test_distdoc.py:4`와
`dochan/hwp/records/ctrl_header.py:24`의 참조 설명을 명세 인용으로 바꿔 표에서 뺐다).

| 파일과 줄 | 분류 | 언급의 역할 |
| --- | --- | --- |
| `dochan/hwp/section.py:11` | 기대값 근거·호환성 비교다. | hwplib 이슈에서 레코드 순서 사례를 인용한다. 구현 코드 인용이라고 쓰여 있지는 않다. |
| `dochan/quality/batch_validate.py:17, 18, 159, 209, 221` | 기대값 근거·호환성 비교다. | pdfplumber·Open Dataloader를 선택적 검증 엔진으로 호출한다. |
| `dochan/quality/cross_validator.py:4, 5, 175, 179` | 기대값 근거·호환성 비교다. | 독립 PDF 추출 결과를 비교하는 어댑터다. |
| `scripts/build_apache_poi_fixture_index.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/build_apache_tika_fixture_index.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/check_doc_word_preservation.py:5` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/generate_pdf_core14.py:9` | 외부 사실 데이터의 출처다. | PDFBox에 Adobe 원본 AFM이 보존되어 있다는 입수 이력이다. 파서 구현 참고가 아니다. |
| `scripts/probe_crypto_review.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_doc_captions.py:3` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_docppt_polish.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_legacy_crypto.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_legacy_objects.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_officeart.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_ooxml_charts.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_ooxml_crypto.py:1, 3, 4` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_pdf_annotations.py:3` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_pdf_features.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_pdf_link_boundaries.py:1, 3` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_pdf_notes.py:79` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_pdf_passwords.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_pdf_vertical.py:3` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_ppt_corpus.py:52` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_ppt_crypto.py:1, 26` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_ppt_review.py:4` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_xls_charts_review.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_xls_formula_pairs.py:3, 292, 333` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_xls_links_formulas.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/probe_xls_review_cells.py:113` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/run_apache_poi_probe.py:1` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `scripts/verify_ooxml_docx.py:1, 3` | 기대값 근거·호환성 비교다. | 외부 공개 코퍼스·테스트 기대값 또는 독립 도구 출력을 검증에 사용한다. |
| `tests/test_ooxml_charts.py:108` | 기대값 근거·호환성 비교다. | openpyxl 등 작성기의 축 위치 속성을 관찰한 설명이다. |
| `tests/test_pdf_crypto.py:5, 51` | 기대값 근거·호환성 비교다. | pikepdf/qpdf로 생성한 암호화 합성 픽스처의 출처다. |
| `tests/test_pdf_crypto_password.py:3` | 기대값 근거·호환성 비교다. | pypdf 참조 인코더로 만든 암호문·숫자의 출처다. |
| `tests/test_ppt_text.py:247` | 기대값 근거·호환성 비교다. | POI 테스트의 Symbol 문자 기대값을 인용한다. |
| `tests/test_reader_magic_byte_fallback.py:88` | 기대값 근거·호환성 비교다. | POI 손상 코퍼스에서 발견한 회귀 사례다. |
| `tests/test_xls_drawing.py:1` | 기대값 근거·호환성 비교다. | 합성 픽스처가 POI 코퍼스와 독립적임을 설명한다. |

기존 `distdoc.py`의 모듈 docstring은 hwplib·pyhwp 구현을 상수 단위로 확인했다고
명시했으므로 변경 전에는 “구현 참고”였다. 현재 docstring은 한컴 절 번호와 명세의
공백만 기록한다. `tests/test_distdoc.py`의 과거 참조 설명도 명세 절 인용으로 바꿨다.
`ctrl_header.py:24`의 머리말·꼬리말 컨트롤 ID는 「한글 문서 파일 구조 5.0」 4.2.10절 표에 그대로
실려 있음을 확인하고 주석을 명세 인용으로 바꿔 표에서 뺐다.

fontTools 생성기 참조와 생성물의 MIT 고지는 이번 변경으로 제거했다. 현재 조사한
주석·docstring에서는 msoffcrypto·pdfminer·PyMuPDF를 찾지 못했다. 이름이 없다는 사실만으로
과거의 구현 참고 여부까지 입증되지는 않는다. 이전 benchmark 문서의 fontTools 설명은
과거 시점의 기록이며 현재 생성 절차는 이 문서와 새 benchmark를 따른다.
