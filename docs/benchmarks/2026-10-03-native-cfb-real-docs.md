# 자체 CFB 리더 실물 검증

2026년 10월 3일 `illuwa/w-native-cfb`에서 `olefile` 런타임 의존성을 `dochan/cfb.py`로 교체했다. 구현 근거는 Microsoft 공개 [MS-CFB] 명세와 공개 코퍼스의 바이트 관찰이다. olefile과 다른 프로젝트의 구현 코드는 열거나 번역하지 않았다. olefile은 비교 프로그램 안에서만 선택적으로 가져와 읽기 결과를 정답으로 사용했다.

전체 코퍼스 100% 일치라는 인수 기준은 **미달**이다. 6,388개 중 6,325개는 저장소·스트림 목록, 선언 크기, 읽은 크기와 SHA-256이 모두 일치했다. 50개는 olefile만 열었으며, 10개는 열렸지만 일부 스트림 검증이 끝나지 않았고, 3개는 양쪽 모두 거부했다. 어느 쪽도 읽기에 실패하지 않은 공통 스트림의 바이트 해시 차이는 없었다. CFB v4 실물은 한 개도 없으므로 v4 실물 검증은 미검증이다. README는 수정하지 않았다.

## 명세와 구현 범위

헤더는 [MS-CFB §2.2](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/05060311-bfce-4b12-874d-71fd4ce63aea)를 따른다. 버전 3/4, 섹터 512/4,096바이트, 미니 섹터 64바이트와 4,096바이트 경계를 구현했다. 할당은 [§2.3 FAT](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/30e1013a-a0ff-4404-9ccf-d75d835ff404), [§2.4 MiniFAT](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/c5d235f7-b73c-4ec5-bf8d-5c08306cd023), [§2.5 DIFAT](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/0afa4e43-b18f-432a-9917-4f276eca7a73)를 근거로 작성했다.

디렉터리는 [§2.6.1](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/60fe8611-66c3-496b-b70d-a504c94c9ace)의 128바이트 엔트리, UTF-16 이름, 유형, 형제·자식 포인터와 크기를 읽는다. v3 크기의 상위 32비트는 명세 권고대로 무시한다. [§2.6.4](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/d30e462c-5f8a-435b-9c4c-cc0b9ea89956)의 이름 비교 원칙에 따라 UTF-16 단위의 비확장 대문자 키를 만든다. 형제 트리는 양쪽 링크를 반복문으로 순회하므로 생산자의 트리 균형이나 정렬 순서에 의존하지 않는다. 순환, 중복 엔트리와 동일 저장소 내 이름 충돌은 거부한다. 완전한 red-black 균형·적합성 검사기나 쓰기 API는 아니다.

메타데이터를 색인한 뒤 스트림 체인은 `openstream()`에서, 페이로드는 `read()`에서 읽는다. 루트 미니 스트림 전체를 메모리에 복사하지 않는다. 순환·중복 할당·잘린 체인·범위 초과는 `CFBError(OSError)`로 알리고 기존 문서 리더의 `doc.errors` 처리 경로를 유지한다. 읽지 않은 사용자 스트림까지 미리 검사한다고 주장하지 않는다. 모든 스트림을 열어 검사하는 비교 프로그램은 해당 검증을 끝까지 수행한다. 이 선택은 [§4.1의 지연 검증 설명](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/3c5249cc-1dc2-46f0-8faf-06c6a36f0085)과 부합한다.

CFB 자체 상한은 파일 512 MiB, 스트림 256 MiB, 일반 섹터 1,048,576개, 디렉터리 엔트리 131,072개, 저장소 깊이 128, 누적 경로 구성요소 1,048,576개이다. 정규화 이름은 `(부모 엔트리 ID, 이름 키)`로 한 번씩만 저장한다. 기존 문서 리더의 파일 200 MiB·스트림 100 MiB 상한은 그대로 적용된다. 이 수치는 형식 최대치나 실측 최대치가 아니라 악성 입력의 자원 사용을 제한하는 구현 정책이다.

