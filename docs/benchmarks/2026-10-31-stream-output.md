# JSON·Markdown 파일 출력 스트리밍

2026-10-31. 기준 소스는 이 작업의 시작 커밋 `c1a6e0b`다. 파일 writer API를 추가하고
CLI `convert -o`와 배치의 JSON·Markdown 파일 출력에 연결했다. 문자열 반환 API와 출력 스키마는 유지한다.

## 구현과 범위

- `dochan.output.json_out.write_json(doc, fp, indent=2)`와 `Dochan.write_json(fp, indent=2)`:
  섹션·요소·표 행을 `Stream`으로 직렬화한다. 문자열 조각의 합계가 65,536자에 도달하면 파일에 쓰고 버린다.
  전체 결과 문자열이나 전체 dict 트리를 만들지 않는다. 단일 스칼라 문자열·한 행 자체는 메모리에 존재하므로
  절대적인 64KiB 메모리 상한은 아니다. 순환 참조와 직렬화 불가능한 값은 오류로 처리한다.
- `dochan.output.markdown.write_markdown(doc, fp)`와 `Dochan.write_markdown(fp)`:
  섹션 단위로 출력한다. 각주 상태는 문서 전체에 공유하고 정의는 말미에 출력한다. 단일 거대 섹션 내부의
  표 문자열까지 행 단위로 나누지는 않는다.
- Python 3.13+에서도 파일 writer는 자체 walker를 사용한다. 문자열 API의 표준 라이브러리 C 인코더 위임은
  유지하지만 파일 writer는 `indent=None`까지 지연 행을 유지한다. C 인코더의 문자열 반환 속도보다
  파일 출력 시 최대 메모리를 우선한다.
- 기존 `_atomic_write_text`가 문자열 또는 writer callable을 받는다. 임시 파일·flush·fsync·원자적 교체,
  경로/심볼릭 링크/입력 별칭 검사, 실패 시 임시 파일 정리 및 기존 대상 보존을 유지한다.
  표준 출력과 text 형식은 기존 경로다. 문자열 API만 가진 reader도 기존 호환 경로를 유지한다.
- 기존 파서의 출력량 제한과 배치 snapshot 512MiB 제한을 변경하지 않았다. 이 기준 버전에는 CLI 직렬화 파일
  전체 바이트를 따로 제한하는 정책은 없으며 새로 도입하지 않았다.

## 검증 방법

새 writer API와 지연 쓰기·실패 시 원자적 보존 테스트 7건이 구현 전에 실패함을 확인했다.
순환 참조·잘못된 타입 및 압축 Stream도 별도의 실패 테스트를 먼저 확인하고 구현했다.
추가 검증은 표·각주·자산, Unicode·실수·상속 타입·빈 값, 들여쓰기, 섹션 간 상태,
실제 XLSX의 CLI·batch 경로에서 문자열 API 호출 금지, Python 3.13의 전체 dict 생성 금지를 포함한다.

공통 규칙의 `git worktree add --detach`는 저장소 `.git` 쓰기 제한으로 실패했다.
따라서 같은 시작 커밋을 `git archive HEAD`로 별도 디렉터리에 추출했다. 작업 디렉터리를
복사하지 않아 미커밋 변경을 기준 소스에 포함하지 않았다. 커밋·스테이징은 수행하지 않았다.

## 재현

```bash
# BASELINE은 시작 커밋 소스, CORPUS는 읽기 전용 공개 코퍼스 루트
python -m scripts.probe_stream_output --before "$BASELINE" --after . \
  --output .codex-work/stream-measurements.json \
  "$CORPUS/poi-src/test-data/spreadsheet/46904.xls" \
  "$CORPUS/poi-src/test-data/spreadsheet/53446.xls" \
  "$CORPUS/poi-src/test-data/spreadsheet/bug62181.xlsx"
```

스크립트는 20열×5,000/9,900행 합성 XLSX(숫자·한글 공유 문자열 혼합)를 직접 만들고,
JSON·Markdown 각각 전·후·후·전·전·후 순서로 새 CLI 프로세스를 실행한다.
매번 출력 SHA-256이 같음을 확인하고 결과 파일을 지운다. 합성 입력도 작업 종료 시 정리한다.
공개 코퍼스는 읽기만 하며 결과 기록에는 공개 표본 이름·시간·RSS·해시·바이트 수만 남긴다.

## 전수 출력 동일성

`probe_output_speed collect --source "$BASELINE"`와 변경 후 수집을 `compare`로 대조했다.
Python 3.9.6, 작업자 8개, 15,216건(공개 14,959 + 내부 257)에서
JSON·Markdown·일반 텍스트·오류 목록 SHA-256 차이 **0**, 변환 실패 **0**, 직렬화 폴백 **0**이다.
내부 문서의 이름과 내용은 이 기록에 포함하지 않는다.

| 형식 | 문서 수 | 해시 차이 |
|---|---:|---:|
| HWP | 5,761 | 0 |
| HWPX | 2,973 | 0 |
| PDF | 2,362 | 0 |
| DOCX | 1,785 | 0 |
| XLS | 721 | 0 |
| PPTX | 545 | 0 |
| DOC | 492 | 0 |
| XLSX | 356 | 0 |
| PPT | 221 | 0 |

