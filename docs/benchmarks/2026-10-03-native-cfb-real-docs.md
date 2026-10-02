# 자체 CFB 리더 실물 검증

2026년 10월 3일 `illuwa/w-native-cfb2`에서 자체 CFB 리더의 남은 호출부와 손상 입력 처리를 마무리했다. 구현 근거는 Microsoft [MS-CFB] 명세와 공개 파일의 바이트 관찰이다. 다른 프로젝트의 구현 코드는 읽거나 옮기지 않았고 `olefile`은 실행 결과를 대조하는 선택적 로컬 정답지로만 사용했다. README와 uv.lock은 수정하지 않았다.

리뷰 반영 후 전체 출력 비교와 변경 파일 목록은 [native-cfb2-fix 검증](2026-10-02-native-cfb2-fix-real-docs.md)에 있다. 이 문서의 컨테이너 수치는 리뷰 반영 후 재실행 값으로 갱신했으며, 이전 문제 표본 추적과 기존 테스트 수치는 별도 표시한 리뷰 전 기록이다.

## 판정 기준과 범위

이 작업은 README의 새로운 표시 요소를 추가하는 작업이 아니라 기존 HWP·DOC·PPT·XLS와 암호 패키지의 공통 컨테이너를 교체하는 작업이다. 단위 테스트와 실물 검증을 구분한다. 손상 컨테이너까지 모두 같은 결과라는 주장은 하지 않으며, 아래의 잔여 차이는 개별 원시 바이트 근거로 판정한다. CFB v4 실물은 없어 미검증이다.

[MS-CFB §2.2](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/05060311-bfce-4b12-874d-71fd4ce63aea)의 헤더, §2.3 FAT, §2.4 MiniFAT, §2.5 DIFAT, §2.6 디렉터리와 스트림 크기를 주소 해석의 근거로 삼았다. 이번 실행에서는 네트워크를 사용하지 않았다. 명세 위반을 수용하는 복구 동작을 명세가 허용한 정상 파일이라고 표현하지 않는다.

기본 모드에서는 해석 가능한 물리 바이트만 회수한다. 선언 FAT 개수 뒤의 슬롯은 할당 주소로 해석하지 않는다. 없어진 FAT 접미부는 기존 워드 위치를 보존한 채 제외하고, 미니 할당표의 마지막 부분 섹터에서는 실제로 있는 완전한 워드만 읽는다. 색상, 스트림의 미사용 자식 포인터와 루트 라벨은 주소를 바꾸지 않는다. 잘못된 디렉터리 분기는 제외하고 이름이나 부모 경로를 만들어 붙이지 않는다. 도달하지 않는 고아 엔트리는 노출하지 않는다.

짧은 체인과 잘린 마지막 섹터는 연속으로 확인된 접두부만 반환한다. 첫 섹터가 없으면 빈 접두부이다. `get_size()`는 선언 크기를 그대로 반환하므로 기존 `read_ole_stream()`이 실제 크기와 다름을 검출하고 기존 리더의 `doc.errors` 경로로 전달한다. 실제로 없는 데이터를 0으로 채우지 않는다. 복구 원인은 `parsing_issues`에 중복 없이 남는다. 내용 누락에 영향을 주는 범주는 공통 함수가 `doc.errors`에 범주별 한 번, 최대 16개 WARN으로 전달한다. 메타데이터만 다른 정상 문서에는 WARN을 추가하지 않는다. `raise_defects=DEFECT_INCORRECT`는 모든 편차를 거부하며, 내장 OLE 검증용 `strict_recovery=True`는 주소·절단 손상만 거부한다.

실제 데이터의 순환·교차 할당, 주소 체계를 결정할 수 없는 헤더와 루트 유형은 계속 거부한다. Byte Order 표식은 주소 산식에 쓰이지 않으므로 기본 모드에서는 메타데이터 편차로 기록하고 엄격 모드에서만 거부한다. 선언 범위 이후의 꼬리는 다른 스트림의 실제 소유권을 빼앗지 않는다. 실패한 체인 탐색이 남긴 소유권은 되돌린다. 실제 페이로드가 교차 할당된 파일은 먼저 연 스트림 뒤의 충돌을 거부하므로 모든 손상 파일에 읽기 순서 독립성을 보장하지 않는다.