## 기존 호출 계약

| API | 실제 사용과 유지한 의미 |
| --- | --- |
| `OleFileIO` | 경로 문자열, `Path`, 바이트와 `BytesIO`를 읽는다. 호출자가 준 파일 객체는 닫지 않는다. |
| 컨텍스트 관리자와 `close()` | 직접 연 파일의 수명을 관리한다. |
| `listdir(streams=True, storages=False)` | 기본 스트림 목록과 선택적 저장소 목록을 이름 구성요소 리스트로 반환한다. |
| `exists`, `get_size`, `get_type` | 슬래시 문자열과 이름 리스트 경로를 받는다. 저장소·스트림 존재를 구별하며 선언 크기를 제공한다. |
| `openstream` | `read(size)`, `read()`, `seek`, `tell`, `readinto`, `close`와 컨텍스트 관리자를 제공한다. |
| `isOleFile` | 매직 바이트만 판별한다. 외부 파일 객체의 위치를 복원한다. 구조 유효성 검사는 아니다. |
| 상수·예외 | `STGTY_STREAM`, `STGTY_STORAGE`, `DEFECT_INCORRECT`, `OleFileError`를 제공한다. |

런타임 호출부는 `reader.py`, `hwp/bin_data.py`, `office_binary/{doc,ppt,xls,ole_objects}.py`이다. `crypto/ooxml.py` 등 암호 모듈은 전달받은 컨테이너의 `get_size`·`openstream`만 사용하므로 수정할 필요가 없었다. `utils/bounded_io.py`는 설명 문자열만 바뀌었다. 기존 프로브 20개도 자체 모듈로 전환했다. `hwpx_inventory.py`는 직접 파일로 실행할 때 설치된 구버전 패키지를 가져오던 문제를 저장소 루트 경로 설정으로 수정했다.

## 실물 코퍼스와 전체 결과

확장자로 제한하지 않고 지정한 여섯 루트의 모든 파일에서 매직을 확인했다. 내부 `test_pairs`와 `local-samples`는 사용하지 않았으며 코퍼스 파일을 복사하지 않았다. 아래 개수는 중복 경로를 제거한 파일 개수이며, 내용이 같은 별도 파일은 별도 표본으로 센다. 모든 CFB 표본의 헤더는 v3/512바이트였다.

| 코퍼스 루트 | CFB 표본 수 |
| --- | ---: |
| 공개 `hwp-public/hwp` | 5,389 |
| POI `test-data/document` | 162 |
| POI `test-data/slideshow` | 145 |
| POI `test-data/spreadsheet` | 420 |
| LibreOffice `lo-src` | 262 |
| Tika `tika-test-docs` | 10 |
| 합계 | 6,388 |

공개 HWP 루트의 5,389개 중 5,364개는 `.hwp`, 25개는 확장자만 `.hwpx`인 CFB였다. 이 루트와 Tika 10개는 모두 완전 일치했다.

| 판정 | 파일 수 | 의미 |
| --- | ---: | --- |
| 완전 일치 | 6,325 | 저장소·스트림 목록, 선언 크기, 실제 크기와 SHA-256이 전부 일치했다. |
| olefile만 열림 | 50 | 자체 리더가 구조 손상 또는 상한 초과를 거부했다. |
| 양쪽 열림, 스트림 검증 차이 | 10 | 8개 파일의 10개 스트림은 자체 리더가 거부했고, 2개 파일의 2개 스트림은 검증기 크기 상한을 넘었다. |
| 양쪽 모두 거부 | 3 | 양쪽이 컨테이너를 열지 못했다. |
| 자체 리더만 열림 | 0 | 반대 방향 차이는 없었다. |

양쪽이 열린 파일에 나열된 74,968개 스트림 중 74,956개가 크기와 SHA-256까지 일치했다. 나머지 12개를 성공 분모에 숨기지 않았다. 실제 바이트 불일치, 스트림 목록 불일치와 저장소 목록 불일치는 모두 0건이었다.

