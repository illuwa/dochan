# HWP·HWPX 문서 단위 서식 런 예산 검증

2026-10-03에 기준 HEAD `558695c80eca17c41dfa4b3088e795af2633f02e`와 변경 구현을 비교했다. 공개 HWP 5,376개와 HWPX 1,700개의 Markdown, JSON, 오류 목록은 모두 동일했다. 이 작업은 지원 요소를 새로 추가하는 작업이 아니라 기존 서식 처리의 자원 증폭을 제한하는 작업이다. README의 지원 표는 수정하지 않았다.

아래 성능표와 테스트 집계는 최초 구현 `44c6733`의 기록이다. 리뷰 반영 후의 문단·각주 예산, 최종 테스트와 재측정 수치는 [리뷰 반영 검증](2026-10-02-hwp-runs-fix-real-docs.md)에 기록했다.

## 판정과 구현 정책

| 칸 | 표본 파일 또는 범위 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| HWP 글자모양·TextRun | 공개 HWP 5,376개, 최대 런 표본 `hwp/big_file.hwp` | 동일 입력의 HEAD 공개 API 출력과 원시 PARA_CHAR_SHAPE 바이트 관찰 | Markdown·JSON·오류 목록 변경 0건 | 5,376/5,376개 일치, 변경 0건 | 회귀 검증 통과다. |
| HWPX 글자모양·TextRun | 공개 HWPX 1,700개, 아래 상위 20 표본 | 동일 입력의 HEAD 공개 API 출력과 XML run 계수 | Markdown·JSON·오류 목록 변경 0건 | 1,700/1,700개 일치, 변경 0건 | 회귀 검증 통과다. |
| HWP 초과 서식 폴백 | 합성 100만·300만 글자모양 구간 | 직접 조립한 WCHAR 본문과 위치·서식 ID 쌍 | 상한까지 서식을 보존하고 나머지 본문을 무서식으로 유지하며 경고를 한 번만 낸다. | 정상 런 524,288개와 꼬리 1개, 본문 전부 보존, WARN 1회다. | 단위·증폭 검증을 통과했다. 상한 초과 실물은 없다. |
| HWPX 초과 서식 폴백 | 합성 10만·30만 XML run | 직접 조립한 ZIP/XML 본문 | 문서 전체에서 상한을 공유하고 본문을 보존한다. | 10만은 변화가 없고, 30만은 정상 런 150,000개와 두 문단의 꼬리 2개다. | 단위·증폭 검증을 통과했다. 상한 초과 실물은 없다. |
| HWP↔HWPX 동일 문서 | 내부 실물 76쌍 | HWPX 출력을 정답으로 삼은 기존 쌍 비교 도구 | 전후 집계와 쌍별 판정이 동일하다. | 76/76쌍의 비교 결과가 동일하다. | 검증을 통과했다. 파일명과 내용은 기록하지 않았다. |

HWP 상한은 공개 문서의 모델 런 최대 131,072개의 4배인 524,288개다. 최대 표본은 문단 131,072개에 각각 런 하나가 있는 문서이며, 한 문단의 글자모양 분할 수가 아니다. 실제 문단당 PARA_CHAR_SHAPE 쌍의 최대는 152개다. HWPX 서식 런 상한은 공개 모델 런 최대 33,617개의 약 4.46배인 150,000개다. 명세가 정한 숫자가 아니라 공개 코퍼스 실측에 여유를 둔 구현 정책이다. 리뷰 반영에서는 HWPX 문단·각주와 개체 분할 경계도 별도로 제한하고, 초과 본문을 한 무서식 문단으로 모은다. 글자 수를 잘라 본문을 버리지는 않는다.

HWP는 PARA_CHAR_SHAPE 전체를 튜플 목록으로 만들던 경로를 `memoryview`와 `struct.iter_unpack` 순회로 바꿨다. 예산을 소진하면 추가 서식 구간의 런 생성을 멈추고 해독된 본문의 남은 문자열을 한 런으로 보존한다. 하이퍼링크가 추가로 만드는 분할에도 같은 예산을 적용하고, 무서식 꼬리에는 링크를 다시 적용하지 않는다. 다음 문단·섹션과 표·각주 등 중첩 본문도 같은 파서의 예산을 소비한다.

