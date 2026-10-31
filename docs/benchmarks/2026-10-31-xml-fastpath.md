# 안전 XML 요소 콜백 단축 검증 (2026-10-31)

## 변경과 보안 경계

기준 커밋은 `c1a6e0bb0c11abccb902c328ed7a794ae5d35c22`이다. 네임스페이스 스코프가 필요 없는
단순 byte XML만 C `TreeBuilder`의 요소·문자 메서드로 구성한다. 네임스페이스 선언 콜백은 기존
`_BoundedTree.start_ns`를 그대로 재사용한다. 선택적 `_cxml` 확장은 자체 작성한 선형 구조 검사기이며
XML 문법 해석기는 아니다. 실제 XML 문법·이름·속성·엔티티 처리는 계속 표준 라이브러리가 담당한다.
외부 라이브러리나 런타임 의존성은 추가하지 않았다.

| 기존 보장 | 기존 근거 | 새 경로의 보존 방법 |
| --- | --- | --- |
| 최대 입력 크기 100 MiB, 호출자 지정 크기 | `test_safe_xml.py::test_depth_and_size_limits` | `fromstring`의 크기 검사 변경 없음 |
| 트리 구성 전 DTD·엔티티 선언 거부, 네트워크/파일 resolver 없음 | `test_reject_declarations_before_tree_parser`, `test_recovery_still_rejects_dtd` | `_decode` → `check_prolog` 순서 그대로, fastpath는 그 이후에만 실행 |
| 기본 깊이 256, huge_tree 2048, 요소 1,000,000개를 할당 전에 제한 | `test_stdlib_xml_review.py::test_depth_is_limited_during_tree_build`, 신규 공격 차등 검사 | C 검사기가 모든 시작/종료/빈 요소를 한 번 스캔해 깊이·개수 증명. 초과/모호한 경우 기존 경로로 반환하여 기존 예외 순서 유지 |
| namespace 선언 수, URI 닫는 중괄호 거부 | `test_namespace_limit_precedes_tree_build`, `test_namespace_uri_with_brace_is_rejected` | 같은 `start_ns` 함수가 요소 구성 전에 실행 |
| namespace scope 복제량 상한, 재바인딩, Strict/MC 선택 | `test_namespace_scope_allocation_is_bounded`, `test_choice_scopes_are_recorded_without_every_element`, `test_ooxml_strict.py` | `namespaces`가 참이거나 `Requires`/`Choice` 바이트가 있으면 기존 경로 |
| 선언 URI 집합 보존, 기본 namespace 해제 | `test_namespace_undeclaration_is_allowed`, 신규 C 메서드 회귀 | 성공 시 기존과 같은 frozenset을 weak mapping에 저장 |
| 잘린 XML 복구와 오류 종류·메시지 | `test_recovery_still_rejects_dtd`, 신규 차등 검사 | 구조 증명 실패는 기존 경로. C 트리 파싱 중 문법 오류도 기존 파서로 다시 처리 |
| truncate 시 최대 깊이의 8배까지 검사 후 잘라내기 | package/하드닝 테스트, 신규 truncate 경계 검사 | 요청 깊이를 넘는 입력은 전부 기존 경로로 보내 기존 잘라내기 사용 |
| 주석·PI·CDATA의 텍스트/꼬리 및 깊이 처리 | `test_comments_pi_tail_and_parent_map`, `test_cdata_closing_text_cannot_reduce_depth_bound` | 해당 markup 입력은 기존 경로 |
| 손상 XLSX 시트 격리, 손상 전 완료 행 유지 | `test_sheet_keeps_completed_rows_before_damage`, `test_xlsx_vml_part_error_does_not_discard_sheet` | `iterparse`, `_sheet_rows`, VML 복구 코드 변경 없음 |

OOXML package의 `<` 개수 검사만 의존하지 않는다. `fromstring`을 직접 호출하는 경우에도 사전 할당 상한을
보장한다. C 확장이 없거나 `DOCHAN_DISABLE_ACCEL=1`이면 `<` 바이트 수가 깊이 상한 이하인 작은
byte XML만 빠른 경로로 보낸다. 그 수는 요소 수와 깊이 모두의 보수적 상한이다.

## 옛 경로와 달라질 수 있는 입력

- 문법이 깨졌지만 구조 상한 스캔은 통과한 XML은 파싱을 두 번 시도할 수 있다. 반환/예외는 기존 경로로
  결정하지만 실행 시간과 임시 할당량은 달라질 수 있다. 앞선 트리는 기존 파서가 입력을 받기 전에 해제된다.