| 칸 또는 기능 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| v3 헤더·일반 스트림·미니 스트림·저장소 경로 | POI `SampleDoc.doc` | MS-CFB 필드 및 olefile 목록·SHA-256 비교이다. | 스트림 8개, 저장소 2개와 모든 바이트가 같아야 한다. | 스트림 8개, 저장소 2개가 일치했고, 미니 3개·일반 5개를 읽었다. | 통과이다. |
| XLS 일반 스트림 | POI `Simple.xls` | olefile 목록·SHA-256 비교이다. | 스트림 3개가 같아야 한다. | 3개 모두 일치했다. | 통과이다. |
| 헤더 밖 DIFAT와 여러 DIFAT 섹터 | 공개 HWP 집계 121개 | 원시 헤더의 DIFAT 개수와 olefile 스트림 비교이다. | 연결된 DIFAT를 통해 모든 스트림을 같은 바이트로 읽어야 한다. | 121개 모두 일치했다. 전체 DIFAT 사용 표본 122개 중 나머지 1개는 손상 입력이었다. | 해당 121개 범위에서 통과이다. |
| 잘못된 FAT 표식의 안전한 수용 | POI `pictures.ppt` | 실제 DIFAT 주소·FAT 표식과 olefile 해시이다. | 실제 FAT 섹터를 예약하고 스트림 5개를 같게 읽어야 한다. | 5개 모두 일치했다. 표식 편차를 기록했다. | 통과이다. |
| 비정상 루트 이름의 안전한 수용 | POI `numbers.ppt` | 루트 이름 길이 2바이트의 원시 관찰과 olefile 해시이다. | 이름 검색에 쓰지 않는 루트 라벨 때문에 본문을 버리지 않아야 한다. | 스트림 4개가 일치했다. | 통과이다. |
| 루트 미니 스트림의 여분 할당 | POI `Bug60942.doc` | 선언량 2섹터·실제 체인 3섹터 관찰과 olefile 해시이다. | 전체 체인을 검증하되 선언된 범위만 노출해야 한다. | 스트림 3개가 일치했다. | 통과이다. |
| 쓰이지 않는 MiniFAT 개수 | POI `46904.xls` | 시작 `ENDOFCHAIN`, 개수 1, 루트 크기 0, 일반 `Book` 스트림의 바이트이다. | 사용하지 않는 할당기의 오래된 개수 때문에 일반 스트림을 버리지 않아야 한다. | 스트림 1개가 일치했다. | 통과이다. |
| 마지막 섹터 패딩 생략 | POI `47251.xls`, Tika `protect.xlsx`, `protectedFile.xlsx` | 파일 길이와 선언 데이터의 실제 바이트, olefile 해시이다. | 선언 데이터가 완전하면 읽고, 없는 바이트를 채워 만들지 않아야 한다. | 해당 표본들이 완전 일치했다. 잘린 데이터의 합성 테스트는 계속 거부했다. | 통과이다. |
| v4/4,096바이트 섹터 | 해당 실물 표본이 없다. | 합성 v4 테스트만 있다. | 실물에서 같은 스트림을 읽어야 한다. | 실물 0개이다. | 미검증이며 ⬜ 유지가 맞다. |

## 불일치 원인과 수용 정책

olefile만 열었던 50개는 FAT/DIFAT 개수 또는 배치 문제 35개, 디렉터리 문제 8개, 범위 밖 참조 4개, 헤더 문제 2개, 할당 수 상한 1개였다. 모두 열렸지만 자체 리더가 읽기를 거부한 10개 스트림은 범위 밖 참조 6개, 순환·중복 할당 2개, 선언량 대비 물리 섹터 부족 2개였다. 거대 선언 크기로 검증기가 읽기를 생략한 2개 스트림은 어느 쪽의 바이트도 검증했다고 판정하지 않았다. 양쪽 모두 거부한 3개는 헤더 2개와 FAT/DIFAT 1개였다.

