# 미완료 항목 개선 순서 (추적용)

작성 2026-10-02. 미완료 항목을 중요도 순으로 세우고 진행 상황을 한곳에서 따라가기 위한 문서다.
항목을 끝내면 이 표의 상태와 근거를 고치고, README `Supported Elements` 표는 AGENTS.md 의 규칙대로
단위 테스트와 실물 문서 검증을 모두 통과한 뒤에만 ✅ 로 바꾼다.

출처는 스펙(`docs/superpowers/specs/2026-06-20-native-universal-document-conversion-design.md`)의
단계별 "Not yet completed" 문장과 README 표의 ⬜ 칸이다. 상태는 2026-10-02 의 코드와 테스트를 직접
확인해 적었다. 스펙 문장이 코드보다 뒤처진 곳은 그 사실을 함께 적었다.

## 순서와 상태

| 순위 | 항목 | 상태 |
|---|---|---|
| 1 | Office 이미지 바이너리 추출 (DOCX·PPTX·XLSX) | 리더 구현 완료, 파일 저장 기능은 없음 |
| 2 | Office 표·그림 캡션, 차트 데이터 | 진행 중 (차트 종류·축 제목 2026-10-02 추가) |
| 3 | Office 심층 기능 (임베드 미디어, 숨긴 시트, 암호화 문서) | 미착수 |
| 4 | PDF 표 (연결형 중첩 표, 페이지 경계 셀 결합, 병합 셀 완전 일치) | 미착수 |
| 5 | PDF 세로쓰기 (WMode 1 세로 폰트) | 미착수, 실물 표본 없음 |
| 6 | PDF LZW 필터, TIFF predictor | 미착수 |
| 7 | PDF 사용자 암호가 필요한 문서 | 미착수 |

## 1순위 — Office 이미지 바이너리 추출

DOCX·PPTX·XLSX 리더는 임베드 이미지의 바이트를 `Image.image_data` 로 읽고 `Document.assets` 에
`AssetRef` 로 기록한다. 세 리더 모두 단위 테스트가 있다(`test_*_embedded_image_bytes_extracted_for_ocr`,
`test_records_*_image_relationship_as_asset`). README 의 `이미지 참조`·`이미지 OCR` 칸도 세 형식 모두 ✅ 다.

남은 일은 두 가지다. 스펙 Phase 2(DOCX)와 Phase 4(XLSX)의 "Not yet completed … image" 문장이 코드보다
뒤처져 있으니 고쳐야 한다. 그리고 읽은 이미지를 파일로 저장하는 CLI·배치 옵션은 HWP·HWPX 를 포함해 어느
형식에도 없다. 이 옵션이 필요한지는 따로 정한다.

## 2순위 — 표·그림 캡션, 차트 데이터

2026-10-02 에 끝낸 것(PPTX·XLSX 공통, `dochan/ooxml/charts.py`):

- 차트 종류를 데이터 표의 위쪽 캡션으로 낸다(`Chart type: column + line`). 세로/가로 막대는 `c:barDir` 로
  가르고, 혼합 차트는 종류를 모두 적는다. 모르는 종류의 태그 이름은 내보내지 않는다.
- 축 제목을 같은 캡션에 잇는다(`Category axis: 분기; Value axis: 금액`). 숨긴 축은 뺀다. 데이터가 없는
  차트는 축 제목이 있을 때만 캡션을 일반 문단으로 낸다.
- 차트 제목은 `c:chart/c:title` 만 읽는다. 전에는 PPTX 가 축 제목까지 제목에 이어 붙였고, XLSX 는 차트
  제목이 없으면 축 제목을 3단계 제목으로 올렸다.
- 제목 글자는 런을 붙이고(런 안 공백 보존), 줄바꿈과 문단을 공백으로 잇는다. 셀에 연결된 제목
  (`c:strRef` 캐시)과 `mc:AlternateContent` 로 감싼 요소도 한 갈래만 읽는다.
- PPTX 도 분산형·거품형의 `c:xVal`/`c:yVal` 값을 읽는다. X 값이 계열마다 다르면 두 형식 모두
  `Series | X | Y` 긴 표로 낸다.

