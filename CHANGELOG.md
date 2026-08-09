# Changelog

## [1.3.0] - 2026-08-09

네이티브 PDF 리더(텍스트·표준 암호화·이미지 OCR·글리프 폭 레이아웃), 크로스
포맷 이미지 추출+OCR(PDF/DOCX/PPTX/XLSX), OOXML·레거시 서식과 DOCX 수식,
HWP 바이너리 열 완성(도형 텍스트·하이퍼링크·대체 텍스트·주석·캡션·북마크)을
추가한 대형 릴리스. 모든 신규 기능은 공인 시험 벡터·실물 문서·회귀 코퍼스로
검증했으며, 검증하지 못한 기능은 비교표에서 의도적으로 미표기(⬜)로 남겼다.

### 추가 (E — HWP/HWPX 잔여 항목)

- **HWP 표/그림 캡션**: 캡션 LIST_HEADER 가 셀로 오인돼 표 차원이 무너지던 버그
  수정 — TABLE 레코드 전 LIST_HEADER 를 캡션으로 분리, 위치코드로 side 판정.
  정보보안 세부지침 등에서 HWPX 정답지와 표 차원·캡션 텍스트 일치 확인
- **HWP·HWPX 내부 북마크**: 책갈피를 `[bookmark: NAME]` 마커로 추출(`_GoBack`
  등 자동 책갈피 제외). corpus 쌍 5/5 일치
- **HWP·HWPX 내부 하이퍼링크**: 책갈피형 링크를 `#앵커` 로 복원(스크립트형 제외).
  143E 쌍에서 두 포맷 `[김영훈](#참조)` 동일
- **필드 결과 텍스트**: HWP·HWPX 가 필드(누름틀·계산식·하이퍼링크) 결과 텍스트를
  이미 인라인 캡처함을 회귀 테스트로 고정
- 스타일 상속·변경 추적은 검증할 실문서 데이터 부재로 보류(정직 ⬜ 유지)

### 추가 (B — 크로스 포맷 이미지 추출 + OCR)

- **PDF 이미지 추출 + OCR**: 이미지 XObject 바이너리를 추출(DCTDecode/JPX 는 원본,
  무압축·Flate raw 는 Pillow 로 PNG 재구성)해 Image 요소로 넣고 OCR 연결. 실물
  스캔 PDF 교육수료증(이전 0자)에서 발급번호·이름 등 한글 291자 추출
- **DOCX/PPTX/XLSX 이미지 추출 + OCR**: 임베드 이미지 바이트를 Image 요소로 넣어
  `Dochan(ocr=True)` 동작 (네 포맷 모두 end-to-end OCR 검증). 문서당 100MB 상한
- Image 모델에 image_format·provenance 필드 추가(가산)

### 추가 (A — PDF 글리프 폭 레이아웃 엔진)

- **글리프 폭 기반 좌표 추출**: 폰트 /Widths·/W·/DW 로 WidthMap 을 만들고
  텍스트 행렬(Tm/Td/TD/T*/TJ)로 각 텍스트 조각의 실제 x/y 를 누적.
  단어 간격을 어림값이 아닌 글리프 폭 기반으로 판정 (80쌍 유사도 0.868→0.878)
- **PDF 서식(bold/italic)**: BaseFont 이름·FontDescriptor Flags·FontWeight 로 판정,
  서식별 run 분리로 부분 굵게 보존. 실물 Helvetica-Bold PDF 로 검증
- **표 재구성은 보류 유지**: 실측 결과 HWP→PDF 는 셀이 아닌 어절 단위로 좌표를
  찍고 표 격자는 벡터 그래픽으로 그려, 텍스트 좌표만으로는 열 경계를 신뢰성
  있게 잡을 수 없다(별표19 x좌표 미정렬 확인). 그래픽 연산자 파싱이 선행되어야
  하는 별도 과제로 이월. 읽기 순서도 CTM 미반영 위험으로 콘텐츠 순서 유지

### 추가 (4순위 — PDF 표준 암호화 복호화)

- **PDF 표준 보안 핸들러**: RC4(V1/V2/V4)·AESV2(AES-128-CBC)·AESV3(AES-256-CBC,
  R6 경화 해시) 복호화를 stdlib 만으로 구현. 빈 사용자 암호(소유자만 잠근 문서)와
  사용자 제공 암호 모두 처리. AES 유틸을 CBC·256비트로 확장
