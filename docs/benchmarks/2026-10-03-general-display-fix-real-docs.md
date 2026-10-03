# General 표시 리뷰 반영: 공개 실물 종단 검증

2026-10-03에 공개 Apache POI test-data와 LibreOffice 문서를 XLS·XLSX 실제 리더로 읽었다. 비교 기준은 커밋 `546b4a4` 사본이며, 최종 수정 전 커밋 `ba6ee5a`와도 별도로 비교했다. 문서별 셀 문자열은 디스크에 저장하지 않고 SHA-256과 길이·출처 좌표만 저장했다. 차이가 난 문서의 셀만 다시 읽어 종류와 표본을 확인했다.

## 칸별 검증

| 칸 | 표본 파일(공개 파일명) | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| XLS General·서식 없는 숫자 | `fact.xls`, `53446.xls`, `54686_fraction_formats.xls` | BIFF 숫자 바이트와 15자리 표시 계약, Excel 저장 분수 `.txt` | 일반 셀과 차트의 큰 수가 15자리 지수 표기를 쓰고 분수는 유지한다. | 리더 종단 숫자 변경 13,975셀(General 서식 확인 13,933셀, 수식·차트 등 원시 서식 메타데이터를 확인하지 못한 42셀). 분수 3,540/3,540셀 일치. | 변경 범위와 회귀 방지는 통과했다. 긴 General 숫자의 독립 Excel CSV 정답은 없다. |
| XLSX General·서식 없는 숫자 | `65016.xlsx`, `FormulaEvalTestData_Copy.xlsx`, `GeneralFormatTests.xlsx` | OOXML 저장 수치와 Excel `TEXT()` 저장 캐시 | 짧은 정수의 `.0`를 정리하고 지수 경계 밖 큰 수를 짧은 표기로 낸다. | 리더 종단 숫자 변경 14,065셀(General 확인 14,054셀, 수식 캐시 등 메타데이터 미확인 11셀). `TEXT()` 캐시 547/832행 일치. | 변경 범위와 캐시 대조는 통과했다. 긴 General 숫자의 독립 Excel CSV 정답은 없다. |
| XLS 텍스트 구역·논리값 | `59858.xls`, `florida_data.ashx.xls`, `StringContinueRecords.xls` | 수정 전·후 리더 출력, BIFF FORMAT/XF 바이트, 합성 XLS 종단 테스트 | 빈 네 번째 구역에서 원문을 보존하고 `_x` 양끝 패딩을 생략한다. | 수정 전 숨겨졌던 라벨·논리값 36셀이 `59858.xls`에서 복구됐다. `546b4a4` 대비 문자열 변경은 접두 문구를 더한 5셀뿐이다. | 원문 소실·회계 패딩 회귀가 해소됐다. 5개 접두 문구의 독립 Excel 표시 정답은 없다. |
| XLSX 텍스트 구역·논리값 | `TextFormatTests.xlsx`, `GeneralFormatTests.xlsx`, 공개 XLSX 텍스트 서식 7셀 | Excel `TEXT()` 저장 캐시와 합성 XLSX 종단 테스트 | 서식 리터럴을 적용하고 빈 네 번째 구역에서 원문을 보존한다. | 실제 리더로 구성한 캐시 입력 832행 중 547행 일치, 기존 일치 손실 0행·신규 일치 30행. 수정 전과 비교한 실제 문자열 변경 7셀은 모두 회계 패딩 제거다. | 공개 캐시와 종단 테스트는 통과했다. |

## 집계 기준과 회귀 검사

공개 XLS 720개와 XLSX 352개, 합계 1,072개의 읽기를 두 코드 사본에서 시도했다. 양쪽 모두 88개에서 리더의 `ERR:`가 있었고 155개는 비어 있는 표 출력을 냈다. 셀 출력이 있는 917개 문서의 실제 표 셀 1,561,789개 해시가 좌표별로 정렬됐고, 최종 변경은 195개 파일의 28,045셀이다. 숫자 28,040셀(XLS 13,975, XLSX 14,065), 문자열 5셀(XLS), 논리값 0셀로 분류됐다. 저장 형식 메타데이터를 독립 원시 프로브에서 식별하지 못한 숫자 53셀은 별도로 남겼다. 차트 시트의 비출력 숫자는 이 집계에 들어가지 않는다.