대표적인 공개 손상 표본은 LibreOffice `crash-1.ppt`, `hang-10.ppt`, POI `clusterfuzz-testcase-minimized-POIHWPFFuzzer-5195207308541952.doc`, `45290.xls`, `61300.xls`이다. 63개 예외 표본의 파일명·헤더 수치·선언량·실제 읽기량·고정 원인 분류는 `.codex-work/cfb-discrepancy-classification.json`에 모두 기록했다. 손상 입력을 기준 구현과 같이 부분 읽기하거나 순환을 무시하여 100% 수치를 만드는 변경은 하지 않았다.

기본 읽기 모드에서는 주소 해석에 영향을 주지 않는 다섯 편차를 `parsing_issues`에 중복 없이 기록하고 허용한다. 루트 이름 종료 문자, FAT/DIFAT 표식, 최종 DIFAT의 `FREESECT`, 루트 미니 스트림 여분 섹터, 실제 미니 스트림이 전혀 없는 파일의 부재 MiniFAT 개수가 그 대상이다. `raise_defects=DEFECT_INCORRECT`를 준 포함 객체 검사는 이 편차도 거부한다. 일반 스트림의 짧은 체인이나 순환, 실제 데이터 부족과 중복 할당은 기본 모드에서도 거부한다. 마지막 섹터의 패딩 생략은 실제 요청 바이트가 파일에 존재하는지로 판단한다.

## 변환 출력 비교

같은 `Dochan` 코드에서 컨테이너 모듈만 교체하여 `to_markdown()`, `to_json()`, `errors`의 정확한 문자열 해시를 비교했다. 난수 시드 `20261003`으로 형식별 최대 300개를 선택했고, PPT는 실제 보유한 210개를 모두 사용했다. 손상 표본을 사전에 빼지 않았다.

| 형식 | 표본 | 세 출력 완전 일치 | 차이 | 자원 상한으로 미검증 |
| --- | ---: | ---: | ---: | ---: |
| HWP | 300 | 300 | 0 | 0 |
| DOC | 300 | 293 | 7 | 0 |
| PPT | 210 | 173 | 37 | 0 |
| XLS | 300 | 285 | 12 | 3 |
| 합계 | 1,110 | 1,051 | 56 | 3 |

56개 차이는 컨테이너 자체 거부 48개, 스트림 손상 5개, 양쪽 컨테이너 거부 3개에 대응한다. 거부 이유가 다르면 기존 오류 문자열도 달라지므로 오류만 다른 경우 역시 불일치로 계산했다. 컨테이너의 모든 스트림 바이트가 동일하게 검증된 문서에서 출력이 달라진 사례는 0개였다.

XLS 표본 ID 811·856·943은 1.5 GiB 감시 상한에 걸렸다. 별도 프로세스에서 olefile만 사용한 변환과 자체 CFB만 사용한 변환을 각각 재실행했으며, 여섯 번 모두 상한을 넘었다. 따라서 기존 하위 XLS 변환의 자원 문제이며 이 작업의 CFB 회귀라고 보지 않는다. 그렇더라도 세 표본은 변환 일치 검증에 실패한 채 남는다. 상세 증거는 `.codex-work/cfb-heavy-conversions.json`과 `cfb-conversion-classification.json`이다.

## 손상 입력과 단위 테스트

시드 `20261003`으로 공개 코퍼스에서 8 MiB 이하의 CFB를 골라 바이트 반전, 자르기, 구간 덮어쓰기와 꼬리 추가를 총 5,000회 실행했다. 3,546회는 읽혔고 1,454회는 예상된 입력 오류로 거부됐다. 예상 밖 예외, 시간 초과, 프로세스 비정상 종료와 메모리 상한 초과는 각각 0회였다. 자식 프로세스 최대 RSS는 45.0 MiB, 가장 오래 걸린 사례는 0.0218초였다. 이는 해당 시드와 표본에 대한 실측이며 모든 악성 입력에 대한 증명은 아니다.

