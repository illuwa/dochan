# DOC·PPT 문서 속성 실물 검증 (2026-10-04)

DOC·PPT의 OLE `\x05SummaryInformation`에서 제목과 작성자를 읽어 OOXML과 같은 순서로 놓았다. DOC는 앞쪽 머리글 뒤·본문 앞, PPT는 본문 앞에 속성 문단을 놓는다. [MS-OLEPS]의 SummaryInformation FMTID, 속성 ID 2·4, `VT_LPSTR`·`VT_LPWSTR`, 코드 페이지 속성 ID 1을 기준으로 읽었다. [MS-DOC]의 `WordDocument`와 [MS-PPT]의 `PowerPoint Document`는 기존 본문·암호 판정 경로로 읽고, 성공한 문서에만 속성 문단을 넣었다. Apache POI와 LibreOffice의 구현 코드는 참고하지 않았다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| DOC 제목·작성자 | `corpus/poi-src/test-data/document/SampleDoc.doc` | `SampleDoc.docx`의 `docProps/core.xml` 출력과 POI `TestProblems.java:195`의 작성자 기대값 | `# Test Document`, `Author: Nick Burch` | 같은 두 문단이 본문 앞에 나왔다. | 일치 |
| DOC 제목·작성자 | `corpus/poi-src/test-data/document/PageSpecificHeadFoot.doc` | `PageSpecificHeadFoot.docx`의 `docProps/core.xml` 출력 | `# ODD Page Header text`, `Author: Nick Burch` | 같은 두 문단이 본문 앞에 나왔다. | 일치 |
| DOC 제목·작성자 | `corpus/poi-src/test-data/document/documentProperties.doc` | 원본 OLE 속성 스트림의 CP1252 문자열과 `documentProperties.docx` 출력 | 원본 DOC는 `This is document title`·`Sergey Vladimirov`이고, DOCX 짝은 `Hello World`·`Paolo Mottadelli`다. | 원본 DOC의 두 값을 정확히 냈다. | 원본과 일치, 짝의 속성값은 다름 |
| PPT 제목·작성자 | `corpus/poi-src/test-data/slideshow/basic_test_ppt_file.ppt` | POI `TestPOIDocumentScratchpad.java:59`의 작성자 기대값과 원본 OLE 속성 스트림 | `Author: Hogwarts` | `# This is a test title` 다음에 `Author: Hogwarts`가 나왔다. | 일치 |
| PPT 제목·작성자 | `corpus/poi-src/test-data/slideshow/SampleShow.ppt` | `SampleShow.pptx`의 `docProps/core.xml` 출력 | `# SlideShow Sample`, `Author: Nick Burch` | 같은 두 문단이 본문 앞에 나왔다. | 일치 |
| PPT 제목·작성자 | `corpus/poi-src/test-data/slideshow/backgrounds.ppt` | 원본 OLE 속성 스트림의 CP1252 문자열과 `backgrounds.pptx` 출력 | 원본 PPT는 `PowerPoint Presentation`·`Yegor Kozlov`이고, PPTX 짝은 `Solid Fill`·`yegor`다. | 원본 PPT의 두 값을 정확히 냈다. | 원본과 일치, 짝의 속성값은 다름 |
| DOC 제목·작성자 | `corpus/lo-src/sw/qa/core/layout/data/floattable-then-table.doc` | 원본 OLE 속성 스트림의 CP1252 문자열과 같은 줄기의 DOCX 출력 | 원본 DOC 작성자는 `alicia`이고, DOCX 짝은 `hxe2`다. | `Author: alicia`를 냈다. | 원본과 일치, 짝의 속성값은 다름 |

POI의 같은 줄기 짝은 DOC 13개와 PPT 8개다. 속성 사전 전체가 같은 짝은 각각 12/13, 7/8이다. DOC 속성 요소의 위치도 13/13에서 짝과 같고, 머리글이 있는 7쌍 모두 머리글 뒤에 놓인다. PPT 속성 위치는 8/8에서 같다. LibreOffice DOC 짝은 1/2가 같다. 나머지 세 짝은 변환본의 저장 속성값 자체가 다르다. 세 원본 OLE 스트림의 FMTID는 모두 `e0859ff2f94f6810ab9108002b27b3d9`였고, 위 표의 원본 문자열은 각각 속성 스트림의 CP1252 바이트에서 직접 확인했다. 따라서 이 세 차이를 맞추기 위해 원본 값을 변환본 값으로 치환하지 않았다.

`python -m scripts.compare_office_pairs`의 POI 21쌍 평균 토큰 유사도는 변경 전 0.7406, 변경 후 0.8792였다. LibreOffice DOC 2쌍은 0.4375에서 0.4413으로 변했다. 이 값은 문서 전체 비교 지표이므로 속성 정확도 판정에는 쓰지 않았다.

`scripts.probe_legacy_docprops`로 파일마다 Markdown·JSON의 SHA-256·문자 수·오류 요약만 보관했다. POI DOC 160개 중 132개, LibreOffice DOC 330개 중 199개에 속성 문단이 추가되었다. POI PPT 145개 중 119개, LibreOffice PPT 75개 중 43개에 추가되었다. DOC 490개와 PPT 220개 모두 속성 문단을 제거한 본문 Markdown SHA-256이 `99dcf19`와 같았다. DOC 3개와 PPT 12개에서는 손상 속성·알 수 없는 코드 페이지·OLE 복구 경고 때문에 오류 목록이 달라졌다. 0바이트 속성 스트림은 경고 없이 건너뛴다. 암호가 필요한 문서는 기존 본문 성공 경로에 도달하기 전 속성을 내지 않는다. 리뷰 반영 표본·위치·한계의 상세 기록은 [별도 검증 기록](2026-10-04-legacy-docprops-fix-real-docs.md)에 있다.

암호 계약은 POI·Tika의 공개 DOC 4개와 PPT 6개로 별도 확인했다. 암호 없이 본문을 열지 못한 10개 모두 섹션과 속성 문단이 0개였다. `testWORD_protected_drm.doc`는 기존 리더에서 오류 없이 본문을 읽는 별개 표본이므로 이 집계에 넣지 않았다.

XLS는 POI 417개와 LibreOffice 303개의 변경 전후 Markdown 및 JSON 전체 출력 SHA-256이 모두 같았다. 오류 목록과 속성 문단도 720개 모두 같았다. XLS 공용 파서 전환 시에도 기존 손상 속성의 경고 정책을 보존했다.
