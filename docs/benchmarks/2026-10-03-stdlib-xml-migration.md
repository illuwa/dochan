# lxml 런타임을 표준 라이브러리 XML로 전환한 검증 기록

2026년 10월 3일, 기준 커밋 `5a56b2156b020c247513a0107e27c95e3374bc6a`와 전환본을 비교했습니다. 평가 기록 `2026-10-03-lxml-replacement-evaluation.md`의 단일 경로 결정을 따랐습니다. 런타임과 테스트·스크립트의 lxml import를 모두 제거했으며, 배포 의존성 선언은 오케스트레이터가 정리하도록 그대로 두었습니다. README와 CHANGELOG는 변경하지 않았습니다.

## 공개 실물 검증

POI, LibreOffice, Tika, pdf.js, hwp-public 전체에서 DOCX/DOCM, PPTX/PPTM, XLSX/XLSM, HWPX, PDF를 재귀 탐색했습니다. 같은 입력 경로, 같은 Python 3.9와 `PYTHONHASHSEED=0`으로 Markdown, JSON, errors 각각의 UTF-8 SHA-256을 비교했습니다. 암호화·손상 입력의 기존 오류도 포함하여 비교했으며, 출력이 동일하다는 판정은 오류 없는 문서라는 뜻이 아닙니다.

| 대상 | 표본 파일 또는 집합 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| DOCX | 공개 DOCX/DOCM 1,794개이며 `deep-table-cell.docx`, `ExternalEntityInText.docx`를 포함합니다. | 동일 파일의 HEAD 출력입니다. | Markdown·JSON·errors 변경이 없어야 합니다. | 1,794/1,794개가 동일합니다. | 통과했습니다. |
| PPTX | 공개 PPTX/PPTM 549개입니다. | 동일 파일의 HEAD 출력입니다. | 세 출력이 모두 같아야 합니다. | 549/549개가 동일합니다. | 통과했습니다. |
| XLSX | 공개 XLSX/XLSM 370개이며 `BrNotClosed.xlsx`와 아래 대형 표본을 포함합니다. | 동일 파일의 HEAD 출력입니다. | 일반·스트리밍·VML의 출력 계약이 같아야 합니다. | 370/370개가 동일합니다. | 통과했습니다. |
| HWPX | 공개 HWPX 1,700개이며 `encrypt.hwpx`를 포함합니다. | 동일 파일의 HEAD 출력입니다. | 정상 결과와 손상 입력 진단이 같아야 합니다. | 1,700/1,700개가 동일합니다. | 통과했습니다. |
| PDF | 공개 PDF 1,007개입니다. | 동일 파일의 HEAD 출력입니다. | 주석과 MathML을 포함한 세 출력이 같아야 합니다. | 1,007/1,007개가 동일합니다. | 통과했습니다. |

총 5,420개에서 변경은 0개이고 미검증도 0개입니다. 일반 API는 5,419개에 사용했습니다. `poc-shared-strings.xlsx`는 1MiB 문자열을 반복 참조하여 전체 문자열을 한꺼번에 생성하는 검증이 60초 제한에 걸렸으므로, 원자료에는 이 사실을 남기고 출력 바이트 전량을 순차 해싱하는 별도 검증을 수행했습니다.

### 대형 반복 문자열 표본

JSON은 제품의 `to_dict`와 동일한 `JSONEncoder(ensure_ascii=False, indent=2).iterencode`를 사용했습니다. Markdown은 원래 `_cell_text` 결과를 재사용하고 동일한 표 행·구분자·문서 바깥 출력을 순서대로 해싱했습니다. 축소한 실물 모델과 한글·이모지·이스케이프·병합 셀·불균일 행을 포함한 합성 6문서에서 일반 API의 실제 출력과 해시·바이트수 일치를 먼저 검증했습니다. 파일명으로 통과시키거나 모델 해시만으로 출력 동일성을 대신하지 않았습니다.

| 출력 | 전체 UTF-8 바이트 | HEAD와 전환본에서 일치한 SHA-256 |
|---|---:|---|
| Markdown | 12,579,810,358 | `660ed23976190164526b13a390b5d9ec51cbb75c22db26aa67c1c90abd7a2123` |
| JSON | 37,760,638,086 | `3bc48e753a20af3655b6ccd966915bf88cddf3d1cbcab2b9f367af7d92269e13` |

errors도 같습니다. 최대 RSS는 HEAD 약 103.4MiB, 전환본 약 85.7MiB였습니다. 이 수치는 순차 해시 검증 프로세스의 실측값이며 제품의 일반 대용량 출력 메모리 성능을 뜻하지 않습니다.

## 내부 짝 검증

내부 HWP/HWPX 76쌍과 PDF/HWPX 79쌍을 같은 비교 스크립트로 전후 검증했습니다. 실행 시간 항목을 제외한 모든 지표가 같습니다. 내부 파일명·내용은 기록하지 않았습니다.