`ba6ee5a` 대비 최종 출력은 20개 파일의 5,169셀에서 달라졌다. 문자열 5,103셀(XLS 5,096, XLSX 7), 숫자 66셀(XLS 62, XLSX 4)이다. 5,039셀은 양끝 공백만 달라졌고, `59858.xls`에서 사라졌던 라벨 33셀과 논리값 3셀은 다시 나타났다. `fact.xls`와 `FormulaEvalTestData_Copy.xlsx`의 수백 자리 고정 표기는 15자리 유효숫자 지수 표기로 짧아졌다.

실제 리더 경로에 공개 `TEXT()` 입력값과 서식을 넣은 합성 XLSX를 통과시키면 원본 리더 사본은 517/832행, 최종 리더는 547/832행 일치했다. 기존 일치 손실은 0행이고 신규 일치는 30행이다. 구형 서식기 직접 호출 프로브의 513→547, 신규 34행이라는 수치는 불리언 입력 유형을 종단 경로로 보존하지 않은 탓에 독립 검증 수치로 사용하지 않는다. 공개 분수 `54686_fraction_formats.xls`의 실제 리더 출력에서 수식 주석을 제외한 표시 부분은 Excel 저장 텍스트의 3,540/3,540셀과 공백 정규화 후 일치했다.

닫히지 않은 따옴표와 대괄호·따옴표 혼합 형식을 포함한 50,000개 난수 서식에서 숫자·문자열 예외는 각각 0건이었다. 그중 잘못된 따옴표 또는 대괄호 형식 23,923개는 원문 소실 0건이었다. 리뷰가 제공한 압축 XLSX 증폭 표본(약 2.9KB, 공유 문자열 100만 자, 20셀, `@` 100개)은 수정 전 `546b4a4` 최대 RSS 35MiB, 현재 32MiB였고 `doc.errors`에 한 건의 경고가 남았다.

## 실제 리더 변경 셀 무작위 표본

아래 30개는 28,045개 변경 셀에서 고정 시드 20261003으로 균등 추출했다. 표의 파일명은 공개 코퍼스 상대 경로이며, 셀 좌표는 실제 출력 모델의 출처 좌표다.