파일 512 MiB, 스트림 256 MiB, 일반 섹터 1,048,576개, 디렉터리 엔트리 131,072개, 깊이 128, 경로 구성요소 합계 1,048,576개 상한을 유지했다. 반복 시도와 미사용 꼬리 탐색도 컨테이너당 누적 4,194,304단계로 제한했다. 이 수치는 명세 최대치나 코퍼스에서 실측한 최댓값이 아니라 구현의 자원 정책이다.

## 현재 전체 코퍼스

내부 `test_pairs`와 `local-samples`는 사용하지 않았으며 원본 문서를 복사하지 않았다. 확장자와 관계없이 매직을 확인했고, 같은 내용의 별도 경로는 별도 표본으로 계산했다. 6,761개 모두 v3/512바이트 헤더였다.

| 코퍼스 루트 | CFB 표본 수 |
| --- | ---: |
| `corpus/hwp-public/hwp` | 5,389 |
| `corpus/poi-src/test-data/document` | 162 |
| `corpus/poi-src/test-data/slideshow` | 145 |
| `corpus/poi-src/test-data/spreadsheet` | 420 |
| `corpus/lo-src` | 635 |
| `corpus/tika-test-docs` | 10 |
| 합계 | 6,761 |

이전 실행 이후 LibreOffice 표본이 262개에서 635개로 늘었다. 현재 코퍼스로 수정 전 HEAD를 재검증한 기준선은 완전 일치 6,657개, 자체 리더만 거부 73개, 양쪽에서 열리지만 검증 차이가 있는 파일 17개, 양쪽 거부 14개였다. 이전 보고서의 50개·10개·56개는 별도로 원래 파일을 매핑해 재검증했다.

| 현재 최종 판정 | 파일 수 | 판정의 의미 |
| --- | ---: | --- |
| 완전 일치 | 6,722 | 저장소·스트림 목록, 선언 크기, 실제 읽은 크기와 SHA-256이 같았다. |
| 양쪽 열림, 검증 차이 | 20 | 실제 교차 할당·순환, 해석 불가능한 이름 제외, 검증 크기 상한 등을 아래 표에서 구별한다. |
| olefile만 열림 | 5 | 주소에 영향을 주는 잘못된 헤더 상수 3개, 잘못된 루트 유형 1개, 디렉터리 순환 1개이다. |
| 양쪽 거부 | 13 | 해석 불가능한 헤더를 양쪽이 거부했다. 오류 문구 동일성을 성공으로 세지 않는다. |
| 자체 리더만 열림 | 1 | 손상된 미사용 영역과 분리하여 실제 존재하는 스트림 접두부를 회수했다. |

양쪽이 열린 파일의 기준 스트림 77,281개 중 77,252개가 크기와 해시까지 검증됐다. 나머지 29개를 통과로 계산하지 않았다. 바이트 차이는 손상 PPT 3개의 Current User 스트림에 남았다. 실제 루트 체인은 1,024바이트인데 미니 스트림 시작은 루트 오프셋 1,728이므로, 참조가 내는 64바이트 대신 자체 리더가 빈 물리 접두부를 반환하는 것이 주소 근거에 맞다. 나머지 공통 스트림의 읽힌 바이트 차이는 없다. 공개 HWP 루트의 5,389개와 Tika 10개는 모두 완전 일치했다. DIFAT 사용을 선언한 헤더는 132개이며 정상 공개 HWP 121개는 완전히 일치했다. 나머지는 손상 헤더의 비정상 개수까지 포함한다.

## 리뷰 전 실행에서 이전 작업의 정확한 문제 표본 재검증

이전 워크트리의 `cfb-discrepancy-classification.json`과 `cfb-conversion-classification.json`을 읽기 전용으로 확인했다. 이전 63개 파일 모두 현재 공개 코퍼스에서 파일명과 파일 크기로 유일하게 대응했고, 현재 SHA-256도 기록했다. 증가한 코퍼스의 새 표본 추첨 결과를 이전 56개 결과와 혼동하지 않았다.