동일한 출력 위치의 중복 쌍에서 빈 런을 만들지 않는 것은 기존 동작이다. 이번 변경은 쌍 전체의 튜플 목록을 제거하고, 그런 중복 쌍이 서식 예산을 소비하지 않도록 한 것이다. 서로 다른 위치의 같은 서식은 JSON의 기존 런 경계를 유지한다. 이를 무조건 합치면 기존 출력이 달라지므로 합치지 않았다.

HWPX도 XML run마다 TextRun을 만들던 경로에 증폭이 있었다. 남은 예산이 없으면 문자열 조각만 수집하고 문단이나 개체 경계에서 무서식 런 하나로 확정한다. 단일 XML run 안의 필드 경계 분할도 제한한다. 파서를 새 문서에 재사용하면 예산과 경고 상태를 초기화한다.

이는 문서 전체의 **서식 분할 예산**이다. 본문 구조를 보존하기 위한 무서식 폴백 런, HWP 책갈피와 독립 양식 마커, HWPX 각주 참조 마커는 별도로 남는다. 따라서 모든 종류의 TextRun 합계가 항상 서식 상한 이하라는 뜻은 아니다. 리뷰 반영에서는 HWPX 각주 참조가 만드는 문단도 문단·각주 예약에 포함한다. 기존 레코드·문서 바이트·XML 크기·깊이 제한도 유지된다. XML DOM, 원시 문자 위치 맵, 본문 문자열 및 JSON 직렬화 자체의 비용까지 제거하는 변경은 아니다.

## 공개 전체 회귀와 내부 쌍 검증

두 폴더의 확장자를 대소문자 구분 없이 수집했다. `hwp/`에는 HWPX 25개가, `hwpx/`에는 HWP 12개가 있었으며 대문자 HWP 확장자도 1개 있었다. 폴더 이름만으로 형식을 고르거나 소문자 glob만 쓰면 전체 검증에서 누락된다.

공개 7,076개 모두 공개 API 실행을 마쳤다. Markdown 문자열, JSON 문자열, 오류 목록 각각의 SHA-256을 HEAD와 비교해 변경 0건, 누락 0건, 프로브 예외 0건을 확인했다. HWP 32개와 HWPX 16개에는 기준 구현부터 진단이 있었으며, 이 진단도 그대로였다. 모든 표본이 오류 없는 완전한 문서라는 판정은 아니다. 4개 프로세스의 전체 순회는 HEAD 62.808초, 변경 구현 57.010초였으며, 이 순회 시간은 성능 회귀 판정용 통제 실험으로 보지 않는다.

내부 실물 76쌍의 평균 텍스트 토큰 비율은 0.9997, 최소는 0.9927이었다. 표 구조 일치율은 0.9987, 평균 셀 일치율은 0.9991, 중첩 표 일치율과 동일 본문 문단의 평균 서식 일치율은 1.0이었다. 오류가 있는 쌍은 0개였다. 이 수치와 익명 쌍별 결과는 전후 동일하다. HWP와 HWPX 출력이 모든 면에서 완전히 같다는 뜻은 아니다.

## 합성 증폭 입력의 공개 API 측정

Apple M5 Pro, 메모리 48GB, macOS의 `/usr/bin/python3` 3.9에서 각 조건을 새 인터프리터로 한 번씩 측정했다. 입력 준비는 부모 프로세스에서 끝냈으며 아래 시간은 `Dochan` 생성부터 `to_markdown`, `to_json`까지의 합이다. RSS는 macOS `ru_maxrss`를 MiB로 환산한 프로세스 최고값이다. 반복 측정의 평균이나 보장 성능은 아니다.

HWP는 기존 재현과 같이 OLE 스트림 경계만 대역으로 제공하고, 압축 해제·DocInfo·본문 파싱·두 직렬화는 실제 공개 API를 실행했다. 따라서 OLE 디렉터리 디코딩 비용은 포함하지 않는다. HWPX는 실제 ZIP 파일을 읽었다. HWPX 30만 run은 기존 섹션 XML 토큰 제한에 걸리지 않도록 10만씩 세 섹션에 담았다. 전후 입력은 같다.

