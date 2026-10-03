# XLS와 XLSX 출력 차이 실물 검증

2026년 10월 4일 공개 Apache POI의 같은 이름 XLS/XLSX 36쌍을 현재 리더로 비교했다. XLSX 출력은 비교 정답으로 사용하되, 두 원본 파일의 내용이 다른 경우에는 XLSX를 XLS의 바이트보다 우선하지 않았다. 구현 근거는 [MS-XLS]의 BLANK·MULBLANK·DIMENSION·ROW·COLINFO·Lbl·ARRAY·FORMULA 레코드, [MS-OLEPS]의 SummaryInformation 속성 집합과 공개 파일 바이트이다. 다른 프로젝트의 구현 코드는 보지 않았다.

## 칸별 실물 검증

| 칸 | 표본 파일(POI 공개 파일명) | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| XLS 표 끝 빈 행·열 | `57798.xls`, `ShrinkToFit.xls` | 동명 XLSX의 표 크기는 각각 2행 2열과 1행 1열이다. XLS의 추가 좌표에는 BLANK·ROW·COLINFO·DIMENSION만 있고 표시 내용은 없다. | 셀 좌표 사이의 빈 칸은 보존하고 끝 빈 행·열은 잘라낸다. | 각각 2행 2열과 1행 1열이 되었으며 XLSX의 표와 일치했다. | 통과했다. |
| XLS 표 끝 빈 행·열 | `ConditionalFormattingSamples.xls` | 동명 XLSX의 공통 시트 16개와 XLS의 DIMENSION·BLANK를 대조했다. | 끝의 빈 열 때문에 255열로 커진 표를 실제 내용 범위로 줄인다. | 공통 시트의 15개 표 구조가 일치했다. 나머지 한 표는 원본 행 내용 차이로 13행과 12행이다. XLSX에만 있는 시트 두 개는 복원하지 않았다. | 범위 수정은 통과했고 문서 전체 일치는 미달이다. |
| XLS 문서 속성 | `57798.xls`, `ShrinkToFit.xls`, `SampleSS.xls` | OLE `SummaryInformation`의 속성 ID 2(제목)·4(작성자), 동명 XLSX `docProps/core.xml` 출력이다. | 제목은 `# 제목`, 작성자는 `Author: 작성자`로 시트 제목 앞에 낸다. | 세 표본에서 제목·작성자와 순서가 일치했다. 36쌍 중 양쪽에 속성이 있는 31쌍에서 30쌍이 같았다. | 통과했다. `48703`의 작성자 차이는 원본 속성값 차이이다. |
| XLS 숨김·내부 정의 이름 | `ConditionalFormattingSamples.xls` | 원시 NAME 옵션값 `0x000b`의 숨김 비트와 `_xlfn.COUNTIFS` 이름, 동명 XLSX의 정의 이름 출력이다. | 해당 미래 함수 자리표시자는 본문에 내지 않는다. | `Defined name: _xlfn.COUNTIFS = #NAME?`가 사라지고 보이는 이름은 유지됐다. | 통과했다. |
| XLS 배열 수식의 후속 셀 | `57798.xls` | XLS의 ARRAY 범위 B1:B2, 두 FORMULA의 문자열 캐시 `one`, XLSX의 B1 수식·B2 캐시만 있는 셀이다. | B1은 `one (=A1)`, B2는 `one`으로 낸다. | 두 셀과 문서 Markdown 전체가 동명 XLSX와 일치했다. | 통과했다. |

`57798.xls`의 B2에도 FORMULA와 PtgExp가 있다. 이는 B1의 배열 수식 범위 안에서 후속 셀이 캐시를 담는 레코드이므로, B2를 독립 수식으로 다시 표시하지 않았다. XLSX의 B2에는 `<f>`가 없고 문자열 캐시만 있다. 이 판단은 수식을 없애기 위한 파일명별 예외가 아니라 배열 범위와 셀 역할에 따른 것이다.

## 전체 짝 지표

