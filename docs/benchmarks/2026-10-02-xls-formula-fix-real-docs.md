# XLS 수식 리뷰 수정과 실물 재측정

2026년 10월 2일 `illuwa/w-xls-formula`에서 두 독립 리뷰를 재현하고 수정했다. 이 문서는 앞선 `2026-10-02-xls-formula-real-docs.md`의 최종 판정을 갱신한다. README는 변경하지 않았다. 배정된 수식 경로와 리뷰 수정은 구현했지만, 전체 XLS 수식 칸은 남은 생략과 미검증 범위를 오케스트레이터가 판단할 때까지 **⬜ 유지**를 제안한다.

## 비교 기준과 짝 1,070개

수정 전은 HEAD가 아니라 리뷰 대상이었던 미커밋 파서의 시작 시점 복사본이다. 같은 코퍼스를 같은 프로브로 전후 측정했다. 원본 Office 문서는 읽기만 했으며 저장소에 복사하지 않았다. POI 구현 코드는 옮기거나 번역하지 않았다.

동명 XLS/XLSX 36쌍 중 수식이 있는 20쌍의 1,070셀을 비교했다. 외부 참조 원인 분류는 책 한정자만 정규화한 뒤 전체 식이 같아야 허용한다. 시트 이름, 셀 좌표, `$`, 연산자, 문자열 리터럴, 구조화 참조는 보존한다. 책 번호만 다른 경우도 원인 분류일 뿐, 일치 셀로 올리지 않는다. 수식 일치율은 기존의 정확 비교 및 공백 정규화 비교를 유지한다.

| 지표 | 리뷰 수정 전의 엄격 분류 결과 | 리뷰 수정 후의 엄격 분류 결과 |
|---|---:|---:|
| 정확 일치이다. | 986/1,070개(92.15%)이다. | 986/1,070개(92.15%)이다. |
| 공백 정규화를 포함한 일치이다. | 1,059/1,070개(98.97%)이다. | 1,059/1,070개(98.97%)이다. |
| 원시 `<f>` 219개만의 정확 일치이다. | 187/219개이다. | 187/219개이다. |
| 원시 `<f>` 219개만의 정규화 포함 일치이다. | 208/219개이다. | 208/219개이다. |
| 불일치이다. | 11개이다. | 11개이다. |
| 자동 미분류 불일치이다. | 3개이다. | 3개이다. |
| 프로브 예외이다. | 0개이다. | 0개이다. |

미분류 세 셀은 `52575_main.xls`의 Tabelle1!A1/A2/A3이다. XLSX는 경로 한정자와 상대참조 `A1` 등을, XLS 원시 바이트는 첫 외부 통합문서와 절대참조 `$A$1` 등을 담는다. 시트와 셀 번호가 같더라도 절대참조 표기가 다르므로 책 한정자만의 차이라고 분류하지 않는다. 기존의 “미분류 0개” 주장을 철회한다. 세 셀의 XLS 복원 자체는 기존 문서의 SUPBOOK·XTI·Ref3d 바이트 검증으로 확인했지만 두 원본이 같은 식이라고 주장하지 않는다.

나머지 여덟 불일치는 XLS 원시 FORMULA가 없는 좌표 세 개, XLS에 없는 시트의 네 개, 구조화 참조와 일반 범위의 차이 한 개다. 파일별 20쌍의 결과는 앞선 문서의 표와 동일하다. 독립 xlrd 캐시 비교 역시 정확 860개, 숫자 서식 동등 194개, 불일치 10개, 정답지 오류 6개로 변하지 않았다. 캐시 비교 실패를 수식 비교 통과에 포함하지 않는다.

## 전체 코퍼스의 셀 수식 생략률