같은 서식 조건은 서로 다른 두 서식 ID가 같은 속성을 가지며, 교대 서식 조건은 실제 굵기 속성도 바뀐다. 모델의 글자 수뿐 아니라 Markdown과 JSON에 출력된 본문 전체도 기대한 글자 수와 비교했다. 모든 측정에서 본문을 보존했다.

| 형식 | 입력 구간 | 서식 | 압축 입력 bytes | 런 수 전→후 | API 초 전→후 | 최고 RSS MiB 전→후 |
|---|---:|---|---:|---:|---:|---:|
| HWP | 1,000,000 | 동일 | 1,639,812 | 1,000,000 → 524,289 | 7.988 → 3.948 | 2148.8 → 1169.4 |
| HWP | 1,000,000 | 교대 | 1,639,815 | 1,000,000 → 524,289 | 8.473 → 4.056 | 2145.4 → 1169.7 |
| HWP | 3,000,000 | 동일 | 4,915,786 | 3,000,000 → 524,289 | 26.025 → 4.661 | 6405.6 → 1310.7 |
| HWP | 3,000,000 | 교대 | 4,915,789 | 3,000,000 → 524,289 | 28.210 → 4.418 | 6386.0 → 1311.5 |
| HWPX | 100,000 | 동일 | 16,618 | 100,000 → 100,000 | 1.228 → 1.049 | 307.0 → 306.9 |
| HWPX | 100,000 | 교대 | 16,624 | 100,000 → 100,000 | 1.196 → 1.072 | 306.6 → 306.5 |
| HWPX | 300,000 | 동일 | 49,086 | 300,000 → 150,002 | 3.461 → 2.180 | 724.9 → 417.0 |
| HWPX | 300,000 | 교대 | 49,092 | 300,000 → 150,002 | 3.786 → 2.202 | 711.9 → 417.3 |

## 단위 테스트와 재현

`tests/test_hwp_run_budget.py`는 앞부분 서식과 꼬리 본문, 섹션 간 누적, 일반 문단의 예산 소비, 중복 위치, 중첩 각주, 링크 분할, 조기 할당 중단, 링크와 글자모양 꼬리 병합을 검증한다. `tests/test_hwpx_run_budget.py`는 공개 API, 중첩 표·각주·섹션, 개체 경계, 정확한 상한과 파서 재사용, 단일 XML run 내부 필드 분할을 검증한다. `tests/test_hwp_runs_benchmark.py`는 합성 입력의 실제 굵기 교대와 본문, HWPX 섹션 분할을 검증한다.

TDD에서 HWP 신규 테스트는 구현 전 7개 실패·중복 위치 1개 통과였고, HWPX 신규 테스트는 구현 전 5개 실패였다. 구현 후 모두 통과했다. 전체 테스트는 3,347 passed, 25 skipped, 14 xfailed였고 `ruff check dochan scripts tests`와 `git diff --check`도 통과했다. 기존 테스트 단언은 변경하지 않았다.

코퍼스 파일은 저장소에 복사하지 않는다. 아래 `CORPUS`, `HEAD_SOURCE`는 사용자가 제공하는 코퍼스와 기준 소스 경로다. 측정 스크립트는 문서 본문을 출력하거나 저장하지 않고 공개 표본 식별자·수치·해시를 기록한다.