동일 이름의 DOC/DOCX·PPT/PPTX·XLS/XLSX 전체 57쌍에서 파싱 실패는 전후 모두 0건이다. 전체 표 구조 일치는 54/83에서 75/83으로, 전체 셀 일치는 7,558/7,958에서 7,779/7,958으로 바뀌었다. 전체 평균 토큰 유사도는 0.7983에서 0.8581로 올랐다. 이 변화는 XLS 리더와 XLS 시트 전제 문단의 출력 변경에서 왔다.

XLS 36쌍만 보면 표 구조 일치는 51/79에서 72/79로, 셀 일치는 7,518/7,896에서 7,739/7,896으로, 평균 토큰 유사도는 0.8320에서 0.9266으로 바뀌었다. Markdown 전문이 완전히 같은 짝은 3쌍에서 23쌍이 됐다. 토큰 유사도와 표 구조 일치는 서로 다른 측정이며, 남은 원본 차이를 오류로 단정하지 않는다.

## 남은 XLS/XLSX 짝 불일치의 원인

다음 13쌍은 수정 후에도 Markdown 전문이 다르다. 공통 원인 중 하나만 적지 않고 해당 표본에서 확인한 주된 차이를 적었다. 나머지 23쌍은 전문이 일치한다.

| 공개 XLS 파일 | 수정 후 토큰 유사도 | 확인한 주된 원인 |
| --- | ---: | --- |
| `48703.xls` | 0.1000 | 작성자가 서로 다르고 XLS는 3시트·XLSX는 4시트이며 표 내용도 다르다. 같은 이름의 다른 원본이다. |
| `52575_main.xls` | 0.5556 | 외부 워크북 경로의 수식 표기와 캐시 값이 다르다. 양쪽 표 크기와 작성자는 같다. |
| `56737.xls` | 0.8571 | `IF` 수식의 쉼표와 연산자 주변 공백만 다르다. |
| `AmpersandHeader.xls` | 0.9333 | 동일 머리글 텍스트를 XLSX는 `<!-- header: … -->`, XLS는 `Header: …`로 표시한다. |
| `ConditionalFormattingSamples.xls` | 0.9387 | XLSX는 18시트, XLS는 16시트다. XLS Home에는 Obj·TxO 각 17개가 있어 텍스트박스 원문이 있으나 현 XLS 출력은 본문 1문단만 낸다. XLSX는 Home 문단 18개를 내며 두 추가 시트의 표와 다른 시트의 텍스트박스도 낸다. 공통 `Regional sales` 표는 13행과 12행으로 다르다. |
| `FormatChoiceTests.xls` | 0.6854 | XLS에만 `Debug` 플래그와 `Basic, Debug` 값이 있고 여러 수식의 표시 공백·캐시가 다르다. 두 형식의 Tests 표 크기는 같다. |
| `FormatKM.xls` | 0.9878 | XLSX의 한 숫자 캐시는 `10.199999999999999`, XLS의 저장·표시값은 `10.2`이다. |
| `MatrixFormulaEvalTestData.xls` | 0.9949 | 배열 수식 두 곳에서 `B2:D4 + E2:G4`와 `B2:D4+E2:G4`처럼 공백만 다르다. |
| `RepeatingRowsCols.xls` | 0.9545 | 같은 Print_Titles 범위를 XLSX는 `$1:$1`·`$A:$A`, XLS는 `$A$1:$IV$1`·`$A$1:$A$65536`으로 펼쳐 쓴다. |
| `SimpleScatterChart.xls` | 0.9643 | XLSX 차트 제목 `Y` 문단 두 개가 XLS 본문에는 없다. 계열 데이터 표 세 개의 구조는 일치한다. |
| `comments.xls` | 0.6111 | XLS 원본에는 NOTE 세 개, XLSX에는 주석 하나만 있다. 공통 주석 하나는 일치하고 XLS에만 있는 두 메모가 추가 출력된다. |
| `resize_compare.xls` | 0.8571 | 그림 두 개의 자산 경로·배치 출력이 두 리더에서 다르다. 본문 표 구조는 일치한다. |
| `tile-range-test.xls` | 0.9189 | XLS에는 머리글 `sheet`와 바닥글 `Page #`가 있고 XLSX는 바닥글을 주석 표기로 낸다. |