| 번호 | 공개 파일 | 셀 | 종류 | 이전 표시 | 최종 표시 |
| ---: | --- | --- | --- | --- | --- |
| 1 | `test-data/spreadsheet/65016.xlsx` | `Splits!BG63` | number | `0.0` | `0` |
| 2 | `test-data/spreadsheet/65016.xlsx` | `Splits!AW320` | number | `0.0` | `0` |
| 3 | `test-data/spreadsheet/65016.xlsx` | `Splits!Y51` | number | `162.0` | `162` |
| 4 | `test-data/spreadsheet/65016.xlsx` | `Splits!AS19` | number | `155.0` | `155` |
| 5 | `test-data/spreadsheet/FormulaEvalTestData_Copy.xlsx` | `EverythingTests!L72` | number | `3.5068523895692182E-6` | `0.00000350685238956922` |
| 6 | `lo-src/sc/qa/unit/data/xls/opencl/logical/xor.xls` | `Logical_test!B2606` | number | `-1.3805252543380053` | `-1.38052525433801` |
| 7 | `test-data/spreadsheet/65016.xlsx` | `Splits!AF216` | number | `260.0` | `260` |
| 8 | `lo-src/sc/qa/unit/data/xls/opencl/logical/xor.xls` | `Logical_test!A2530` | number | `39.560811286053756` | `39.5608112860538` |
| 9 | `lo-src/sc/qa/unit/data/xls/opencl/logical/xor.xls` | `Logical_test!A7` | number | `-45.107985080627785` | `-45.1079850806278` |
| 10 | `lo-src/sc/qa/unit/data/xls/opencl/logical/xor.xls` | `Logical_test!B2079` | number | `32.80532669574029` | `32.8053266957403` |
| 11 | `lo-src/sc/qa/unit/data/xls/opencl/statistical/TInv.xls` | `TINV_NAN!C17` | number | `0.9409645772351826` | `0.940964577235183` |
| 12 | `lo-src/sc/qa/unit/data/xls/opencl/financial/Amorlinc.xls` | `Sheet1!H6` | number | `1970.1100000000001` | `1970.11` |
| 13 | `test-data/spreadsheet/65016.xlsx` | `Splits!AS129` | number | `170.0` | `170` |
| 14 | `lo-src/sc/qa/unit/data/xls/opencl/statistical/GammaDist.xls` | `Sheet1!E9` | number | `0.0017651970566456786` | `0.00176519705664568` |
| 15 | `test-data/spreadsheet/65016.xlsx` | `Splits!B45` | number | `264.0` | `264` |
| 16 | `test-data/spreadsheet/65016.xlsx` | `Splits!B374` | number | `261.0` | `261` |
| 17 | `test-data/spreadsheet/65016.xlsx` | `Splits!AJ207` | number | `1014.0` | `1014` |
| 18 | `lo-src/sc/qa/unit/data/xls/opencl/logical/xor.xls` | `Logical_test!A2908` | number | `-35.78365417583499` | `-35.783654175835` |
| 19 | `test-data/spreadsheet/styles-3563.xls` | `районы !L470` | number | `700.8144599999996` | `700.81446` |
| 20 | `lo-src/sc/qa/unit/data/xls/opencl/logical/not.xls` | `Logical_test!A749` | number | `17.310938887907312` | `17.3109388879073` |
| 21 | `test-data/spreadsheet/53446.xls` | `Large Positions!AC118` | number | `623509.9999999851` | `623509.999999985` |
| 22 | `test-data/spreadsheet/65016.xlsx` | `Splits!L152` | number | `260.0` | `260` |
| 23 | `lo-src/sc/qa/unit/data/xls/opencl/logical/not.xls` | `Logical_test!A1620` | number | `30.46011863562508` | `30.4601186356251` |
| 24 | `lo-src/sc/qa/unit/data/xls/opencl/logical/xor.xls` | `Logical_test!B42` | number | `-26.03017233858673` | `-26.0301723385867` |
| 25 | `test-data/spreadsheet/65016.xlsx` | `Splits!AF55` | number | `260.0` | `260` |
| 26 | `test-data/spreadsheet/57231_MixedGasReport.xls` | `December 2013!AA18` | number | `48400.27426526795` | `48400.274265268` |
| 27 | `lo-src/sc/qa/unit/data/xls/opencl/logical/xor.xls` | `Logical_test!A410` | number | `4.6104694742693075` | `4.61046947426931` |
| 28 | `test-data/spreadsheet/65016.xlsx` | `Splits!AG304` | number | `8030.0` | `8030` |
| 29 | `test-data/spreadsheet/65016.xlsx` | `Splits!Y27` | number | `159.0` | `159` |
| 30 | `lo-src/sc/qa/unit/data/xls/opencl/logical/not.xls` | `Logical_test!A216` | number | `-44.244826778828426` | `-44.2448267788284` |

## 판정 범위

15자리 표시와 지수 경계는 두 형식에 공통으로 적용한 추출 계약이다. `GeneralFormatTests.xlsx`의 `TEXT()` 캐시는 작은 수의 일부 경계를 뒷받침하지만, `-10 < adjusted exponent < 15` 전체와 긴 수의 표시가 Excel 화면 또는 CSV와 완전히 같다는 독립 정답은 확보하지 못했다. `JSON`과 Markdown의 표시 문자열에는 원래 수의 16자리 이상 정밀도와 원문 지수 표기가 남지 않는다. 이 한계는 `docs/SUPPORT_NOTES.md`에도 적었다.

`scripts/probe_general_display_e2e.py`의 `dump`·`compare`·`values`·`summarize`로 종단 집계를 재현할 수 있다. `fraction` 명령은 공개 분수 XLS와 동명 `.txt`를 인자로 받는다. `scripts/probe_general_text_cache_e2e.py`의 `snapshot`·`compare`는 공개 캐시 입력을 종단 경로에 넣는다. 원시 셀 프로브 `scripts/probe_general_display.py`의 기존 수치는 후보 탐색에만 쓴다.