```bash
/usr/bin/python3 -m scripts.probe_hwp_runs "$CORPUS" --source-root "$HEAD_SOURCE" --output .codex-work/runs-head.json
/usr/bin/python3 -m scripts.probe_hwp_runs "$CORPUS" --source-root . --compare .codex-work/runs-head.json --output .codex-work/runs-current.json
/usr/bin/python3 -m scripts.benchmark_hwp_runs --source-root "$HEAD_SOURCE" --format hwp --count 3000000 --style alternating
/usr/bin/python3 -m scripts.benchmark_hwp_runs --source-root . --format hwp --count 3000000 --style alternating
/usr/bin/python3 -m scripts.benchmark_hwp_runs --source-root . --format hwpx --count 300000 --style alternating
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

상한 초과 공개 실물은 발견하지 못했다. 따라서 초과 시의 폴백은 합성 입력으로 검증한 기능이며, 상한 초과 실물 검증은 미검증으로 남긴다. 기존 지원 표의 체크를 새로 부여할 근거로 확대하지 않는다.

## 공개 코퍼스 HEAD 분포

공개 HWP 5,376개와 HWPX 1,700개를 HEAD에서 읽고, 파서가 방문한 문단의 원시 글자모양 쌍과 텍스트 및 최종 모델에 남은 TextRun을 계수했다. HWP의 문단 글자 수는 PARA_TEXT를 해독한 유니코드 문자 수이며, HWPX는 문단의 직접 run 안 t 요소의 문자 수이다. HWPX의 글자모양 쌍 열은 직접 run 요소 개수로 측정했다. 기존 제한 또는 오류로 방문하지 못한 문단은 분포에 포함하지 않았다.

| 형식 | 지표 | 관측 수 | 최대 | p50 | p90 | p95 | p99 | p99.9 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| HWP | 문단당 글자모양 쌍(HWPX: run) | 2,286,219 | 152 | 1 | 1 | 2 | 7 | 20 |
| HWP | 문단당 글자 수 | 2,286,219 | 3,354 | 5 | 30 | 57 | 134 | 308 |
| HWP | 문서당 TextRun 수 | 5,376 | 131,072 | 62 | 599 | 1,123 | 7,138 | 24,851 |
| HWPX | 문단당 글자모양 쌍(HWPX: run) | 708,767 | 96 | 1 | 2 | 3 | 12 | 26 |
| HWPX | 문단당 글자 수 | 708,767 | 3,236 | 5 | 43 | 72 | 147 | 329 |
| HWPX | 문서당 TextRun 수 | 1,700 | 33,617 | 97 | 1,050 | 1,720 | 4,986 | 33,547 |

### HWP 문단당 글자모양 쌍(HWPX: run) 상위 20

| 순위 | 공개 표본 파일 | 문단 인덱스(0부터) | 값 |
|---:|---|---:|---:|
| 1 | hwp/hangulang-api-doc.hwp | 1189 | 152 |
| 2 | hwp/hwpctl_API_v2.4.hwp | 1189 | 152 |
| 3 | hwp/hangulang-api-doc.hwp | 899 | 141 |
| 4 | hwp/hwpctl_API_v2.4.hwp | 899 | 141 |
| 5 | hwp/hangulang-api-doc.hwp | 2585 | 127 |
| 6 | hwp/hwpctl_API_v2.4.hwp | 2585 | 127 |
| 7 | hwp/scourt-A1176 소송절차 안내서(합의.단독).hwp | 40 | 126 |
| 8 | hwp/hangulang-api-doc.hwp | 839 | 102 |
| 9 | hwp/hangulang-api-doc.hwp | 2584 | 102 |
| 10 | hwp/hwpctl_API_v2.4.hwp | 839 | 102 |
| 11 | hwp/hwpctl_API_v2.4.hwp | 2584 | 102 |
| 12 | hwp/scourt-(서울중앙지방법원)지식재산전담부 소송절차 안내서(게시유지의견및 내용 년도 업데이트).hwp | 158 | 99 |
| 13 | hwp/nts-251015 (기재부 보도자료) 토지거래허가구역 규제지역 지정, 대출규제 보완 등 주택시장 안정화 대책 마련.hwp | 21 | 96 |
| 14 | hwp/hangulang-api-doc.hwp | 1981 | 95 |
| 15 | hwp/hwpctl_API_v2.4.hwp | 1981 | 95 |
| 16 | hwp/hangulang-api-doc.hwp | 2722 | 89 |
| 17 | hwp/hwpctl_API_v2.4.hwp | 2722 | 89 |
| 18 | hwp/nts-별지 제1호 서식_현금영수증 미발급 신고서.hwp | 95 | 89 |
| 19 | hwp/hangulang-api-doc.hwp | 3857 | 84 |
| 20 | hwp/hangulang-api-doc.hwp | 3912 | 84 |

### HWP 문단당 글자 수 상위 20

| 순위 | 공개 표본 파일 | 문단 인덱스(0부터) | 값 |
|---:|---|---:|---:|
| 1 | hwp/scourt-8_기초조사표(조정신청서용 신청인)(완료3).hwp | 183 | 3,354 |
| 2 | hwp/scourt-9_기초조사표(조정신청서용-피신청인(완료3).hwp | 181 | 3,353 |
| 3 | hwp/hwpparser-maven-test-필드_누름틀.hwp | 19 | 3,329 |
| 4 | hwp/multicolumns.hwp | 1 | 1,968 |
| 5 | hwp/multicolumns.hwp | 2 | 1,845 |
| 6 | hwp/hangulang-para-001.hwp | 20 | 1,691 |
| 7 | hwp/para-001.hwp | 20 | 1,691 |
| 8 | hwp/scourt-6_기초조사표(소송용 - 피고)(완료3).hwp | 181 | 1,634 |
| 9 | hwp/scourt-7_기초조사표(소송용 원고)(완료3).hwp | 173 | 1,634 |
| 10 | hwp/hwpparser-maven-구버전_5.0.2.2_Picture_컨트롤.hwp | 40 | 1,421 |
| 11 | hwp/alhangeul-macos-exam_eng.hwp | 306 | 1,298 |
| 12 | hwp/exam_eng.hwp | 306 | 1,298 |
| 13 | hwp/nts-(제2025-9호)현금영수증 발급의무 위반자를 신고한 자에 대한 포상금 고시.hwp | 180 | 1,244 |
| 14 | hwp/catalogue.hwp | 5413 | 1,239 |
| 15 | hwp/scourt-6_기초조사표(소송용 - 피고)(완료3).hwp | 182 | 1,204 |
| 16 | hwp/scourt-7_기초조사표(소송용 원고)(완료3).hwp | 174 | 1,204 |
| 17 | hwp/hwpparser-maven-구버전_5.0.2.2_Picture_컨트롤.hwp | 22 | 1,187 |
| 18 | hwp/alhangeul-macos-exam_eng.hwp | 344 | 1,183 |
| 19 | hwp/exam_eng.hwp | 344 | 1,183 |
| 20 | hwp/rhwp-1342000_edu_curriculum_map.hwp | 442 | 1,151 |

### HWP 문서당 TextRun 수 상위 20

| 순위 | 공개 표본 파일 | 문단 인덱스(0부터) | 값 |
|---:|---|---:|---:|
| 1 | hwp/big_file.hwp | — | 131,072 |
| 2 | hwp/hwplib-big_file.hwp | — | 131,072 |
| 3 | hwp/catalogue.hwp | — | 54,034 |
| 4 | hwp/rhwp-1130000-201900011_D0150004-1-002_2017년기준_시장구조조사.hwp | — | 52,734 |
| 5 | hwp/pubinst-kostat_2024년_사회조사_결과_보도자료.hwp | — | 29,671 |
| 6 | hwp/rhwp-1342000_edu_curriculum_map.hwp | — | 24,851 |
| 7 | hwp/han_grammar.hwp | — | 21,149 |
| 8 | hwp/hwp3-sample10-hwp5.hwp | — | 20,571 |
| 9 | hwp/korea-old-210525 2020년 기업특성별 무역통계잠정 결과.hwp | — | 20,250 |
| 10 | hwp/nts-원천징수의무자를위한연말정산신고안내.hwp | — | 20,002 |
| 11 | hwp/issue2063_huge_cellbreak_table.hwp | — | 19,087 |
| 12 | hwp/nts-원천징수의무자를위한연말정산신고안내_2.hwp | — | 19,047 |
| 13 | hwp/nts-원천징수의무자를위한연말정산신고안내_4.hwp | — | 18,429 |
| 14 | hwp/pubinst-kostat_2024년_인구주택총조사_결과(등록센서스_방식)_보도자료.hwp | — | 17,713 |
| 15 | hwp/nts-원천징수의무자를위한연말정산신고안내_3.hwp | — | 17,514 |
| 16 | hwp/nts-2021 원천징수의무자를 위한 연말정산 신고안내.hwp | — | 16,827 |
| 17 | hwp/nts-간이과세 배제 고시 .hwp | — | 15,921 |
| 18 | hwp/nts-2021.1.1.시행 간이과세 배제기준(국세청 고시 제2020-40호).hwp | — | 15,862 |
| 19 | hwp/nts-2020.1.1.시행간이과세배제기준(국세청고시2019_27호).hwp | — | 15,860 |
| 20 | hwp/nts-간이과세배제기준.hwp | — | 15,679 |

### HWPX 문단당 글자모양 쌍(HWPX: run) 상위 20

| 순위 | 공개 표본 파일 | 문단 인덱스(0부터) | 값 |
|---:|---|---:|---:|
| 1 | hwpx/nts-251015 (기재부 보도자료) 토지거래허가구역‧규제지역 지정, 대출규제 보완 등 ｢주택시장 안정화 대책｣ 마련.hwpx | 21 | 96 |
| 2 | hwpx/(250813) (보도자료) 2025년 7월중 가계대출 동향.hwpx | 312 | 83 |
| 3 | hwpx/nts-250907 (기재부) ‘30년까지 서울·수도권 135만호 착공.hwpx | 21 | 74 |
| 4 | hwpx/pypandoc-hwpx-test-from-docx.hwpx | 25 | 73 |
| 5 | hwpx/pypandoc-hwpx-test-from-docx.hwpx | 27 | 73 |
| 6 | hwpx/pypandoc-hwpx-test-from-docx.hwpx | 90 | 73 |
| 7 | hwpx/pypandoc-hwpx-test-from-docx.hwpx | 91 | 73 |
| 8 | hwpx/pypandoc-hwpx-test-from-html.hwpx | 14 | 73 |
| 9 | hwpx/pypandoc-hwpx-test-from-html.hwpx | 16 | 73 |
| 10 | hwpx/pypandoc-hwpx-test-from-html.hwpx | 78 | 73 |
| 11 | hwpx/pypandoc-hwpx-test-from-html.hwpx | 79 | 73 |
| 12 | hwpx/pypandoc-hwpx-test-from-json.hwpx | 25 | 73 |
| 13 | hwpx/pypandoc-hwpx-test-from-json.hwpx | 27 | 73 |
| 14 | hwpx/pypandoc-hwpx-test-from-json.hwpx | 90 | 73 |
| 15 | hwpx/pypandoc-hwpx-test-from-json.hwpx | 91 | 73 |
| 16 | hwpx/pypandoc-hwpx-test-from-md.hwpx | 14 | 73 |
| 17 | hwpx/pypandoc-hwpx-test-from-md.hwpx | 16 | 73 |
| 18 | hwpx/korea-mid-8.31 2023년 7월 사업체노동력조사 및 4월 지역별사업체노동력조사 주요 결과(참고 노동시장조사과).hwpx | 40 | 69 |
| 19 | hwpx/pypandoc-hwpx-test-from-docx.hwpx | 26 | 69 |
| 20 | hwpx/pypandoc-hwpx-test-from-docx.hwpx | 28 | 69 |

### HWPX 문단당 글자 수 상위 20

| 순위 | 공개 표본 파일 | 문단 인덱스(0부터) | 값 |
|---:|---|---:|---:|
| 1 | hwpx/python-hwpx-hancom-native-toc-B.hwpx | 13 | 3,236 |
| 2 | hwpx/python-hwpx-hancom-native-toc-A.hwpx | 17 | 1,735 |
| 3 | hwpx/python-hwpx-hancom-native-toc-B.hwpx | 17 | 1,735 |
| 4 | hwpx/hangulang-para-001.hwpx | 20 | 1,691 |
| 5 | hwpx/para-001.hwpx | 20 | 1,691 |
| 6 | hwpx/rhwp-width_ladder.hwpx | 2 | 1,600 |
| 7 | hwpx/rhwp-width_ladder.hwpx | 4 | 1,600 |
| 8 | hwpx/python-hwpx-hancom-native-toc-A.hwpx | 13 | 1,511 |
| 9 | hwpx/nts-[별지 제1호 서식]현금영수증 미발급 신고서.hwpx | 106 | 1,365 |
| 10 | hwpx/hwp3-sample10-hwpx.hwpx | 18388 | 1,096 |
| 11 | hwpx/hwp3-sample10-hwpx.hwpx | 26088 | 1,096 |
| 12 | hwpx/hwp3-sample10-hwpx.hwpx | 26086 | 1,085 |
| 13 | hwpx/hwp3-sample11-hwpx.hwpx | 1980 | 1,052 |
| 14 | hwpx/ministry-[7월1일] 7월 주요 시행법령 소개(영문본).hwpx | 29 | 974 |
| 15 | hwpx/nts-2024.1.1. 시행 간이과세배제기준(국세청_고시_제2023-20호).hwpx | 8001 | 964 |
| 16 | hwpx/nts-2026.1.1. 간이과세배제기준 고시_국세청고시 제2025-28호.hwpx | 8012 | 964 |
| 17 | hwpx/nts-2026.7.1. 간이과세배제기준 고시_국세청 고시 제2026-19호.hwpx | 7696 | 964 |
| 18 | hwpx/nts-간이과세배제기준 고시 개정안(전문).hwpx | 7995 | 964 |
| 19 | hwpx/nts-간이과세배제기준 고시.hwpx | 7801 | 964 |
| 20 | hwpx/hwp3-sample10-hwpx.hwpx | 2997 | 940 |

### HWPX 문서당 TextRun 수 상위 20

| 순위 | 공개 표본 파일 | 문단 인덱스(0부터) | 값 |
|---:|---|---:|---:|
| 1 | hwpx/nts-2025년 귀속 기준경비율 단순경비율.hwpx | — | 33,617 |
| 2 | hwpx/nts-2024년 귀속 기준경비율 단순경비율.hwpx | — | 33,547 |
| 3 | hwpx/korea-mid-8.31 2023년 7월 사업체노동력조사 및 2023년 4월 지역별사업체노동력조사 결과(노동시장조사과).hwpx | — | 20,664 |
| 4 | hwpx/hwp3-sample10-hwpx.hwpx | — | 20,571 |
| 5 | hwpx/pubinst-kostat_2024년_인구주택총조사_결과(등록센서스_방식)_보도자료.hwpx | — | 17,712 |
| 6 | hwpx/nts-2024년 오피스텔 및 상업용건물 기준시가 재산정고시 호별 명세.hwpx | — | 16,092 |
| 7 | hwpx/nts-2024.1.1. 시행 간이과세배제기준(국세청_고시_제2023-20호).hwpx | — | 15,424 |
| 8 | hwpx/nts-간이과세배제기준 고시 개정안(전문).hwpx | — | 15,412 |
| 9 | hwpx/nts-2026.1.1. 간이과세배제기준 고시_국세청고시 제2025-28호.hwpx | — | 15,158 |
| 10 | hwpx/nts-간이과세배제기준 고시.hwpx | — | 14,953 |
| 11 | hwpx/nts-2026.7.1. 간이과세배제기준 고시_국세청 고시 제2026-19호.hwpx | — | 11,858 |
| 12 | hwpx/pubinst-mois_2025_행정업무운영_편람(최종).hwpx | — | 9,545 |
| 13 | hwpx/rhwp-2025_행정업무운영_편람_최종.hwpx | — | 9,545 |
| 14 | hwpx/nts-2024년 귀속 경비율 고시(국세청 고시 제2025-6호, 2025.03.28).hwpx | — | 6,548 |
| 15 | hwpx/nts-2025년 귀속 경비율 고시.hwpx | — | 6,243 |
| 16 | hwpx/text_footnote_tail_overpagination.hwpx | — | 5,477 |
| 17 | hwpx/admrul-관세조사-운영-훈령.hwpx | — | 5,441 |
| 18 | hwpx/rhwp-table_scattered_header_rowbreak.hwpx | — | 4,986 |
| 19 | hwpx/hwp3-sample11-hwpx.hwpx | — | 4,965 |
| 20 | hwpx/error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx | — | 4,886 |
