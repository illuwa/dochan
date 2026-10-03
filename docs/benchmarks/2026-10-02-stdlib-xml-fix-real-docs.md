# 표준 라이브러리 XML 전환 3차 리뷰의 실물 검증

2026년 10월 3일에 `59a5ead`를 기준으로 같은 공개 문서의 Markdown, JSON, errors를 UTF-8 SHA-256으로 비교했다. Python 3.9와 `PYTHONHASHSEED=0`을 사용했다. 코퍼스 파일은 읽기만 했고, 출력 전문은 저장하지 않았다. 기존 Supported Elements의 새 칸을 구현한 작업이 아니므로 README 판정은 바꾸지 않는다.

## 공개 실물 판정

| 대상 | 표본 파일 또는 집합 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| DOCX 및 Strict | 공개 DOCX/DOCM 1,794개이며 `FDO74774.docx`, `crop-roundtrip.docx`, `textbox_picturefill.docx`를 포함한다. | 동일 파일의 `59a5ead` 출력 해시다. | 세 출력이 같아야 한다. | 1,794/1,794개가 같았다. | 통과했다. |
| PPTX 및 스타일 | 공개 PPTX/PPTM 549개다. | 동일 파일의 `59a5ead` 출력 해시다. | 세 출력이 같아야 한다. | 549/549개가 같았다. | 통과했다. |
| XLSX 및 스트리밍·VML | 공개 XLSX/XLSM 370개이며 `BrNotClosed.xlsx`와 `poc-shared-strings.xlsx`를 포함한다. | 동일 파일의 `59a5ead` 출력 해시다. | 정상 문서 출력은 같고 손상은 해당 시트에 격리되어야 한다. | 일반 API 369개 중 368개가 같았다. 대형 표본 1개는 순차 출력 해시가 같았다. | 출력 동일성은 369/370개이며, 손상 격리 1개는 의도한 계약 변경이다. |
| HWPX | 공개 HWPX 1,700개다. | 동일 파일의 `59a5ead` 출력 해시다. | 세 출력이 같아야 한다. | 1,700/1,700개가 같았다. | 통과했다. |
| PDF 주석·MathML | 공개 PDF 1,007개다. | 동일 파일의 `59a5ead` 출력 해시다. | 세 출력이 같아야 한다. | 1,007/1,007개가 같았다. | 통과했다. |

일반 API 비교는 5,419개 중 5,418개 동일하며, 대형 표본을 더한 최종 동일성은 5,420개 중 5,419개다. 차이가 난 공개 파일은 `poi-src/test-data/spreadsheet/LIBRE_OFFICE-116306-0.xlsx`다. 기준본은 `xl/worksheets/sheet1.xml`의 요소 수 상한을 패키지 실패로 처리해 출력이 비었다. 수정본은 그 시트에 `ERR: XLSX sheet XML parse failed`를 남기고, 워크북의 다른 정상 시트와 표를 보존한다. 시트 단위 격리 요구와 기존 출력 전량 동일 요구는 이 실물에서 충돌한다. 이 차이를 동일하다고 판정하지 않는다.

`poc-shared-strings.xlsx`는 출력 전체를 파일로 쓰지 않고 순차 해싱했다. Markdown 12,579,810,358바이트의 SHA-256은 `660ed23976190164526b13a390b5d9ec51cbb75c22db26aa67c1c90abd7a2123`이다. JSON 37,760,638,086바이트의 SHA-256은 `3bc48e753a20af3655b6ccd966915bf88cddf3d1cbcab2b9f367af7d92269e13`이다. 두 값과 errors 해시는 기준본과 같다.

## 합성 결함 재현과 수정

