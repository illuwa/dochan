# 차트 세부 실물 검증

2026-10-03에 `illuwa/w-chart-details`에서 공개 POI·LibreOffice 표본을 읽기 전용으로 검사했다. 원본 문서는 저장소에 복사하지 않았다. 구현은 저장소의 기존 파서, ECMA-376 21.2의 차트 요소 구조, Microsoft [MS-XLS] 명세와 원시 XML·BIFF 레코드 관찰을 근거로 했다. BIFF8의 구체적인 근거는 [MS-XLS] v20250819의 2.4.29 BRAI, 2.4.48 ChartFormat, 2.4.182 ObjectLink, 2.4.256 SerToCrt, 2.5.165 IFmt다. 외부 프로젝트의 구현 코드는 읽거나 옮기지 않았다. Office GUI 렌더링을 새로 실행한 검증은 아니다. 축 제목의 독립 정답은 차트 XML의 제목·축 위치·교차 연결이다.

리뷰 반영 최종 출력 검증과 칸별 제안은 [chart-details-fix 실물 검증](2026-10-02-chart-details-fix-real-docs.md)에 기록한다. 아래 전수 비교 수치는 이전 리뷰의 기준 `107e18d`에 대한 이력이다. 이번 3차 리뷰의 기준 `62b8c3e` 및 최종 수치는 링크 문서를 따른다. 아래는 기존 파트 프로브의 보조 근거이며, 원시 표 비교만으로 표시 출력의 무손실을 주장하지 않는다.

## 출력 계약과 구현

분산형과 거품형의 축은 차트 그룹의 `axId`로 찾고, 상호 `crossAx` 연결을 확인한다. `axPos=b/t`는 X이고 `l/r`는 Y이다. 두 위치가 같거나 불완전한 생성기는 상호 연결된 축 쌍의 그룹 참조 순서를 사용한다. 참조가 없거나 교차 연결이 모순되면 기존 `Value axis` 표기를 유지한다. 주축과 보조축을 서로 섞지 않는다. 축 ID 인덱스는 캡션마다 한 번 만들며 축 8개와 차트 그룹 1,000개 상한을 적용한다. 초과 그룹은 문서 경고로 보고하고 해당 선택적 차트를 비운다.

막대와 분산형이 함께 있으면 `Series | Category | X | Y` 표를 사용한다. 거품 크기도 있으면 마지막에 `Bubble size`를 붙인다. 범주 계열은 Category에만, 분산 계열은 X에만 값을 쓴다. 두 계열의 범주 문자열과 숫자가 우연히 같아도 열을 합치지 않는다. 기존 `Table`, `Cell`, Markdown·JSON 출력 경로를 그대로 쓴다.

차트 데이터는 원시 숫자 문자열을 기본으로 출력한다. 숫자 캐시의 `formatCode` 또는 캐시 없는 참조에서 얻은 원본 셀 서식은 지원하는 날짜·시각에만 적용한다. 단순 경과 시간은 총 시·분·초로 표시하며 반복 단위의 글자 수만큼 0을 채운다. 5차 리뷰에서 소수 초 1~3자리와 한 글자 s 시각, 경과 시간의 지역·색상 토큰 및 리터럴을 지원했다. 1904 체계 음수 경과 시간은 부호를 붙여 표시한다. 음수 날짜·시각, 1900 체계 음수 경과 시간 및 미지원 조합은 원시 값을 보존한다. 축의 `numFmt`는 눈금 레이블 서식이므로 데이터 값에 적용하지 않는다. 백분율도 0.0891처럼 원시 값을 보존하며 일반 숫자·과학·회계 서식을 이용한 반올림은 하지 않는다. 문자열 범주에는 숫자 서식을 적용하지 않는다.

날짜는 ISO 날짜, 시간은 24시간 표기를 사용한다. `h:mm`의 일련값에 날짜 부분이 있으면 날짜도 보존한다. Excel의 시각 전용 표시에는 없는 날짜 접두를 붙이는 것은 일수를 잃지 않기 위한 의도적 차이다. `mm:ss`는 분·초 표시이며 시트와 같은 계약을 따른다. 표의 좌표 동일성은 표시 문자열에 붙인 원시 숫자를 비교하므로 날짜·시간 표시가 같아도 서로 다른 X 좌표를 합치지 않는다. 표시값 메타데이터는 내부 문자열 확장이며 공유 모델과 JSON 스키마를 바꾸지 않았다.