- 정상 대형 XML은 기존의 요소마다 검사 대신 입력 전체를 먼저 스캔한다. 과도한 깊이/개수는 빠른 경로에서
  예외를 만들지 않고 기존 파서로 넘기므로 오류 우선순위를 유지한다. 사전 스캔 시간은 추가된다.
- UTF-16/32, Unicode 문자열, bytes 하위 클래스, 특이한 깊이 값, 주석/CDATA/일반 PI, `Requires`/`Choice`,
  truncate가 필요한 트리와 잘린 토큰은 기존 경로다. 안전성을 확신하지 못하는 표현을 억지로 가속하지 않는다.
- Python 객체를 monkeypatch하여 `TreeBuilder` 자체나 내부 타깃 클래스를 교체하는 비공개 사용은 경로가 다르다.
  공개 반환 트리·네임스페이스·오류 계약을 검증하며 내부 콜백 호출 횟수는 의도적으로 달라진다.
- C 확장은 선택 사항이다. 아래 native 성능 수치를 확장을 설치하지 않은 배포판의 수치로 해석하면 안 된다.

## 검증 방법

새 테스트 `tests/test_safe_xml_fastpath.py`의 Python 요소 콜백 금지 검사는 변경 전 `1 failed`임을 먼저 확인했다.
깊이 100,000, 요소 2,000,000, 2 MiB 속성, DOCTYPE/UTF-16 DTD, namespace 상한·URI 중괄호,
잘린 XML, 인용된 `/>`, comment/PI/CDATA를 기본·recover·truncate·namespace 상한 옵션에서
기존 경로와 비교한다. 반환 트리 바이트·선언 URI 집합 또는 정확한 예외 타입·메시지를 비교한다.
고정 시드의 손상 변이 1,000개도 native/portable 각각 비교한다.

처음 시도한 Python 정규식 구조 검사는 합성 10,000요소 ×20에서 0.144초로 기존 0.100초보다 느려 폐기했다.
최종 C 검사 버전의 같은 구조 ×100은 새 0.272초 / 기존 0.504초(사전 검사만 0.025초)였다.
이 합성 수치는 코퍼스 전체 성능과 구분한다.

## 공개 코퍼스 범위와 재현 명령

현재 읽기 전용 공개 코퍼스는 HWPX 2,883, DOCX 1,784, PPTX 545, XLSX 356으로 합계 5,568개다.
HWPX는 `hwp-public` 1,700개와 `press-pairs` 및 holdout 1~4의 1,183개이고,
Office는 POI·LibreOffice·Tika 공개 표본이다. 내부 문서와 숨김 디렉터리는 제외했다.
지시서의 HWPX 2,973/DOCX 1,785를 공개 문서 수로 그대로 재현할 수 없으므로 그 숫자의 완료를 주장하지 않는다.

기준 소스는 시작 커밋을 독립 로컬 clone에 복제한 뒤 `git worktree add --detach`로 만들었다.
원 저장소의 `.git` 쓰기 제한을 우회해 수정하지 않았으며, 기준/변경 후 모두 같은 Python 3.9와
`DOCHAN_BUILD_ACCEL=1 python setup.py build_ext --inplace --force` 빌드 조건이다.
`CORPUS`는 공개 코퍼스 루트, `BASELINE`은 위 기준 worktree, `OUT`은 결과 파일로 설정한다.

```sh
python -c 'from scripts import probe_output_speed as p; p.EXTENSIONS=("hwpx","docx","pptx","xlsx"); raise SystemExit(p.main())' collect \
  "$CORPUS/hwp-public" "$CORPUS/press-pairs" "$CORPUS/press-pairs-holdout" \
  "$CORPUS/press-pairs-holdout2" "$CORPUS/press-pairs-holdout3" "$CORPUS/press-pairs-holdout4" \
  "$CORPUS/poi-src" "$CORPUS/lo-src" "$CORPUS/tika-test-docs" \
  --workers 8 --source "$BASELINE" --output "$OUT"
# 변경 후는 위 명령에서 --source 인자만 생략한다.
python -m scripts.probe_output_speed compare before.json after.json
```

기존 probe의 확장자 선택 상수만 프로세스 내에서 제한하며 수집·해시·비교 구현을 바꾸지 않는다.
전·후·후·전·전·후 순서로 실행한다. 형식별 parse 시간은 파일별 parse 시간의 합이고,
동시에 처리하는 작업자가 8개이므로 전체 경과 시간과는 다르다.

수량 차이는 내부 컬렉션의 확장자별 개수만 확인한 결과 HWPX 90개·DOCX 1개와 정확히 대응했다.
해당 내부 문서의 이름·내용은 기록하지 않았으며 이번 공개 코퍼스 측정에 섞지 않았다.

