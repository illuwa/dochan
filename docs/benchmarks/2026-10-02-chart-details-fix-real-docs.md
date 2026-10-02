# 차트 세부 3차 리뷰 실물 검증

2026-10-03에 공개 POI·LibreOffice·hwp-public 코퍼스를 읽기 전용으로 검사했다. 이번 비교 기준은 `62b8c3e`다. 기준 코드를 `git archive`로 분리하고 같은 입력을 기준본과 수정본의 `Dochan.to_markdown()` 및 `Dochan.to_dict()`에 각각 전달했다. 이전 보고서의 `107e18d` 대비 3,545셀·43파일 변경 수치는 이번 비교 수치가 아니다. 원본 문서와 내부 문서는 복사하지 않았다.

## 출력 정책

`_x`와 `*x`, 따옴표 리터럴 및 역슬래시 이스케이프는 서식 분류에서 제외한다. XLSX 시트의 공백 폭 토큰은 공백 하나로 표시하고 채움 토큰은 제거한다. 따옴표 안의 밑줄·별표는 문자이므로 보존한다. 기존 숫자 정밀도·통화·부호 계약은 유지한다.

경과 시간 `[h+]`·`[m+]`·`[s+]`, 소수 초, 한 글자 s 및 음수 날짜·시각은 정확한 표시를 주장하지 않고 원시 일련값으로 보존한다. 예를 들어 `1.5`의 `[hh]:mm:ss`를 `12:00:00`이나 `36:00:00`으로 내지 않고 `1.5`로 남긴다. 이는 이번 명시적 정책이며 Excel의 경과 시간 표시 구현 완료를 뜻하지 않는다. XLSX 시트 백분율은 15유효자리 기준으로 정규화한 뒤 Decimal HALF_UP을 적용한다. 차트 백분율은 계속 원시 숫자다.

`c:title` 자체가 없는 자동 제목 생성은 실물 근거가 없어 제거했다. `c:title`이 있고 `c:tx`가 없으며 autoTitleDeleted가 명시적 false인 단일 계열의 이름만 제목으로 사용한다. 차트 시각의 일련값이 하루 이상이면 일수를 잃지 않도록 날짜를 붙인다. `57181.xlsm`의 `2015-07-28 07:00`은 Excel의 `07:00`과 의도적으로 다른 표시다.

## 비교 범위와 결과

검토군은 기존과 같은 854파일이다. 차트 포함 OOXML 93개, XLS 720개와 차트 포함 HWPX 41개로 구성한다. XLS 720개가 모두 차트 문서라는 뜻은 아니다. 시트 회귀군은 XLS 720개와 XLSX 계열 367개이며 두 검토군의 합집합은 1,193개다.

`poc-shared-strings.xlsx`는 전후 모두 직렬화 120초 한도를 넘었다. 이 1파일은 성공으로 세지 않는다. 따라서 완결된 출력 비교는 검토군 854개와 추가군 338개를 합한 1,192개다. 파서 경고가 있는 문서도 포함한 회귀 비교이며 모든 문서가 완전히 지원된다는 뜻은 아니다.

| 검토 집합 | 파일 수 | Markdown 변경 | JSON 변경 | 경고·예외 변화 | 판정 |
|---|---:|---:|---:|---|---|
| 차트 리뷰 검토군 | 854 | 4 | 4 | 0개이며 경고 문서 126개도 동일하다. | 854/854 출력을 비교했다. |
| 추가 시트 검토군 | 339 | 11 | 11 | 0개이며 경고 문서 20개도 동일하다. | 338개를 비교했고 악성 표본 1개는 미검증이다. |
| XLS 시트 | 720 | 0 | 0 | 기존 동작이 유지됐다. | 시트 서식기는 수정하지 않았다. |
| XLSX 계열 시트 | 367 | 15파일, 2,143셀 | 같은 셀 변경을 확인했다. | 셀별 원시 XML 근거를 확보했다. | 아래 독립 대조와 제한을 따른다. |

변경된 2,143셀의 원시 값, 서식, 날짜 체계, XML 위치, 전후 표시, 기대와 판정은 [시트 변경 셀 CSV](2026-10-02-chart-details-fix-sheet-values.csv)에 기록했다. 날짜·시간 174셀은 원시 문자열 폴백을 확인했다. 회계·숫자 레이아웃 1,969셀은 원시 수치에 독립 Decimal 반올림을 적용하고 통화·부호·앞뒤 공백을 결합한 기대 문자열과 정확히 일치했다. 이 중 `48962.xlsx` B13은 기존 로캘 통화·부호 위치를 보존한 `$-123.00 `과 정확히 일치했다. 이를 원시 문자열 `-123`과 같다고 세거나 Excel의 음수 회계 표시와 동일하다고 주장하지 않는다.