- 검증: RC4(RFC 6229)·AES-128/256-CBC(NIST SP 800-38A) 공인 시험 벡터 +
  qpdf 생성 RC4/AES-128/AES-256 최소 PDF 엔드투엔드(base64 임베드, CI 자립형) +
  실제 암호화 정부 PDF 에서 이전 0자 → 한글 1,279자 추출
- 진짜 사용자 암호가 필요한 문서는 여전히 명확한 경고로 보고(미지원 아님, 암호 부재)

### 추가 (1순위 — HWP 바이너리 열 완성)

- **HWP 텍스트박스/도형 텍스트**: GSO SHAPE_COMPONENT 서브트리의 문단을 문서 흐름으로
  배치 (HWPX drawText 와 동등 — 실문서 쌍에서 43건 전부 일치)
- **HWP 하이퍼링크**: `%hlk` 필드 Command 에서 URL 추출, TextRun.link 연결
  (레이아웃을 실물 hexdump 로 실증, HWP↔HWPX 쌍 URL 집합 일치)
- **HWP 이미지 대체 텍스트**: 개체 공통 속성 설명문 → `Image.alt_text`
  (HWPX shapeComment 와 값 일치 확인)
- **HWP·HWPX 주석**: `tcmt` 숨은설명(HWP)과 hiddenComment/memogroup(HWPX) 추출,
  DOCX 와 동일한 `[^comment-N]` 규약으로 렌더
- 검증 중 발견한 기존 버그 3건 수정: 머리말/꼬리말 ctrlId 오류('hdr '/'ftr ' →
  실측 'head'/'foot')로 실문서 머리말이 전부 무시되던 문제, 이미지 binItem
  0-based 오프셋으로 엉뚱한 BinData 에 연결되던 문제, HWPX Path-부재 하이퍼링크 누락
- 회귀 검증: 전체 574개 테스트, 코퍼스 7,190개 재스캔 무회귀
  (empty_output 324→244 — 도형 텍스트·머리말이 새로 추출된 개선)

### 추가 (3순위 — PDF Phase 2)

- **현대 PDF(1.5+) 구조**: xref 스트림·객체 스트림(ObjStm) 네이티브 파싱 + PNG
  Predictor(Sub/Up/Average/Paeth) 해제. 실물 검증 — qpdf 변환 xref 스트림 PDF 에서
  클래식 원본과 바이트 단위 동일 추출
- **Outline 북마크**: 목차 섹션 + Dest 페이지 번호 매핑 (순환 가드, 1,000개 상한)
- **링크 주석 URL**: /Annots 의 URI 액션 추출, `TextRun.link` 연결
- **제목 감지**: 페이지 폰트 크기 중앙값 대비 임계(1.5×→h1, 1.25×→h2) — 실문서에서
  문서 제목 감지 확인
- 표 재구성은 의도적 보류 — 어절 단위 좌표(실측 근거) 때문에 글리프 폭 메트릭 없이는
  열 경계 신뢰성이 부족. 거짓 체크 대신 스펙에 이월 기록
- **리더 견고성**: 손상 문서의 파서 예외를 doc.errors 로 강등 (Apache POI 퍼저
  픽스처 573개 실측에서 발견한 계약 위반 47건 → 0건)

### 추가 (2순위 — 비교표 커버리지 확대)

- **XLSX 셀 서식**: `xl/styles.xml` fonts + cellXfs fontId 기반 bold/italic/underline/strike
- **XLS 셀 서식**: BIFF `FONT`(0x0031)/`XF` 레코드 기반 서식 (폰트 인덱스 4 부재 quirk 보정)
- **DOCX 수식**: OMML → LaTeX 변환 (분수·첨자·근호·∑∫∏·구분자·함수·극한),
  블록/인라인 수식 모두 문서 흐름에 배치
- PPTX 서식(b/i/u/strike)·DOCX/PPTX 이미지 참조는 기구현 확인 후 검증 테스트 추가로 비교표 ✅ 반영
- 날짜/숫자 서식 행의 DOC/PPT/DOCX/PPTX 는 "해당 없음(—)"으로 정정 —
  렌더된 텍스트 포맷에는 서식 해석할 원시 값이 없다

### 추가