| 이전 판정 | 이전 표본 | 현재 완전 일치 | 현재 양쪽 열림·차이 | 현재 자체 리더 거부 | 현재 양쪽 거부 | 현재 자체 리더만 열림 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| olefile만 열림 | 50 | 37 | 9 | 4 | 0 | 0 |
| 스트림 검증 차이 | 10 | 7 | 3 | 0 | 0 | 0 |
| 양쪽 거부 | 3 | 0 | 0 | 0 | 2 | 1 |
| 합계 | 63 | 44 | 12 | 4 | 2 | 1 |

이전 50개 열기 차이는 FAT/DIFAT 35개, 디렉터리 8개, 범위 밖 참조 4개, 헤더 2개, 개수 상한 1개였다. 현재는 이 중 46개를 열며, 남은 4개는 헤더 상수 2개·루트 유형 1개·디렉터리 순환 1개이다. 이전 스트림 차이 10개 중 7개가 완전히 일치하게 됐고, 3개는 실제 미니 스트림 순환 1개와 거대 선언 크기로 인한 검증 상한 2개이다.

이전 변환 차이 56개를 같은 파일에서 다시 실행한 결과 **45개는 세 출력이 일치하고 11개는 차이가 남았다.** 나머지 11개 중 Markdown 차이는 3개, JSON·진단만 다른 것은 8개이다. Markdown 차이 3개는 루트 유형이 248인 `hang-18.ppt`, 미니 스트림 경계가 318,771,200인 POI `clusterfuzz-testcase-minimized-POIHSLFFuzzer-6614960949821440.ppt`, 디렉터리 순환이 있는 POI `clusterfuzz-testcase-minimized-POIHSSFFuzzer-5816431116615680.xls`이다. 정상 상수를 임의로 대입하거나 순환 경로를 임의로 선택해 텍스트를 만드는 대신 오류를 반환하는 경계가 더 정확하다. 이것을 원래 손상 전 문서의 본문 정답을 복원했다는 주장으로 확대하지 않는다.

`cfb-previous-recheck.json`은 이전 ID·현재 ID·공개 상대 경로·크기·SHA-256·이전 오류·현재 출력 해시·원시 바이트 감사 근거를 포함한다. [파일별 판정 문서](2026-10-03-native-cfb-residuals.md)에 11개 모두의 판정을 남긴다.

## 기능별 실물 판정

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 일반·미니 스트림과 저장소 경로 | POI `SampleDoc.doc`, `Simple.xls` 및 공개 HWP 5,389개이다. | olefile 목록·크기·SHA-256과 원시 할당 주소이다. | 실제 스트림이 동일해야 한다. | 전체 표본이 완전 일치했다. | 해당 범위에서 통과이다. |
| 미사용 DIFAT 슬롯 | LibreOffice `hang-5.ppt`, `hang-11.ppt`, `crash-2.ppt`이다. | 선언 FAT 개수 뒤의 손상 슬롯과 실제 참조하는 FAT의 바이트이다. | 미사용 주소를 따라가지 않고 유효한 스트림을 읽어야 한다. | PPT 실물 프로브 10개 전부 통과했다. | 통과이다. |
| 선언량 이후의 꼬리 교차 참조 | POI `45290.xls`이다. | Workbook은 43섹터를 선언하지만 44번째 링크는 디렉터리 섹터 44이다. | 선언된 22,016바이트만 읽고 디렉터리를 데이터로 노출하지 않아야 한다. | 스트림 전체 비교가 일치했다. | 통과이다. |
| 잘린 접두부 | POI `clusterfuzz-testcase-minimized-POIFuzzer-5429732352851968.ppt`, `crash-9bf3cd4bd6f50a8a9339d363c2c7af14b536865c.xlsx`이다. | 선언 8,872바이트와 실제 4,452바이트의 원시 범위 및 olefile 해시이다. | 없는 바이트를 보충하지 않아야 한다. | 읽은 길이와 해시가 일치했다. | 통과이다. |
| 미사용 MiniFAT 개수 | POI `clusterfuzz-testcase-minimized-POIHSSFFuzzer-6537773940867072.xls`이다. | 루트 크기 0, 시작 ENDOFCHAIN, 미사용 개수 808,150,272이다. | 선언 개수만큼 메모리를 할당하지 않아야 한다. | 실제 일반 스트림 접두부가 일치했다. | 통과이다. |
| 부분 FAT·디렉터리와 고아 엔트리 | 공개 손상 표본 63개 및 확대 기준선 104개이다. | 파일별 원시 슬롯·주소·길이를 감사 JSON에 기록했다. | 해석 가능한 부분만 노출하고 주소를 추정하지 않아야 한다. | 파일별 판정을 아래 표에 기록했다. | 개별 판정 범위에 한정한다. |
| v4와 4,096바이트 섹터 | 실물 표본이 없다. | 합성 v4 테스트만 있다. | 실물에서 검증해야 한다. | 실물 0개이다. | 미검증이며 ⬜ 유지이다. |

