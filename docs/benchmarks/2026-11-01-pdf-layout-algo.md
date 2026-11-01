# PDF 레이아웃 순수 Python 계산량 최적화

기준 커밋: `d9683a9c100d7359e2fb87c0b9765ede38f8328c`.
동일 커밋의 기존 detached checkout `base-d9683a9`와 비교했다. 커밋·푸시는 하지 않았다.

## 변경 범위

- 표: 페이지 기준점을 한 번 계산해 색인·숫자 행 보강·셀 배정에 재사용한다. 숫자 행 후보는 조각을 원래 행 구간에 한 번 배정한다. 기존 작업량 상한, 엄격한 경계 비교, 조각 순서는 보존한다. 괘선 성분이 없는 페이지는 색인을 만들지 않는다.
- 각주·미주: 두 콘텐츠 추출 경로 모두 비유한 좌표를 거르므로 리더에서 방향 분류 목록을 공유한다. 독립 호출의 유한성 검사는 유지한다. 각주 참조가 생긴 페이지는 분리 표지의 폭 변경을 고려해 미주 단계에서 재검사한다.
- 제목: 조립 중 문단 문자열을 한 번만 얻는다.
- 댓글 앵커: 임시 Document 없이 깊이 32·동일 객체 중복 억제·기존 순서를 보존하는 순회로 찾는다. 댓글이 없으면 순회하지 않는다.
- CMap: 공개 `code_lengths` 집합의 값이 바뀔 때만 정렬한다. 단일 BMP 비서로게이트 범위는 `chr`를 쓰고, 서로게이트·다중 코드 단위·오버플로는 기존 UTF-16 경로를 유지한다. 매핑 상한과 진단은 그대로다.
- 링크: 영역 후보가 없는 조각은 글자 루프를 생략한다. 기하 검사·이웃 검사 예산은 그대로다.
- 선분: 두 원소 정렬을 같은 안정적인 비교·교환으로 바꾼다. NaN·무한대·부호 있는 0을 포함한 49쌍을 기존 정렬과 대조했다.

`content.py`, `objects.py`, `structure.py`, C 소스, 공용 문서 모델, README, CHANGELOG는 수정하지 않았다. 런타임·빌드 의존성을 추가하지 않았다.

이미지는 PNG 바이트 유무가 이미지 요소·Markdown 자리표시자 생성에 관여하고 추출 단계에서 진단도 발생한다. 지연 인코딩은 모델·자산 계약 변경 없이 안전하게 분리하지 못하므로 유지했다. AES도 수정하지 않았다.

## 입력과 출력 동일성

현재 디스크에서 지정된 공개 코퍼스 PDF는 **2,281건**이다. 지시문의 2,362건보다 81건 적다. 확인되지 않은 81건을 검증했다고 주장하지 않는다. 내부 문서는 사용하지 않았다.

| 코퍼스 | PDF 수 |
|---|---:|
| pdfjs-src | 983 |
| lo-src | 24 |
| press-pairs | 375 |
| press-pairs-holdout | 217 |
| press-pairs-holdout2 | 232 |
| press-pairs-holdout3 | 233 |
| press-pairs-holdout4 | 217 |
| 합계 | 2,281 |

300개 고정 표본에는 공개 `ContentStreamCycleType3insideType3.pdf`, `IdentityToUnicodeMap_charCodeOf.pdf`, `Pages-tree-refs.pdf`, `ThuluthFeatures.pdf` 등이 포함된다.

휴리스틱이나 임계값을 보정하지 않았다. 보류 코퍼스는 최종 출력 동일성 확인에만 사용했다.