이번 수정에서 실제 차트 표·제목·캡션의 변경은 0개다. 모든 변경 JSON 요소가 시트 표임을 확인했으며 나머지 표와 문단은 전후 동일했다. [전체 출력 차이](2026-10-02-chart-details-fix-output-diffs.md)와 [출력 변경 셀 CSV](2026-10-02-chart-details-fix-output-values.csv)는 이를 기록한다. 이전 CSV는 변경 행 양쪽에 함께 나온 숫자 21,480개를 문서 내 수치 후보와 대조했지만, 이번 CSV는 실제 바뀐 2,143개 셀만 원본 좌표로 직접 연결한다. 따라서 현재 두 값 CSV는 동일한 2,143개 셀을 담으며 과거 행 수와 비교하지 않는다.

## 칸별 실물 근거

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| XLSX 공백·채움 토큰 | `LIBRE_OFFICE-128382-0.xlsx`, `ConditionalFormattingSamples.xlsx`, `mv-calculator-final-2-20-2013.xlsm` 등 | 셀 XML의 원시 값·formatCode와 독립 자리수/통화/공백 계산이다. | `_x`는 공백 하나가 되고 `*x`는 사라져야 한다. | 회계 레이아웃 1,969셀의 기대 표시가 일치했다. | 해당 수정 범위만 통과했다. 전체 회계 서식 지원을 주장하지 않는다. |
| 음수 날짜·시각 | `DateFormatTests.xlsx`, `bug60858.xlsx` | 원시 음수 일련값과 날짜 체계다. | 부호를 잃거나 이전 날짜로 변환하지 않고 원문을 남겨야 한다. | `bug60858.xlsx` N2의 `-1.0` 등 원시 값이 보존됐다. | 폴백을 검증했다. |
| 소수 초 | `57181.xlsm`, `DateFormatTests.xlsx` | 소수 초가 있는 원본 셀 서식과 원시 값이다. | 초 정밀도를 버린 문자열 대신 원시 값을 내야 한다. | 두 파일의 변경 173셀은 원시 값과 일치했다. 이 중 DateFormatTests는 음수 날짜 사례도 포함한다. | 표시 구현이 아닌 원시 보존을 검증했다. |
| 반복 경과 단위·단일 s | `ElapsedFormatTests.xlsx`, `DateFormatTests.xlsx`의 TEXT 캐시다. | Excel이 저장한 TEXT 결과, 참조 원시 숫자와 서식이다. | Excel 표시 일치와 원시 폴백을 구분해야 한다. | 아래 138건 대조와 합성 회귀에서 원시 보존을 확인했다. | 일반 서식 칸은 ⬜를 유지한다. |
| 백분율 15유효자리 HALF_UP | 공개 138건 TEXT 캐시와 합성 경계값이다. | 원시 double의 15유효자리 및 명시적 HALF_UP 정책이다. | `0.034999999999999996`의 `0%`는 `4%`여야 한다. | 합성 경계값이 통과했고 공개 정확 일치 항목의 회귀는 없다. | 해당 경계값의 Excel 실물 정답을 새로 확보한 것은 아니다. |
| c:tx 없는 제목 요소 | `bar-chart.pptx`, `60509.xlsx`, 공개 HWPX 단일 계열 표본이다. | c:title, autoTitleDeleted=false 및 계열명 캐시다. | 검증된 제목 생성만 유지해야 한다. | 기존 공개 출력이 유지됐다. c:title 없는 생성의 실물은 0개다. | 자동 제목 전체 칸은 ⬜를 유지한다. |
| 차트 시각 날짜 접두 | `57181.xlsm`이다. | `h:mm` 캐시와 정수 날짜 부분이다. | 날짜 부분을 보존해야 한다. | `2015-07-28 07:00` 등 기존 차트 출력이 유지됐다. | Excel 표시와의 의도적 차이를 기록했다. |
| chartEx 군집 막대·파레토·txData 제목 | 새 해당 실물은 없다. | 이전 공개 코퍼스 조사와 이번 출력 회귀다. | 해당 종류의 실물 증거가 필요하다. | 합성 및 기존 종류의 회귀만 있다. | ⬜를 유지한다. |

## Excel TEXT 캐시 138건

9개 공개 `*Format*Tests.xlsx`의 실제 `TEXT(값셀, 서식셀)` 수식 캐시 138개를 재계산 없이 정답으로 사용했다. 정확 일치는 `62b8c3e`와 수정본 모두 59/138이다. 정확 일치를 새로 얻거나 잃은 항목은 각각 0개다. 수정본의 나머지는 원시 폴백 19개와 표시 미지원 60개다. 원시 폴백을 Excel 표시 성공으로 세지 않는다.

