# 차트 세부 리뷰 반영 실물 검증

2026-10-03에 공개 POI·LibreOffice·hwp-public 코퍼스를 읽기 전용으로 조사했다. 비교 기준은 `107e18d7725af8cc6680d5ba0e1ca2b931ed8163`이며, 이 커밋의 코드는 `git archive`로 별도 작업 디렉터리에 추출했고, 동일 입력을 HEAD와 수정본의 `Dochan.to_markdown()` 및 `Dochan.to_dict()`로 각각 실행했다. 코퍼스 원본과 내부 문서는 복사하지 않았다.

## 비교 범위와 방법

리뷰의 854개 파일 목록을 다시 만들었다. POI·LibreOffice의 차트 포함 OOXML 93개, XLS 720개와 hwp-public의 차트 포함 HWPX 41개가 일치했다. 시트 셀 회귀 검사는 POI·LibreOffice의 XLS 720개와 XLSX 계열 367개를 대상으로 했다. 두 집합의 합집합은 1,193개이며 차트 검토군 외에 339개가 추가됐다. XLSX 계열은 `.xlsx`, `.xlsm`, `.xltx`를 포함한다.

비교는 표시 서식을 제거하거나 파트 파서 결과를 정답으로 다시 쓰는 방식이 아니다. 실제 Markdown·JSON 출력 전체를 저장하여 비교하고, 시트 셀은 `sheet!cell` 좌표로 변경점을 추출했다. 바뀐 시트 값은 XML의 `c/v`, `numFmtId` 및 `formatCode`, 또는 BIFF NUMBER·RK·MULRK·FORMULA 레코드 값과 바이트 오프셋을 별도로 기록했다. 차트의 변경된 표 행에서는 Markdown diff 양쪽의 모든 숫자·백분율·ISO 날짜·시간 셀을 원시 XML XPath 또는 BIFF 오프셋과 대조했다.

diff의 수치 대조는 해당 문서의 원시 수치 후보와 일치하는지 확인하는 검사다. 같은 숫자가 여러 계열에 나타날 수 있으므로 이 검사만으로 원본 계열·좌표 대응까지 증명하지 않는다. 계열·점 순서는 별도의 원시 Y 값 프로브 및 혼합 계열 회귀 테스트와 구분해서 평가했다. 헤더·제목·축 캡션 변화는 숫자 검사에 섞지 않았다.

## 출력 자원 제한과 추가 발견

추가 시트군의 악성 표본 `poc-shared-strings.xlsx`는 HEAD와 중간 수정본 모두 출력 직렬화가 120초를 넘겼다. 이 파일은 출력 비교 미완료로 제외했으며 성공 수에 넣지 않았다. 차트 854개 검토군에는 속하지 않는다. 프로브의 직렬화에도 시간 상한을 추가했다. 이는 이번 수정으로 새로 생긴 문서 파싱 회귀라고 판정하지 않는다.

첫 출력 전수 검사에서 `49273.xlsx`의 F1·F2가 시간 전용 서식 `h"时"mm"分"ss"秒";@`인데 날짜 접두가 붙는 문제를 발견했다. 원시 값은 각각 `0.55556712962962962`, `0.5555671296296296`이었다. 콜론 없이 리터럴로 구분된 시간 토큰도 구분하도록 실패 테스트와 셀 서식기를 추가 수정한 다음 최종 출력 전체를 재실행했다. K1·K2의 `[DBNum1][$-804]General`은 로캘 지정자를 달러 기호로 오인하던 동작을 바로잡았다.

## 최종 결과

| 검토 집합 | 파일 수 | Markdown 변경 | JSON 변경 | 전후 경고·예외 변화 | 판정 |
|---|---:|---:|---:|---|---|
| 리뷰 차트 검토군 | 854 | 33 | 33 | 0개이며, 기존 경고가 있는 126개 문서도 동일했다. | 854/854의 실제 출력을 비교했다. |
| 추가 시트 검토군 | 339 | 10 | 10 | 0개이며, 기존 경고가 있는 20개 문서도 동일했다. | 338개 출력을 비교했고 악성 표본 1개는 미검증이다. |
| XLS 시트 셀 | 720 | 셀 변경 0 | 셀 변경 0 | 셀 회귀가 없었다. | 통과했다. |
| XLSX 계열 시트 셀 | 367 | 11개 파일의 3,545셀 | 같은 셀 변경을 확인했다. | 원시 XML 근거 3,545/3,545를 확보했다. | 비교 가능한 변경 셀 3,545/3,545가 아래 독립 판정과 일치했다. |

3545개 시트 변경 셀은 원시 수치 보존 3314개, 날짜·시간 의미 대조 211개, 지정 자릿수 백분율 HALF_UP 20개로 나뉜다. 날짜·시간은 원시 부동소수점 수의 역복원이 아니라 정규화한 시각 의미를 검증했다. 시트 백분율은 Excel double의 십진 표현을 바탕으로 표시 자릿수와 HALF_UP을 독립 계산했다. 차트의 일반 숫자·백분율은 이 표시 반올림을 적용하지 않고 원시 수치를 유지했다.