| 검증 | 문서 | Markdown 차이 | JSON 차이 | 텍스트 차이 | 진단 차이 | 실패 |
|---|---:|---:|---:|---:|---:|---:|
| 표 변경 직후 | 300 | 0 | 0 | 0 | 0 | 0 |
| 각주·제목·순회 변경 직후 | 300 | 0 | 0 | 0 | 0 | 0 |
| CMap 변경 직후 | 300 | 0 | 0 | 0 | 0 | 0 |
| 링크·선분 변경 직후 | 300 | 0 | 0 | 0 | 0 | 0 |
| 최종 가속 ON | 2,281 | 0 | 0 | 0 | 0 | 0 |
| 최종 가속 OFF | 2,281 | 0 | 0 | 0 | 0 | 0 |

모든 문서에 네 해시가 존재한다. 누락·실패 변화·JSON 폴백도 모두 0이다. 전체 해시 수집은 4 worker 병렬 검증이며 그 시간은 성능 근거로 쓰지 않았다.

입력 목록 SHA-256:

- 300개 표본: `479a3160522b9f8ee10f6ff1d1a3c041cfa722b260e77691a42e89e13d0edd2a`
- 전체 목록: `658a1dbe7c158bc841fd9a6978bbe9d31f98ea3d620418ea1ab2fa9b9aeaf7d8`

## 측정 방법

`scripts/benchmark_pdf_layout.py`는 고정 JSON 파일 목록을 받는다. 기본 모드는 기존 `probe_output_speed.measure_file`로 네 출력 해시를 수집하고 기존 `compare`로 대조한다. `--parse-only`는 Dochan 생성 시간만 합산하며 직렬화·프로파일 시간을 성능 측정에서 제외한다.

전체 테스트·해시 수집 프로세스가 끝난 뒤 단일 worker, 매 실행 새 프로세스로 **전·후·후·전·전·후** 순서로 측정했다. 두 인터프리터의 ON/OFF 조합마다 이 순서를 따로 수행한다. 각 변형의 세 번 중앙값을 비교한다. 실행 시간 변동이 있어 각 회차 원시값도 공개한다. 개선율은 이 300개 표본과 해당 실행 환경에 한정되며 모든 PDF의 동일한 향상을 보장하지 않는다. cProfile은 시간 측정 후 별도로 실행한다.

환경: Xcode Python 3.9.6 / Pillow 11.3.0, bench venv Python 3.12.12 / Pillow 13.0.0. Python별 전후 환경은 동일하며 서로 다른 Python의 절대 시간만으로 구현 효과를 판단하지 않는다. C 확장은 Xcode 3.9의 기존 빌드 명령으로 빌드했다. 기준과 변경본 네 확장의 arm64 `__text` 섹션이 동일함을 확인했다.

재현 예시(경로 변수는 실행 환경에 맞게 지정):

```sh
"$BENCH_PYTHON" -m scripts.benchmark_pdf_layout --source "$BENCH_BASE" \
  --manifest .codex-work/all-pdf.json --workers 4 --output .codex-work/check-before.json
"$BENCH_PYTHON" -m scripts.benchmark_pdf_layout --source . \
  --manifest .codex-work/all-pdf.json --workers 4 --output .codex-work/check-after.json
"$BENCH_PYTHON" -m scripts.probe_output_speed compare \
  .codex-work/check-before.json .codex-work/check-after.json
"$BENCH_PYTHON" -m scripts.benchmark_pdf_layout --source . \
  --manifest .codex-work/sample-pdf-300.json --parse-only --output .codex-work/time.json
```

OFF는 `DOCHAN_DISABLE_ACCEL=1`로 실행한다. ON은 이 변수를 해제한다. 프로파일은 같은 parse-only 명령에 `--profile .codex-work/parse.prof`를 추가한다.

## 교대 측정 결과

단위: 초. 각 칸의 세 수치는 해당 변형의 실행 순서다.