검증기는 문서마다 별도 프로세스를 사용하며, 부모의 시간 제한과 자식 RSS 최고치 50ms 표본을 보고 종료한다. 이 macOS 샌드박스는 `RLIMIT_DATA/AS` 설정을 거부하므로 OS가 강제한 절대 메모리 상한이라고 표현하지 않는다. 부모 감시가 별도로 동작했고, 비정상 종료 분류는 단위 테스트로 확인했다.

`tests/test_cfb.py`의 합성 바이트 테스트 44개와 비교 프로그램 테스트 6개가 통과했다. 일반·미니 스트림, v3/v4, 두 개 이상의 DIFAT 섹터, v3 상위 크기 비트, 경로·파일 수명·지연 읽기, 체인 순환·중복·범위·부족, 디렉터리 순환, 자원 예산과 관찰된 호환 편차를 포함한다. 기존 수정 테스트 15개 파일의 단언 657개는 HEAD와 AST가 동일했다. olefile import를 강제 차단한 별도 프로세스에서도 5,632바이트 합성 DOC가 Markdown·JSON으로 변환됐으며 `errors=[]`였다.

전체 검증 명령은 다음과 같다.

```sh
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

결과는 **3,147 passed, 24 skipped, 14 xfailed**이며 실행 시간은 37.49초였다. 새 코드와 직접 실행 경로 수정 파일의 Ruff 검사, Python 3.9 구문 검사와 `git diff --check`도 통과했다.

## 재실행과 증거 파일

아래 명령의 경로는 읽기 전용 입력이다. 비교 스크립트의 `--mode`를 `convert` 또는 `fuzz`로 바꾸어 같은 루트·시드로 실행할 수 있다. 변환은 `--per-format 300`, 퍼즈는 `--iterations 5000`을 준다. olefile이 없는 환경에서는 비교·변환 모드를 명시적으로 건너뛰고 이유를 JSON에 기록한다. 퍼즈와 일반 런타임은 olefile을 요구하지 않는다.

```sh
/usr/bin/python3 -m scripts.compare_cfb_olefile \
  /Users/illuwa/dev/personal/dochan/corpus/hwp-public/hwp \
  /Users/illuwa/dev/personal/dochan/corpus/poi-src/test-data/document \
  /Users/illuwa/dev/personal/dochan/corpus/poi-src/test-data/slideshow \
  /Users/illuwa/dev/personal/dochan/corpus/poi-src/test-data/spreadsheet \
  /Users/illuwa/dev/personal/dochan/corpus/lo-src \
  /Users/illuwa/dev/personal/dochan/corpus/tika-test-docs \
  --mode compare --jobs 4 --timeout 30 --memory-mb 1536 \
  --seed 20261003 --output .codex-work/cfb-compare-final.json
```

표준 결과는 `.codex-work/cfb-compare-final.json`, `cfb-convert-final.json`, `cfb-fuzz-final.json`에 있다. 이 경로는 git에서 제외되며 원본 코퍼스를 포함하지 않는다. 비교 스크립트의 파일 ID는 같은 입력 루트에서 정렬한 경로의 순번이므로 코퍼스 구성이나 표본 시드를 바꾸면 다시 계산해야 한다.

## 통합 시 남은 일

오케스트레이터가 `uv.lock`을 다시 잠그고 README의 olefile 감사·의존성 설명을 실제 런타임 상태에 맞게 정리해야 한다. 해당 파일은 이 작업에서 수정하지 않았다. v4 실제 파일 확보, 손상 입력 수용 정책의 인수 기준 확정과 기존 XLS 세 표본의 변환 자원 문제는 남아 있다. 전체 일치와 v4까지 검증됐다는 ✅ 표시는 제안하지 않는다.