변경된 Markdown 표 행의 전후 숫자 셀 21,480개를 모두 조사했다. 이 수에는 같은 행에서 함께 다시 출력된 변경되지 않은 숫자도 포함된다. 수정본 `+`쪽 10,767개는 원시 Decimal 수치 일치 9951개, 날짜·시간 산술 일치 709개, 시트 백분율 표시 90개, 생성 범주 인덱스 10개, 원본 숫자형 문자열 5개, 기존 지수 표시 2개였다. 수정본 수치에 허용오차를 사용한 경우와 미확인 값은 모두 0개였다. HEAD 쪽의 역사적 이진수·백분율 표시 오차 80개에만 `1e-14` 허용오차를 사용했으며 수정본의 무손실 판정과 구분했다. 이 수치 후보 검사의 좌표 정합성 한계는 앞 절에 적었다.

다음 부속 표는 각 변경 셀과 원시 값·서식·기대·실제·판정을 모두 남긴다.

- [시트 변경 셀 3545개](2026-10-02-chart-details-fix-sheet-values.csv)는 시트 좌표별 독립 판정이다.
- [변경 표 행의 전후 숫자 21480개](2026-10-02-chart-details-fix-output-values.csv)는 차트 표를 포함한 모든 Markdown 숫자 셀의 근거다.
- [파일별 전체 출력 차이](2026-10-02-chart-details-fix-output-diffs.md)는 CSV의 diff 줄 번호를 확인하기 위한 표다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| 차트 일반 숫자·백분율 정밀도 | `DataTableCities.xlsx`, `47813.xlsx`, `dataValidationTableRange.xlsx`, `rhwp-1790387_prep_final_report.hwpx` | 원시 numCache/formatCode와 최종 Markdown·JSON 값 | 축 눈금이나 백분율 반올림으로 원시 값을 바꾸지 않아야 한다. | 121.5, 31.23, 긴 소수, 0.0049/0.0891을 원시 정밀도로 유지했다. | 손실 회귀는 수정했다. 일반 숫자 서식 전체 지원의 ✅ 제안은 철회한다. |
| OOXML 분산형 축·원시 좌표 | `DataTableCities.xlsx`, `tdf124398_groupshapeChart.docx` | axId·crossAx·axPos와 원시 xVal/yVal | X/Y 역할을 구분하고 원시 좌표로 행을 판정해야 한다. | 축 캡션 역할을 구분했고 축 서식에 의한 값 반올림이 사라졌다. | 기존 축 판정 증거를 유지한다. |
| XLS 혼합 계열·날짜 | `external_name.xls`, `forum-mso-de-48440.xls` | ChartFormat.icrt·SerToCrt·BRAI 및 원시 RK/FORMULA | 계열별 범주/X/Y를 분리하고 날짜는 시각 의미대로 표시해야 한다. | 혼합 표 5개를 유지했고 `external_name.xls`의 날짜 104개는 독립 날짜 산술과 일치했다. | 해당 실물 검증은 통과했다. OOXML 혼합 실물 전체를 검증한 것은 아니다. |
| 자동 제목 생성 | `bar-chart.pptx`, `60509.xlsx`, 공개 HWPX 단일 계열 표본 등 | c:tx 없는 c:title, autoTitleDeleted=false, 단일 계열의 원시 이름 | 실제 JSON에서 heading_level=3인 제목이어야 한다. | 조건 후보 25파트 중 이름 있는 23파트를 확인했고 실제 출력 제목은 21파트였다. | 구현을 보완했다. 요청대로 README 칸은 ⬜를 유지한다. |
| HWPX 자동 제목·표 출력 | `2차원원형.hwpx`, `charts.hwpx`, `rhwp-가로막대형_하나만있을떄_단일시리즈제목.hwpx` 등 | 공개 차트 XML과 문서 JSON의 차트 캡션·heading_level | 기존 공개 HWPX를 실제 리더로 검사해야 한다. | 41파일 중 37파일에서 차트 표 73개가 출력됐다. 자동 제목은 출력 가능한 후보 8/8에서 판매 또는 계열 1과 일치했다. | 공개 HWPX 실물이 없다는 이전 기록을 정정한다. 미지원 종류까지 성공으로 세지 않는다. |
| XLSX 시간·로캘 | `49273.xlsx`, `DateFormatTests.xlsx`, `right-to-left.xlsx` | 셀의 원시 숫자·numFmt·workbookPr.date1904 | 시간 토큰·로캘·1904 체계를 올바르게 구분해야 한다. | 13:20:01, 1904 기반 날짜시간, 로캘 지정자의 달러 오인 제거가 독립 기대와 일치했다. | 변경 셀 검증을 통과했다. |
| XLSX 백분율 표시 | `AverageTaxRates.xlsx`, `60512.xlsm` | 원시 XML 숫자를 Excel double로 읽은 값과 독립 HALF_UP | 0.125는 13%이고 0.015는 2%여야 한다. | 최종 `60512.xlsm` G10은 2%로 HEAD와 같아졌고 세율 표의 변경 20셀은 독립 반올림과 일치했다. | 출력 검사에서 발견한 추가 under-round 회귀도 수정했다. |
| XLSX 미지원 축약 스케일 | `FormatKM.xlsx`, `bug69812.xlsx` | 조건부 formatCode의 숫자 뒤 쉼표와 원시 수치 | 지원하지 않는 K/M 축약을 잘못 표시하지 않아야 한다. | `1,021K` 같은 잘못된 표시 대신 원시 1021.02를 보존했다. | 지원 범위를 늘렸다고 주장하지 않고 원시 값으로 안전하게 복귀했다. |
| chartEx 군집 막대·파레토·연결 제목 | 해당 실물 표본을 찾지 못했다. | 기존 공개 코퍼스 파트 조사 | 해당 종류의 실제 출력이 필요하다. | 합성 검증과 기존 종류 회귀 검증만 있다. | ⬜를 유지한다. |