전체 XLS 417개를 조사했다. 원시 Workbook/Book 스트림을 조사할 수 있는 398개 중 181개에 FORMULA 셀이 있었다. 암호화, 손상, 비OLE 등으로 원시 스트림을 조사할 수 없는 19개는 별도 실패 목록에 남겼으며 분모를 추정하지 않았다. 분모는 원시 FORMULA가 있는 고유 시트·셀 좌표다. NAME 정의 수식은 셀 수식과 구분한다. 생략은 최종 셀 출력에 수식 문자열이 없는 경우이며, 수식의 의미나 계산 결과가 맞는지를 증명하는 지표가 아니다.

| 지표 | 리뷰 수정 전 | 리뷰 수정 후 |
|---|---:|---:|
| 원시 FORMULA 좌표이다. | 78,733개이다. | 78,733개이다. |
| 수식을 표시한 셀이다. | 77,117개이다. | 77,163개이다. |
| 수식을 생략한 셀이다. | 1,616개이다. | 1,570개이다. |
| 셀 수식 생략률이다. | 2.05251%이다. | 1.99408%이다. |
| 리더가 호출자에게 던진 예외이다. | 0개이다. | 0개이다. |

일곱 파일에서 46개 셀을 추가로 복원했고, 전에 표시되던 식이 생략된 셀은 0개다. `13796.xls`, `14330-1.xls`, `44891.xls`에서 각각 일곱 개, `AreaErrPtg.xls`와 `ErrPtg.xls`에서 각각 한 개, `FormulaEvalTestData.xls`에서 다섯 개, `ex45978-extraLinkTableSheets.xls`에서 열여덟 개를 추가 복원했다.

남은 생략 1,570개 중 1,399개는 `49219.xls`의 DDE/OLE 이름 참조다. 그 밖에 데이터 테이블 PtgTbl, 메모리 관련 토큰, 일부 공유 수식과 구형 BIFF 및 손상 입력 등이 남는다. 파일별 좌표와 경고는 프로브 JSON에 보존했다. 전체 수식을 지원한다고 주장하지 않는다. 리뷰의 “약 1,110건” 추정은 이번 원시 FORMULA 셀의 복구 수 46개와 같지 않으므로 검증된 최종 수치로 사용하지 않는다. 특히 `56450.xls`에는 FORMULA 셀이 없으며 해당 수정 효과는 NAME 정의 수식에 있다.

NAME 수식도 별도로 다시 측정했다. 이름과 수식 길이가 0이 아니고 선언된 바이트가 존재하는 원시 NAME 레코드 7,791개를 분모로 삼았으며, 출력된 `Defined name:` 문단 개수를 뺐다. NAME 표시 개수는 6,621개에서 7,708개로 늘었고 생략은 1,170개에서 83개로 줄었다. NAME 생략률은 **15.01733%에서 1.06533%**로 낮아졌다. 파일별 NAME 표시 개수가 줄어든 사례는 0개였으나, 이 개수 비교가 모든 이름별 식의 동등성을 검증하지는 않는다.

셀과 NAME을 합하면 86,524개 중 생략 2,786개에서 1,653개로, 생략률은 **3.219916%에서 1.910453%**로 줄었다. 셀 46개와 NAME 1,087개를 더 표시하며 개선 파일은 40개다. 리뷰의 대략적 수치 대신 이 분모별 실측을 최종 수치로 사용한다. `56450.xls`만 보면 정의 이름 표시가 4,780개에서 5,527개로 늘었다. 이 증가분 전체를 SUPBOOK만의 효과로 주장하지 않으며, SUPBOOK으로 복구된 네 외부 매크로 이름은 별도로 원시 바이트와 대조했다.

## 칸별 실물 검증