## 리뷰 전 형식별 최대 300개 표본의 변환과 퍼즈

같은 `Dochan` 코드에서 컨테이너 백엔드만 바꾸고 Markdown, JSON, errors 문자열의 해시를 비교했다. 시드 20261003과 형식별 최대 300개를 사용했다.

| 형식 | 표본 | 완전 일치 | 차이 | 자원 상한으로 미검증 |
| --- | ---: | ---: | ---: | ---: |
| HWP | 300 | 300 | 0 | 0 |
| DOC | 300 | 284 | 16 | 0 |
| PPT | 213 | 206 | 7 | 0 |
| XLS | 300 | 293 | 0 | 7 |
| 합계 | 1,113 | 1,083 | 23 | 7 |

XLS 7개는 별도 프로세스에서 reference와 native를 각각 실행한 14회 모두 1,536 MiB RSS 감시 상한을 넘었다. 이를 CFB 교체의 회귀라고 볼 근거는 없지만 변환 일치 통과로 세지 않았다. `cfb-heavy-recheck.json`에 공개 상대 경로와 각 백엔드의 시간·RSS를 남겼다.

공개 CFB를 바이트 반전·자르기·구간 덮어쓰기·꼬리 추가로 5,000회 변형했다. 4,709개 컨테이너를 열었고 291개를 예상된 오류로 거부했다. 열린 컨테이너의 개별 손상 스트림도 검사했으며 예상 밖 예외·무한 실행에 따른 시간 초과·프로세스 비정상 종료·메모리 감시 상한 초과는 각각 0회였다. 최대 자식 RSS는 42.80 MiB, 최장 입력 처리 시간은 0.0278초였다. 이는 해당 표본과 시드의 관찰 결과이며 모든 악성 입력에 대한 증명은 아니다.

## 리뷰 전 테스트와 의존성

초기 7개 실패는 기존 monkeypatch 대상 6개와 로컬 절대 경로 검사 1개였다. monkeypatch를 새 모듈로 옮긴 뒤 드러난 실제 IRM 경고 누락도 런타임 호출부 전환으로 고쳤다. 새 복구 동작마다 합성 바이트의 실패 테스트를 먼저 확인했다. 기존 함수 42개의 `assert` 문 81개는 AST 대조에서 바뀌지 않았다.

기존 CFB 테스트 다섯 곳의 실행 조건은 새로 요청된 복구 정책에 맞춰 바꿨다. `test_invalid_headers_and_directory_graph`, `test_invalid_allocation_chains`, `test_truncated_sector_is_clear_error`, `test_partial_last_sector_with_complete_declared_payload`는 엄격 모드에서 기존 거부 단언을 유지한다. `test_unused_absent_minifat_count_does_not_hide_regular_stream`도 실제 필요한 MiniFAT 부재의 엄격 거부를 유지한다. 기본 모드의 부분 회수와 실제 순환·교차 할당 거부는 별도 테스트로 검증한다. 기존 기본 모드의 무조건 거부를 그대로 유지했다고 주장하지 않는다.