자동 제목의 나머지 4파트 중 `tdf137116.docx`와 `chart-size.docx`는 계열 이름 캐시가 비었고, HWPX `원형대가로막대형.hwpx`와 `원형대원형.hwpx`는 ofPieChart 자체가 현재 출력되지 않았다. HWPX에서 차트 표가 나오지 않은 나머지 2파일은 stockChart 표본이다. 기존 미지원 배치를 자동 제목 성공이나 값 보존 성공으로 포장하지 않았다.

마지막 셀 서식 수정의 영향을 확인하기 위해 1,514,726개 원시 숫자·서식 쌍, 중복을 제외한 155,610개 조합을 구·신 formatter와 1900/1904 양 체계에 각각 투입했다. 종류 또는 표시가 바뀐 파일과 별도 원시 추출기가 읽지 못한 59파일은 최종 코드로 Markdown·JSON 전체를 다시 수집했다. 마지막 스케일 수정에서는 후보 `FormatKM.xls`, `FormatKM.xlsx`, `bug69812.xlsx` 중 XLS 시트 출력은 유지됐고 XLSX 두 파일만 바뀌었다. 최종 수치는 이 재수집 결과를 반영했다.

최종 전체 테스트는 3,384개 통과, 24개 건너뜀, 기존 예상 실패 14개였다. 새 검증 프로브는 실제 공개 코퍼스로 실행했고 Ruff 검사도 통과했다. README·공유 모델·출력 writer는 이 리뷰 반영에서 수정하지 않았다.

## 재현 명령

다음 명령에서 `before-final`은 HEAD 코드, `after-final`은 수정본 코드의 스냅샷 디렉터리다. 결과는 `.codex-work/output-audit/` 아래에 저장한다. 스냅샷은 같은 디렉터리의 완료 파일을 재사용하므로 다른 코드 상태를 검증할 때는 반드시 새 출력 디렉터리를 쓴다. `compare --refresh <manifest>`는 이미 수집한 전체 비교에서 추가 수정으로 재수집한 파일만 갱신할 때 사용한다.

```bash
/usr/bin/python3 -m scripts.probe_chart_review_outputs inventory --corpus /Users/illuwa/dev/personal/dochan/corpus --manifest .codex-work/output-audit/manifest.json
/usr/bin/python3 -m scripts.probe_chart_review_outputs snapshot --corpus /Users/illuwa/dev/personal/dochan/corpus --manifest .codex-work/output-audit/manifest.json --tree .codex-work/output-audit/head --output .codex-work/output-audit/before-final
/usr/bin/python3 -m scripts.probe_chart_review_outputs snapshot --corpus /Users/illuwa/dev/personal/dochan/corpus --manifest .codex-work/output-audit/manifest.json --tree . --output .codex-work/output-audit/after-final
/usr/bin/python3 -m scripts.probe_chart_review_outputs compare --corpus /Users/illuwa/dev/personal/dochan/corpus --manifest .codex-work/output-audit/manifest.json --before .codex-work/output-audit/before-final --after .codex-work/output-audit/after-final --output .codex-work/output-audit/comparison
/usr/bin/python3 -m scripts.probe_chart_review_evidence --corpus /Users/illuwa/dev/personal/dochan/corpus --comparison .codex-work/output-audit/comparison/comparison.json --output .codex-work/output-audit/sheet-evidence.json
/usr/bin/python3 -m scripts.probe_chart_review_diff_values --corpus /Users/illuwa/dev/personal/dochan/corpus --comparison .codex-work/output-audit/comparison/comparison.json --output .codex-work/output-audit/diff-value-evidence.json --csv docs/benchmarks/2026-10-02-chart-details-fix-output-values.csv
/usr/bin/python3 -m scripts.probe_chart_review_evidence --corpus /Users/illuwa/dev/personal/dochan/corpus --manifest .codex-work/output-audit/manifest.json --snapshot .codex-work/output-audit/after-final --output .codex-work/output-audit/auto-titles-final.json
/usr/bin/python3 -m scripts.probe_chart_review_sheet_values --evidence .codex-work/output-audit/sheet-evidence.json --output .codex-work/output-audit/sheet-verdicts.json --csv docs/benchmarks/2026-10-02-chart-details-fix-sheet-values.csv
```
