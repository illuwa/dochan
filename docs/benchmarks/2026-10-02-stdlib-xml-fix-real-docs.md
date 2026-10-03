# 표준 라이브러리 XML 전환 리뷰 수정의 실물 검증

2026년 10월 3일에 첫 전환 커밋 `9aa2edd`의 두 독립 리뷰를 재현하고 수정했다. 출력 기준은 lxml을 사용하던 `HEAD~1`이다. README의 Supported Elements 판정은 이 수정에서 바꾸지 않는다. 공개 코퍼스의 같은 파일을 Python 3.9와 `PYTHONHASHSEED=0`으로 읽어 Markdown·JSON·errors의 UTF-8 SHA-256을 비교했다. 암호화 또는 손상 때문에 원래 오류가 있는 문서도 오류 문자열까지 비교했다.

## 공개 실물 검증

| 대상 | 표본 파일 또는 집합 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| DOCX 및 Strict | 공개 DOCX/DOCM 1,794개이며 `deep-table-cell.docx`를 포함한다. | 동일 파일의 `HEAD~1` 출력이다. | 깊은 표의 절단 결과를 포함해 세 출력이 같아야 한다. | 1,794/1,794개가 같았다. | 통과했다. |
| PPTX 및 스타일 | 공개 PPTX/PPTM 549개이며 `ShapeLineProperties.pptx`를 포함한다. | 동일 파일의 `HEAD~1` 출력이다. | 세 출력이 같아야 한다. | 549/549개가 같았다. | 통과했다. |
| XLSX 및 스트리밍·VML | 공개 XLSX/XLSM 370개이며 `BrNotClosed.xlsx`, `poc-shared-strings.xlsx`를 포함한다. | 동일 파일의 `HEAD~1` 출력이다. | 행·VML 이미지 및 세 출력이 같아야 한다. | 일반 API 369개와 순차 출력 해시 1개가 모두 같았다. | 통과했다. |
| HWPX | 공개 HWPX 1,700개이며 `encrypt.hwpx`를 포함한다. | 동일 파일의 `HEAD~1` 출력이다. | 본문과 오류 진단이 같아야 한다. | 1,700/1,700개가 같았다. | 통과했다. |
| PDF 주석·MathML | 공개 PDF 1,007개다. | 동일 파일의 `HEAD~1` 출력이다. | 세 출력이 같아야 한다. | 1,007/1,007개가 같았다. | 통과했다. |

일반 API 5,419개의 변경은 0개다. 큰 반복 문자열 표본 `poc-shared-strings.xlsx`는 제품의 출력 순서와 동일한 청크를 전부 해싱했다. Markdown 12,579,810,358바이트의 SHA-256은 `660ed23976190164526b13a390b5d9ec51cbb75c22db26aa67c1c90abd7a2123`이고, JSON 37,760,638,086바이트의 SHA-256은 `3bc48e753a20af3655b6ccd966915bf88cddf3d1cbcab2b9f367af7d92269e13`이다. errors 해시도 기준과 같다. 이 단독 검증은 69.49초, 최대 RSS 약 82MiB였으며 일반 API로 50GB 출력을 한꺼번에 만드는 메모리 수치를 뜻하지 않는다. 따라서 공개 5,420개 모두 기존 출력과 같지만, 마지막 한 개에는 순차 출력 방식을 사용했다.

## 리뷰 공격 입력 검증

다음 입력은 테스트 안에서 바이트를 조립하거나 리뷰의 생성기에서 만든 합성 입력이다. 시간은 Python 3.9의 단일 실행 관측치이며 성능 보장을 뜻하지 않는다. 상한을 검증하는 단위 테스트는 시간 대신 파서 사용 여부, 부모 노드의 자식 수, 노드 할당 수, 부모별 일괄 제거를 단언한다.

| 지적 | 합성 입력과 기대 | 실제 | 판정 |
|---|---|---|---|
| VML 미완성 시작 태그 | `<a ` 4만 개 또는 `<a b='` 4만 개가 선형으로 끝나야 한다. | 각각 0.01초였고 HTMLParser를 호출하지 않았다. | 통과했다. |
| XLSX 형제 누적 | `<x/><row/>` 16만 쌍에서 이전 형제를 남기지 않아야 한다. | 16만 행을 0.24초에 순회했고 부모 자식이 누적되지 않았다. | 통과했다. |
| HWPX 본문 예산 | 텍스트 문단 15만 개와 초과 빈 문단 2만 개를 일괄 제거해야 한다. | XML 생성은 0.34초, 예산 처리는 0.35초였다. 남은 문단은 15만 개다. | 통과했다. |
| DTD 정화 | 닫히지 않은 `<!DOCTYPE ` 4만 개를 재검색하지 않아야 한다. | 0.04초였고 DTD 정규식을 사용하지 않았다. | 통과했다. |
| DOCX 캡션 | 캡션·표 2만 쌍에서 형제 목록 복사·선형 위치 검색을 반복하지 않아야 한다. | 문서 읽기는 1.22초였고 오류가 없었다. | 통과했다. |
| 스트리밍 요소 상한 | 50MB의 빈 요소를 완주하지 않고 상한에서 중단해야 한다. | 100만 요소 상한 오류를 0.75초에 반환했다. | 통과했다. |
| 깊은 XML | 40만 단 중첩에서 트리 노드 생성 전에 깊이 상한을 적용해야 한다. | 16,384단 파싱 상한에서 0.03초에 거부했다. | 통과했다. |
| 손상 시트 복구 | 잘못된 형제 뒤의 정상 `<row>`를 제한된 범위에서 찾아야 한다. | 합성 XML의 두 행을 모두 반환했다. 최대 네 번, 오류 위치 뒤 4MiB 이내에서만 재동기화한다. | 단위 검증을 통과했다. 해당 손상 형태의 공개 실물 표본은 확인하지 못했다. |

