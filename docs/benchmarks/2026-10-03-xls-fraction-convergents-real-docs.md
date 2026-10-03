# 가변 분모 분수의 Excel 선택 규칙 검증

2026-10-03. 공개 Apache POI `54686_fraction_formats.xls` 와 Excel 이 저장한 같은 이름의 `.txt` 표시값을 정답으로 썼다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| XLS·XLSX 숫자 서식: 가변 분모 분수 | `54686_fraction_formats.xls`·`.txt` D·E·F·M열 | Excel 저장 `.txt` 1,416셀(`# ?/?`·`# ??/??`·`# ???/???`·`# ??/?????????` 각 354셀) | 공백 정규화 후 Excel 표시와 같아야 한다 | 1,416/1,416셀 일치(이전 1,300). 고정 분모 포함 표 전체 3,540/3,540 | 통과 |
| 회귀: 공개 XLS 전체 숫자 셀 | POI test-data·LibreOffice 테스트 문서의 XLS 720개(정렬 셀 705,683개) | 변경 전 HEAD 와 셀 표시 해시 비교 | 분수 셀 외에는 바뀌지 않아야 한다 | 바뀐 셀 116개, 모두 분수 서식이며 위 표의 개선분과 같다 | 통과 |
| 회귀: 공개 XLSX 전체 숫자 셀 | 같은 코퍼스의 XLSX 352개(정렬 셀 320,856개) | 변경 전 HEAD 와 셀 표시 해시 비교 | 바뀌지 않아야 한다 | 바뀐 셀 0개 | 통과 |
| 회귀: `TEXT()` 캐시 | POI 서식 테스트 XLSX 의 `TEXT()` 캐시 832행 | Excel 이 계산해 저장한 캐시 문자열 | 정확 일치가 줄지 않아야 한다 | 266/832행 그대로(얻음 0, 잃음 0) | 통과 |

## 규칙

Excel 은 분수 부분을 가장 가까운 분수로 고르지 않는다. 0.94 를 `# ?/?` 로 표시하면 8/9(오차 0.051)가 아니라 1(오차 0.06)을 내고,
0.7 은 5/7 이 아니라 2/3 을 낸다. 표 전체를 설명하는 규칙은 연분수 전개의 수렴분수 가운데 분모가 자릿수 한도(9, 99, 999 …)를 넘기 직전의
것을 고르는 것이다. 중간 분수(semiconvergent)는 고르지 않는다.

전개는 정확한 유리수가 아니라 부동소수로 한다. 0.1 의 실제 이진값은 0.1 보다 조금 크므로 정확히 전개하면 1/9 가 수렴분수로 나오지만,
부동소수에서는 `1 / 0.1` 이 정확히 10.0 이라 첫 수렴분수가 1/10 이 되고 `# ?/?` 에서 0 이 된다. Excel 도 0 을 낸다. 0.89·0.87 처럼
몫이 정수에 아주 가까운 값도 같은 이유로 갈린다. 이전에 시험한 "정확한 유리수의 수렴분수만" 가설은 이 차이 때문에 26셀이 틀렸다.

## 재현

```bash
python -m scripts.probe_xls_fraction_excel corpus/poi-src/test-data/spreadsheet --before-code <HEAD 소스 사본> --output <출력>
python -m scripts.probe_spreadsheet_format_hashes snapshot corpus/poi-src/test-data corpus/lo-src --suffix xls --output <출력>
python -m scripts.probe_chart_review_text_cache snapshot --corpus corpus/poi-src/test-data/spreadsheet --tree <소스> --output <출력>
```

전후 출력은 저장소 밖 작업 디렉터리에 해시로만 남겼다.
