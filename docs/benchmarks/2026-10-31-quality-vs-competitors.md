# 공개 삼중 짝 PDF 정확도 대조 — 2026-10-31

이번 측정은 새 벤치마크의 기준선이다. 파서·런타임 변경이나 속도 개선은 없으며, 전후 성능 향상을 주장하지 않는다.

## 표본과 재현 조건

- 기준 소스: `c1a6e0bb0c11abccb902c328ed7a794ae5d35c22` + 이번 `scripts/bench_quality.py`.
- dochan Python 3.9.6, 경쟁 도구는 별도 가상환경 Python 3.12.12. 런타임/빌드 의존성 추가 없음.
- 공개 정책브리핑 코퍼스를 읽기 전용으로 사용. 내부 문서 사용 없음. HWP는 삼중 짝 확인·해시에만 사용하고 본문 정답은 HWPX에서 생성.
- 실제 폴더: 개발 HWP 111/HWPX 346/PDF 375, 보류 HWP 36/HWPX 207/PDF 217. 완전 삼중 짝 교집합은 개발 91/보류 30건이다. 과거 403/217건 전체를 측정한 결과가 아니다.
- 개발 smoke 2건 뒤 개발 전체 측정. 지표·추출 설정을 동결하고 보류 전체 30건은 단 한 번 측정했다. 보류2~4는 사용하지 않았다.
- 개발·보류 PDF ID 교집합 0건. 문서별 HWP/HWPX/PDF SHA-256, 정답/출력 텍스트 SHA-256을 원시 결과에 기록했다.
- 문서 병렬도 4, 각 추출 subprocess 제한 120초. 시간은 품질 비교의 성능 지표로 사용하지 않았다. API 기본 설정이며 OCR·LLM·맞춤 튜닝 없음.

```bash
# CORPUS: 읽기 전용 공개 코퍼스 루트, BENCH_PYTHON: 별도 가상환경 Python
python -m scripts.bench_quality --pairs-dir "$CORPUS/press-pairs" --split development \
  --venv-python "$BENCH_PYTHON" --output quality-development.json
# 보류는 사전에 계획한 단 한 번의 실행에만 사용한다.
python -m scripts.bench_quality --pairs-dir "$CORPUS/press-pairs-holdout" --split holdout \
  --venv-python "$BENCH_PYTHON" --output quality-holdout.json
```

출력 파일이 이미 있으면 덮어쓰기를 거부한다. `--venv-python`이 없거나 파일이 없으면 dochan만 측정한다(별도 smoke 성공). 기존 결과 분석은 JSON을 읽어 수행하며 보류를 재추출하지 않는다.

## 지표와 출력 계약

- 토큰 유사도: `compare_pdf_pairs.token_ratio` 그대로 사용. NFC + 공백 정규화 후 공백 토큰 SequenceMatcher, autojunk=False. 문서별 점수의 중앙값·산술평균. 문자 정확도나 의미 정확도가 아니다. 빈 문자열끼리는 기존 함수 정의상 1이다.
- 셀 일치율: 기존 `cell_hit_rate` 재사용. 정규화한 비어 있지 않은 정답 셀 중 후보 셀 텍스트 집합에 정확히 존재하는 비율. 동일 정답 셀 반복은 각각 분모에 들어가고 후보 중복은 세지 않는다. 표 대응·위치·병합·중복 개수 정확도를 뜻하지 않는다. 정답 셀이 없는 문서는 평균에서 제외.
- 표 복원율(행×열): 문서별 `(행 수, 최대 열 수)` 다중집합 교집합 합계 / 정답 표 수 합계. 후보 하나로 같은 모양의 여러 정답 표를 맞혔다고 세지 않는다. 내용이 다른 동형 표도 일치할 수 있고, 페이지 분할·중첩·병합 span은 평가하지 않는다. 원래 구조 전체의 복원율이 아니다.
- dochan: `to_plain_text()`, 재귀 `find_all("table")`, `is_heading`. PyMuPDF: `get_text()` + `find_tables().tables[].extract()`. pdfplumber: `extract_text()` + `extract_tables()`. pypdf/pdfminer.six는 텍스트만 추출.
- markitdown: `text_content`를 그대로 채점하고 줄 시작 ATX 제목(`#`~`######`)만 센다. Markdown 표식도 토큰 점수에 영향을 줄 수 있다. 이 PDF 경로가 제목을 제공하지 않는 경우 0이며 다른 도구의 제목 미지원은 —로 구별한다. 임의 제목 추론은 하지 않는다.
- 표 수는 추출 객체 수, 제목 수는 위 계약의 개수일 뿐 제목의 내용·레벨 정확도를 뜻하지 않는다. 미지원 지표는 —이고 0점으로 채우지 않는다.
- 실패 문서는 평균·중앙값 분모에서 제외하고 실패 수로 공개한다. 정답 생성 실패는 모든 도구의 실패 수에 포함하며 PDF 도구 자체 실패와 구분한다. 텍스트와 표 추출 중 하나라도 실패하면 해당 도구/문서는 실패 처리한다.

