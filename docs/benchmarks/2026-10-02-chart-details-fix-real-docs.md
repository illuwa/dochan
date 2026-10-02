# 차트 세부 5차 리뷰 실물 검증

2026-10-03에 공개 POI·LibreOffice·hwp-public 코퍼스를 읽기 전용으로 검사했다. 시작 HEAD는 `8340045`이며, 회귀 판정 기준은 `107e18d`(1.7.0)이다. 1.7.0 코드를 `git archive`로 분리하여 기준본과 수정본에서 Markdown·JSON을 새로 생성했다. 내부 문서와 원본 코퍼스는 복사하지 않았다.

## 구현과 출력 계약

시간 분류와 미지원 토큰 검사는 선택한 구역만 사용한다. 양수 `0.5`에 `h:mm;h:m:s` 또는 `h:mm;[h]:mm`를 적용하면 `12:00`이다. 사용하지 않는 음수 구역이 양수 표시를 원시값으로 바꾸지 않는다.

경과 시간의 색·지역·조건 대괄호를 표시에서 제외하고, 단위 사이의 따옴표·역슬래시 리터럴을 보존한다. `_x`는 공백 하나, `*x`는 빈 문자열이다. 소수 초는 `.0`부터 `.000`까지 지원한다. 전체 일련값의 총 초를 15유효자리로 정규화한 뒤 표시 정밀도에서 HALF_UP으로 한 번 반올림한다. 날짜도 같은 반올림 결과의 정수 일수를 사용하므로 자정 carry가 유지된다. 1904 체계의 음수 경과 시간은 부호를 붙이고, 1900 체계의 음수 경과 시간과 음수 날짜·시각은 원시값을 유지한다.

`ss`와 `s` 단독 표시는 각각 두 자리와 한 자리 초이며, `h:m:s.00`은 각 단위의 폭을 따른다. 기존 일반 시각의 `HH:MM[:SS]`와 ISO 날짜 정규화는 유지한다. 차트의 하루 이상 시각에는 날짜를 붙여 일수를 보존한다. 이는 Excel의 시각 전용 표시와 의도적으로 다르므로 문자열 정확 일치로 세지 않는다. 일반 차트 숫자·백분율과 축 눈금 정책은 바꾸지 않았다.

`[<0]"";0%`의 음수는 빈 문자열이다. 기존 XLSX 출력기가 빈 셀을 생략하므로 실제 출력에서는 해당 좌표가 빠질 수 있다. 미지원 경과 조합인 `[h]:[m]`, `[h]:ss`와 네 자리 이상의 소수 초는 원시값으로 남긴다.

## 전수 비교와 판정

검토군은 차트 포함 OOXML 93개, XLS 720개, 차트 포함 HWPX 41개로 총 854파일이다. XLS 720개가 모두 차트 문서라는 뜻은 아니다. 추가 시트군은 339개이며 합집합은 1,193개다. `poc-shared-strings.xlsx`는 전후 동일하게 직렬화 120초 제한을 넘었으므로 미검증이다. 완결된 출력 비교는 1,192개다.

| 비교 | Markdown·JSON 변경 | 시트 변경 | 경고·예외 변화 |
|---|---:|---:|---:|
| 1.7.0 → 수정본, 차트 검토군 | 35파일이다. | 아래 23파일 집계에 포함했다. | 0개다. 경고 문서 126개가 동일하다. |
| 1.7.0 → 수정본, 추가 시트군 | 19파일이다. | 아래 23파일 집계에 포함했다. | 0개다. 경고 문서 20개가 동일하다. |
| 1.7.0 → 수정본, 전체 시트 | 전체 출력 변경은 54파일이다. | 23파일 5,515셀이다. | 좌표별 원시 근거를 모두 확보했다. |
| 저장된 4차 출력 → 수정본 | 2파일이다. | `DateFormatTests.xlsx` 185셀, `57181.xlsm` 3셀이다. | 0개이며 실제 차트 표도 모두 동일하다. |

Opus의 `classify.py`와 같이 변경 표시를 원시 값·서식에 연결하되, 동일 표시가 여러 좌표에 반복되는 경우도 각각 대조했다. `scripts/probe_chart_review_classify.py`는 다음 관찰 서식군의 독립 계산·토큰 제거 결과를 확인하고 그 외에는 미확인으로 실패한다. 판정은 Excel 표시와의 방향 비교이며 전체가 Excel 문자열 정확 일치라는 뜻은 아니다.