## 최초 구현의 빌드 및 테스트 결과

| 검사 | 결과 |
| --- | --- |
| 가속 활성 전체 `python -m pytest tests/ -q -p no:cacheprovider` | 6,617 passed, 36 skipped, 14 xfailed, 81.09초 |
| `DOCHAN_DISABLE_ACCEL=1` 전체 | 6,615 passed, 38 skipped, 14 xfailed, 89.10초; 추가 skip 2개는 native 전용 |
| 최종 native XML 차등 파일 재검증 | 66 passed |
| `python -m ruff check dochan scripts tests setup.py` | 통과 |
| Xcode Python 3.9 `DOCHAN_BUILD_ACCEL=1 ... setup.py build_ext --inplace --force` | 통과 |
| `clang -std=c99 -Wall -Wextra -Wpedantic -Werror -fsyntax-only` + Python 3.9 헤더 | 통과 |
| sdist / abi3 wheel 빌드 및 멤버 확인 | sdist에 `_cxml.c`, wheel에 `_cxml.abi3.so` 포함; wheel C 소스 제외 |
| native 요소 경계 직접 확인 | 1,000,000개 허용, 1,000,001개는 기존 경로로 반환 |

전체 테스트는 보안·하드닝·OOXML package·손상 시트 격리 회귀를 포함한다.
패키지 검사는 위 멤버 포함과 로컬 빌드 검증이며 다른 운영체제/아키텍처에서의 실행 검증을 뜻하지 않는다.

## 속도 수치 정정과 감수 결과

최초 공유 호스트 측정의 17~29% 감소는 다른 워커가 실행 중이던 결과이므로 대표 성능 수치로 철회한다.
그 실행에서 공개 5,568개 ×6회 출력 해시 차이 0이라는 기능 검증 결과는 유지한다.
원시 수치는 로컬 작업 기록에 보존한다.

오케스트레이터가 한가한 장비에서 workers=8, 전·후·후·전·전·후로 재측정해 제공한
형식별 parse 합계 중앙값 변화는 다음과 같다. 전후 범위는 겹치지 않았다.
이번 후속 작업에서 직접 얻은 수치와 구분하며, 제공된 결과에 없는 절대 시간은 추정하지 않는다.

| 형식 | 파싱 시간 변화 |
| --- | ---: |
| HWPX | −4.1% |
| DOCX | −5.3% |
| PPTX | −10.0% |
| XLSX | −5.1% |

### 옛 경로와 달라질 수 있는 입력: 감수 실측

손상 입력은 두 번 파싱되어 1.85~2.37배 느렸다. 감수 표본은 요소 999,000개 문서 끝 오류에서
새 경로 2.48초 / 옛 경로 1.44초, 90 MB 텍스트 끝 오류에서 0.263초 / 0.111초였다.
제공된 범위와 별개로 첫 표본의 두 절대값 비율은 약 1.72배이므로 동일한 통계로 합치지 않는다.
요소가 적고 텍스트가 큰 정상 문서도 사전 스캔 비용으로 1.33~1.45배 느렸다.
이 수치는 독립 감수자가 제공한 실측이며 이번 실행의 재측정값은 아니다.

이번 수정에서는 텍스트 밀도 우회 휴리스틱을 추가하지 않았다. 전체 `<` 개수 판정은 추가 선형 스캔이며,
일부 구간 샘플링은 파트 내 요소 분포에 따라 경로가 달라진다. 공개 코퍼스에서 임계값을 선택하고
독립 표본으로 성능을 확인하지 않은 임의 기준을 보안 보완에 함께 넣지 않았다.
따라서 위 감속은 남는 성능 한계이며, 정상 대형 텍스트의 감속을 해결했다고 주장하지 않는다.

### 독립 상한 오라클과 상수 통합

`MAX_ELEMENTS`를 Python의 단일 요소 상한으로 두고 native 스캐너에 세 번째 인자로 전달한다.
두 bounded 타깃, portable 사전 검사, VML 계수도 이 상수를 사용한다.
호출자별 `iterparse(max_elements=...)` 제한은 별도 API다.
상한을 3으로 낮추면 3개 요소는 파싱되고 4개는 빠른 경로에서 거절되며 기존 타깃에서 같은 오류를 낸다.