- **네이티브 PDF 리더 Phase 1** (`dochan/pdf/`): 외부 엔진 없이 표준 라이브러리만으로
  단순 디지털 PDF 의 페이지 텍스트를 추출한다.
  - PDF 객체 문법 파서 (사전·배열·문자열·이름·간접 참조·스트림)
  - 고전 xref 테이블·trailer 체인 파싱 + 손상 시 `N G obj` 스캔 폴백
  - FlateDecode / ASCIIHexDecode / ASCII85Decode 필터 해제
  - 텍스트 연산자(Tj/TJ/'/"/Td/TD/Tm/T*) 해석으로 줄 단위 텍스트 재구성
  - ToUnicode CMap 디코딩 — 한글(Identity-H CID) PDF 텍스트 지원
  - 페이지 번호 provenance (`Provenance(page=N)`) 를 섹션·문단에 기록
  - 암호화·xref 스트림(PDF 1.5+)·객체 스트림·스캔 전용 페이지는 경고로 보고
  - `Dochan("file.pdf")` 라우팅 (확장자 + `%PDF-` 매직), CLI, 배치 `.pdf` 수집
- 보안 한도: 파일 500MB, 스트림 해제 50MB, 객체 50만 개, 페이지 1만 개,
  참조 해석 깊이 32, 객체 중첩 깊이 64, 페이지 트리 순환 가드

### 수정 (Opus 감수 반영)

- 손상된 bfrange CMap 이 무한 루프(코드 길이 0)·예외 탈출(`]` 목적지)을 일으키던 문제
- 2만 중첩 배열 같은 깊은 중첩 객체가 `RecursionError` 로 크래시하던 문제 — 깊이 한도 + 리더 전체 방어적 예외 처리
- xref 손상으로 객체 스캔 폴백을 탈 때 trailer 를 복구하지 않아 암호화 PDF 를 평문처럼 파싱하던 구멍
- ToUnicode 없는 CID(Identity-H) 폰트의 원시 바이트가 NUL 등 제어문자로 본문에 새던 문제 — 경고 후 해당 텍스트 제외
- 폰트 디코더를 문서 단위로 캐시해 수백 페이지 문서에서 ToUnicode 반복 파싱 제거
- 악성/손상 PDF 방어 회귀 테스트 8건 추가 (`tests/test_pdf_hardening.py`)

### 수정 (Opus 감수 2차 반영)

- CMap 누적 매핑 총량 무제한으로 압축 1KB CMap 이 수 GB 메모리를 강제하던 문제 — 10만 항목 상한
- `/Contents` 배열이 같은 스트림을 반복 참조하면 해제 총량이 증폭되던 문제 — 문서 단위 200MB 누적 예산 + 해제 결과 캐시 + 페이지당 스트림 수 256 상한
- 미매핑 CMap 코드에서 최대 코드 길이만큼 건너뛰어 뒤 문자를 삼키던 문제 — 최소 길이 전진
- 1/2바이트 혼재 CMap 에서 짧은 코드 우선 매칭으로 2바이트 코드가 오매칭되던 문제 — 긴 코드 우선
- 같은 기준선의 왼쪽 되돌림(2단 조판·표 열)이 한 줄로 병합되던 문제 — x 좌표 후퇴 시 줄바꿈
- xref free 엔트리를 tombstone 으로 기록하지 않아 증분 갱신에서 삭제된 객체가 부활하던 문제
- xref 섹션 수 한도 초과 시 조용히 무시하던 문제 — 경고 추가
- 같은 경고가 페이지 수만큼 중복 누적되던 문제 — 문서 단위 dedup
- `.pdf` 확장자를 매직바이트 확인 없이 라우팅하던 문제 — HWP 관행과 동일한 실포맷 보정
- Predictor 인코딩 스트림이 깨진 텍스트를 조용히 내보내던 문제 — 경고 후 건너뜀
- 인라인 이미지 이진 데이터 속 우연한 `EI` 를 종결자로 오인할 수 있던 문제
- 방어 회귀 테스트 10건 추가 (총 535개 테스트)
- 실문서 검증: 동일 문서 HWP/HWPX/PDF 쌍 80세트 크래시·유출 0건, HWPX↔PDF 유사도 평균 0.868

### 검증

- 공개 HWP/HWPX 코퍼스 7,188개(5.4GB) 재다운로드 후 전수 재스캔 — PDF Phase 1
  작업과 라우팅 변경이 기존 경로에 회귀를 일으키지 않음을 확인 (크래시·내부
  오류가 7월 기준선과 파일/카테고리 단위로 일치, 신규 이상 클러스터 0건).
  자세한 내용은 `docs/benchmarks/2026-08-09-hwp-corpus-rescan-after-pdf-phase1.md`

공개 HWP/HWPX 6,977개 코퍼스(`docs/benchmarks/hwp-corpus-fixtures.json`, 법제처·국세청 등
정부 서식·보도자료 + hwplib/pyhwp 등 오픈소스 픽스처)로 회귀 스캔 후 발견한 4건 수정.
`succeeded_with_internal_errors`가 79건에서 8건(전부 암호화 문서로 사양상 제한적 파싱)으로
줄었다. 자세한 내용은 `docs/benchmarks/2026-07-27-hwp-corpus-collection-and-quality-scan.md`.

### 수정

- **배포용(distribution-copy) HWP 문서 본문 소실**: `ViewText/SectionN` 스트림이 압축 전
  AES-128-ECB로 암호화되어 있는데 그대로 zlib 해제를 시도해 크래시 없이 빈 결과만 냈다.
  DistributeDocData 256바이트 블록을 LCG 기반 XOR로 역스크램블해 AES 키를 뽑아낸 뒤
  복호화하고 나서 압축을 해제하도록 고쳤다 (`dochan/hwp/distdoc.py`, `dochan/utils/aes.py`
  — 순정 AES-128 구현, 신규 의존성 없음). 국세청 전자신고 매뉴얼, 통계청 사회조사 결과 등
  실제 공공 배포 문서에서 재현·검증.
- **HWPX 이미지 압축률 가드 오탐**: 단색 영역이 넓은 BMP 이미지는 실사용 문서에서도
  100배 넘게 압축되는 일이 흔한데(실측: 기상청 보도자료 7.85MB BMP → 101.1배), zip bomb
  방어용 `MAX_COMPRESSION_RATIO=100`이 이를 걸러 이미지를 조용히 누락시켰다. 실질적 방어는
  절대 크기 상한(`MAX_FILE_SIZE=100MB`)이 담당하므로 비율 상한을 2000으로 올렸다.
- **확장자/실제 포맷 불일치 시 파싱 실패**: 공개 출처 중 일부는 파일명 확장자와 실제
  바이트가 어긋난 채 배포한다(`.hwp` 확장자인데 실제로는 ZIP/HWPX, 또는 그 반대). 이제
  확장자가 `.hwp`/`.hwpx`면 매직바이트를 먼저 확인해 실제 포맷에 맞는 파서로 보정한다.
- **HWPX 문서 내 무효 XML 제어문자로 섹션 전체 파싱 중단**: XML 1.0에서 금지된 C0
  제어문자(탭/개행/CR 제외) 하나 때문에 `header.xml`/섹션 XML/`content.hpf` 전체가
  파싱 실패했다. 해당 문자만 제거하고 한 번 더 시도하도록 `_parse_xml_tolerant()`를
  추가했다.

## [1.2.0] - 2026-07-27

레거시 오피스(DOC/XLS/PPT) 견고성 수정. Apache POI 테스트 코퍼스 720개(DOC 160, XLS 415,
PPT 145, 퍼징 케이스 포함)를 전수 파싱해 검증했다. HWP/HWPX 출력은 바이트 단위로 동일하다.

|            | 정상 | 경고 | 텍스트 없음 | 빈 결과 | 타임아웃 |
|------------|-----:|-----:|-----------:|--------:|--------:|
| 수정 전    | 628 | 6 | 26 | 50 | 10 |
| 수정 후    | 653 | 5 | 31 | 31 | **0** |

23개 파일이 이전에는 아무 텍스트도 못 뽑던 상태에서 데이터를 복원했다
(최대 199,932자). 실제 내용이 줄어든 파일은 암호화 문서 3건뿐이며, 그 3건은
이전에 암호문을 본문 텍스트라고 내보내던 것을 정확히 거부하게 된 결과다.

### 수정

- **XLS 격자 폭주**: `DIMENSION`/`ROW` 레코드의 선언값을 그대로 믿고 그 범위 전체를
  셀마다 네 개 객체로 실체화했다. 실제 셀 4개짜리 파일이 65536×256 = 1,677만 셀을
  만들었다. 내용 있는 셀 수 대비 격자가 지나치게 크면 선언값으로 부풀려진 것으로 보고
  실제 범위로 되돌린다. 빽빽한 실제 데이터(실측 27만 셀)는 잘리지 않는다.
- **XLS 격자 경계 오산**: 경계를 빈 자리표시자(`MULBLANK`/`BLANK`)까지 포함해 계산해서,
  내용이 30열인 표가 108열로 잡혀 본문의 75%가 잘렸다. 내용이 있는 좌표만으로 계산한다.
- **XLS 워크북 총량**: 시트별 상한만으로는 시트를 여럿 두는 우회를 막지 못했다
  (실측 10.7KB 스트림으로 1,920만 셀). 워크북 전체 예산을 도입했다.
- **`MERGEDCELLS`/`HLINK` 범위 채우기**: 선언한 좌표 범위를 전부 채워 기형 파일 하나가
  65536×256번 반복하게 만들었다. 예산을 두고 초과 시 앵커만 채운다.
- **빈 시퀀스 `max()`**: 행 좌표만 있고 셀이 없는 시트에서 `ValueError` 로 워크북 전체가
  사라졌다(24건).
- **`DIMENSION` 레코드 길이**: BIFF5+ 12바이트 형식만 가정해 BIFF3/4 의 10바이트
  레코드에서 `struct.error` 가 났고, BIFF2 의 8바이트 레코드는 조용히 무시됐다.
- **날짜 변환**: 날짜 서식 셀의 값이 NaN/inf 이거나 표현 범위를 벗어나면 예외가 나
  워크북 전체를 잃었다. 원본 숫자로 떨어뜨린다.
- **DOC 후보 스트림**: `parse_doc_word_stream` 호출이 보호되지 않아 테이블 스트림 하나의
  파싱 실패가 문서 전체를 죽였다. PPT/XLS 와 같은 형태로 맞췄다.
- **병합 앵커 span**: 격자가 잘린 표에서 `row_span`/`col_span` 이 표 밖을 가리켰다.

### 추가

- **암호화 문서 감지**: OLE 컨테이너의 `EncryptedPackage`/`EncryptionInfo`(DOC/XLS/PPT),
  BIFF `FILEPASS` 레코드(XLS), FIB `fEncrypted` 비트(DOC)를 인식해 명확히 보고한다.
  이전에는 "스트림을 찾을 수 없음" 으로 원인을 오해하게 했고, 암호화된 XLS 는 계속
  파싱하려다 쓰레기 좌표로 폭주했으며, 암호화된 DOC 는 암호문을 본문으로 내보냈다.
- **진단 메시지**: 격자를 잘랐을 때와 DOC 본문이 비었을 때 그 사실을 `errors` 에 남긴다.
  조용히 데이터를 버리지 않는다.
- 내용이 하나도 없는 큰 격자는 표를 만들지 않는다. 이전에는 탭만 20만 개인 표가 나왔다.

### 테스트

- `tests/test_office_binary_hardening.py` 신설 (24개). 전체 450개 통과.
  수정 전 트리에서 24개 중 18개가 실패한다.

## [1.1.0] - 2026-07-27

HWPX 파서 고도화. 실문서 80개 기준 텍스트 누락이 325건 8,774자에서 2건 14자로 줄었다.
HWP 경로의 plain text/JSON 출력은 바이트 단위로 동일하다.

### 추가

- **하이퍼링크**: `<hp:fieldBegin type="HYPERLINK">`~`<hp:fieldEnd>` 구간을 인식해
  `TextRun.link`에 URL을 담고 Markdown `[텍스트](URL)`로 출력. 표 셀 안 링크도 지원.
- **표/그림 캡션**: `<hp:caption>`을 `Table.caption` / `Image.caption`으로 파싱하고
  `side` 속성에 따라 표 위/아래에 배치.
- **도형 텍스트**: `<hp:rect>`/`<hp:ellipse>`/`<hp:container>` 안의 `<hp:drawText>` 파싱.
  `<hp:container>` 중첩을 재귀 처리한다.
- **그림 설명**: `<hp:shapeComment>`를 `Image.alt_text`로 담아 Markdown 대체 텍스트에 사용.
  한글이 자동 생성한 메타데이터이므로 본문 텍스트로는 내보내지 않는다.
- **개요 기반 제목 감지**: 스타일 이름(`개요 N`/`Outline N`/`Heading N`)과
  `<hh:paraPr>`의 `<hh:heading type="OUTLINE">`을 사용. 깊은 개요 수준이 본문 열거 항목에
  쓰이는 실태를 감안해 헤딩 승격은 3수준까지로 제한한다.
- **각주/미주 번호**: 본문에 참조 마커를 심고 `[^1]`, `[^2]` 라벨로 정의를 문서 말미에 모은다.
  기존에는 모든 각주가 `[^각주]`, 모든 미주가 `[^미주]`로 나와 둘 이상이면 충돌했다.
- **문서 메타데이터**: HWPX도 `char_shapes`/`para_shapes`/`styles`/`face_names`를 채우고
  `source_format`을 설정해 HWP 경로와 대칭이 된다.
- `<hp:compose composeText="...">` 글자 겹치기 문자 보존.

### 수정

- **`<hp:t>` 안 자식 요소 뒤 텍스트 손실**: `<hp:fwSpace/>`나 `<hp:tab/>` 같은 자식이 있으면
  그 뒤 문장이 통째로 버려졌다. 실문서 기준 최대 손실 원인이었다.
- **표 격자 배치**: `<hp:cellAddr>`의 `colAddr`/`rowAddr`로 격자를 복원한다.
  기존에는 `<tr>` 안 `<tc>` 등장 순서로만 배치해, 병합으로 셀이 빠진 행에서 열이 밀렸다.
  병합에 가려진 자리는 자리표시자 셀로 채워 열 수를 유지한다.
- **중첩 표 텍스트 소실**: 표 안의 표 텍스트가 모든 출력에서 사라졌다.
- **미주 안 표 소실**: 각주/미주/머리글의 내용에서 표가 걸러져 버려졌다.
- **머리글·각주 안 이미지**: `Document.find_all`이 그 내부를 순회하지 않아
  이미지 바이너리 로드와 OCR 대상에서 제외됐다.
- **취소선 오탐**: 일부 문서가 모든 글자모양에 취소선 모양 기본값을 저장해 본문 전체가
  취소선으로 렌더됐다. 전 글자모양에 걸린 경우를 문서 기본값으로 간주한다.
- **`<hp:equation>` 수식 소실**: 수식 원문이 `<hp:script>` 자식 요소에 있는데 읽지 않았다.
- **바이너리 항목 매핑**: `content.hpf`의 `<opf:item id href>`로 정확히 대응시킨다.
  기존 부분 문자열 매칭은 `image1`이 `image10.png`에 걸릴 수 있었다.
- **`<hp:switch>` 분기 해석**: `case`/`default` 양쪽을 모두 읽어 여백 값이 두 번 반영되던 문제.
  해석하지 않는 단위계의 `case`는 건너뛰고 `default`를 쓴다. 이로써 HWP 바이너리와
  문단 모양 값이 일치한다(실문서 76쌍 16,272개 전부 일치).
- 레거시 DOC 리더가 표를 포함한 본문에서 `AttributeError`로 문서 전체를 잃던 문제.
- DOCX 주석이 표로 시작하면 `DOCXReader.read`가 예외를 던지던 문제.
- Markdown 표 셀에 리터럴 탭이 그대로 박혀 표가 깨지던 문제.
- plain text 표에서 병합에 가려진 셀이 빠져 열이 밀리던 문제.

### 보안

- 표 격자 실체화에 문서 단위 셀 예산(20만)을 도입. 이전에는 1KB 미만 파일로
  수 GB를 할당시킬 수 있었다.
- `<hp:t>` 안 XML 주석/엔티티 노드로 섹션 전체가 소실되던 문제 차단.
- `header.xml`/`content.hpf`에도 크기·압축률 상한 적용.
- 이미지 데이터를 `BinData/` 하위로 제한해 아카이브 내 임의 엔트리 참조를 차단.
- 짝이 맞지 않는 필드가 무한히 쌓일 때의 O(n²) 처리 시간 제거.
- 글자 크기 파싱의 `OverflowError`로 문서 전체를 잃던 문제 차단.

### 테스트

- `tests/test_hwpx_reader.py` 신설 (20개). 전체 426개 통과.

## [1.0.2] - 2026-06-21

- PyPI publish workflow switched to token-based authentication (`PYPI_API_TOKEN`) to avoid trusted-publisher env dependency.
- Prepared release retry path for corrected publishing configuration.

## [1.0.1] - 2026-06-21

- Python 3.9 호환성 회귀 수정: `int | None` 타입 힌트를 `Optional[int]`로 교체
- 태그 릴리스 파이프라인이 Python 3.9 테스트를 통과하도록 정리

## [1.0.0] - 2026-06-21

- Stable PyPI packaging baseline for dochan.
- Marked package as production/stable (PEP 621 metadata and classifiers).
- Added PyPI publishing workflow with tag-driven release and tag build gate.
- Excluded internal test package from wheel/sdist distribution.
- Added project changelog and synchronized package version with `dochan.__version__`.

### Supported for this release

- HWP/HWPX: native parsing + markdown/json/plain outputs.
- Office documents: DOC/DOCX, PPT/PPTX, XLS/XLSX.
- CLI conversion + directory batch conversion.
- OCR optional dependency (Tesseract via `dochan[ocr]`).
