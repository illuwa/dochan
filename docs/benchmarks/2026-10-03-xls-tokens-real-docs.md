# XLS 메모리 토큰과 BIFF5 RPN 실물 검증

2026년 10월 3일 공개 POI·LibreOffice·Tika XLS 721개를 작업 시작 HEAD와 비교했다. 메모리 토큰으로 426셀, BIFF5 해석으로 419셀의 수식을 추가 표시했다. 기존 수식이 사라진 셀과 캐시 값이 바뀐 셀은 모두 0개다. XLSX 정답이 있는 1,070셀의 일치 수는 1,059개로 유지됐다. RSTRING과 일부 토큰은 실물 표본이 없어 미검증으로 남긴다. README와 CHANGELOG는 수정하지 않았다.

## 구현 범위와 근거

로컬에 보관된 Microsoft `[MS-XLS] v20250819`의 2.5.198.70–73을 근거로 PtgMemArea·PtgMemErr·PtgMemFunc·PtgMemNoMem을 구현했다. 메모리 토큰은 값을 스택에 넣는 토큰이 아니라 뒤따르는 하위 참조식의 길이를 선언한다. `cce` 바이트 경계와 하위 스택 경계를 따로 관리하고 결과가 하나일 때만 부모 식으로 돌려보낸다. 반복문으로 처리하고 중첩은 256단계로 제한한다. 이 값은 문법 판정 수치가 아니라 악성 입력에 대한 자원 상한이다.

PtgMemArea의 추가 데이터는 2.5.198.61의 PtgExtraMem과 2.5.209의 Ref8U에 따라 소비한다. 2.5.198.103에 따라 배열 상수와 같은 RgbExtra 커서를 토큰 순서대로 사용한다. 범위를 실체화하지 않으며 잘린 데이터와 잘못된 행·열 범위는 셀 캐시를 보존하고 WARN을 남긴다. MemErr의 캐시 오류는 원래 하위 식을 생략하는 근거로 쓰지 않는다. 이 구현은 바이트와 스택 구조를 검증하며 Excel 계산 엔진처럼 모든 참조식의 자료형을 검증하거나 계산하지는 않는다.

PtgElfLel은 2.5.198.50의 `18 01`, `ilel`, `fQuoted`와 2.4.154의 Lel 레코드 `0x01B9`를 사용한다. `ilel-2`로 삭제된 라벨 이름을 찾고 작은따옴표 플래그를 보존한다. 잘못된 Lel도 인덱스를 차지하게 하여 뒤의 이름이 앞당겨지지 않게 했다. 이름 2,047개 상한과 252자 미만 조건은 명세에 따른다. 다른 Elf 하위 토큰은 이름을 추정하지 않고 캐시와 경고를 유지한다.

현행 MS-XLS의 BOF 절은 BIFF8 `0x0600`을 규정하며 BIFF5 RPN 토큰 절을 제공하지 않는다. 따라서 BIFF5는 아래 공개 파일의 원시 바이트 관찰을 구현 근거로 구분한다. 통합문서 BOF `0x0500`을 전달하여 3바이트 Ref/RefN, 6바이트 Area/AreaN, 행 워드의 상대 플래그, 코드페이지 문자열을 분기했다. 시트 BOF와 통합문서 BOF가 다른 실물도 있으므로 시트 BOF만으로 버전을 정하지 않는다. BIFF5의 Name·NameX·3d·배열 상수는 BIFF8 레이아웃을 적용하지 않고 WARN과 캐시를 남긴다. Area·문자열·삭제 참조의 세부 변형은 합성 검증만 끝냈으며 실물 검증은 완료하지 않았다.

## 전수 조사 분모

`corpus/poi-src/test-data`, `corpus/lo-src`, `corpus/tika-test-docs` 아래 확장자가 XLS인 721개를 조사했다. 내부 문서는 사용하지 않았다. HEAD 소스만 별도로 보관하고 같은 프로브를 격리 프로세스에서 실행했다. 원본 코퍼스 문서를 저장소로 복사하지 않았다.

프로브는 721개 모두 끝났고 프로브 예외는 0개였다. 문서에 ERR이 없는 결과는 656개, ERR을 반환한 문서는 65개로 전후 동일했다. RSTRING의 독립 원시 조사에서는 667개 파일의 비암호 Workbook/Book 스트림을 읽었고, 암호 스트림 8개 파일과 손상·스트림 부재 46개 파일을 별도로 기록했다. 해당 파일의 레코드가 없다고 추정하지 않았다.

한 파일에 Workbook과 Book이 함께 있으면 리더가 최종 선택한 문서의 FORMULA 좌표만 수식 분모로 삼았다. 선택되지 않은 스트림의 좌표나 provenance가 없는 차트 표를 섞지 않았다. 이번 분모는 POI만 조사한 과거 78,733셀보다 넓은 공개 코퍼스의 95,932셀이다.