`crypto/legacy.py`와 남은 프로브 네 개를 자체 모듈로 전환했다. `pyproject.toml`에서 olefile 제거는 이전 HEAD에 이미 반영되어 있었다. 런타임·일반 테스트는 olefile을 요구하지 않으며, 비교 테스트는 `pytest.importorskip`을 사용한다. AGENTS, THIRD_PARTY와 Phase 5 문장을 현 상태로 수정했다. 검증기의 자식 종료와 파이프 결과 도착 사이 경쟁 조건은 결정적 재현 테스트로 고쳤다.

전체 테스트는 **3,370 passed, 24 skipped, 14 xfailed**이며 28.17초였다. `sitecustomize.py`에서 `sys.modules['olefile'] = None`을 설정해 모든 자식 프로세스의 import까지 차단한 실행은 **3,369 passed, 25 skipped, 14 xfailed**이며 28.49초였다. 추가 skip 하나는 선택적 비교 테스트이다. stdin으로 pytest를 실행한 첫 격리 시도는 macOS spawn이 `<stdin>`을 다시 열 수 없어 실패했으며, 실제 `python -m pytest`와 자식에게 상속되는 import 차단으로 재검증했다. Ruff 전체 검사, 변경 Python 16개 파일의 3.9 구문 검사와 공백 검사도 통과했다.

비스트림 객체를 `get_size` 또는 `openstream`으로 요청한 오류는 관찰한 기존 API와 같은 `OSError('this file is not a stream')`로 유지했다. 이 차이를 정확성 개선이라고 주장하지 않고 실제 문자열 차이를 제거했다. 비교 도구는 남은 차이를 보고하므로 비교 명령 자체는 종료 코드 1을 반환하며, 이를 무조건 성공한 명령으로 보고하지 않는다.

현재 23개 변환 차이, 이전 표본 11개 변환 차이와 컨테이너 42개의 개별 수치는 [잔여 차이 판정 문서](2026-10-03-native-cfb-residuals.md)에 모두 기록했다. 동등한 손상 거부의 진단 문구 차이는 본문 정확성 우월성으로 포장하지 않는다. 모든 오류 문자열까지 완전히 같거나 모든 차이에서 본문 정확성 우월성이 입증됐다는 엄격한 전체 판정은 내리지 않는다.

## 재실행

코퍼스 경로는 읽기 전용 입력이다. `--mode convert --per-format 300` 또는 `--mode fuzz --iterations 5000`으로 같은 루트에서 변환·퍼즈를 실행한다.

```sh
/usr/bin/python3 -m scripts.compare_cfb_olefile \
  corpus/hwp-public/hwp \
  corpus/poi-src/test-data/document \
  corpus/poi-src/test-data/slideshow \
  corpus/poi-src/test-data/spreadsheet \
  corpus/lo-src corpus/tika-test-docs \
  --mode compare --jobs 4 --timeout 30 --memory-mb 1536 \
  --seed 20261003 --output .codex-work/cfb-compare-final.json

/usr/bin/python3 -m scripts.recheck_cfb_previous \
  corpus .codex-work/previous-cfb --output .codex-work/cfb-previous-recheck.json

/usr/bin/python3 -m scripts.probe_cfb_residuals \
  --corpus corpus --compare .codex-work/cfb-compare-final.json \
  --convert .codex-work/cfb-convert-final.json \
  --output .codex-work/cfb-residual-evidence.json \
  --previous .codex-work/cfb-previous-recheck.json

/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

비교기의 부모 프로세스는 자식의 RSS와 시간을 감시한다. macOS의 rlimit 지원과 별도로 부모의 종료 감시가 동작한다. olefile이 없으면 비교 부분은 이유와 함께 건너뛰며 일반 파싱·퍼즈·원시 바이트 감사는 동작한다. 파일 ID는 입력 목록과 표본 시드에 종속되므로 코퍼스가 바뀌면 이름·크기 또는 해시로 재매핑해야 한다.