아래 POI 테스트 경로의 공통 접두사는 `poi/src/test/java/org/apache/poi/hssf/usermodel/`이다. 기대값을 인용한 테스트만 읽었으며 구현 소스는 사용하지 않았다. 이 표의 표본은 짝 1,070개 분모에 추가하지 않는다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| 수식의 삭제된 3d 셀 참조다. | `27272_1.xls`의 NAME solver_adj다. | `TestFormulas.java:849` 및 토큰 `3c0e0005050500`이다. | `Compliance!#REF!`다. | `Defined name: solver_adj = Compliance!#REF!`다. | 정확히 일치했다. |
| 수식의 삭제된 3d 영역 참조다. | `27272_2.xls`의 NAME POD0001이다. | `TestFormulas.java:858` 및 토큰 `3d00000000981500000f00`이다. | `LOAD.POD_HISTORIES!#REF!`다. | `Defined name: POD0001 = LOAD.POD_HISTORIES!#REF!`다. | 정확히 일치했다. |
| 수식의 삭제된 3d 셀 참조다. | `24207.xls`의 NAME b다. | `TestHSSFName.java:220` 및 토큰 `3c000001000000`이다. | `Sheet1!#REF!`다. | `Defined name: b = Sheet1!#REF!`다. | 정확히 일치했다. |
| 수식의 삭제된 영역 참조다. | `AreaErrPtg.xls`의 Sheet1!C1이다. | 토큰 `2b0000040000c000c01910a000`은 PtgAreaErr 뒤 tAttrSum이다. | `SUM(#REF!)`다. | `#REF! (=SUM(#REF!))`다. | 원시 바이트 기대와 일치했다. |
| 수식의 삭제된 셀 참조다. | `13796.xls`의 Sheet1!E1이다. | 토큰 `2a140004c01e64002a150004c00415051e640006`은 RefErr,100,RefErr,빼기,괄호,곱하기,100,나누기 순서다. | `#REF!*(100-#REF!)/100`이다. | `#REF! (=#REF!*(100-#REF!)/100)`이다. | 원시 바이트 기대와 일치했다. |
| 수식의 내장 이름이다. | `SimpleWithPrintArea.xls`의 NAME이다. | `TestHSSFName.java:199-204` 및 fBuiltin=0x20, 코드 0x06, 토큰 `3b00000000040000000200`이다. | `Print_Area = Sheet1!$A$1:$C$5`다. | `Defined name: Print_Area = Sheet1!$A$1:$C$5`다. | 정확히 일치했다. |
| 시트 목록이 없는 외부 이름이다. | `56450.xls`의 외부 링크 24번이다. | SupBook ctab=0, virtPath 첫 문자 0x01, EXTERNNAME 네 개의 flags=0/scope=0 및 실제 NameX 인덱스다. | 외부 이름 `Macro.tri_ambiance`를 보존한다. | `[24]!Macro.tri_ambiance`로 해석한다. | 링크 테이블의 원시 바이트 기대와 일치했다. 셀 수식 복구로 세지 않는다. |

첫 여섯 표본의 실제 문서 경고는 모두 0개이며, 일곱 번째의 링크 테이블 경고도 0개다. Print_Titles와 _FilterDatabase는 합성 테스트를 통과하고 실물 출력도 확인했지만 독립 정답과의 전체 대조는 하지 않았으므로 별도 통과 수에 넣지 않았다.

## 구현, 자원 제한과 검증 범위

SupBook의 현재 시트 virtPath `\x00`과 미사용 virtPath 공백은 외부 책 번호에서 제외하고 원래 SupBook 인덱스는 유지한다. ctab=0만으로 DDE라고 판단하지 않는다. 외부 이름의 DDE/OLE 본문은 EXTERNNAME의 자체 flags로 구분한다. `56450.xls`의 시트 목록 없는 외부 책을 정상 외부 이름으로 보존했다. 현재 시트·미사용 링크가 앞선 다중 책 번호의 실물 짝은 확보하지 못했으므로 이 변형은 합성 검증만 완료했다.