| 지표 | HEAD | 수정 후 |
|---|---:|---:|
| 선택된 스트림의 FORMULA 좌표다. | 95,932셀이다. | 95,932셀이다. |
| 수식을 표시했다. | 93,588셀이다. | 94,433셀이다. |
| 수식을 표시하지 않았다. | 2,344셀이다. | 1,499셀이다. |
| 수식 미표시 비율이다. | 2.44340%다. | 1.56257%다. |
| 기존 표시 수식이 사라졌다. | 비교 기준이다. | 0셀이다. |
| 셀 캐시 값이 바뀌었다. | 비교 기준이다. | 0셀이다. |

수식 표시가 늘었다는 사실이 새 수식 845개 모두의 의미를 독립 정답으로 검증했다는 뜻은 아니다. 아래 표에서 기대 근거가 있는 표본만 실물 검증 통과로 판정했다.

## 실패 토큰 상위 20개와 원인 분류

다음은 HEAD의 셀 디코더가 처음 멈춘 바이트 또는 진단별 분포다. BIFF5를 BIFF8로 읽은 경우 피연산자 바이트에서 멈출 수 있어 그 값을 실제 토큰이라고 단정하지 않는다. 이 표의 후보 토큰 집계와 아래의 원인 집계를 구분한다.

| 최초 실패 바이트 또는 진단 | 셀 수 | 파일 수 |
|---|---:|---:|
| 해석하지 못한 NameX다. | 1,399 | 1 |
| `0x29` MemFunc 후보이다. | 419 | 7 |
| `0x00`이다. | 363 | 1 |
| `0x02` PtgTbl이다. | 91 | 4 |
| 스택에 결과가 하나 남지 않았다. | 30 | 2 |
| `0x26` MemArea 후보이다. | 8 | 4 |
| 디코더 진단이 없다. | 8 | 1 |
| `0x2D`이다. | 4 | 2 |
| `0x24`이다. | 3 | 3 |
| `0x27` MemErr 후보이다. | 3 | 2 |
| `0x91`이다. | 2 | 2 |
| `0xF5`이다. | 2 | 2 |
| `0x39`이다. | 2 | 2 |
| 연산자 스택이 부족하다. | 2 | 2 |
| `0x18` PtgElf이다. | 1 | 1 |
| `0x9D`이다. | 1 | 1 |
| `0x9E`이다. | 1 | 1 |
| `0xF7`이다. | 1 | 1 |
| `0xF8`이다. | 1 | 1 |
| `0xF9`이다. | 1 | 1 |

통합문서 BOF와 SupBook 종류를 함께 대조한 실제 원인별 분포는 다음과 같다. 이 분류는 2,344셀 전체를 포함한다.

| 원인 | HEAD 셀 수 / 파일 수 | 수정 후 미표시 셀 수 |
|---|---:|---:|
| DDE/OLE NameX이다. | 1,399 / 1 | 1,399 |
| BIFF5 레이아웃이다. | 419 / 3 | 0 |
| PtgMemFunc이다. | 417 / 5 | 0 |
| PtgTbl 데이터 테이블이다. | 91 / 4 | 91 |
| 디코더는 성공했으나 출력 상한으로 셀이 없다. | 8 / 1 | 8 |
| PtgMemArea이다. | 7 / 3 | 0 |
| PtgMemErr이다. | 2 / 1 | 0 |
| 미지원 PtgElf 하위 토큰이다. | 1 / 1 | 1 |

`49219.xls`의 1,399셀은 SupBook의 DDE 서비스·토픽과 해당 XTI를 가리키는 NameX로 확인했다. 같은 이름의 XLSX 정답이 없어 DDE/OLE 호출 표기를 만들지 않았다. 남은 Elf 표본은 `forum-mso-de-49320.xls`의 `18 0a`이며, 이번에 구현한 ElfLel `18 01`의 실물 검증으로 세지 않았다. 진단 없는 8셀은 `SharedFormulaTest.xls` A32769:H32769이며, 토큰 해석은 성공했으나 기존 출력 셀 상한으로 표시되지 않는다. 이를 빼면 토큰 원인의 캐시 폴백은 2,336셀에서 1,491셀로 감소했다. 초기 프로브에서 `pictureOrder.xls` 1셀과 `15228.xls` 21셀은 수식 뒤 주석을 수식 생략으로 오인했다. 실제 디코더 결과와 셀 표시를 대조하여 이 22셀을 수정 전후 모두 표시 셀로 보정하고, 주석 안의 가짜 수식을 세지 않는 회귀 테스트도 추가했다.

## 칸별 실물 검증