오류 위치를 제공하지 않는 XML 인코딩 오류는 재동기화를 시도하지 않고 기존 XMLSyntaxError로 반환한다. 리뷰의 DTD·엔티티 공격 매트릭스 48변형과 6진입점, 총 288건을 다시 실행한 결과 과도한 엔티티 확장은 0건이었고 실행은 0.30초에 끝났다. 안전한 CDATA·문자 참조에 포함된 원문 `lol`의 최대 횟수는 10회였다.

HWPX 섹션은 DTD를 오류로 보고한다. 보조 XML 함수의 기존 DTD 정화 계약은 기존 테스트를 위해 유지한다. OOXML 파트의 DTD 정화는 따옴표와 내부 부분집합을 추적하는 선형 스캐너다. Expat 2.4.0 이상 사용을 권장한다. 검증 호스트의 Python 3.9는 Expat 2.2.8이므로 파서는 오래된 Expat의 중괄호 네임스페이스 URI를 자체적으로 거부하고 해당 오류에 버전 권고를 붙인다. 정상 CLI의 stderr를 비워야 하는 기존 계약 때문에 import 시 경고를 출력하지 않는다.

## 전체 테스트와 시간

`lxml` import를 차단한 전체 테스트에서 Python 3.9는 4,216 passed, 29 skipped, 14 xfailed였고 Python 3.13은 4,212 passed, 33 skipped, 14 xfailed였다. 두 실행 모두 차단된 import 시도는 0회다. Ruff, `git diff --check`, 로컬 절대 경로 검사도 통과했다. 기존 테스트 단언은 바꾸지 않았다.

DOCX·PPTX는 `HEAD~1`의 단일 작업자 전체 코퍼스 실행과 리뷰 반영본의 단일 작업자 실행을 비교했다. 문서 읽기, Markdown·JSON·errors 생성 및 해싱 시간을 합산했으며 작업자 시작 시간은 제외했다.

| 형식 | 문서 수 | 기준 합계 | 리뷰 반영 합계 | 변화 | 목표 |
|---|---:|---:|---:|---:|---|
| DOCX/DOCM | 1,794 | 12.0967초 | 14.2699초 | +17.97% | +10% 이내 미달 |
| PPTX/PPTM | 549 | 2.6446초 | 2.9025초 | +9.75% | +10% 이내 통과 |

두 수치는 각각 한 회차이므로 작은 차이의 통계적 의미는 주장하지 않는다. DOCX에 남은 비용은 안전한 단일 파서가 요소 시작·종료마다 Python 콜백으로 깊이와 요소 수를 검사하고, 정상 XML도 프롤로그 검사를 별도로 거치는 데서 주로 발생한다. 네임스페이스 범위 기록은 Strict 및 `mc:Choice`가 필요한 노드로 줄였고, 깊이 검사는 트리를 다시 전부 순회하지 않는다. 작은 파트의 별도 C 빠른 경로도 측정했으나 DOCX 16.05초·PPTX 3.22초로 개선이 일관되지 않아 제거했다.

재현 명령은 다음과 같다. 코퍼스 경로는 인자로 전달하며 코퍼스 파일은 저장소에 복사하지 않는다.

```sh
PYTHONHASHSEED=0 /usr/bin/python3 -m scripts.probe_stdlib_xml_migration corpus --source . --workers 4 --exclude poi-src/test-data/spreadsheet/poc-shared-strings.xlsx --output current.jsonl
/usr/bin/python3 -m scripts.probe_stdlib_xml_migration --compare baseline.jsonl current.jsonl
/usr/bin/python3 -m scripts.probe_stdlib_xml_migration --source . --stream-file corpus/poi-src/test-data/spreadsheet/poc-shared-strings.xlsx --output current-stream.json
/usr/bin/python3 -m scripts.block_lxml pytest tests/ -q -p no:cacheprovider
```