10건의 표시가 달라졌으며 기존에 정확히 일치하던 사례는 없다. 시간 관련 8건과 공백용 `_?`를 분수 자리로 잘못 읽던 2건이 원시 폴백으로 바뀌었다. `NumberFormatTests.xlsx` A188의 `-3.75`와 `|#_?=/=#|`는 기존 `-|3 3/4|`와 중간 수정의 `-|4|` 모두 Excel 캐시 `-|15 =/=4|`와 다르다. 지원하지 않는 분수를 정수로 반올림하지 않도록 원시 `-3.75`를 남겼다. `_?`가 없는 기존 서식은 이 조치에서 제외해 기존 일치를 유지했다.

행별 전후 결과와 Excel 캐시는 [TEXT 캐시 CSV](2026-10-02-chart-details-fix-text-cache.csv)에 있다. 이 검증은 캐시가 저장된 138건에 한하며 Excel UI를 새로 실행한 결과는 아니다.

## 테스트와 제한

초기 재현은 새 회귀 테스트 및 로컬 경로 검사에서 36개 실패를 확인했다. 구현 후 57개 새 회귀가 통과했고, 비유한 값 가드·255자 차트 서식 상한·차트 단계 조건 선택을 각각 제거한 뮤테이션 3개 모두 새 테스트에서 실패했다. 복사한 코드 트리가 아닌 원본을 잘못 읽지 않도록 별도 pytest 설정과 import 경로를 사용해 검증했다.

최종 전체 테스트는 3,441개 통과, 24개 건너뜀, 기존 예상 실패 14개다. Ruff와 diff 공백 검사가 통과했고 커밋 대상 18개 파일의 로컬 절대 경로 문자열 검사에서 위반은 0개였다.

경과 시간 원시 보존 결정에 따라 기존 단언 네 곳과 합성 벤치마크 기대 두 곳을 정정했다. `test_reads_xlsx_time_and_duration_number_formats`, `test_review_cell_number_formats`의 [s] 사례 및 `test_generate_corpus_writes_ooxml_files_and_expected_manifest`의 두 단언이다. 제목 테스트 두 개는 c:title이 존재하는 픽스처로 범위를 좁혔고, c:title 부재는 별도의 새 무제목 테스트로 확인했다. 그 밖의 기존 단언은 변경하지 않았다.

XLS 시트 서식기의 로캘 토큰 달러 오인, 부동소수점 백분율 표시와 날짜+시각 원시 출력은 범위 밖이므로 수정하지 않았다. `_NumericString`의 메모리 비용 개선도 이번 표시 수정과 분리한 후속 측정 과제다. README·CHANGELOG·공유 모델·출력 writer·런타임 의존성은 바꾸지 않았다.

## 재현 명령

`corpus`는 외부 읽기 전용 코퍼스 루트를 가리키는 경로 인자다. 다음 예시는 상대 경로로 적었다. 매 코드 상태마다 새로운 스냅샷 디렉터리를 사용한다.

```bash
mkdir -p .codex-work/review-r3/head
git archive 62b8c3e | tar -x -C .codex-work/review-r3/head
/usr/bin/python3 -m scripts.probe_chart_review_outputs inventory --corpus corpus --manifest .codex-work/review-r3/manifest.json
/usr/bin/python3 -m scripts.probe_chart_review_outputs snapshot --corpus corpus --manifest .codex-work/review-r3/manifest.json --tree .codex-work/review-r3/head --output .codex-work/review-r3/before-final
/usr/bin/python3 -m scripts.probe_chart_review_outputs snapshot --corpus corpus --manifest .codex-work/review-r3/manifest.json --tree . --output .codex-work/review-r3/after-final
/usr/bin/python3 -m scripts.probe_chart_review_outputs compare --corpus corpus --manifest .codex-work/review-r3/manifest.json --before .codex-work/review-r3/before-final --after .codex-work/review-r3/after-final --output .codex-work/review-r3/comparison
/usr/bin/python3 -m scripts.probe_chart_review_evidence --corpus corpus --comparison .codex-work/review-r3/comparison/comparison.json --output .codex-work/review-r3/sheet-evidence.json
/usr/bin/python3 -m scripts.probe_chart_review_sheet_values --evidence .codex-work/review-r3/sheet-evidence.json --output .codex-work/review-r3/sheet-verdicts.json --csv docs/benchmarks/2026-10-02-chart-details-fix-sheet-values.csv
/usr/bin/python3 -m scripts.probe_chart_review_text_cache snapshot --corpus corpus/poi-src/test-data/spreadsheet --tree .codex-work/review-r3/head --output .codex-work/review-r3/text-before.json
/usr/bin/python3 -m scripts.probe_chart_review_text_cache snapshot --corpus corpus/poi-src/test-data/spreadsheet --tree . --output .codex-work/review-r3/text-after.json
/usr/bin/python3 -m scripts.probe_chart_review_text_cache compare --before .codex-work/review-r3/text-before.json --after .codex-work/review-r3/text-after.json --output .codex-work/review-r3/text-comparison.json --csv docs/benchmarks/2026-10-02-chart-details-fix-text-cache.csv
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```