전수 수집은 테스트와 병행했고 기준 아카이브에는 비추적 C 확장 바이너리가 없었다.
따라서 이 수집의 단계 시간은 성능 비교에 사용하지 않는다. 해시 동일성의 근거로만 사용한다.
원자료는 비추적 작업 폴더의 `corpus-before.json`, `corpus-after.json`, `corpus-compare.log`에 있다.

## 테스트 결과

- Python 3.9.6 전체: 가속 켬 **6,579 passed / 36 skipped / 14 xfailed**,
  `DOCHAN_DISABLE_ACCEL=1`도 **6,579 passed / 36 skipped / 14 xfailed**.
- `ruff check dochan scripts tests setup.py` 통과.
- 기존 테스트의 단언은 변경하지 않았다. 새 테스트는 `tests/test_stream_output.py`에 있다.
- 첫 전체 실행에서 문자열 API만 구현한 reader의 호환 실패 18건이 드러났다.
  파일 writer가 있으면 사용하고 없으면 기존 문자열 경로를 유지하도록 수정했다.
  위 최종 전체 실행 두 번 모두 실패 0건이다.

## CLI 최대 RSS와 시간

Python 3.9.6, macOS `/usr/bin/time -l`, 표본·형식별 전·후·후·전·전·후 6회.
각 열은 전 3회와 후 3회의 중앙값이며 MB는 1,000,000바이트다.
벤치마크 중 이 작업의 테스트·전수 수집은 종료한 상태였다. OS 캐시·열 상태·외부 프로세스는 통제하지 않았다.

| 표본 | 형식 | 출력 바이트 | 최대 RSS 전 → 후 (MB) | 시간 전 → 후 (초) |
|---|---|---:|---:|---:|
| `synthetic-5000.xlsx` | json | 178,990,952 | 1,102.4 -> 209.3 | 2.25 -> 2.68 |
| `synthetic-5000.xlsx` | markdown | 1,149,062 | 210.8 -> 212.3 | 1.09 -> 1.06 |
| `synthetic-9900.xlsx` | json | 354,499,152 | 2,154.0 -> 385.1 | 4.82 -> 5.18 |
| `synthetic-9900.xlsx` | markdown | 2,285,862 | 390.4 -> 390.8 | 2.05 -> 2.05 |
| `46904.xls` | json | 231,978,366 | 913.9 -> 202.5 | 2.70 -> 3.31 |
| `46904.xls` | markdown | 1,190,457 | 203.9 -> 205.2 | 1.21 -> 1.21 |
| `53446.xls` | json | 334,631,379 | 1,286.6 -> 286.1 | 5.25 -> 6.12 |
| `53446.xls` | markdown | 1,123,853 | 285.8 -> 286.0 | 3.28 -> 3.29 |
| `bug62181.xlsx` | json | 311,626,893 | 1,308.3 -> 366.6 | 3.88 -> 4.61 |
| `bug62181.xlsx` | markdown | 1,226,916 | 367.4 -> 369.2 | 2.07 -> 2.06 |

총 60회 출력 SHA-256 동일. JSON RSS 감소는 72.0–82.1%이고 시간은 7.5–22.6% 증가했다.
전체 문자열의 합치기·UTF-8 인코딩 피크를 없앤 대신 조각 버퍼 관리와 파일 쓰기 비용이 추가된다.
속도 개선으로 해석하지 않는다. Markdown은 단일 시트를 섹션 하나로 만들기 때문에 RSS가 사실상 동일하다.

공개 표본은 Apache POI 테스트 데이터의 XLS 2개와 XLSX 1개다. `bug62181.xlsx`는 175,095셀이고
사전 변환에서 오류·경고가 없었다. 최초 후보 `deep-data.xlsx`는 기준 CLI부터 손상 ZIP으로 거부되어 제외했다.
이 표본의 실패를 성공 측정에 섞지 않았으며, 대체 XLSX만 `--no-synthetic`으로 별도 실행했다.

`time -l`은 최초 sandbox에서 `sysctl kern.clockrate`가 차단되었지만 권한 검토 후 정상 실행했다.
표의 모든 RSS는 실제 `time -l` 값이다. 스크립트의 명시적 `--rss-method resource` 대안은 표 측정에 사용하지 않았다.

원자료: 비추적 작업 폴더의 `stream-measurements.json`(48회), `stream-public-xlsx.json`(12회).
실행 로그에는 제외된 손상 ZIP의 실패도 남겼다. 임시 입력·출력 본문은 자동 정리했다.

Python 3.13.18에서도 최종 직렬화·writer 테스트 **250 passed**다. 파일 writer가 native-indent 플래그와
관계없이 `indent=None`·`indent=2`에서 `to_dict`를 호출하지 않는 단언을 포함한다.
Python 3.9 최종 집중 검증(로컬 경로 검사 포함)은 **251 passed**다.