검증 수준: 단위 테스트, 그리고 openpyxl 로 만든 통합문서(막대·가로 막대·선·원·영역·분산·혼합)의 변경 전후
출력 비교. Opus 감수·재감수와 codex 리뷰의 지적(데이터 없는 차트의 축 제목 소실, 줄바꿈, `c:delete`
기본값, 공백 보존, 확장 래퍼와 계열 중복, 분산형 X 값)을 테스트와 함께 반영했다. PowerPoint·Excel 로 만든 실물 차트 문서는
구하지 못해 검증하지 못했다. 그래서 README 표는 바꾸지 않았다(XLSX `차트 제목/데이터` 는 ⬜ 그대로).

남은 일:

- Office 로 만든 실물 PPTX·XLSX 차트 문서로 검증한 뒤 README 의 XLSX `차트 제목/데이터` 칸을 정한다.
- 캐시 없는 차트. openpyxl 같은 생성기는 `c:strCache`/`c:numCache` 를 쓰지 않아 머리 행만 있는 빈 표가
  나온다. 시트 참조(`c:f`)를 풀어 값을 채우거나 빈 표를 내지 않아야 한다.
- DOCX 차트. `docx.py` 에 차트 처리가 없다(README ⬜).
- DOCX·PPTX 표·그림 캡션(README ⬜).
- 분산형의 X/Y 축 구분. `c:axPos` 는 생성기에 따라 두 축 모두 `l` 이라 쓸 수 없다. `c:axId` 순서로
  가르는 방법은 실물 문서로 확인한 뒤에 넣는다.
- Markdown 캡션은 `*…*` 안에 그대로 들어간다. 축 제목에 `a*b` 같은 별표가 있으면 강조가 깨질 수 있다.
  HWPX 캡션과 같은 출력 경로라 함께 고친다.
- 막대와 분산형을 섞은 혼합 차트의 긴 표는 X 열에 범주 이름과 숫자가 섞인다. 실물 표본이 생기면 형식을
  정한다.
- 거품 크기(`c:bubbleSize`), 자동 제목(제목 요소 없이 계열 이름이 제목으로 보이는 차트), 폭포·트리맵 같은
  신형 차트(`chartEx` 파트).
- `feat/hwpx-specialization` 브랜치의 HWPX 차트 추출(`dochan/hwpx/charts.py`)이 main 에 들어오면 종류·축
  제목 표기를 이 문서의 형식과 맞춘다.

## 3순위 — Office 심층 기능

스펙이 PPTX 미완료로 적은 것 가운데 발표자 노트는 README ✅ 이고, SmartArt 글자는 구현과 단위 테스트가
있다(`test_reads_pptx_smartart_diagram_text`). 스펙 문장을 고쳐야 한다.

실제로 남은 것은 PPTX 임베드 미디어(영상·음성), XLSX 숨긴 시트 구분(지금은 보이는 시트와 똑같이 낸다),
DOCX·PPTX·XLSX 암호화 문서(README ⬜)다.

## 4~7순위 — PDF

스펙 Phase 6 의 "Not yet completed" 문장 그대로다.

- 4순위: 부모와 테두리를 공유하는 연결형 중첩 표, 페이지 경계에서 잘린 셀의 결합, 병합 셀 완전 일치,
  괘선 없는 1×1 글상자.
- 5순위: WMode 1 세로 폰트. 79쌍 실물 표본에 회전·세로 조각이 없어 검증 수단부터 마련해야 한다.
- 6순위: LZW 필터, TIFF predictor.
- 7순위: 빈 암호·소유자 경로로 열리지 않는, 사용자 암호가 필요한 문서.
- 순위 밖: 한 글자 문맥으로 정해지지 않는 줄바꿈 공백(약 6%).

## 순위에 넣지 않은 것

Legacy Office(.doc·.ppt·.xls)의 미완료 항목(문단 서식, 병합 셀 표, 이미지, 차트 등)은 스펙 Phase 5 에
적혀 있다. 수요가 확인되면 순위에 넣는다.
