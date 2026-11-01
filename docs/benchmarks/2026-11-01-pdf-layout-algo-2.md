# PDF 레이아웃 2차: 반복 계산 축소

## 범위와 기준

- 기준 커밋: `9f0cf6a61a330e3b9584f99c5b268b681c1a02fd` (`w-pdf-speed2`). 현재 워크트리와 시작 HEAD 동일.
- 기준/현재의 ABI3 가속 모듈 5개 SHA-256 동일. Python 3.9.6 / 3.12.12에서 scanner/interpreter/line/object backend 모두 `c` 확인.
- 변경: `tables.py`, `notes.py`, `annotations.py`, `utils/heading_font.py` 및 회귀 테스트. C·content·objects·structure·AES·README·CHANGELOG 변경 없음. 커밋하지 않음.

## 구현

- 제목 글꼴 표본: 종류별 5회 검색을 기존 모델의 순환/깊이 제한을 그대로 쓰는 1회 순회로 합쳤다. 미지의 note type은 기존처럼 제외 집합에 넣지 않는다.
- 표: 숫자 행 판정과 셀 배정의 동일 조각 순서에 대한 줄 조립 결과를 페이지 안에서 재사용한다. 정렬 키는 쓰기 방향을 한 번만 계산한다. 표 후보가 없는 페이지의 점선·기준점 계산을 생략한다. 연속 동일 방향의 정규화를 재사용하고 점선이 될 수 없는 사선의 길이 계산을 생략한다.
- 미주: 연속 표지의 기준선·크기가 같으면 세로 후보를 재사용한다. 마지막 질의 하나만 보관하고 기하 검사 예산은 매 표지마다 기존 후보 수만큼 차감한다. 각주 정의에 필요한 `)` 조각과 기존 본문 크기 반올림·0.9 조건으로 계산한 보수적 상한을 만족하는 조각이 없으면 줄 조립을 생략한다. 미주 후보는 일치한 조각의 튜플만 만든다.
- 각주 조기 판정 근거: 줄 크기는 해당 줄의 `)` 조각 크기 이상이고, 본문 추정 크기는 전체 조각 최대 크기를 소수 셋째 자리로 반올림한 값 이하이다. 기존 `line.size < body * 0.9`의 필요조건만 검사하며 새 임계값을 도입하지 않았다.
- 링크: 영역이 없을 때 조각 기하 계산을 생략한다.
- 규칙·순서·임계값·예산 경고는 유지한다. 표 캐시는 한 페이지 호출에만 존재하며 줄을 수정하지 않는 판정/문단 조립에서 사용한다.

## 출력 불변 검증

공개 PDF는 pdf.js·LibreOffice·press-pairs 계열 전체 2,281개. 기타 형식은 POI·LibreOffice 전체와 hwp-public에서 확장자별 정렬한 HWP/HWPX 각 1,000개다. 내부 문서는 사용하지 않았다.

| 형식 | 파일 수 | 가속 켬 해시 차이 | 가속 끔 해시 차이 | 수집 실패(전/후, 양 모드) |
|---|---:|---:|---:|---:|
| pdf | 2281 | 0 | 0 | 0 |
| hwp | 1000 | 0 | 0 | 0 |
| hwpx | 1000 | 0 | 0 | 0 |
| docx | 1783 | 0 | 0 | 0 |
| pptx | 544 | 0 | 0 | 0 |
| xlsx | 352 | 0 | 0 | 0 |
| doc | 490 | 0 | 0 | 0 |
| ppt | 220 | 0 | 0 | 0 |
| xls | 720 | 0 | 0 | 0 |

각 파일의 JSON·Markdown·일반 텍스트·진단 SHA-256을 비교했다. 일곱 단계 변경 각각에도 고정 PDF 300개를 기준과 비교해 차이 0을 확인했다. 모든 수집이 완료되어 양쪽 실패를 동일성으로 간주한 파일은 없다.

## 교대 측정

검증 작업이 끝난 뒤 별도 프로세스로 동일 300개를 전·후·후·전·전·후 순서로 파싱했다. 각 실행은 같은 manifest 순서이며 파일 읽기와 파싱을 포함하고 출력 직렬화는 제외한다. 아래는 각 측 3회의 중앙값이다.

| Python | 가속 | 전 중앙값(s) | 후 중앙값(s) | 감소율 | 전 3회(s) | 후 3회(s) |
|---|---|---:|---:|---:|---|---|
| 3.9.6 | on | 7.8848 | 7.1546 | 9.26% | 7.8848 / 8.0275 / 7.8536 | 7.0332 / 7.1866 / 7.1546 |
| 3.12.12 | on | 5.5484 | 5.1071 | 7.95% | 5.5303 / 5.6009 / 5.5484 | 5.1084 / 5.1071 / 5.0145 |

목표 PDF 파싱 합계 10% 감소: 두 Python 모두 미달(3.9: 9.26%, 3.12: 7.95%).

## cProfile (Python 3.9, 가속 켬)

같은 표본을 별도 프로세스에서 다시 수집했다. 시간은 초이며 재귀 호출 수는 전체 호출 수다. 프로파일링 시간이 교대 wall-time과 같지는 않다.