`ConditionalFormattingSamples`의 670행 대 560행 차이는 수정 후 670행 대 531행이다. 기존 XLS의 과도한 빈 격자를 잘라 행 수가 더 줄었다. 누락된 두 시트와 TxO 텍스트박스는 이번 범위 정리로 해결되지 않았으며, 따라서 이 짝의 토큰 유사도 상승만으로 완전성을 주장하지 않는다.

## 공개 XLS 전수 Markdown 변경

POI 417개와 LibreOffice 303개, 총 720개를 파일마다 Markdown SHA-256·문자 수·오류 목록과 모델 요약만 기록해 전후 비교했다. 460개(POI 319개, LibreOffice 141개)의 Markdown이 바뀌었다. 속성 문단이 바뀐 파일은 319개, 표 격자가 바뀐 파일은 224개, 정의 이름 문단이 바뀐 파일은 56개, 비어 있지 않은 표 셀 텍스트 해시가 바뀐 파일은 16개다. 한 파일은 여러 원인을 가질 수 있다. 시트 전제 문단의 순서만 바뀐 파일은 15개다. 나머지 260개는 Markdown 해시가 같다.

비어 있지 않은 셀 텍스트가 바뀐 16개는 배열 수식 후속 셀의 중복 수식 표기를 제거한 파일이다. 대표적인 격자와 셀 변화가 함께 있는 다섯 함수 표본에서는 비어 있지 않은 셀 개수가 전후 같았다. 아래 목록은 파일마다 구조적으로 확인된 변화 종류를 모두 표시한다. 이는 각 파일의 의미상 정답 일치를 보장하는 판정이 아니다.

새 ERR와 프로브 예외는 없었다. 손상·퍼징 표본 네 개에서 SummaryInformation의 잘못된 길이 또는 내용을 알리는 WARN이 추가됐다. 기존 `docs/benchmarks/`의 수치는 각 작업 당시 커밋의 측정 기록이므로 덮어쓰지 않았고, 현행 전후 수치는 이 문서에 별도로 기록했다.

전수 재현은 `python -m scripts.probe_xls_parity corpus/poi-src/test-data/spreadsheet corpus/lo-src --output <결과.json>`으로 한다. 짝 측정은 `python -m scripts.compare_office_pairs corpus/poi-src/test-data/document corpus/poi-src/test-data/slideshow corpus/poi-src/test-data/spreadsheet --output <결과.json>`으로 한다. 검사 스크립트는 문서별 Markdown 전문을 디스크에 저장하지 않는다.

합성 회귀 테스트를 포함한 전체 `python -m pytest tests/` 결과는 5,213개 통과, 36개 건너뜀, 14개 예상 실패이다. `ruff check dochan scripts tests`도 통과했다.

### 변경 파일 목록

아래의 `속성`, `격자`, `이름`, `셀`, `순서`는 각각 OLE 속성 출력, 표 행·열 크기, 정의 이름 문단, 비어 있지 않은 셀 텍스트 해시, 시트 전제 문단 배치의 변경을 뜻한다. 파일 경로는 공개 코퍼스 루트 아래의 상대 경로이다.