## 결과

개발 집계에서는 dochan이 높았지만 **보류 토큰 평균은 dochan 0.8485로 pdfplumber 0.9037 및 pdfminer.six 0.8582보다 낮았다**. 보류 dochan 제목 수는 99개로 HWPX 277개보다 적다. 일괄적인 정확도 우위를 주장할 수 없다.

### 개발: 91건

| 도구(버전) | 성공/실패 | 토큰 중앙값 | 토큰 평균 | 셀 일치 평균 | 표 복원율(행×열) | 추출 표 수 | 제목 수 |
|---|---:|---:|---:|---:|---:|---:|---:|
| dochan (1.15.0) | 90/1 | 0.9555 | 0.9292 | 0.3697 | 0.1813 | 601 | 159 |
| pymupdf (2.0) | 90/1 | 0.9388 | 0.8793 | 0.2484 | 0.0657 | 154 | — |
| pdfplumber (0.11.10) | 90/1 | 0.9337 | 0.8770 | 0.3076 | 0.1301 | 243 | — |
| pypdf (6.21.4) | 90/1 | 0.9341 | 0.8909 | — | — | — | — |
| pdfminer (20260107) | 90/1 | 0.9384 | 0.9000 | — | — | — | — |
| markitdown (0.1.9) | 90/1 | 0.5101 | 0.5345 | — | — | — | 0 |

채점된 HWPX 정답 표 761개, 제목 145개. 셀 평균 대상 89문서.
정답 생성 실패: `156783589`.

원시 결과: [quality-development.json](2026-10-31-quality-development.json).

### 보류(단회): 30건

| 도구(버전) | 성공/실패 | 토큰 중앙값 | 토큰 평균 | 셀 일치 평균 | 표 복원율(행×열) | 추출 표 수 | 제목 수 |
|---|---:|---:|---:|---:|---:|---:|---:|
| dochan (1.15.0) | 30/0 | 0.9524 | 0.8485 | 0.2400 | 0.2058 | 274 | 99 |
| pymupdf (2.0) | 30/0 | 0.9520 | 0.8164 | 0.1663 | 0.0449 | 130 | — |
| pdfplumber (0.11.10) | 30/0 | 0.9510 | 0.9037 | 0.1946 | 0.0607 | 159 | — |
| pypdf (6.21.4) | 30/0 | 0.9324 | 0.8429 | — | — | — | — |
| pdfminer (20260107) | 30/0 | 0.9401 | 0.8582 | — | — | — | — |
| markitdown (0.1.9) | 30/0 | 0.5434 | 0.5551 | — | — | — | 0 |

채점된 HWPX 정답 표 379개, 제목 277개. 셀 평균 대상 30문서.
정답 생성 실패: 없음.

원시 결과: [quality-holdout.json](2026-10-31-quality-holdout.json).

## dochan 열세 사례와 다음 검토 대상

아래는 문서 본문을 저장하지 않고 점수 차이만으로 선정했다. 원인 진단은 별도 과제이며, 보류 결과를 보고 파서 규칙을 수정하지 않았다.

