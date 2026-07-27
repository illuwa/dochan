# Changelog

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