| 집계 지표 | HEAD | 전환본 |
|---|---:|---:|
| HWP/HWPX 평균 토큰 일치율 | 0.9997 | 0.9997 |
| HWP/HWPX 표 서명 일치율 | 0.9987 | 0.9987 |
| HWP/HWPX 평균 셀 일치율 | 0.9991 | 0.9991 |
| HWP/HWPX 평균 서식 일치율 | 1.0000 | 1.0000 |
| PDF/HWPX 평균 토큰 일치율 | 0.9754 | 0.9754 |
| PDF/HWPX 평균 셀 일치율 | 0.9152 | 0.9152 |
| PDF/HWPX 표 서명 일치율 | 0.6533 | 0.6533 |
| PDF/HWPX 병합 일치율 | 0.9277 | 0.9277 |

## 보안 및 호환 정책

공용 모듈은 pyexpat의 DTD·엔티티 선언 핸들러에서 즉시 거부하고 첫 요소에 도달하면 검사를 중지합니다. TreeBuilder의 doctype 예외만으로 보호된다고 가정하지 않습니다. 본문 트리 생성은 이 검사가 끝난 뒤에만 실행합니다. 외부 리소스 resolver는 설치하지 않으며 네트워크나 파일에서 엔티티를 가져오지 않습니다.

기존 OOXML과 HWPX 본문의 엔티티 미확장 계약은 DTD·사용자 정의 참조를 정화한 다음 다시 프롤로그 검사를 하는 방식으로 보존했습니다. UTF-16에서도 같은 절차를 적용합니다. PDF 주석·MathML 및 HWPX 차트는 DTD를 거부합니다. 순수 안전 파서의 기본 정책도 선언 거부입니다.

파트·압축비·ZIP 예산을 유지하며 공용 입력 크기는 기본 100MiB, 트리 깊이는 기본 256입니다. OOXML 패키지는 기존 복구 제한에 맞춰 깊이 2,048에서 잘라냅니다. 스트리밍은 1MiB 청크와 XMLPullParser, 부모 스택, clear·부모 제거를 사용합니다. 선언과 네임스페이스 복사량에도 상한을 둡니다. VML은 엄격 XML 파싱이 실패할 때만 HTMLParser로 필요한 이미지 참조를 수집합니다.

다중 바이트 인코딩은 선언 전체를 입력 크기 상한 안에서 확인한 뒤 문자열 또는 증분 디코더로 처리합니다. Python 3.13 expat의 지연 이벤트는 close 이후까지 모두 소비합니다. Strict 정규화는 확장 이름, 접두사 범위, 관계 Type만 바꾸며 사용자 텍스트를 치환하지 않습니다. 중첩 접두사 재바인딩과 namespace URI의 문자 참조도 검증했습니다.

부모 맵은 읽는 story나 차트의 문맥을 전달하는 용도로 사용합니다. HWPX의 예산 초과 노드 제거에는 순회 목록 복사본을 사용하여 다음 형제 누락을 막았습니다. 주석·PI 노드는 보존하고 텍스트 수집에서 해당 노드의 내용만 제외하며 tail은 기존 계약대로 유지합니다. 프로세스 전역 GC 설정은 바꾸지 않았습니다.

## 테스트와 단계별 판정

| 단계 | Python 3.9 전체 테스트 | 공개 출력 검증 |
|---|---:|---|
| HEAD | 4,153 passed | 기준선을 확보했습니다. |
| 공용 파서 | 4,181 passed | 런타임 연결 전이므로 기준 경로가 같습니다. |
| 작은 모듈 | 4,181 passed | 일반 5,419개 출력이 같았으며 대형 표본은 마지막에 전량 검증했습니다. |
| HWPX 본문 | 4,188 passed | HWPX 1,700개가 같습니다. |
| OOXML 패키지·DOCX·PPTX | 4,193 passed | 일반 Office 2,712개가 같습니다. |
| XLSX 스트리밍 | 4,198 passed | 다섯 형식 5,420개가 같습니다. |
| 최종 lxml 차단 | 4,199 passed | 최종 순차 검증에서도 출력 동일성을 확인합니다. |

최종 Python 3.9 결과는 4,199 passed, 29 skipped, 14 xfailed입니다. Python 3.13은 4,195 passed, 33 skipped, 14 xfailed입니다. HEAD의 건너뜀·예상 실패 개수와 같습니다. 두 버전 모두 `scripts.block_lxml`이 기록한 lxml import 시도는 0회이며, 런타임 import 검색 결과도 0개입니다. 새 테스트의 실패를 먼저 확인한 뒤 구현했고, 기존 단언의 기대값은 바꾸지 않았습니다. nsmap·루트 참조·Resolver 검사 등 파서별 테스트 장치는 동일 의미의 부모 맵·안전 파서 진입 차단 검사로 옮겼습니다.

Python 3.13 환경은 이미 존재하던 인터프리터와 캐시 패키지로 워크트리에 구성했으며 네트워크 설치를 하지 않았습니다. ruff와 로컬 경로 누출 검사도 통과했습니다.