| 묶음 | 공개 PDF ID | 지표 | dochan | 더 높은 도구 | 점수 |
|---|---|---|---:|---|---:|
| development | 156784181.pdf | token_ratio | 0.7466 | pdfminer | 0.9562 |
| development | 156783774.pdf | token_ratio | 0.7823 | pdfplumber | 0.9435 |
| development | 156783638.pdf | token_ratio | 0.8198 | pdfminer | 0.9607 |
| development | 156783553.pdf | cell_hit | 0.1579 | pymupdf | 0.3158 |
| development | 156783822.pdf | cell_hit | 0.5088 | pdfplumber | 0.6667 |
| development | 156784175.pdf | cell_hit | 0.1429 | pymupdf | 0.2857 |
| holdout | 156783095.pdf | token_ratio | 0.2864 | pymupdf | 0.9905 |
| holdout | 156782883.pdf | token_ratio | 0.5143 | pymupdf | 0.9590 |
| holdout | 156783330.pdf | token_ratio | 0.5060 | pdfplumber | 0.9383 |
| holdout | 156782929.pdf | cell_hit | 0.2810 | pdfplumber | 0.4298 |
| holdout | 156783095.pdf | cell_hit | 0.1045 | pdfplumber | 0.2521 |
| holdout | 156782883.pdf | cell_hit | 0.1224 | pdfplumber | 0.2115 |

개발 토큰 열세 문서는 읽기 순서·공백·누락 여부, 셀 열세 문서는 셀 분할·표 경계 여부를 후속 조사할 후보이다. 이 측정만으로 원인을 확정하지 않는다. 보류 사례는 이후 튜닝용으로 사용하면 더 이상 보류 정답이 아니므로 신규 보류 묶음이 필요하다.

## 해석 한계

같은 문서의 다른 형식을 기준으로 삼았지만, 정답 텍스트·표·제목은 **dochan의 HWPX 파서**가 생성한다. 독립 수동 주석 정답이 아니며 HWPX 파서의 누락·구조 표현이 dochan PDF에 유리하거나 불리할 수 있다. 개발 공개 ID `156783589`는 HWPX가 ERR와 빈 텍스트를 반환해 제외했다. 실패 원인을 경쟁 PDF 추출기의 문제로 돌리지 않는다.

사용 가능한 완전 삼중 짝에 한정된 편의 표본이다. 전체 보도자료·임의 PDF·스캔 PDF로 일반화할 수 없다. 문서 길이가 달라도 토큰 평균에서 한 문서의 가중치는 같고 표 복원율은 표 수로 가중한다. 서로 다른 출력 계약과 기본 옵션을 비교하므로 도구의 최대 성능 순위를 뜻하지 않는다. 총평이 좋더라도 위 열세 사례를 숨기지 않는다.

본문·셀 내용·예외 문자열은 결과 파일에 저장하지 않는다. 추출 본문은 메모리와 subprocess 익명 파이프에만 존재한다. 결과는 공개 ID, 도구·버전/묶음 메타데이터, 수치와 SHA-256만 포함한다.

## 검증

합성 지표 테스트: 최초 모듈 부재 실패 → 구현 중 미지원 제목(None) 집계 실패 → 수정 후 4 passed. 정규화, 부분 토큰 일치, 중복 표 모양 소모, 셀 점수, 미지원/빈 값, 실패 제외와 분모를 검증한다.

`/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider`: 6555 passed, 36 skipped, 14 xfailed (131.78초). `DOCHAN_DISABLE_ACCEL=1` 동일 명령: 6555 passed, 36 skipped, 14 xfailed (153.55초). `/usr/bin/python3 -m ruff check dochan scripts tests setup.py`: 통과. `git diff --check`와 신규 파일 별도 공백·로컬 절대경로 검사 통과. 커밋·스테이징하지 않았다.

JSON 2개 전체 9,187개 노드를 검사해 수치/null과 허용된 버전·묶음·해시만 저장됨을 확인했고, 합성 본문 canary가 score 결과에 포함되지 않음을 확인했다. 원시 행으로 summary를 재계산한 값이 저장된 집계와 같았으며, 두 묶음의 HWP/HWPX/PDF 파일 해시 교집합은 각각 0이었다.