| 지적 | 합성 입력 또는 근거 | 수정 후 결과 | 판정 |
|---|---|---|---|
| 손상 시트 재동기화 | 완료 행 뒤에 비ASCII 텍스트·잘못된 형제·잘린 꼬리를 놓은 세 형태와 다중 시트 문서를 만들었다. | 재파싱 없이 완료 행만 유지하고 해당 시트에 ERR를 남겼다. 다른 시트는 읽었다. | 단위 테스트를 통과했다. 동일한 손상 형태의 공개 표본은 확인하지 못했다. |
| 시작 태그 상한 | 8,000개 속성, 청크 경계의 긴 속성, 24MiB 속성 값을 만들었다. | Expat에 내용을 전달하기 전에 최대 256KiB 시작 태그와 1,024개 속성 상한을 적용했다. | 단위 테스트를 통과했다. |
| VML 가짜 이미지 | 주석·CDATA·처리 명령 안의 `imagedata` 뒤에 진짜 이미지 태그를 놓았다. | 진짜 이미지 한 개만 읽었다. | 단위 테스트를 통과했다. |
| VML 닫는 태그 | 열린 태그 250개와 짝 없는 닫는 태그 100만 개를 메모리에서 만들었다. | 이름별 열린 위치 색인을 사용해 1.49초에 끝났고 진짜 이미지를 읽었다. | 단위 테스트와 계측을 통과했다. |
| DTD 내부 주석 | `<!DOCTYPE r [<!-- [ -->]><r/>`를 정화했다. | 유효한 `<r/>`가 남았다. | 단위 테스트를 통과했다. |
| 닫히지 않은 DTD | 내부 부분집합 뒤 31MiB의 일반 바이트를 메모리에서 만들었다. | C 정규식 검색으로 건너뛰어 0.07초에 빈 결과를 반환했다. | 단위 테스트와 계측을 통과했다. |
| 파트 오류 격리 | VML 파트에 깊이 상한 오류를 합성했다. | 해당 파트 ERR만 기록하고 시트 처리를 계속했다. | 단위 테스트를 통과했다. |

시작 태그 상한 때문에 기존의 24MiB 속성을 허용하던 `test_large_token_stream_and_dtd_guard`의 단언을 변경했다. 이 단언은 Expat가 제한 콜백보다 먼저 대량 속성 자료를 만드는 결함을 고정하고 있었다. 차트의 거대 숫자 픽스처는 XML 상한 이내인 5,000자리로 줄였으며, 숫자 변환 보호를 확인하는 단언은 유지했다. DOCX 공개 파일의 관측 최대 시작 태그는 약 174KiB이므로 256KiB 상한을 택했다. 이는 공개 표본 관측치에 맞춘 상한이며 임의의 특정 파일 예외가 아니다.

## 성능

단일 작업자로 DOCX/DOCM 1,794개와 PPTX/PPTM 549개의 읽기·Markdown·JSON·errors 해시 시간을 기준본 네 번, 수정본 세 번 측정했다. 실행 순서를 바꾸어 반복했으며 표는 각 집합의 최솟값을 비교한다. 별도 작업자 시작 시간과 코퍼스 탐색 시간은 제외했다.

| 형식 | 기준본 4회(초) | 수정본 3회(초) | 최솟값 변화 | 판정 |
|---|---|---|---|---|
| DOCX/DOCM | 15.1244, 14.2508, 15.4401, 15.7017 | 17.2663, 17.1603, 20.2585 | +20.42% | 이전 +10% 목표에는 못 미쳤다. |
| PPTX/PPTM | 3.1791, 2.9295, 3.2733, 3.2897 | 3.5937, 3.4856, 4.0619 | +18.98% | 이전 +10% 목표에는 못 미쳤다. |

파트 전체가 시작 태그 바이트 상한보다 작고 등호의 총수가 속성 수 상한 이내이면 상세 검사 없이 통과시킨다. 이 조건에서는 어떤 시작 태그도 상한을 넘을 수 없다. 위험 후보가 있는 큰 파트에는 경계 검사기를 적용한다. 세 회차 모두 DOCX·PPTX 출력 2,343개가 기준과 같았다. 시간은 이 호스트의 관측치이며 보장된 성능 수치는 아니다.

## 재현 명령

코퍼스 루트는 인자로 준다. 일반 비교 결과는 해시·문자 수·오류 요약만 남긴다.

```sh
PYTHONHASHSEED=0 /usr/bin/python3 -m scripts.probe_stdlib_xml_migration corpus --source . --workers 4 --exclude poi-src/test-data/spreadsheet/poc-shared-strings.xlsx --output result.jsonl
/usr/bin/python3 -m scripts.probe_stdlib_xml_migration --compare baseline.jsonl result.jsonl
PYTHONHASHSEED=0 /usr/bin/python3 -m scripts.probe_stdlib_xml_migration --source . --stream-file corpus/poi-src/test-data/spreadsheet/poc-shared-strings.xlsx --output stream-summary.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```