POI 표본 경로는 `corpus/poi-src/test-data/spreadsheet/`, LO 표본 경로는 `corpus/lo-src/sc/qa/unit/data/xls/`를 기준으로 한다. POI·LO의 구현 코드는 사용하지 않았으며 테스트의 기대값과 원시 바이트만 근거로 삼았다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| 수식의 MemArea이다. | `Intersection-52111.xls` A3이다. | POI `poi/src/test/java/org/apache/poi/hssf/usermodel/TestBugs.java:2192–2196`과 원시 `46 … 13 00` 뒤 두 영역 및 교집합 토큰이다. | `(C2:D3 D3:E4)`와 캐시 4다. | `4 (=(C2:D3 D3:E4))`다. | 1/1셀 정확히 일치했다. |
| 수식의 MemArea이다. | `IntersectionPtg.xls` C5이다. | `26 … 13 00` 뒤 A1:B2, B2:C3, 교집합 `0f`, AttrSum과 캐시 5다. | `SUM(A1:B2 B2:C3)`다. | `5 (=SUM(A1:B2 B2:C3))`다. | 1/1셀 바이트 기대와 일치했다. |
| 수식의 MemFunc이다. | `RangePtg.xls` B4이다. | `29 0b 00 23 01 00 00 00 24 01 00 01 c0 11`과 NAME `pineapple`, AttrSum이다. | `SUM(pineapple:B2)`와 캐시 10이다. | `10 (=SUM(pineapple:B2))`다. | 1/1셀 바이트 기대와 일치했다. |
| 수식의 MemFunc이다. | `maxindextest.xls` Sheet2 E8이다. | `29 16 00` 뒤 B1, B1:B3, 정수 2, INDEX, 범위 `11`, AttrSum이다. | `SUM(B1:INDEX(B1:B3,2))`와 캐시 7이다. | `7 (=SUM(B1:INDEX(B1:B3,2)))`다. | 1/1셀 바이트 기대와 일치했다. |
| 수식의 MemErr이다. | `FormulaEvalTestData.xls` EverythingTests G47·H47이다. | 두 `47` 메모리 헤더의 cce는 25·15이며 뒤 참조 토큰과 교집합 연산 및 오류 캐시를 읽었다. | `D8:(E7) (E10):F9`, `$A12:$IV12 H10`과 각각 `#NULL!`이다. | 기대 식을 모두 표시하고 `#NULL!` 캐시를 보존했다. | 2/2셀 바이트 기대와 일치했다. |
| 수식의 BIFF5 Ref이다. | `testEXCEL_5.xls`, `testEXCEL_95.xls` E19이다. | 각 FORMULA의 `44 12 00 02 1e 0a 00 05`와 double 1960이다. | `$C$19*10`과 캐시 1960이다. | 각 `$1,960.00 (=$C$19*10)`이다. | 2/2셀 일치했다. 두 파일의 전체 74식은 모두 표시한다. |
| 수식의 BIFF5 단항 연산이다. | 같은 두 파일의 B7:B20이다. | Ref의 3바이트 뒤 `12`는 Uplus이고 그 뒤 정수 1과 덧셈이 온다. | B7은 `+$B$6+1`이며 이후 행도 같은 형태다. | 이전에 삼킨 단항 `+`를 28셀에서 복원했다. 캐시는 동일하다. | 28/28셀 바이트 기대와 일치했다. |
| 공유 수식의 BIFF5 RefN이다. | LO `shared-formula/biff5.xls` E6:E376이다. | LO `sc/qa/unit/subsequent_filters_test2.cxx:460–471`의 371셀 그룹 단언과 SHRFMLA `4c 00 c0 fe 4c 00 c0 ff 03`이다. | 각 행에서 왼쪽 두 셀을 더한다. E6은 C6+D6, E7은 C7+D7이다. | 371/371셀에 해당 식을 표시했다. E6 캐시 24663.3, E7 캐시 607.2는 원시 입력 셀의 합과도 일치했다. | 그룹과 좌표 패턴이 100% 일치했다. 전체 파일 373식도 모두 표시한다. |
| MemNoMem과 ElfLel이다. | 확인된 실물 표본이 없다. | 명세 구조를 합성 바이트로 테스트했다. | 실물 정답과 비교해야 한다. | 단위 테스트만 통과했다. | 실물은 미검증이다. |
| 셀 단위 RSTRING이다. | 조사 가능한 공개 XLS 667개에서 발견하지 못했다. | 원시 Workbook/Book 레코드 id `0x00D6`를 전수 조사했다. | SST와 같은 텍스트·서식 런 계약이다. | 레코드 0개다. 기존 SST/RSTRING 공통 합성 테스트는 통과했다. | 실물은 미검증이다. |

