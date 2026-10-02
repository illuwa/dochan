# legacy Office 변경 전 기준선

2026년 10월 2일 Apache POI `test-data/document`, `slideshow`, `spreadsheet`의 같은 NFC 줄기 이름인 DOC/DOCX, PPT/PPTX, XLS/XLSX 짝 전체를 측정했다. 기준 리더 커밋은 `6a63a590a04f6718b957f1604f0f6a16557321b6`이다. 이 작업은 리더 본체와 공유 모델을 바꾸지 않았으므로 아래 수치는 공용 OfficeArt를 리더에 연결하기 전의 출력 기준선이다. 표본과 구현 소스는 저장소에 복사하지 않았다.

## 측정 계약

두 파일을 `Dochan`으로 읽고 OOXML 출력을 정답으로 삼았다. 토큰 유사도는 NFC·공백 정규화 후 `SequenceMatcher(autojunk=False)`의 순서 유사도이다. 그림 자산, 주석, 머리글, 메타데이터, 발표자 노트가 plain text에 포함되는 기존 출력도 그대로 비교했다. 따라서 파일 자체가 같은 문서여도 현재 리더의 누락·잡음·서식 숫자 변환 때문에 토큰 유사도가 낮을 수 있다. 이 값은 문서 동일성을 증명하는 값이 아니다.

`metrics`는 정답 수, legacy 수, 다중집합 일치 수, 정답 수를 분모로 한 회수율을 기록한다. 정답 수가 0이면 모든 회수율과 텍스트 유사도는 null이다. 같은 개념의 후보 추가 출력은 legacy 수에 드러나며 회수율만으로 과잉 출력을 판정하지 않는다. URL은 집합 회수율과 Jaccard, 집합 완전 일치 여부를 추가로 기록한다.

표는 행·열 수와 병합 span 다중집합이 같은 경우에 구조 일치로 센다. 셀은 병합으로 가려진 셀을 제외하고 빈 셀까지 포함하며 정규화된 텍스트의 다중집합으로 비교한다. 병합 셀은 각 표 안의 행·열 좌표와 row_span/col_span을 비교한다. 인접한 같은 bold/italic 런은 합친 뒤 정규화 텍스트와 두 서식 플래그로 비교하며, 누락된 문장의 런도 정답 분모에 포함한다.

이미지는 Image 모델의 배치 수에 Image 모델이 없는 자산 참조를 더해 센다. 별도로 고유 자산 참조 수와 바이트가 있는 Image 수를 기록한다. 같은 그림을 여러 위치에 쓴 경우 배치 수와 고유 참조 수가 다르다. 대체 텍스트는 Image.alt_text의 비어 있지 않은 값을 센다. AssetRef.label은 원본 파일명이나 기본 라벨일 수 있어 대체 텍스트로 간주하지 않는다.

