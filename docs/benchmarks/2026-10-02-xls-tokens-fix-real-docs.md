# XLS 토큰 리뷰 반영 실물 검증

2026년 10월 3일 공개 XLS 721개를 리뷰 반영 전 HEAD와 같은 프로브로 비교했다. 실제 Markdown·JSON 출력이 바뀐 파일은 아래 여섯 개뿐이다. 모두 BIFF5 BOUNDSHEET의 이름을 통합문서 코드페이지로 다시 읽은 결과다. 시트명을 같은 시트로 대응시켜 비교하면 셀 텍스트 변경, 기존 수식 소실, 캐시 변경은 각각 0개다. 정의 이름의 파싱 경고는 한 파일에서 바뀌었으나 새 정의 이름 문단은 출력되지 않았다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| BIFF5 PtgMemArea 부가 범위이다. | 해당 공개 실물 표본은 발견하지 못했다. | BIFF5의 행 2바이트 두 개와 열 1바이트 두 개라는 레이아웃을 합성 바이트로 검사했다. | 범위당 6바이트를 소비하고 뒤 수식을 보존해야 한다. | 합성 테스트에서 `SUM($A$1,$B$2)`를 복원했다. | 단위 테스트만 통과했으므로 BIFF5 변형은 실물 미검증이다. |
| BIFF5 코드페이지 32768·32769와 잘못된 문자 바이트이다. | 해당 코드페이지를 쓰는 공개 실물 표본은 확인하지 못했다. | 합성 CODEPAGE 레코드와 단일 바이트 문자열을 사용했다. | 32768은 Mac Roman, 32769는 Windows-1252를 사용하고 잘못된 바이트는 대체 문자로 표시해야 한다. | 세 합성 사례에서 기대 문자열을 복원했다. | 해당 코드페이지의 실물은 미검증이다. |
| 메모리 프레임 안의 PtgExp 진단이다. | 해당 공개 실물 표본은 발견하지 못했다. | 합성 `PtgMemFunc` 안의 `PtgExp`를 사용했다. | 캐시를 유지하고 WARN을 남겨야 한다. | 빈 수식과 `PtgExp inside memory expression` 경고를 반환했다. | 실물은 미검증이다. |
| BIFF5 시트 이름이다. | `testEXCEL_5.xls`와 `testEXCEL_95.xls`이다. | BOUNDSHEET 원시 바이트 `06 46 65 75 69 6c 31`은 길이 6과 `Feuil1`이다. | 두 파일의 첫 시트가 `Feuil1`이어야 한다. | 두 파일 모두 `Feuil1`이며 37식씩 그대로 표시한다. | 2/2파일에서 원시 바이트와 일치했다. |
| BIFF5 시트 이름이다. | `chartx.xls`와 `chartx2.xls`이다. | CODEPAGE 1251과 BOUNDSHEET 원시 바이트 `05 cb e8 f1 f2 31`은 `Лист1`이다. | 두 파일의 첫 시트가 `Лист1`이어야 한다. | 두 파일 모두 `Лист1`이다. | 2/2파일에서 원시 바이트와 일치했다. |
| BIFF5 시트 이름이다. | `shared-formula/biff5.xls`와 `59074.xls`이다. | 첫 파일의 원시 이름은 `Sheet1`이고 둘째 파일의 원시 이름은 `MISSINGDATA`이다. | 각 이름의 첫 글자를 잃거나 UTF-16으로 잘못 읽지 않아야 한다. | 두 이름을 모두 그대로 표시했다. 공유식 파일의 373식도 그대로 표시한다. | 2/2파일에서 원시 바이트와 일치했다. |
| BIFF5 NAME 레코드이다. | `shared-formula/biff5.xls`이다. | NAME의 14바이트 헤더 바로 뒤 원시 이름은 `_FilterDatabase`이다. | 이름의 첫 바이트를 플래그로 소비하지 않아야 한다. | 이름 `_FilterDatabase`와 scope 1을 읽었다. 뒤의 BIFF5 3D 토큰은 여전히 미지원이라 정의 이름 문단을 만들지 않고 경고를 남겼다. | 이름 필드만 실물 1/1레코드에서 검증했다. 전체 정의 이름 수식은 미검증이다. |

리뷰 반영 전 HEAD 대비 실제 출력이 바뀐 공개 파일은 `chartx.xls`, `chartx2.xls`, `shared-formula/biff5.xls`, `59074.xls`, `testEXCEL_5.xls`, `testEXCEL_95.xls` 여섯 개다. 이 중 NAME 경고가 바뀐 파일은 `shared-formula/biff5.xls` 한 개다. 나머지 715개 파일의 Markdown·JSON 해시는 같다. 수식 총 95,932셀 가운데 94,433셀이 표시되고 1,499셀이 표시되지 않아 리뷰 전후 수치가 같다. 문서 ERR이 없는 파일 656개, ERR이 있는 파일 65개, 프로브 예외 0개다.

같은 이름의 POI XLS/XLSX 36쌍 중 수식이 있는 20쌍, 1,070셀을 다시 비교했다. 정확 일치 986셀과 공백 표기만 다른 73셀을 합쳐 1,059셀(98.97%)이 일치한다. 기존 일치가 깨진 셀은 0개다. 독립 캐시 정답 비교도 정확 860개, 숫자 서식 동등 194개, 불일치 10개, 정답지 오류 6개로 유지됐다.

재현에는 `python -m scripts.probe_xls_tokens corpus --output 결과.json`과 `python -m scripts.probe_xls_formula_pairs corpus/poi-src/test-data/spreadsheet --oracle-python 정답지파이썬 --output 결과.json`을 사용했다. 셀별 최종 자료와 리뷰 전후 대응 결과는 각각 `.codex-work/tokens-fix-final.json`, `.codex-work/tokens-fix-regression.json`, `.codex-work/pairs-fix-final.json`에 보관했다. 코퍼스 원본은 저장소로 복사하지 않았다.