트리를 만들지 않는 pyexpat StartElement/EndElement 계수기를 추가했다.
C가 참을 반환한 각 입력에서 문법 오류 직전까지의 최대 깊이와 시작 요소 수를 독립적으로 확인한다.
기존 고정 시드 변이 1,000개와 동일한 입력·깊이 선택에 더해 XML/인코딩 선언, latin-1,
8비트 본문+utf-16 선언, UTF BOM, 비ASCII 이름, `}` URI, 깊이 경계 ±1,
자기 닫힘 혼합, 끝 오류, 요소 1,000,000/1,000,001개를 검사한다.
주석·PI·CDATA·`<!`는 C 함수를 직접 호출해 거절을 검사한다.
항상 참을 반환하는 결함 스캐너를 주입했을 때 새 오라클이 깊이 초과를 검출하는 것도 확인했다.
감수 참고 코드를 복사하지 않고 테스트를 작성했다.

### 후속 수정 검증

| 검사 | 결과 |
| --- | --- |
| 가속 활성 전체 | 6,625 passed, 36 skipped, 14 xfailed (132.11초) |
| 가속 비활성 전체 | 6,616 passed, 45 skipped, 14 xfailed (140.66초) |
| native fastpath 테스트 파일 | 74 passed |
| Ruff / 엄격 clang / Python 3.9 제한 API 빌드 | 모두 통과 |

비활성 모드의 추가 skip 9개는 native 검사 전용이다. 두 suite는 일부 병행 실행했으므로
위 실행 시간을 속도 비교로 해석하지 않는다. 코퍼스 측정은 두 suite 종료 뒤 별도로 실행했다.
신규 테스트의 변경 전 실패는 8건이며 새 상수/API가 없는 데서 발생했다. 독립 오라클 자체의
결함 검출력은 깊이 초과를 허용하는 스캐너 주입으로 따로 확인했다.

### 후속 공개 출력 검증과 단일 작업자 측정

후속 구현과 같은 기준 커밋을 Python 3.9로 각각 빌드하여 공개 5,568개를 새로 처리했다.
workers=8의 전후 각 1회는 출력 회귀 검증 목적이다. 두 실행 모두 처리 실패 0,
`probe_output_speed compare`의 Markdown/JSON/text/errors 해시 차이 0, 실패 변화 0,
누락 0, JSON 폴백 0이었다. 아래 단회 시간은 교대 3회 대표 성능 수치를 대체하지 않는다.

| 형식 | 파일 | 전→후 parse 합(초), 단회 |
| --- | ---: | --- |
| HWPX | 2883 | 154.429 → 137.973 |
| DOCX | 1784 | 22.044 → 22.743 |
| PPTX | 545 | 4.929 → 4.438 |
| XLSX | 356 | 19.229 → 19.309 |

단일 작업자는 같은 공개 목록에서 PPTX 전부 545개, 전체 경로를 사전순 정렬한 DOCX 앞 300개를
고정했다. 표본을 복사하지 않고 probe의 `collect_paths` 결과 목록만 이 845개로 제한했다.
`collect(..., workers=1, source=...)`를 별도 Python 프로세스에서 전·후·후·전·전·후로 실행했다.
매회 실패 0, 세 쌍 `probe_output_speed compare`의 모든 출력 차이·폴백·누락 0이다.

| 형식 | 파일 | 6회 parse 합(초) | 전→후 중앙값(초) | 변화 |
| --- | ---: | --- | --- | ---: |
| PPTX | 545 | 3.652 / 3.313 / 3.554 / 3.750 / 3.349 / 2.430 | 3.652 → 3.313 | -9.3% |
| DOCX | 300 | 2.805 / 2.824 / 2.720 / 2.805 / 2.312 / 1.967 | 2.805 → 2.720 | -3.0% |

PPTX의 −9.3%는 제공된 8-worker −10.0%와 비슷하고 DOCX 표본의 −3.0%는 전수 −5.3%보다 작다.
DOCX 표본 모집단도 다르고 단일 작업자 실행의 전후 범위가 겹치며 후반 실행이 함께 빨라졌다.
따라서 병렬 측정이 개선을 눌렀다는 가설을 확인했다고 주장하지 않는다. 이 세션이 실행한 테스트는
종료 후 측정했지만 호스트의 다른 프로세스·열 상태는 통제하지 않았다.

원시 결과: `.codex-work/fix-full-*.json`, `fix-single-*.json`, `fix-summary.json`.
고정 표본과 실행·집계 도우미: `fix-sample.json`, `fix-benchmark.py`, `fix-summarize.py`.
빌드/테스트/비교 로그: `fix-build.log`, `fix-red.log`, `fix-enabled.log`, `fix-disabled.log`,
`fix-benchmark.log`. 모두 로컬 작업 기록이며 코퍼스 원문은 저장소에 복사하지 않았다.