| Python | 가속 | 전 3회 | 후 3회 | 전 중앙값 | 후 중앙값 | 감소율 |
|---|---|---|---|---:|---:|---:|
| 3.9.6 | ON | 11.857 / 13.019 / 12.377 | 10.724 / 12.458 / 10.905 | 12.377 | 10.905 | 11.90% |
| 3.9.6 | OFF | 33.707 / 39.219 / 39.181 | 31.641 / 31.902 / 31.732 | 39.181 | 31.732 | 19.01% |
| 3.12.12 | ON | 7.143 / 7.120 / 7.142 | 6.369 / 6.374 / 6.401 | 7.142 | 6.374 | 10.75% |
| 3.12.12 | OFF | 19.203 / 21.947 / 20.141 | 19.922 / 22.540 / 18.823 | 20.141 | 19.922 | 1.09% |

가속 ON은 Python 3.9에서 11.90%, 3.12에서 10.75% 감소해 두 인터프리터 모두 목표 10%를 넘었다. OFF의 Python 3.12는 1.09% 감소에 그쳤다. 가속 ON이 이번 작업의 주 측정 조건이다. OFF는 전체 파싱에서 Python 콘텐츠 해석이 차지하는 비중이 크므로 별도로 기록했다. 개선율은 위 중앙값 비율이며 프로파일 시간이나 병렬 해시 수집 시간에서 계산하지 않았다.

## cProfile 전후

가속 ON, 같은 300개 parse-only. 호출 수는 재귀 호출을 포함한다. 시간은 자체 / 누적 초이며, 프로파일 오버헤드가 있으므로 위 성능 개선율과 구분한다. 해당 실행에서 호출되지 않은 함수는 0으로 표시한다.

### Python 3.9.6

| 함수 | 호출 전 → 후 | 자체 전 → 후 | 누적 전 → 후 |
|---|---:|---:|---:|
| `tables.py:_reference_point` | 1,647,761 → 405,530 | 0.746 → 0.213 | 0.824 → 0.232 |
| `tables.py:_numeric_row_rules` | 1,037 → 1,037 | 0.133 → 0.148 | 0.971 → 0.533 |
| `tables.py:_assign_text` | 987 → 987 | 0.185 → 0.177 | 0.894 → 0.766 |
| `tables.py:_short_dash_runs` | 840 → 840 | 0.149 → 0.150 | 0.240 → 0.242 |
| `notes.py:_finite_fragment` | 910,608 → 0 | 0.139 → 0.000 | 0.578 → 0.000 |
| `notes.py:detect_notes` | 840 → 840 | 0.016 → 0.014 | 0.935 → 0.540 |
| `notes.py:endnote_references` | 840 → 840 | 0.062 → 0.060 | 0.892 → 0.463 |
| `document.py:_find_recursive` | 211,574 → 176,345 | 0.434 → 0.354 | 0.593 → 0.483 |
| `reader.py:_page_paragraphs` | 0 → 180 | 0.000 → 0.000 | 0.000 → 0.000 |
| `headings.py:sized_runs` | 6,115 → 6,115 | 0.194 → 0.162 | 0.478 → 0.437 |
| `annotations.py:_attach_unique_links` | 850 → 850 | 0.263 → 0.234 | 0.376 → 0.336 |
| `cmap.py:decode` | 516,601 → 516,601 | 0.420 → 0.335 | 0.667 → 0.416 |
| `cmap.py:_parse_bfrange_block` | 523 → 523 | 0.099 → 0.108 | 0.485 → 0.178 |
| `cmap.py:_int_to_text` | 527,909 → 16,384 | 0.099 → 0.003 | 0.335 → 0.014 |
| `content.py:writing_direction` | 1,825,081 → 1,369,777 | 0.203 → 0.152 | 0.273 → 0.203 |
| `sorted` | 1,404,657 → 98,136 | 0.379 → 0.152 | 1.084 → 0.735 |
| `all` | 1,842,705 → 931,309 | 0.334 → 0.176 | 1.116 → 0.556 |
| `ImagingEncoder.encode` | 59 → 59 | 0.266 → 0.256 | 0.266 → 0.256 |