| 함수 | 호출 수 전→후 | 자체 시간 전→후 | 누적 시간 전→후 |
|---|---:|---:|---:|
| `tables.py:build_tables` | 840→840 | 0.0520→0.0452 | 2.2585→2.2422 |
| `tables.py:_assign_text` | 987→987 | 0.1753→0.1654 | 0.7188→0.8436 |
| `tables.py:_numeric_row_rules` | 1037→1037 | 0.1234→0.1160 | 0.5390→0.5373 |
| `tables.py:_short_dash_runs` | 840→548 | 0.1538→0.1444 | 0.2453→0.2230 |
| `tables.py:_reference_point` | 405530→371811 | 0.2108→0.0668 | 0.2297→0.0669 |
| `tables.py:_reference_axes` | 0→1044 | 0.0000→0.0007 | 0.0000→0.0008 |
| `tables.py:_cell_lines` | 0→36501 | 0.0000→0.0379 | 0.0000→0.7115 |
| `headings.py:finalize_emphasized_headings` | 298→298 | 0.0109→0.0106 | 0.5744→0.1844 |
| `heading_font.py:body_font_size` | 298→298 | 0.0073→0.0074 | 0.5313→0.1419 |
| `heading_font.py:_sample_exclusions` | 298→298 | 0.0027→0.0103 | 0.5088→0.1196 |
| `document.py:find_all` | 1490→0 | 0.0049→0.0000 | 0.5027→0.0000 |
| `document.py:_find_recursive` | 176345→35269 | 0.3650→0.0755 | 0.4966→0.1025 |
| `notes.py:detect_notes` | 840→840 | 0.0138→0.0120 | 0.4656→0.4151 |
| `notes.py:endnote_references` | 840→840 | 0.0599→0.0313 | 0.5316→0.1962 |
| `annotations.py:_attach_unique_links` | 850→850 | 0.2305→0.0474 | 0.3325→0.0897 |
| `content.py:writing_direction` | 1369777→811188 | 0.1506→0.0904 | 0.2021→0.1217 |
| `content.py:assemble_lines` | 39092→29316 | 0.0111→0.0087 | 0.8442→0.9810 |
| `layout.py:merge_lines` | 26916→26916 | 0.0596→0.0956 | 0.1673→0.2029 |
| `cmap.py:_parse_bfrange_block` | 523→523 | 0.0880→0.0903 | 0.1560→0.1594 |
| 미주 valid 후보 listcomp | 123966→123966 | 0.2023→0.0029 | 0.2030→0.0029 |
| 미주 세로 후보 listcomp | 0→10347 | 0.0000→0.0142 | 0.0000→0.0145 |

프로파일 전체 자체 시간: 10.4338 → 9.4551초.

## 테스트와 재현

- on-final: `6819 passed, 36 skipped, 14 xfailed in 113.32s (0:01:53)`
- off: `6810 passed, 45 skipped, 14 xfailed in 107.15s (0:01:47)`
- `ruff check dochan scripts tests setup.py`: 통과. `git diff --check`: 통과.
- 새 회귀 테스트 8개: 순환/공유 노드 표본 집합, 동일 셀 줄 조립 재사용, 빈 링크 기하 계산, 미주 캐시 히트의 예산 차감, 정의 필수 문자가 없는 각주 처리, 연속 방향 정규화 재사용, 균일 크기 문서의 각주 생략, 반올림 경계 유지. 앞의 3개 호출 수 회귀 검사는 기준 소스에서 실패함을 확인했다. 추가 반복 계산 검사 3개도 구현 전 실패를 확인했다.

실행 자료는 `.codex-work/`에 보관했다. `measure.py`는 manifest를 읽어 `scripts.probe_output_speed.measure_file`로 동일한 네 출력 해시를 수집하며 `--source`와 같은 방식으로 대상 소스를 import 경로의 처음에 둔다. 입력 manifest는 `sample-pdf-300.json`, `all-pdf.json`, `all-other.json`이다.

```sh
python .codex-work/measure.py "$BASELINE" .codex-work/all-pdf.json .codex-work/pdf-on-before.json hash
python .codex-work/measure.py "$CURRENT" .codex-work/all-pdf.json .codex-work/pdf-on-after.json hash
python -m scripts.probe_output_speed compare .codex-work/pdf-on-before.json .codex-work/pdf-on-after.json
# DOCHAN_DISABLE_ACCEL=1 로 반복. 기타 형식은 all-other.json 사용.
# timing.sh: 3.9/3.12 × 가속 켬 × 전후 교대 6회 + 프로파일
python -m pytest tests/ -q -p no:cacheprovider
DOCHAN_DISABLE_ACCEL=1 python -m pytest tests/ -q -p no:cacheprovider
python -m ruff check dochan scripts tests setup.py
```

## 한계

- 10% 목표 미달. 표 복원 전체 누적 시간은 2.2585→2.2422초로 거의 같았고, `_assign_text` 누적 시간은 0.7188→0.8436초로 늘었다. 호출 수 감소 자체를 전체 속도 개선으로 간주하지 않는다.
- 이 결과는 고정 공개 표본과 현재 기기의 측정이다. 전체 코퍼스 수집 시간은 병렬 수집/테스트 부하가 섞이므로 성능 개선의 판정에는 사용하지 않았다.
- 문서가 반환한 진단은 해시로 동일성을 검증했으며, 진단이 없는 정상 문서라는 뜻은 아니다.
- HWP/HWPX는 요청한 표본 1,000개씩이며 전체 공개 HWP 코퍼스 검증으로 확대해 주장하지 않는다.