이미 캐시가 있는 참조에서 서식만 얻기 위해 원본 셀을 조회하지 않는다. 이는 뒤 차트의 누락 캐시 보충 예산을 보존한다. XLS BRAI의 연결 서식도 실제 숫자에만 같은 정책으로 적용한다. 서식은 255자 이하로 제한하고 서식기 LRU는 128개, 결과는 128자 및 원시값 대비 추가 64자 이하로 제한한다.

HWPX의 `parse_chart_xml(data)`는 기존 원시 캐시 API를 보존한다. 추가 인자 `display_values=True`가 표시 서식과 명시적 자동 제목을 사용하며, HWPX 문서 리더가 이를 켠다. 따라서 기존 원시값 테스트의 단언을 바꿀 필요가 없다.

자동 제목은 `c:title`이 있고 그 안의 `c:tx`가 없고 이름 있는 계열이 하나이며 `autoTitleDeleted`가 명시적으로 false인 경우에만 생성한다. autoTitleDeleted가 true이거나 값 없는 요소이면 생성하지 않는다. c:title 또는 autoTitleDeleted 자체가 생략된 경우도 무제목을 유지한다. 생략 상태의 Office 동작은 이번 코퍼스로 확인하지 못했으므로 이 처리를 Office 전체 규칙 검증 완료로 주장하지 않는다. `c:tx`가 있는 명시적 빈 제목은 보존한다. `c:title`만 있고 `c:tx`가 없는 실물 자동 제목은 이번 리뷰에서 추가 검증했다. 자동 제목 README 칸은 변경하지 않는다.