프로파일 전체: 호출 110,355,992 → 90,518,681, 자체 시간 합계 16.960 → 14.562초.

### Python 3.12.12

| 함수 | 호출 전 → 후 | 자체 전 → 후 | 누적 전 → 후 |
|---|---:|---:|---:|
| `tables.py:_reference_point` | 1,647,761 → 405,530 | 0.542 → 0.140 | 0.636 → 0.164 |
| `tables.py:_numeric_row_rules` | 1,037 → 1,037 | 0.131 → 0.146 | 0.850 → 0.520 |
| `tables.py:_assign_text` | 987 → 987 | 0.183 → 0.173 | 0.801 → 0.755 |
| `tables.py:_short_dash_runs` | 840 → 840 | 0.114 → 0.124 | 0.218 → 0.230 |
| `notes.py:_finite_fragment` | 910,608 → 0 | 0.113 → 0.000 | 0.619 → 0.000 |
| `notes.py:detect_notes` | 840 → 840 | 0.055 → 0.025 | 0.856 → 0.420 |
| `notes.py:endnote_references` | 840 → 840 | 0.256 → 0.195 | 0.787 → 0.341 |
| `document.py:_find_recursive` | 211,574 → 176,345 | 0.274 → 0.237 | 0.458 → 0.395 |
| `reader.py:_page_paragraphs` | 0 → 180 | 0.000 → 0.000 | 0.000 → 0.000 |
| `headings.py:sized_runs` | 6,115 → 6,115 | 0.185 → 0.186 | 0.473 → 0.477 |
| `annotations.py:_attach_unique_links` | 850 → 850 | 0.243 → 0.226 | 0.412 → 0.389 |
| `cmap.py:decode` | 516,601 → 516,601 | 0.360 → 0.308 | 0.694 → 0.452 |
| `cmap.py:_parse_bfrange_block` | 523 → 523 | 0.095 → 0.082 | 0.524 → 0.162 |
| `cmap.py:_int_to_text` | 527,909 → 16,384 | 0.109 → 0.004 | 0.371 → 0.014 |
| `content.py:writing_direction` | 1,825,081 → 1,369,777 | 0.213 → 0.163 | 0.317 → 0.240 |
| `sorted` | 1,404,657 → 98,136 | 0.322 → 0.155 | 0.977 → 0.697 |
| `all` | 1,842,702 → 931,306 | 0.438 → 0.245 | 1.278 → 0.703 |
| `ImagingEncoder.encode` | 59 → 59 | 0.204 → 0.205 | 0.204 → 0.205 |

프로파일 전체: 호출 109,335,701 → 89,521,139, 자체 시간 합계 16.177 → 14.492초.

## 테스트

| 최종 검사 | 결과 |
|---|---|
| 전체 테스트, 가속 ON | 6,711 passed · 36 skipped · 14 xfailed |
| 전체 테스트, 가속 OFF | 6,702 passed · 45 skipped · 14 xfailed |
| Ruff (`dochan scripts tests setup.py`) | 통과 |
| `git diff --check` | 통과 |

전체 테스트는 `python -m pytest tests/ -q -p no:cacheprovider`로 실행했다. OFF에서 늘어난 9개 skip은 가속기 전용 테스트다. 지시문에 적힌 이전 테스트 수 대신 실제 실행 결과를 기록했다. 추가 회귀 테스트 9개 중 계산량을 제한하는 테스트는 기존 코드에서 실패함을 먼저 확인했다. 기존 테스트의 단언은 변경하지 않았다.

원시 증거는 `.codex-work/`의 `sample-*.json`, `all-*.json`, `compare-all-*.log`, `*-red.log`, `*-green.log`, `tests-final-*.log`, `timings.json`, `profile-*.prof`, `accel-text-hashes.json`에 있다. 이 폴더의 경로 목록·대용량 원시 산출물은 커밋 대상이 아니다.
