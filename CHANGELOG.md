# Changelog

## [Unreleased]

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
  참조 해석 깊이 32, 페이지 트리 순환 가드

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