## 항목별 실물 판정

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| OOXML 분산형 X/Y 축 | POI `DataTableCities.xlsx`, `xl/charts/chart1.xml` | 원시 XML: axId 307857760/307857368, b/l, 상호 crossAx, 제목 Longitude/Latitude | X axis: Longitude; Y axis: Latitude | 두 축 제목과 역할이 일치했다. | 통과했다. |
| OOXML 분산형 X/Y 축 | LO `tdf124398_groupshapeChart.docx`, `word/charts/chart1.xml` | 원시 XML: axId 1940630128/1679089488, b/l, 상호 crossAx | X axis: Frequency (Hz); Y axis: Output Voltage (dB) | 두 축 제목과 역할이 일치했다. | 통과했다. |
| XLS 분산형 X/Y 축 | POI `26100.xls`, LO `pass/ooo47086-1.xls` | Scatter 및 ObjectLink 원시 레코드의 역할 3=X, 2=Y | 6개 차트의 X/Y 제목을 구분해야 한다. | 6개 차트의 축 캡션이 변경됐고 값은 보존됐다. | 통과했다. |
| 막대·분산 혼합 긴 표 | POI `external_name.xls`, `forum-mso-de-48440.xls` | ChartFormat·SerToCrt·Bar·Scatter 레코드와 계열 원시 값 | 2개 문서, 5개 차트에서 범주와 X를 다른 열에 보존해야 한다. | 5개 차트가 Series/Category/X/Y 표로 바뀌었고 계열별 값이 보존됐다. | XLS 실물은 통과했다. OOXML 혼합 실물은 발견하지 못했다. |
| 시간 범주 표시 | POI `57181.xlsm`, `xl/charts/chart1.xml` | numCache formatCode=h:mm, catAx numFmt=h:mm/sourceLinked=0, 독립 datetime 산술 | 42213.291666666664부터의 30개 범주를 시간으로 표시해야 한다. | 2015-07-28 07:00부터 같은 날 21:30까지 날짜를 포함한 30/30이 일치했다. | 통과했다. |
| 날짜 범주 표시 | LO `tdf130031.docx`, `testAreaChartNumberFormat.docx`, POI `chartex.docx`의 classic chart3·chart5 | 원시 formatCode=m/d/yyyy, 독립 datetime 산술 | 4개 차트의 날짜 범주 37개를 ISO 날짜로 표시해야 한다. | 37/37이 일치했다. 37261은 2002-01-05로 표시됐다. | 통과했다. |
| 백분율 원시 값 보존 | POI `45540_classic_Footer.xlsx`, `45540_classic_Header.xlsx`, `45544.xlsx` | 원시 formatCode=0.0% 및 numCache 문자열 직접 대조 | 6개 차트의 39개 값을 반올림 없이 원시 문자열로 보존해야 한다. | 39/39이 일치했다. 0.217은 0.217로 보존됐다. | 통과했다. |
| XLS 날짜 표시·백분율 원시 값 보존 | POI `external_name.xls`, `45538_classic_Header.xls`, `45538_classic_Footer.xls` | BIFF BRAI IFmt, 통합문서 FORMAT·원시 숫자 및 동일 표시 함수 | 날짜 범주 2개 차트를 ISO로 표시하고 백분율 4개 차트의 숫자를 원시 값으로 보존해야 한다. | 해당 표시가 변경됐으며 아래 값 보존 비교가 통과했다. | 날짜·백분율 실물은 통과했다. 시간·1904 체계는 합성 검증만 했다. |
| chartEx 군집 막대·파레토·txData 제목 | 해당 표본을 찾지 못했다. | POI 지정 세 폴더와 LO 전체의 OOXML 2,719개를 조사했다. | 실제 해당 종류와 셀 연결 제목으로 대조해야 한다. | chartEx 3개는 sunburst, boxWhisker, waterfall이었다. | 미검증이므로 ⬜를 유지한다. |
| chartEx 기존 종류 회귀 | POI `chartex.docx`, LO `forum-mso-de-138303.pptx` | chartEx 원시 차원 캐시·제목 | 기존 3개 파트의 값이 보존돼야 한다. | 원시 값 비교와 기존 제목 검사가 유지됐다. | 회귀 검증을 통과했다. |
| 자동 제목 삭제 상태 | 이름 있는 단일 계열·제목 없는 공개 파트 23개 | 원시 autoTitleDeleted=1 | 제목을 생성하지 않아야 한다. | 23/23에서 무제목이 유지됐다. | 삭제 상태만 실물 검증을 통과했다. |
| c:tx 없는 제목 요소의 자동 제목 생성 | 공개 HWPX를 포함한 실물 표본이 있다. | c:title에 c:tx가 없고 autoTitleDeleted=0이며 계열이 하나인 원시 XML이다. | 저장된 계열 이름을 제목으로 내야 한다. | 최종 출력 및 표본별 판정은 리뷰 벤치마크에 기록했다. | 사용자 결정에 따라 ⬜를 유지한다. |
| HWPX 표시 서식 연결 | hwp-public의 차트 포함 HWPX 41개다. | 원시 XML과 HEAD 대비 Markdown·JSON 출력이다. | 공용 서식과 원시 API 호환성을 함께 유지해야 한다. | 41개를 최종 출력 검증에 포함했다. | 세부 판정은 리뷰 벤치마크를 따른다. |

## 전수 비교와 제한

OOXML 후보 2,719개에서 차트가 있는 문서 91개, 차트 파트 140개를 찾았다. 구성은 DOCX 64파트, XLSX 38파트, PPTX 36파트, XLSM 2파트다. 손상된 ZIP·비ZIP 48개는 별도 오류로 집계하고 성공 표본으로 세지 않았다. 이 절의 기준 출력은 원래 구현 전 `107e18d`에서 확보한 이력이다.

140개 파트의 원시 Y 값은 2,873/2,873으로 일치했다. 표시 서식만 제거한 복제본의 표는 변경 전후 140/140이 동일했다. 새 계약의 날짜·시간 표시 및 백분율 원시 문자열 검사는 재실행에서 106/106이었다. HEAD 대비 바뀐 파트는 20개로, 제목 13파트·표 값 5파트·축 캡션 2파트다. 최종 변경 파일·값 수는 문서 출력 수준의 리뷰 벤치마크에서 집계한다.