| 서식군 | 변경 셀 | 가까워짐 | 중립 | 근거 |
|---|---:|---:|---:|---|
| 회계·공백 | 1,969 | 1,969 | 0 | 이전 수치는 유지하면서 원시 서식의 공백·채움 토큰 제거 결과와 새 표시가 일치한다. |
| 날짜·시각 | 83 | 83 | 0 | 유리수 일련값의 날짜·시간 계산과 대조했다. 이 중 45셀은 소수 초 날짜·시각이다. 날짜 철자는 ISO로 정규화한다. |
| 잘못된 접미·통화 제거 | 25 | 25 | 0 | 잘못 붙었던 M/K·달러를 제거한다. 원시값 폴백을 정확 표시로 세지 않는다. |
| 경과 시간 | 128 | 128 | 0 | 독립 유리수 HALF_UP 계산과 표시가 128/128 일치한다. |
| 빈 조건 구역 | 140 | 140 | 0 | 음수 구역의 빈 리터럴과 빈 출력이 일치한다. |
| 영값 `[=0]?` 구역 | 3,148 | 2,497 | 651 | 2,497셀의 잘못된 날짜는 제거했다. 공백 대신 0을 표시하는 제한은 남아 있다. |
| 백분율 | 20 | 20 | 0 | 15유효자리 HALF_UP 기대와 일치한다. |
| 음수 날짜·쉼표 배율 원시값 | 2 | 0 | 2 | 기준본도 Excel 표시와 달랐으며 수정본도 표시 성공으로 세지 않는다. |
| 합계 | **5,515** | **4,862** | **653** | **멀어짐 0개, 미확인 0개다.** |

## 칸별 실물 증거

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| OOXML 소수 초 날짜·시각 | `DateFormatTests.xlsx`의 45셀이다. | `xl/styles.xml`의 `dd\-mmm\-yyyy\ hh:mm:ss.000`과 1904 일련값을 독립 유리수 산술로 계산했다. | 예를 들어 `1952-10-11 14:35:27.000`이다. | 45/45가 날짜·시간·밀리초 의미와 일치한다. | 1.7.0의 날짜만 표시하거나 4차의 원시값을 표시하던 상태보다 개선됐다. ISO 날짜 철자는 Excel 원문과 다르다. |
| OOXML 경과 시간 | `57181.xlsm`의 128셀이다. | 원시 수치와 조건부 `[hh]:mm:ss` 또는 `[hh]:mm` 구역, 독립 유리수 HALF_UP 산술이다. | 반초 경계 3셀은 `00:00:41`이다. | 전체 128/128이 일치한다. 4차와 같은 표시는 125개다. | 독립 산술 일치다. 이 3셀에는 Excel 표시 캐시가 없으므로 TEXT 캐시 검증과 구분한다. |
| OOXML 조건부 빈 표시 | `DateFormatTests.xlsx`의 140셀이다. | 원시 `[<0]"";0%` 구역과 음수 값이다. | 빈 문자열이다. | 140/140이 빈 표시이며 출력 셀은 생략된다. | 일치한다. |
| OOXML 서식의 Excel 직접 정답 | `NumberFormatTests.xlsx`, `DateFormatTests.xlsx`, `ElapsedFormatTests.xlsx`, `FormatChoiceTests.xlsx`, `FormatConditionTests.xlsx`, `GeneralFormatTests.xlsx`, `TextFormatTests.xlsx`, `NumberFormatApproxTests.xlsx`, `DateFormatNumberTests.xlsx`다. | 원본 XML에 저장된 `TEXT()` 결과 138건이다. | 저장된 Excel 문자열이다. | 1.7.0 48/138, 시작 HEAD 59/138, 수정본 63/138이 정확히 일치한다. | 두 기준 모두 기존 일치 손실 0개다. 나머지 15개는 원시값, 60개는 표시 미지원이다. |
| 선택 구역, 색·지역·리터럴, 1904 음수 경과 | 해당 조합의 공개 실물 셀은 별도 확보하지 못했다. | 합성 XML 및 직접 서식 테스트다. | 선택 구역과 단위별 표시를 따른다. | 단위·네 차트 리더 통합 테스트를 통과했다. | 이 조합의 실물은 미검증이며 ✅로 확대하지 않는다. |

새로 정확 일치한 TEXT 캐시는 네 건이다. `DateFormatTests.xlsx` A40의 `h:m:s.00`은 `4:5:6.01`, `ElapsedFormatTests.xlsx` A2의 `[h]:m:s.000`은 `75:23:53.376`, 같은 파일 A7의 `[ss].000`은 `271433.376`, `DateFormatNumberTests.xlsx` A2의 날짜·시각은 `1904-01-02 00:00:00.000`이다.