| 공개 코퍼스 파일 | 변경 종류 |
| --- | --- |
| `corpus/lo-src/sc/qa/unit/data/xls/XlStartupExternal.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/array_formula_with_macros.xls` | 셀 |
| `corpus/lo-src/sc/qa/unit/data/xls/bug-fixes.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/cell-anchored-group.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/cell-borders.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/cell-multi-line.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/data-table/mortgage.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/database.xls` | 속성·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/embedded-chart.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/emptyAnchor.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/enhanced-protection.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/external-ref.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/external_named_function.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/file-with-png-image.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/formats.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/formula-reference.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/formula_with_macros.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/forum-en-29552.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/forum-fr-59757.xls` | 순서 |
| `corpus/lo-src/sc/qa/unit/data/xls/forum-mso-de-37362.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/forum-mso-de-48440.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/forum-mso-de-49320.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/forum-mso-en4-102737.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/forum-mso-en4-109082.xls` | 속성·격자·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/forum-mso-en4-147004.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/forum-mso-en4-243595.xls` | 속성·격자·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/forum-mso-en4-258437.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/forum-mso-en4-368528.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/inline-array.xls` | 속성·셀 |
| `corpus/lo-src/sc/qa/unit/data/xls/matrix.xls` | 속성·셀 |
| `corpus/lo-src/sc/qa/unit/data/xls/named-ranges-global.xls` | 속성·셀 |
| `corpus/lo-src/sc/qa/unit/data/xls/named-ranges-local.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/database/dvar.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/Fvschedule.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/IRR.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/MDuration1.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/MIRR.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/NPER.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/NPER1.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/NPV.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/Nominal.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/Oddlprice.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/Oddlyield.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/PMT.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/PPMT.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/Price.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/PriceDisc.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/RRI.xls` | 이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/XNPV.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/financial/general.xls` | 격자·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/logical/not.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/logical/or.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/logical/xor.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/MROUND.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/averageif.xls` | 속성·격자·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/averageif_mix.xls` | 이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/averageifs.xls` | 속성·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/combina.xls` | 격자·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/convert.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/cos.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/cosh.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/countifs.xls` | 속성·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/even.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/mod.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/odd.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/pi.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/random.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/sinh.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/sumifs.xls` | 속성·격자·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/sumproductTest.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/math/sumsq.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/AverageA.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/B.xls` | 이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/Covar.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/DevSq.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/Expondist.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/Fisher.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/FisherInv.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/Gamma.xls` | 격자·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/GammaLn.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/Gauss.xls` | 격자·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/GeoMean.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/HarMean.xls` | 순서 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/HarMean1.xls` | 순서 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/HypGeomDist.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/Kurt1.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/LogInv.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/Permutation.xls` | 속성·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/Phi.xls` | 이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/Poisson.xls` | 순서 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/Skewp.xls` | 이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/StDevA1.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/StDevPA1.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/Var.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/VarA.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/VarA1.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/VarP.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/VarPA.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/VarPA1.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/opencl/statistical/ZTest.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pass/crash-6.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pass/crash-7.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pass/forcepoint-pivot-1.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/pass/forcepoint-selfseriesadd.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/pass/ooo47086-1.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/pass/ooo56295-1.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/pass/ooo956-3.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pictureOrder.xls` | 속성·격자·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivot-getpivotdata.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivottable_bool_field_filter.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivottable_date_field_filter.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivottable_dates_grouping.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivottable_double_field_filter.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivottable_empty_item.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivottable_ext_grouping.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivottable_ext_source_fields.xls` | 속성·격자·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivottable_number_grouping.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivottable_page_field_filter.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivottable_rowcolpage_field_filter.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/pivottable_string_field_filter.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/shared-formula/basic.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/shared-formula/biff5.xls` | 이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/shared-formula/gap.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/shared-formula/horizontal.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/shared-formula/relative-refs1.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/shared-formula/relative-refs2.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/shared-formula/wrapped-refs.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/shared-string/literal-in-formula.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/systematic.xls` | 속성·이름 |
| `corpus/lo-src/sc/qa/unit/data/xls/tdf112501.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/tdf120177.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/tdf128976.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/tdf165080.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/tdf170285_controlsInGroupShape.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/tdf171083.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/tdf79542_radioGroupBox.xls` | 격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/tdf81470.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/track-changes/simple-cell-changes.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/universal-content.xls` | 속성 |
| `corpus/lo-src/sc/qa/unit/data/xls/user_defined_function.xls` | 속성·격자 |
| `corpus/lo-src/sc/qa/unit/data/xls/validation.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/12561-1.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/12561-2.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/12843-1.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/12843-2.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/13224.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/14330-2.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/14460.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/15228.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/15375.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/15556.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/1900DateWindowing.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/1904DateWindowing.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/19599-1.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/19599-2.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/24215.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/25183.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/25695.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/26100.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/27272_1.xls` | 속성·이름 |
| `corpus/poi-src/test-data/spreadsheet/27272_2.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/27349-vlookupAcrossSheets.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/27852.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/27933.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/28772.xls` | 순서 |
| `corpus/poi-src/test-data/spreadsheet/28774.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/29675.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/29942.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/29982.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/30540.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/30978-alt.xls` | 순서 |
| `corpus/poi-src/test-data/spreadsheet/30978-deleted.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/31749.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/31979.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/32822.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/33082.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/34775.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/35564.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/35565.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/36947.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/37376.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/37684-1.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/37684-2.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/37684.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/39512.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/39634.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/41139.xls` | 격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/42016.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/42464-ExpPtg-bad.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/42464-ExpPtg-ok.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/42844.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/43251.xls` | 격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/43493.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/43623.xls` | 속성·격자·셀 |
| `corpus/poi-src/test-data/spreadsheet/43902.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/44010-SingleChart.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/44010-TwoCharts.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/44167.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/44235.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/44297.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/44593.xls` | 속성·이름 |
| `corpus/poi-src/test-data/spreadsheet/44636.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/44693.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/44840.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/44861.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/44891.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/44958.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/44958_1.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/45129.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/45365-2.xls` | 순서 |
| `corpus/poi-src/test-data/spreadsheet/45365.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/45492.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/45538_classic_Footer.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/45538_classic_Header.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/45538_form_Footer.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/45538_form_Header.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/45565.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/45672.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/45720.xls` | 이름 |
| `corpus/poi-src/test-data/spreadsheet/45761.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/45784.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/46137.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/46250.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/46368.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/46445.xls` | 격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/46515.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/46670_http.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/46670_local.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/46670_ref_airline.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/47034.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/47154.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/47245_test.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/47251.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/47701.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/47847.xls` | 격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/47920.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/47924.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/48026.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/48180.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/48703.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/49096.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/49185.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/49219.xls` | 격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/49237.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/49524.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/49529.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/49581.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/49751.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/49896.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/49928.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/49931.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/50020.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/50298.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/50756.xls` | 순서 |
| `corpus/poi-src/test-data/spreadsheet/50833.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/50939.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/51143.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/51262.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/51461.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/51535.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/51670.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/51675.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/52447.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/52527.xls` | 속성·격자·셀 |
| `corpus/poi-src/test-data/spreadsheet/52575_main.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/52575_source.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/53109.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/53433.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/53446.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/53588.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/53691.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/53798_shiftNegative_TMPL.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/53972.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/53984.xls` | 격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/54016.xls` | 속성·이름 |
| `corpus/poi-src/test-data/spreadsheet/54206.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/54686_fraction_formats.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/55341_CellStyleBorder.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/55668.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/55906-MultiSheetRefs.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/55982.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/56325.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/56325a.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/56450.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/56563a.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/56563b.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/56737.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/57003-FixedFunctionTestCaseData.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/57074.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/57231_MixedGasReport.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/57456.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/57798.xls` | 속성·격자·셀 |
| `corpus/poi-src/test-data/spreadsheet/57925.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/59264.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/59830.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/59858.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/60273.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/60405.xls` | 순서 |
| `corpus/poi-src/test-data/spreadsheet/60460.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/61116.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/AmpersandHeader.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/AreaErrPtg.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/BOOK_in_capitals.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/Basic_Expense_Template_2011.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/BooleanFunctionsTestCaseData.xls` | 격자·셀 |
| `corpus/poi-src/test-data/spreadsheet/CodeFunctionTestCaseData.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/ColumnStyle1dp.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/ColumnStyle1dpColoured.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/ColumnStyleNone.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/ComplexFunctionTestCaseData.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/ConditionalFormattingSamples.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/ContinueRecordProblem.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/DBCSHeader.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/DBCSSheetName.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/DGet.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/DStar.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/DateFormats.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/DateTimeToNumberTestCases.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/DeltaFunctionTestCaseData.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/DrawingAndComments.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/DrawingContinue.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/EmbeddedChartHeaderTest.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/Employee.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/ErrPtg.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/FactDoubleFunctionTestCaseData.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/ForShifting.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/FormatChoiceTests.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/FormatKM.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/Formatting.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/FormulaEvalTestData.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/FormulaRefs.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/FormulaSheetRange.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/HyperlinksOnManySheets.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/IfFormulaTest.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/IfFunctionTestCaseData.xls` | 격자·셀 |
| `corpus/poi-src/test-data/spreadsheet/IfNaTestCaseData.xls` | 이름 |
| `corpus/poi-src/test-data/spreadsheet/ImRealFunctionTestCaseData.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/ImaginaryFunctionTestCaseData.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/IndexFunctionTestCaseData.xls` | 순서 |
| `corpus/poi-src/test-data/spreadsheet/IndirectFunctionTestCaseData.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/Intersection-52111.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/IntersectionPtg.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/IrrNpvTestCaseData.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/LogicalFunctionsTestCaseData.xls` | 격자·셀 |
| `corpus/poi-src/test-data/spreadsheet/MRExtraLines.xls` | 순서 |
| `corpus/poi-src/test-data/spreadsheet/MatchFunctionTestCaseData.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/MatrixFormulaEvalTestData.xls` | 속성·셀 |
| `corpus/poi-src/test-data/spreadsheet/NewStyleConditionalFormattings.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/NoGutsRecords.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/OddStyleRecord.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/PercentPtg.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/QuotientFunctionTestCaseData.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/RangePtg.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/ReadOnlyRecommended.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/RepeatingRowsCols.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/ReptFunctionTestCaseData.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/RomanFunctionTestCaseData.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/RowFunctionTestCaseData.xls` | 격자·셀 |
| `corpus/poi-src/test-data/spreadsheet/SampleSS.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SharedFormulaTest.xls` | 순서 |
| `corpus/poi-src/test-data/spreadsheet/SheetWithDrawing.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/ShrinkToFit.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/Simple.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SimpleChart.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SimpleMacro.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SimpleMultiCell.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SimpleScatterChart.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SimpleWithAutofilter.xls` | 속성·이름 |
| `corpus/poi-src/test-data/spreadsheet/SimpleWithChoose.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SimpleWithColours.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SimpleWithDataFormat.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SimpleWithFormula.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SimpleWithPageBreaks.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/SimpleWithPrintArea.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SimpleWithSkip.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SimpleWithStyling.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SingleLetterRanges.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SolverContainerAfterSPGR.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SquareMacro.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/StringContinueRecords.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/StringFormulas.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/SubtotalsNested.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/Themes2.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/Trend.xls` | 속성·셀 |
| `corpus/poi-src/test-data/spreadsheet/TwoOperandNumericFunctionTestCaseData.xls` | 격자·셀 |
| `corpus/poi-src/test-data/spreadsheet/TwoSheetsNoneHidden.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/TwoSheetsOneHidden.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/UncalcedRecord.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/UnionPtg.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/WORKBOOK_in_capitals.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/WeekNumFunctionTestCaseData.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/WeekNumFunctionTestCaseData2013.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/WithChart.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/WithCheckBoxes.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/WithEmbeddedObjects.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/WithExtendedStyles.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/WithFormattedGraphTitle.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/WithHyperlink.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/WithThreeCharts.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/WithTwoCharts.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/WithTwoHyperLinks.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/WrongFormulaRecordType.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/XRefCalcData.xls` | 순서 |
| `corpus/poi-src/test-data/spreadsheet/angelo.edu_content_files_19555-nsse-2011-multiyear-benchmark.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/ar.org.apsme.www_Form%20Inscripcion%20Curso%20NO%20Socios.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/at.gv.land-oberoesterreich.www_cps_rde_xbcr_SID-4A1B954F-5C07F98E_ooe_stat_download_bp10.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/atp.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/blankworkbook.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/bug55505.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/bug66319.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/bug69021.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/bug_42794.xls` | 순서 |
| `corpus/poi-src/test-data/spreadsheet/cf9f845e73447b092477d0472402a5baea4b8c9f.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4977868385681408.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5285517825277952.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5436547081830400.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/com.aida-tour.www_SPO_files_maldives%20august%20october.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/crash-e329fca9087fe21bca4a80c8bc472a661c98d860.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/dg-text.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/drawings.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/duprich2.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/empty.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/ex42564-21435.xls` | 순서 |
| `corpus/poi-src/test-data/spreadsheet/ex42564-21503.xls` | 이름 |
| `corpus/poi-src/test-data/spreadsheet/ex42570-20305.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/ex44921-21902.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/ex45046-21984.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/ex45582-22397.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/ex45672.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/ex45698-22488.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/ex45978-extraLinkTableSheets.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/ex46548-23133.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/ex47747-sharedFormula.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/excel_with_embeded.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/excelant.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/externalFunctionExample.xls` | 격자 |
| `corpus/poi-src/test-data/spreadsheet/external_image.xls` | 속성·격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/external_name.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/finance.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/florida_data.ashx.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/intercept.xls` | 이름 |
| `corpus/poi-src/test-data/spreadsheet/maxindextest.xls` | 속성·이름 |
| `corpus/poi-src/test-data/spreadsheet/mirrTest.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/moodle.iamm.fr_pluginfile.php_2971_mod_resource_content_4_evaluation_module_decouverte_qesamed.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/mortgage-calculation.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/namedinput.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/ole2-embedding.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/rank.xls` | 격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/resize_compare.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/rk.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/shared_formulas.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/styles-3563.xls` | 속성·격자 |
| `corpus/poi-src/test-data/spreadsheet/sumifformula.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/sumifs.xls` | 격자·이름 |
| `corpus/poi-src/test-data/spreadsheet/templateExcelWithAutofilter.xls` | 속성·이름 |
| `corpus/poi-src/test-data/spreadsheet/testArraysAndTables.xls` | 셀 |
| `corpus/poi-src/test-data/spreadsheet/testRRaC.xls` | 이름 |
| `corpus/poi-src/test-data/spreadsheet/testRVA.xls` | 셀 |
| `corpus/poi-src/test-data/spreadsheet/text.xls` | 속성 |
| `corpus/poi-src/test-data/spreadsheet/unicodeNameRecord.xls` | 속성 |