전체 문서 리더로 91개 파일을 읽었을 때 실제 출력된 차트 표 127개는 모두 파트 단위 출력과 일치했다. 나머지 13파트는 문서 출력에 나타나지 않아 파트 해석만 검사했다. 정확한 HEAD 기준으로 문서 리더도 다시 실행하여 동일한 13파트가 미출력임을 확인했다. 미출력 파트는 LO `tdf147586.pptx`의 chart1, `tdf169781.pptx`의 chart1·2, `tdf123651.docx`의 chart1, `chart-in-footer.docx`의 chart1, `fdo78474.docx`의 chart2, `tdf115557.docx`의 chart1과 POI `123233_charts.xlsx`의 chart1~4, `56557.xlsx`의 chart1, `65016.xlsx`의 chart1이다. 파트가 해석된다는 사실을 문서 내 배치 지원의 증거로 바꾸지 않았다.

기존 범주 문제 14개는 남았다. LO `tdf126244.docx`의 다단계 범주 공백 3개와 `tdf138773.docx`의 비분산형 계열 범주 정렬 11개다. 이들은 전후 동일하며 원시 Y 값 불일치 0과 구분한다. 이번 변경이 모든 차트의 좌표 정합성을 완성했다는 뜻은 아니다.

XLS에서는 차트 문서 36개, 차트 97개, 비어 있지 않은 계열 Y 값 3,822개를 비교했고 불일치는 0개였다. 백분율은 숫자로 역변환하고 부동소수점 허용오차 `rel_tol=abs_tol=1e-12`로 비교했다. 이 비교는 빈 셀 위치 및 모든 X 좌표의 독립 정답 검사까지 의미하지 않는다. 차트·계열 수는 유지됐다.

## 재현과 테스트

다음 명령은 코퍼스를 수정하지 않는다. 비교용 `--baseline` 파일은 구현 전 같은 명령으로 저장한 JSON이다. JSON은 `.codex-work/`에만 보관한다.

```bash
/usr/bin/python3 -m scripts.probe_chart_details \
  --roots corpus/poi-src/test-data/spreadsheet \
  corpus/poi-src/test-data/slideshow \
  corpus/poi-src/test-data/document \
  corpus/lo-src \
  --baseline .codex-work/chart-details-all-before.json \
  --output .codex-work/chart-details-fix-after.json
/usr/bin/python3 -m scripts.probe_chart_details_integration \
  --probe .codex-work/chart-details-fix-after.json \
  --baseline .codex-work/chart-details-integration-before.json \
  --output .codex-work/chart-details-fix-integration.json
/usr/bin/python3 -m scripts.probe_xls_chart_details \
  corpus/poi-src/test-data/spreadsheet \
  corpus/lo-src/sc/qa/unit/data/xls \
  --baseline .codex-work/xls-chart-before.json \
  --output .codex-work/xls-chart-after.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

새 테스트는 먼저 실패를 확인한 뒤 구현했다. 1차 핵심 동작은 14개 실패를 확인했고, 이후 원본 셀 서식·날짜시간·HWPX 표시·chartEx 숫자 서식·3차원 축 문제도 실패를 재현했다. BIFF8에서는 6개 실패를 먼저 확인했다. 이전 리뷰 당시 기존 테스트의 단언은 수정하지 않았다. 앞선 3,316개 통과 기록은 리뷰 전 결과다. 리뷰 후 최종 전체 테스트 수와 Ruff·diff 검사 결과는 `.codex-work/report.md`의 리뷰 반영 절에 기록한다. 3차 리뷰에서 경과 시간까지 원시 값으로 바꾼 정책은 4차 지시에서 정정됐다. 시트의 `[h]:mm:ss` 1.5는 다시 `36:00:00`이며 합성 벤치마크 기대 두 곳과 해당 검증 단언 두 곳도 복구했다. `[s]`는 총 초를 표시한다. c:title 없는 자동 제목 테스트 두 개는 검증된 c:title 존재 픽스처로 고쳤으며, 제목이 없는 경우 무제목임을 새 테스트로 검증한다. 정확한 변경 근거는 리뷰 보고서에 기록한다.

README와 CHANGELOG는 수정하지 않았다. 실물이 없는 항목을 ✅로 제안하지 않는다.