경과 시간 검색은 XLSX 계열 367개를 대상으로 했다. 비ZIP·암호화 등 읽을 수 없는 16개는 제외했고, 원시 경과 서식 후보 2,625셀 중 2,497개는 `[=0]?` 구역이므로 경과 표시 성공에 포함하지 않았다.

## 재현과 산출물

코퍼스 경로는 인자로 받는다. 다음에서 `corpus`는 공개 코퍼스 루트이며, 원본을 작업 트리에 복사할 필요가 없다.

```bash
mkdir -p .codex-work/review-r5/base .codex-work/review-r5/head
git archive 107e18d dochan | tar -x -C .codex-work/review-r5/base
git archive 8340045 dochan | tar -x -C .codex-work/review-r5/head
/usr/bin/python3 scripts/probe_chart_review_outputs.py inventory --corpus corpus --manifest .codex-work/review-r5/manifest.json
/usr/bin/python3 scripts/probe_chart_review_outputs.py snapshot --corpus corpus --manifest .codex-work/review-r5/manifest.json --tree .codex-work/review-r5/base --output .codex-work/review-r5/before
/usr/bin/python3 scripts/probe_chart_review_outputs.py snapshot --corpus corpus --manifest .codex-work/review-r5/manifest.json --tree . --output .codex-work/review-r5/after
/usr/bin/python3 scripts/probe_chart_review_outputs.py compare --corpus corpus --manifest .codex-work/review-r5/manifest.json --before .codex-work/review-r5/before --after .codex-work/review-r5/after --output .codex-work/review-r5/comparison
/usr/bin/python3 -m scripts.probe_chart_review_evidence --corpus corpus --comparison .codex-work/review-r5/comparison/comparison.json --output .codex-work/review-r5/evidence.json
/usr/bin/python3 -m scripts.probe_chart_review_classify --evidence .codex-work/review-r5/evidence.json --output .codex-work/review-r5/classified.json --csv docs/benchmarks/2026-10-02-chart-details-fix-sheet-values.csv
/usr/bin/python3 scripts/probe_chart_review_text_cache.py snapshot --corpus corpus/poi-src/test-data/spreadsheet --tree .codex-work/review-r5/head --output .codex-work/review-r5/text-head.json
/usr/bin/python3 scripts/probe_chart_review_text_cache.py snapshot --corpus corpus/poi-src/test-data/spreadsheet --tree . --output .codex-work/review-r5/text-after.json
/usr/bin/python3 scripts/probe_chart_review_text_cache.py compare --before .codex-work/review-r5/text-head.json --after .codex-work/review-r5/text-after.json --output .codex-work/review-r5/text-comparison.json --csv docs/benchmarks/2026-10-02-chart-details-fix-text-cache.csv
```

`sheet-values.csv`와 `output-values.csv`는 동일한 5,515셀의 원시 근거와 판정을 담는다. `output-diffs.md`는 1.7.0 대비 변경 문서의 실제 Markdown diff다. `text-cache.csv`는 138건 전부이며 HEAD 열은 `8340045`다. `elapsed-values.csv`는 경과 시간 128건이며 기준 열은 이전 경과 표시가 있던 `62b8c3e`다. 이 비교 기준들을 혼동하지 않는다.

## 테스트와 남은 범위

첫 재현에서 28개 실패를 확인했다. 새 회귀 테스트 38개와 기존 회귀를 포함한 전체 결과는 **3,568 passed, 24 skipped, 14 xfailed**다. Ruff와 diff 공백 검사를 통과했다. 날짜 has_time의 초 검사를 제거하는 변이와 차트의 날짜 접두를 제거하는 변이는 각각 새 직접 테스트에서 실패했다.

4차의 원시값 폴백을 고정한 기존 테스트 23개 사례는 이번 명시적 지원 결정에 맞춰 정확한 표시 기대로 바꿨다. 소수 초·단일 s·경과 리터럴은 이번 실패 테스트와 네 Excel 캐시가 근거이고, 1904 음수 경과는 합성 기대다. 변경 전에는 새 28개 재현 테스트가 모두 실패했다. 기존 일반 숫자·백분율·축 서식·자동 제목 계약은 유지했다.

전체 숫자 서식 칸의 ⬜ 판정은 유지한다. 영값 ?의 공백, 일반 Excel 사용자 서식 전체, chartEx 군집 막대·파레토·txData 제목, c:title 없는 자동 제목, XLS 시간·1904 실물 검증은 남아 있다. 독립 산술·합성 검증을 Excel UI 실물 검증으로 과장하지 않는다.