## 독립 순차 성능

다른 테스트와 코퍼스 검증을 종료한 뒤, 같은 Python 3.9에서 작업자 1개로 HEAD 전체를 먼저 읽고 전환본 전체를 이어 읽었습니다. 시간은 문서 읽기와 Markdown·JSON·errors 생성 및 해싱 구간의 합계입니다. 작업자 생성·교체 비용은 합계에서 제외했습니다. GC 전역 설정을 바꾸지 않았습니다. 단일 회차 측정이므로 작은 변화에 통계적 유의성을 주장하지 않습니다.

| 형식 | 일반 API 표본 수 | HEAD 합계(초) | 전환본 합계(초) | 변화 |
|---|---:|---:|---:|---:|
| DOCX | 1,794 | 12.0967 | 15.1728 | +25.43% |
| PPTX | 549 | 2.6446 | 3.3507 | +26.70% |
| XLSX | 369 | 31.4937 | 33.7621 | +7.20% |
| HWPX | 1,700 | 51.7721 | 56.4031 | +8.94% |
| PDF | 1,007 | 28.0486 | 27.4378 | -2.18% |
| 일반 API 합계 | 5,419 | 126.0556 | 136.1265 | +7.99% |

DOCX와 PPTX의 형식별 시간 증가는 20%를 넘습니다. 요청한 중단 기준은 전체 합계 +20%이며 일반 API 합계는 그 아래입니다. 위 표는 대형 반복 문자열 XLSX 1개의 대체 출력 검증 시간을 포함하지 않으며, 이를 아래에서 별도로 합산합니다. 독립 측정에서도 일반 5,419개의 출력 해시는 전부 동일했습니다.

대형 반복 문자열 표본도 일반 표본의 측정이 끝난 뒤 HEAD, 전환본 순서로 독립 재측정했습니다. 이 표본은 일반 API가 전체 출력 문자열을 한꺼번에 만들기 어려우므로, 양쪽 모두 같은 순차 출력 검증 도구를 사용했습니다. 따라서 아래 전체 합계는 **일반 API 5,419개와 대체 출력 검증 1개를 합친 동일 방법 간 비교**이며, 5,420개 모두를 일반 API로 완주한 시간은 아닙니다. 대체 출력 시간은 문서 파싱, 출력 사전 준비, Markdown·JSON 전체 바이트 및 errors 해싱을 포함하며 합성 사전 점검과 import 시간은 제외합니다.

| 측정 구분 | 표본 수 | HEAD 합계(초) | 전환본 합계(초) | 변화 |
|---|---:|---:|---:|---:|
| 일반 API 출력·해싱 | 5,419 | 126.0556 | 136.1265 | +7.99% |
| 대형 XLSX 순차 출력·해싱 | 1 | 66.5100 | 64.8328 | -2.52% |
| 전체 동일 방법 합계 | 5,420 | 192.5655 | 200.9593 | +4.36% |

전체 증가는 **4.36%로 +20% 중단 기준보다 낮습니다**. 대형 표본을 제외한 일반 API 합계도 +7.99%로 기준 이내입니다. 독립 재측정에서도 5,420개 모두의 Markdown·JSON·errors 해시는 같았습니다. 대형 표본의 독립 실행 최대 RSS는 HEAD 103.4MiB, 전환본 86.4MiB였습니다.

## 재현 방법

기준 소스는 비교할 커밋을 별도 디렉터리에 추출하여 고정하고, 실제 코퍼스는 복사하지 않고 인자로 전달합니다. 출력 경로는 git에서 제외되는 작업 디렉터리를 권합니다.

```sh
PYTHONHASHSEED=0 python -m scripts.probe_stdlib_xml_migration corpus --source BASELINE_SOURCE --workers 1 --exclude poi-src/test-data/spreadsheet/poc-shared-strings.xlsx --output baseline.jsonl
PYTHONHASHSEED=0 python -m scripts.probe_stdlib_xml_migration corpus --source . --workers 1 --exclude poi-src/test-data/spreadsheet/poc-shared-strings.xlsx --output current.jsonl
python -m scripts.probe_stdlib_xml_migration --compare baseline.jsonl current.jsonl
python -m scripts.block_lxml pytest tests/ -q -p no:cacheprovider
python -m scripts.compare_hwp_pairs test_pairs/
python -m scripts.compare_pdf_pairs test_pairs/
```

대형 표본은 다음과 같이 같은 명령을 각 소스에 실행하여 비교합니다.

```sh
python -m scripts.probe_stdlib_xml_migration --source BASELINE_SOURCE --stream-file corpus/poi-src/test-data/spreadsheet/poc-shared-strings.xlsx --output baseline-stream.json
python -m scripts.probe_stdlib_xml_migration --source . --stream-file corpus/poi-src/test-data/spreadsheet/poc-shared-strings.xlsx --output current-stream.json
```

원자료는 작업 보고서가 가리키는 비교 JSON과 실행 로그에 보존합니다.