`49219.xls`의 실제 `IDT\x03IMKB`, `MTX\x03DATA`는 service·topic 경로인 DDE로 구분하고 외부 링크 번호에는 포함한다. 0x01로 시작하는 인코딩된 통합문서 경로 안의 0x03은 디렉터리 구분자이므로 DDE로 오인하지 않는다. 일반 이름 `Class1`, `Object`도 외부 책으로 보존한다. POI `poi/src/test/java/org/apache/poi/hssf/record/TestExternalNameRecord.java:104-125`의 실제 DDE 레코드 flags=0x7fe2도 합성 경계 테스트의 근거다. DDE 호출 자체의 복원은 미지원이다.

시트 이름의 길이 헤더를 포함한 원시 문자열 총량을 워크북마다 1MiB로 제한한다. 이 값은 명세 의미 판정을 위한 임계값이 아니라 자원 상한이다. 개별 문자열을 디코딩하기 전에 남은 예산과 비교하고, 초과한 책의 인덱스와 외부 번호는 유지하며 참조는 경고와 캐시 보존으로 처리한다. 반복 초과 경고는 한 번만 남긴다.

빈 NAME은 인덱스만 보존하고 메타데이터 문단을 만들지 않는다. invalid NAME 경고는 중복 제거한다. PtgName 상위 워드에 쓰레기 값이 있는 호환 입력은 기존 HEAD처럼 하위 워드의 이름을 찾는다. fBuiltin 이름은 NAME을 읽을 때 표준 이름으로 바꾸어 일반 Name과 내부 NameX가 같은 이름을 사용하게 한다.

PtgRefErr/PtgAreaErr와 3d 변형의 R/V/A 클래스를 처리한다. 3d는 유효한 시트 한정자를 보존하며, 삭제된 시트가 이미 `#REF!`인 경우 중복 오류 문자열을 만들지 않는다. 잘린 토큰은 캐시를 남기고 경고한다. SHRFMLA는 선택한 토큰 시작 위치와 RgbExtra 경계를 함께 반환하여 기존 대체 오프셋에서 발생한 한 바이트 차이를 없앴다. 대체 오프셋의 배열은 합성으로만 검증했으며 실물 표본은 미검증이다.

HEAD 테스트 단언은 바꾸지 않았다. 이전 작업의 미커밋 `test_formula_probe_distinguishes_external_link_spelling` 단언 하나는 `A1`과 `$A$1` 차이를 숨기는 버그를 고정하고 있어 `unclassified mismatch`로 정정했다. 변경 전 실패 로그와 변경 후 실행 결과는 `.codex-work/`에 있다. 공유 모델·출력·라우팅 파일과 README·CHANGELOG·AGENTS·패키지 메타데이터를 변경하지 않았고 런타임 의존성을 추가하지 않았다.

최종 전체 테스트는 **2,630 passed, 24 skipped, 14 xfailed**로 종료했다. 리뷰 수정에 추가한 합성 테스트는 56개이며, 건너뜀과 예상 실패는 통과로 세지 않았다. `git diff --check`도 통과했다.

## 재현 명령

코퍼스 경로는 인자로 전달한다. 시작 시점 파서의 복사본과 JSON은 git에 포함하지 않는다.

```bash
/usr/bin/python3 -m scripts.probe_xls_formula_pairs /Users/illuwa/dev/personal/dochan/corpus/poi-src/test-data/spreadsheet --oracle-python /Users/illuwa/dev/personal/dochan/corpus/.venv-oracle/bin/python --output .codex-work/formula-pairs-after-review-strict.json
/usr/bin/python3 -m scripts.probe_xls_formula_corpus /Users/illuwa/dev/personal/dochan/corpus/poi-src/test-data/spreadsheet --parser-snapshot .codex-work/before-review/dochan/office_binary --output .codex-work/formula-corpus-before-review.json
/usr/bin/python3 -m scripts.probe_xls_formula_corpus /Users/illuwa/dev/personal/dochan/corpus/poi-src/test-data/spreadsheet --output .codex-work/formula-corpus-after-review.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
git diff --check
```