`forum-fr-59757.xls`에서는 MemFunc로 412식을 추가 표시하여 619/619식을 표시한다. G10의 출력은 `IF(Rec<MediaGG,"",AVERAGE(INDEX(Tab,Rec-MediaGG+1,6):INDEX(Tab,Rec,6)))`이다. 이 412개 전체에 대한 독립 XLSX 정답은 없으므로 별도 수식 정확도 100%로 주장하지 않는다.

## XLSX 짝과 독립 캐시 정답

POI 동명 XLS/XLSX 36쌍 중 수식이 있는 20쌍, 1,070셀을 비교했다. 정확 일치는 986개, 공백 정규화 후 추가 일치는 73개로 총 1,059개(98.97%)다. HEAD와 각 셀의 기대·실제 식을 대조했으며 기존 일치가 깨진 셀 0개, 실제 수식 문자열이 바뀐 셀 0개다. 남은 11개는 기존 원본 차이와 외부 참조 표기 차이이며, 분모를 바꾸거나 정규화를 넓혀 일치 수를 올리지 않았다.

저장소 밖 xlrd 정답지로 비교한 캐시는 정확 860개, 숫자 서식 동등 194개, 불일치 10개, 정답지 오류 6개다. 이는 기존 결과와 같으며 불일치·오류를 통과로 세지 않는다. LO에는 같은 디렉터리의 동명 XLSX 짝이 없었고 Tika의 한 짝은 암호 표본이어서 수식 정답 비교에서 실패로 기록했다.

## 출력 회귀와 검증

공개 721파일의 Markdown과 JSON을 모두 HEAD와 비교했다. Markdown은 22파일, JSON은 23파일에서 바뀌었다. 셀 단위 변화는 추가 수식 845개와 BIFF5 Uplus 복원 28개이며, 수식 소실·캐시 값 변화는 0개다. 28개 변경은 Ref의 마지막 바이트로 잘못 소비하던 단항 연산자 `0x12`를 되살린 수정이며 기존 단위 테스트 단언을 바꾸지 않았다.

변경된 23파일의 실제 JSON 구조를 다시 비교했다. 수식 텍스트, 경고, 새로 표시한 `Defined name:` 문단 75개를 분리한 뒤에는 구조 차이가 0개였다. 기존 정의 이름 문단은 삭제하지 않았다. 같은 23파일에 포함된 이미지 25개의 바이트 SHA256도 모두 동일했다.

공유 모델·출력·라우팅 파일은 변경하지 않았다. 새 런타임 의존성을 추가하지 않았으며 기존 `캐시 (=식)` 출력 계약을 유지했다. BIFF5 시트 이름의 기존 디코딩 문제와 이름 레코드 경고는 이번 수식 토큰 범위에서 변경하지 않았다.

최종 전체 테스트는 4,383 passed, 29 skipped, 14 xfailed다. 새 토큰 합성 테스트 64개와 프로브 테스트 4개가 통과했다. 정상 복원 테스트의 최초 실패를 확인한 뒤 구현했고 잘린 길이, 스택 침범, 추가 데이터 범위, 중첩·이름 개수 상한도 검사했다. 기존 테스트의 단언은 변경하지 않았다. `ruff check dochan scripts tests`와 `git diff --check`도 통과했다.

## 재현

HEAD 스냅샷은 코퍼스를 복사하지 않고 소스만 보관한다. 아래의 첫 명령은 작업 시작 시점 소스에서 실행한 기준 측정이며, 수정 후에는 동일한 프로브로 비교한다.

```bash
/usr/bin/python3 -m scripts.probe_xls_tokens corpus --source-root .codex-work/head-baseline --output .codex-work/tokens-head-v2.json
/usr/bin/python3 -m scripts.probe_xls_tokens corpus --compare .codex-work/tokens-head-v2.json --output .codex-work/tokens-current.json
/usr/bin/python3 -m scripts.probe_xls_formula_pairs corpus/poi-src/test-data/spreadsheet --oracle-python corpus/.venv-oracle/bin/python --output .codex-work/pairs-after.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-final
ruff check dochan scripts tests
git diff --check
```

셀별 토큰·캐시·출력 증거는 `.codex-work/tokens-head-v2.json`, `.codex-work/tokens-current.json`, `.codex-work/tokens-regression.json`에 보관했다. XLSX의 셀별 회귀 결과는 `.codex-work/pair-regression.json`에 있다. 프로브 결과와 원본 문서는 커밋하지 않는다.

구조 차이와 이미지 검증은 `.codex-work/tokens-details/structure-diff.json`, `.codex-work/tokens-details/image-comparison.json`에 있다. 이 디렉터리의 `index.json`은 변경 파일과 실제 전후 출력 파일의 대응을 기록한다.