각주·미주·머리글·바닥글은 기존 모델을 읽는다. 주석은 Footnote/Comment와 기존 PPT(X)/XLS(X)의 `[comment: ...]` 출력 표기를 읽고, legacy PPT의 `#comments` 출처도 확인한다. 책갈피는 기존 `[bookmark: ...]` 표기를 읽는다. 발표자 노트는 `notesSlides/` 또는 `#notes` 출처의 문단을 슬라이드별로 모으며 생성된 Notes 제목은 제외한다. 차트는 출력 요소·캡션에 붙은 charts/*.xml 또는 #chart 출처의 고유 경로 수이다. 원본에 차트가 있어도 리더 출력 요소가 전혀 없으면 복원 개수는 0이다.

모델 순환·깊이 32·노드 1,000,000개를 제한한다. 토큰 수가 어느 쪽이든 20,000개를 넘으면 토큰 유사도는 null이고 `token_limit_exceeded`를 기록한다. 이 코퍼스에는 이 한도를 넘는 짝이 없었다. ERR가 있는 짝은 원시 JSON에 모든 지표·경고를 남기지만 정상 집계에서 제외한다. 단순 WARN만 있는 짝은 집계한다.

## 전체 기준선

57쌍 중 51쌍을 오류 없이 측정했다. 나머지 6쌍은 모두 XLS COLINFO 범위 오류를 보고했다. 평균 토큰 유사도는 0.5402, 중앙값은 0.6102, 최소는 0.0000, 최대는 0.9589이다. 이 원시 기준선에는 이름만 같은 것으로 확인한 짝도 보존했다.

| 형식 | 전체 짝 | 정상 집계 | ERR 짝 | 평균 토큰 유사도 |
|---|---:|---:|---:|---:|
| DOC | 13 | 13 | 0 | 0.7234 |
| PPT | 8 | 8 | 0 | 0.3129 |
| XLS | 36 | 30 | 6 | 0.5215 |

| 지표 | OOXML 정답 수 | legacy 수 | 일치 수 | 회수율 | 분모가 있는 짝 |
|---|---:|---:|---:|---:|---:|
| alt_text | 24 | 0 | 0 | 0.0000 | 2 |
| bookmarks | 0 | 0 | 0 | null | 0 |
| cells | 4298 | 4539 | 3350 | 0.7794 | 32 |
| charts | 7 | 0 | 0 | 0.0000 | 4 |
| comments | 3 | 3 | 0 | 0.0000 | 1 |
| endnotes | 0 | 0 | 0 | null | 0 |
| footers | 11 | 0 | 0 | 0.0000 | 7 |
| footnotes | 0 | 0 | 0 | null | 0 |
| format_runs | 2758 | 2594 | 1072 | 0.3887 | 51 |
| headers | 12 | 0 | 0 | 0.0000 | 8 |
| hyperlinks | 16 | 0 | 0 | 0.0000 | 2 |
| image_bytes | 24 | 0 | 0 | 0.0000 | 2 |
| image_references | 12 | 0 | 0 | 0.0000 | 2 |
| images | 24 | 0 | 0 | 0.0000 | 2 |
| merged_cells | 35 | 32 | 32 | 0.9143 | 3 |
| sheets | 74 | 73 | 73 | 0.9865 | 30 |
| slides | 82 | 84 | 79 | 0.9634 | 8 |
| speaker_notes | 42 | 8 | 0 | 0.0000 | 3 |
| tables | 57 | 82 | 38 | 0.6667 | 32 |

## 이름만 같은 짝을 거르는 기준

유사도 분포의 가장 낮은 두 양수 수준은 0.0350877과 0.0540541이다. 그 사이의 실측 중간값 0.0445708867보다 낮은 짝은 원문 확인 대상으로 표시하는 기준을 정했다. 아래 6쌍이 해당한다. 이 경계는 분포에서 가져온 검토 기준이며 명세의 수치나 문서 동일성 판정 규칙이 아니다.

| 확인 대상 | 토큰 유사도 | 선택과 근거 |
|---|---:|---|
| `documentProperties.doc` / `.docx` | 0.0000 | 내용이 다른 짝으로 확인했다. DOC 본문은 `This is document text`이며 OOXML word/document.xml의 w:t는 `Hello World`, `!`이다. 큐레이션 집계에서만 명시적으로 제외한다. |
| `SimpleMultiCell.xls` / `.xlsx` | 0.0000 | 제외하면 안 된다. XLS RK의 첫 상위 IEEE 754 워드가 0x3FF00000으로 1.0이며 이어지는 15개 값은 1부터 15이다. OOXML의 15개 v 값도 1부터 15이다. 현재 XLS 출력은 RK 값을 작은 비정상 실수로 복원한다. 동일 문서의 리더 결손으로 남긴다. |
| `51921-Word-Crash067.doc` / `.docx` | 0.0000 | DOC가 바이너리 잡음을 출력한다. 문서 동일성은 미확정이며 자동 제외하지 않는다. |
| `table_test.ppt` / `.pptx` | 0.0000 | PPT는 내부 마커를 출력하고 PPTX는 빈 표와 메타데이터를 출력한다. 문서 동일성은 미확정이며 자동 제외하지 않는다. |
| `49928.xls` / `.xlsx` | 0.0000 | 숫자·통화 서식 차이가 있다. 문서 동일성은 미확정이며 자동 제외하지 않는다. |
| `backgrounds.ppt` / `.pptx` | 0.0351 | 낮은 출력 유사도만 확인했다. 문서 동일성은 미확정이며 자동 제외하지 않는다. |

동일 문서인 `SimpleMultiCell`과 다른 문서인 `documentProperties`가 모두 0이므로 토큰 유사도만으로 안전하게 자동 제외할 단일 임계값은 이번 실측에서 성립하지 않는다. 같은 핵심 문구가 있는 `SampleShow`도 legacy master·내부 마커 잡음 때문에 0.6429에 그쳤다. 따라서 기본 측정기는 필터를 강제하지 않는다. `--min-token-ratio`는 원하는 유사도 구간의 보조 집계에만 사용하며, 다른 문서로 확인한 짝은 `--exclude-pair documentProperties.doc`로 제외한다. 원시 JSON에는 제외한 짝도 그대로 남는다.

내용 차이를 확인한 `documentProperties` 1쌍만 제외하면 정상 집계는 50쌍이고 평균 토큰 유사도는 0.5510이다. 나머지 저유사도 짝을 성능 수치를 높이기 위해 삭제하지 않았다. 각주·미주·북마크는 정상 집계 OOXML의 분모가 0이어서 null이며 지원 판정을 내릴 수 없다.

## 전체 짝 목록

아래 이름은 POI 공개 표본 이름이다. 같은 줄기에 대응 확장자 docx/pptx/xlsx를 붙인 파일이 정답이다. ERR가 있는 짝도 유사도 원시값을 기록하되 정상 집계에서 제외했다.

| legacy 공개 파일 | OOXML 공개 파일 | 토큰 유사도 | 집계 상태 |
|---|---|---:|---|
| `51921-Word-Crash067.doc` | `51921-Word-Crash067.docx` | 0.0000 | 원시 기준선에 포함했다. |
| `DiffFirstPageHeadFoot.doc` | `DiffFirstPageHeadFoot.docx` | 0.7152 | 원시 기준선에 포함했다. |
| `FancyFoot.doc` | `FancyFoot.docx` | 0.9474 | 원시 기준선에 포함했다. |
| `HeaderFooterUnicode.doc` | `HeaderFooterUnicode.docx` | 0.8586 | 원시 기준선에 포함했다. |
| `NoHeadFoot.doc` | `NoHeadFoot.docx` | 0.9589 | 원시 기준선에 포함했다. |
| `PageSpecificHeadFoot.doc` | `PageSpecificHeadFoot.docx` | 0.7755 | 원시 기준선에 포함했다. |
| `SampleDoc.doc` | `SampleDoc.docx` | 0.9254 | 원시 기준선에 포함했다. |
| `SimpleHeadThreeColFoot.doc` | `SimpleHeadThreeColFoot.docx` | 0.8034 | 원시 기준선에 포함했다. |
| `ThreeColFoot.doc` | `ThreeColFoot.docx` | 0.9109 | 원시 기준선에 포함했다. |
| `ThreeColHead.doc` | `ThreeColHead.docx` | 0.8515 | 원시 기준선에 포함했다. |
| `ThreeColHeadFoot.doc` | `ThreeColHeadFoot.docx` | 0.8235 | 원시 기준선에 포함했다. |
| `capitalized.doc` | `capitalized.docx` | 0.8333 | 원시 기준선에 포함했다. |
| `documentProperties.doc` | `documentProperties.docx` | 0.0000 | 원시 기준선에 포함했고 큐레이션에서 제외했다. |
| `SampleShow.ppt` | `SampleShow.pptx` | 0.6429 | 원시 기준선에 포함했다. |
| `WithMaster.ppt` | `WithMaster.pptx` | 0.3733 | 원시 기준선에 포함했다. |
| `alterman_security.ppt` | `alterman_security.pptx` | 0.0858 | 원시 기준선에 포함했다. |
| `backgrounds.ppt` | `backgrounds.pptx` | 0.0351 | 원시 기준선에 포함했다. |
| `bug58144-headers-footers-2007.ppt` | `bug58144-headers-footers-2007.pptx` | 0.4308 | 원시 기준선에 포함했다. |
| `bug60993.ppt` | `bug60993.pptx` | 0.4762 | 원시 기준선에 포함했다. |
| `customGeo.ppt` | `customGeo.pptx` | 0.4589 | 원시 기준선에 포함했다. |
| `table_test.ppt` | `table_test.pptx` | 0.0000 | 원시 기준선에 포함했다. |
| `48703.xls` | `48703.xlsx` | 0.0541 | 원시 기준선에 포함했다. |
| `49928.xls` | `49928.xlsx` | 0.0000 | 원시 기준선에 포함했다. |
| `52575_main.xls` | `52575_main.xlsx` | 0.2667 | 원시 기준선에 포함했다. |
| `53798_shiftNegative_TMPL.xls` | `53798_shiftNegative_TMPL.xlsx` | 0.1111 | 원시 기준선에 포함했다. |
| `54206.xls` | `54206.xlsx` | 0.5587 | ERR로 제외했다. |
| `55906-MultiSheetRefs.xls` | `55906-MultiSheetRefs.xlsx` | 0.7200 | 원시 기준선에 포함했다. |
| `56737.xls` | `56737.xlsx` | 0.7179 | 원시 기준선에 포함했다. |
| `57798.xls` | `57798.xlsx` | 0.6667 | 원시 기준선에 포함했다. |
| `59264.xls` | `59264.xlsx` | 0.9032 | 원시 기준선에 포함했다. |
| `AmpersandHeader.xls` | `AmpersandHeader.xlsx` | 0.6667 | 원시 기준선에 포함했다. |
| `ConditionalFormattingSamples.xls` | `ConditionalFormattingSamples.xlsx` | 0.4791 | ERR로 제외했다. |
| `ForShifting.xls` | `ForShifting.xlsx` | 0.8340 | 원시 기준선에 포함했다. |
| `FormatChoiceTests.xls` | `FormatChoiceTests.xlsx` | 0.5969 | ERR로 제외했다. |
| `FormatKM.xls` | `FormatKM.xlsx` | 0.4823 | 원시 기준선에 포함했다. |
| `Formatting.xls` | `Formatting.xlsx` | 0.6102 | 원시 기준선에 포함했다. |
| `FormulaSheetRange.xls` | `FormulaSheetRange.xlsx` | 0.6071 | 원시 기준선에 포함했다. |
| `MatrixFormulaEvalTestData.xls` | `MatrixFormulaEvalTestData.xlsx` | 0.6784 | 원시 기준선에 포함했다. |
| `NewStyleConditionalFormattings.xls` | `NewStyleConditionalFormattings.xlsx` | 0.6900 | 원시 기준선에 포함했다. |
| `RepeatingRowsCols.xls` | `RepeatingRowsCols.xlsx` | 0.3040 | 원시 기준선에 포함했다. |
| `SampleSS.xls` | `SampleSS.xlsx` | 0.8354 | 원시 기준선에 포함했다. |
| `ShrinkToFit.xls` | `ShrinkToFit.xlsx` | 0.8889 | 원시 기준선에 포함했다. |
| `SimpleMultiCell.xls` | `SimpleMultiCell.xlsx` | 0.0000 | 원시 기준선에 포함했다. |
| `SimpleScatterChart.xls` | `SimpleScatterChart.xlsx` | 0.3846 | 원시 기준선에 포함했다. |
| `SimpleWithComments.xls` | `SimpleWithComments.xlsx` | 0.4286 | 원시 기준선에 포함했다. |
| `Themes2.xls` | `Themes2.xlsx` | 0.9109 | 원시 기준선에 포함했다. |
| `TwoSheetsNoneHidden.xls` | `TwoSheetsNoneHidden.xlsx` | 0.5714 | 원시 기준선에 포함했다. |
| `TwoSheetsOneHidden.xls` | `TwoSheetsOneHidden.xlsx` | 0.5714 | 원시 기준선에 포함했다. |
| `WithChart.xls` | `WithChart.xlsx` | 0.3692 | 원시 기준선에 포함했다. |
| `WithConditionalFormatting.xls` | `WithConditionalFormatting.xlsx` | 0.6500 | 원시 기준선에 포함했다. |
| `WithThreeCharts.xls` | `WithThreeCharts.xlsx` | 0.2840 | 원시 기준선에 포함했다. |
| `WithTwoCharts.xls` | `WithTwoCharts.xlsx` | 0.3919 | 원시 기준선에 포함했다. |
| `atp.xls` | `atp.xlsx` | 0.7368 | 원시 기준선에 포함했다. |
| `comments.xls` | `comments.xlsx` | 0.5000 | ERR로 제외했다. |
| `resize_compare.xls` | `resize_compare.xlsx` | 0.7273 | ERR로 제외했다. |
| `shared_formulas.xls` | `shared_formulas.xlsx` | 0.3098 | 원시 기준선에 포함했다. |
| `tile-range-test.xls` | `tile-range-test.xlsx` | 0.5676 | ERR로 제외했다. |

XLS 오류 짝은 `54206`, `ConditionalFormattingSamples`, `FormatChoiceTests`, `comments`, `resize_compare`, `tile-range-test`이다. 현재 legacy 리더가 끝 열 256을 포함하는 COLINFO를 범위 오류로 보고했다. 이를 이 작업에서 수정하거나 기존 테스트의 단언을 바꾸지 않았다.

## 재현 방법

```sh
/usr/bin/python3 -m scripts.compare_office_pairs \
  /Users/illuwa/dev/personal/dochan/corpus/poi-src/test-data/document \
  /Users/illuwa/dev/personal/dochan/corpus/poi-src/test-data/slideshow \
  /Users/illuwa/dev/personal/dochan/corpus/poi-src/test-data/spreadsheet \
  --output .codex-work/legacy-office-baseline.json
```

내용 차이가 확인된 짝만 제외한 보조 집계는 같은 명령에 `--exclude-pair documentProperties.doc`를 덧붙인다. 합성 단위 테스트는 `tests/test_compare_office_pairs_script.py`이며 분모 0, 다중집합·서식 런, 표 안 요소, 이미지 자산 중복, 여러 줄 주석, CLI JSON, 오류 보존, 순환 모델, 명시적 제외를 검증한다.