## 감수 반영(2026-10-04)

- 숨은 정의 이름 제외를 되돌렸다. XLSX 리더는 `hidden="1"` 이름(`_FilterDatabase`, `SAPBEXdnldView` 등)도 내므로, XLS 에서 숨은 이름을 지우면 같은 통합문서의 두 형식이 오히려 달라진다(짝 없는 34파일에서 이름 271개가 사라질 뻔했다). `_xlfn.` 미래 함수 자리표시자만 뺀다(두 코퍼스의 어떤 XLSX 에도 `_xlfn.` 정의 이름이 없다). BIFF5 공개 이름 테스트의 원래 단언(`Sheet1!$A$5:$F$376`)을 되살렸다.
- 기존 단언 변경의 성격을 정정한다: 끝 빈 격자 단언은 버그가 아니라 DIMENSION·ROW·COLINFO 사용 범위를 보존하던 이전 계약이었고 이번에 XLSX 계약(서식만 있는 빈 셀 생략)으로 바꿨다. 이름이 "보존"이던 테스트는 `trims_trailing_…` 로 고쳤다. 배열 후속 셀은 ECMA-376 `<f ref>` 가 기준 셀에만 쓰이는 XLSX 계약을 따랐다.
- SummaryInformation: Type 을 2바이트로 읽고(패딩 무시), 코드 페이지는 CODEPAGE 레코드와 같은 매핑(10000·32768 → mac_roman, 32769 → cp1252), 문자열은 첫 NUL 에서 자른다.
- 감수 재측정: 공개 XLS 720개에서 비어 있지 않은 셀이 사라진 경우 0, 바뀐 505셀(16파일)은 모두 배열 후속 셀의 ` (=…)` 꼬리만 빠졌다. 처리 시간 51.9초 → 32.1초.
- 남은 일: 빈 병합이 격자를 늘리는 동작(`15375.xls`, 부모와 같음), DOC·PPT 의 SummaryInformation 제목·작성자(짝 DOC 13/13·PPT 8/8 에서 OOXML 쪽에만 `Author:`) — 공용 OLE 모듈로 옮겨 후속 적용.
