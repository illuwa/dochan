# PDF 표 리뷰 반영 실물 검증

2026-10-03에 기준 커밋 `62bb536`과 수정본을 비교했다. 내부 HWPX/PDF 79쌍은
파일명·본문을 기록하지 않고 문서별 수치만 대조했다. 공개 pdf.js PDF 983개는
기본 모드와 `pdf_text_tables=True` 모드에서 각각 Markdown·JSON 해시와 오류·경고를
대조했다. 모든 결과를 새 파일에 저장해 이전 측정 캐시를 재사용하지 않았다.

## 칸별 판정

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| PDF 표의 중첩 텍스트다. | 내부 79쌍이다. | HWPX의 중첩 구조·셀 위치·span·정규화 텍스트다. | 기존 개선을 보존하고 나빠진 쌍이 없어야 한다. | 문서별 측정값은 79/79쌍에서 동일하다. 중첩 서명은 26/66개이고, 연결형 양성 2개는 구조·텍스트가 2/2개 일치한다. | 한 변 공유형의 검증을 유지하되 전체 칸은 ⬜를 유지한다. |
| 연결형 음성 집합이다. | 중첩 정답 없는 내부 66문서와 공개 983개다. | 내부 HWPX 구조와 공개 수정 전 출력이다. | 새 연결형 발화가 없어야 한다. | 내부 66문서와 공개 983개에서 발화가 각각 0건이다. | 통과했다. 공개 출력 동일성이 의미적 정답을 증명하지는 않는다. |
| PDF 병합 span이다. | 내부 79쌍이다. | HWPX의 셀 위치·span 서명이다. | 기존 병합 일치율을 보존해야 한다. | 218/235개, 92.77%로 동일하다. 전체 표 서명은 552/845개다. | 기존 범위를 유지한다. 완전 일치는 미달이며 추가 ✅를 제안하지 않는다. |
| 공개 PDF 회귀다. | 공개 pdf.js PDF 983개다. | 기준 커밋의 두 모드별 Markdown·JSON과 오류·경고 수치다. | 모든 문서에서 출력과 수치가 같아야 한다. | 각 모드 983/983개가 동일하다. 각 모드에 기존 ERR 문서 13개가 그대로 있다. | 출력 회귀 0개다. 기존 ERR를 정상 해석 성공으로 세지 않았다. |
| 페이지 경계의 같은 셀 결합이다. | 내부 79쌍이다. | HWPX 단일 셀과 PDF 경계 조각의 텍스트 대조다. | 종전 조사 결과가 유지되어야 한다. | 같은 열 후보 37회 중 양성 2개가 그대로다. 두 양성 모두 경계가 닫혀 있고 기존 연결 승인 안의 양성은 0개다. | 자동 결합은 보류하며 ⬜를 유지한다. |
| 괘선 없는 1×1 글상자다. | 내부 1×1 표 77개 중 명시적 무테두리 양성 1개다. | HWPX 네 경계의 NONE 속성과 PDF 출력 텍스트다. | 내용 보존과 구조 복원을 구별해야 한다. | 다른 출력 블록에 내용이 보존되는 것은 1/1개이고, 단일 PDF 셀·문단 복원은 각각 0/1개다. | 구조 지원은 미검증이며 ⬜를 유지한다. |

평균 cell_hit는 0.9152, 평균 tok_ratio는 0.9754로 유지된다. 별도 span 프로브의
최종 동일 크기 미일치 후보는 20개다. 이 중 서명 개수 차이만 있는 것은 1개이고,
span 차이가 있는 것은 19개다. 텍스트 집합 동일 4개·부분 대응 4개·무대응 11개이며,
허용오차 조정으로 복원한 후보는 0개다. 이는 최초 조사 당시의 22개 후보와 구별한다.

## 리뷰별 수정과 재현

Codex의 점선 지적과 Opus P3-2는 같은 결함이다. 실제 노드 생성과 동일한 축 확장과
점선 보강을 적용한 부모·자식 격자로 분리를 사전 검증한다. 보강된 부모의 한 셀에
자식 전체가 들어가지 않으면 성분의 원래 괘선을 그대로 반환한다. 외곽 200×200,
내부 100×100 격자에 x=50의 0.36pt 점선을 0.72pt 간격으로 추가한 합성 PDF에서,
수정 전 두 셀로 합쳐졌던 A/B/C/D가 수정 후 각각의 셀에 한 번씩 보존된다.

Codex의 세제곱 시간 지적은 거절할 자식마다 큰 부모 격자를 먼저 생성한 데서 발생했다.
자식 채택 조건을 먼저 검사하고, 격자 비용에는 셀 수와 각 경계에서 순회하는 실제
선분 수의 상한을 함께 넣었다. Opus P2-1은 모든 성분이 하나의 페이지 검사 예산
200만 회를 공유하도록 고쳤다. 원래 축의 격자가 페이지 50,000셀 상한을 넘으면
연결형 그래프 분석을 건너뛴다. 분리 후 부모·자식의 셀 수는 남은 문서 예산으로도
검사한다. 원래 격자 셀 수만으로 남은 문서 예산을 미리 거절하지는 않는다. 분리로
셀 수가 줄어들 수 있으며, 기존 5셀 예산 양성 테스트의 동작을 보존해야 하기 때문이다.

단절점마다 수행하는 탐색 자체를 선형 블록 분해 알고리즘으로 바꾸지는 않았다.
페이지 전체의 그래프·격자 검사량을 제한하고, 명백히 수용할 수 없는 성분과 자식을
먼저 거절하는 방식으로 수정했다. 예산 초과는 WARN 한 건으로 중복 없이 남기며
해당 성분의 원래 격자를 유지한다.

Opus P2-2의 세 합성 표본에 가드별 독립 표본 두 개를 추가했다. 닫힘 검사 또는
한 변 공유 검사를 실제 호출 경로에서 각각 제거하면 테스트가 각각 2건 실패한다.
정상 구현에서는 모두 통과한다. Opus P3-1은 유효 후보가 둘 이상인 성분 전체를
유지하도록 고쳤다. Opus P3-5는 성분 영역을 `component_boxes`, 셀 영역을
`cell_boxes`로 구분했다. 기존 HEAD 테스트의 단언은 바꾸지 않았다.

## 합성 최악 입력의 전후 시간

동일한 Python 3.9 환경에서 각 입력을 3회 실행한 중앙값이다. 표본 생성·파일 읽기
시간은 제외하고 `build_tables` 호출을 측정했다. 수정 전·후 측정은 순차로 실행했다.
절대 실행 시간은 시스템 부하에 따라 달라질 수 있다.

| 합성 입력 | 수정 전 | 수정 후 | 출력 표 수 전→후 |
| --- | ---: | ---: | ---: |
| 아래 셀만 채운 2행 상자 100개다. | 0.741135초 | 0.023345초 | 1→1개다. |
| 같은 상자 200개다. | 5.148075초 | 0.077179초 | 1→1개다. |
| 같은 상자 300개다. | 15.756406초 | 0.162940초 | 1→1개다. |
| 2,000선 나무 성분 10개다. | 4.648241초 | 0.047316초 | 0→0개다. |
| 1,000선 나무 성분 20개다. | 4.744839초 | 0.058082초 | 0→0개다. |
| 400선 나무 성분 20개다. | 0.768787초 | 0.319253초 | 1→1개다. |

마지막 입력은 개별 성분이 50,000셀보다 작아 조기 거절만으로 해결되지 않는다.
수정 후에는 공용 검사 예산 초과 경고가 발생하며 나머지 성분의 반복 분석을 멈춘다.
앞의 두 큰 나무 입력은 페이지 셀 상한 경고를 유지하면서 불필요한 연결형 분석을
건너뛴다. 상자 300개의 개선은 약 96.70배이며, 원래 격자 생성 비용까지 선형이라고
주장하지 않는다.

## 알려진 한계

Opus P3-3은 보류했다. 테두리 있는 막대그래프의 값 라벨은 표 셀 텍스트와 기하적으로
구별되지 않을 수 있다. 리뷰 합성 입력에서 단일 막대와 여러 막대의 일부가 각각
중첩 표 1개로 남는 것을 확인했다. 일반 차트 판별 조건을 임의로 추가하지 않았으며,
공개 코퍼스의 출력 동일성을 이런 오탐이 전혀 없다는 증거로 해석하지 않는다.

Opus P3-4도 보류했다. 짧은 점선은 완전히 같은 축 좌표로 묶이고, 기존 격자의 내부
축과 정확히 일치할 때만 보강한다. 합성 입력에서 x=50은 보강되지만 x=50.000001은
같은 격자의 x=50에 보강되지 않는 것을 확인했다. 좌표 군집화나 허용오차 확대를
추가하지 않았으므로 실제 점선도 미세한 좌표 차이로 누락될 수 있다.

## 재실행 방법과 테스트

`BASELINE_REPO`는 `62bb536`의 소스 스냅샷, `PAIRS_DIR`는 읽기 전용 내부 짝
디렉터리다. 공개 자료는 아래 상대 경로 또는 다른 코퍼스 경로 인자로 지정한다.
비교 도구가 결과 파일을 재사용하므로 매번 새 출력 이름을 사용한다.

```bash
/usr/bin/python3 scripts/benchmark_pdf_connected_tables.py BASELINE_REPO .codex-work/performance-before.json
/usr/bin/python3 scripts/benchmark_pdf_connected_tables.py . .codex-work/performance-after.json
/usr/bin/python3 scripts/compare_pdf_fix2.py BASELINE_REPO PAIRS_DIR .codex-work/pairs-before.json --mode pairs
/usr/bin/python3 scripts/compare_pdf_fix2.py . PAIRS_DIR .codex-work/pairs-after.json --mode pairs
/usr/bin/python3 scripts/compare_pdf_fix2.py BASELINE_REPO corpus/pdfjs-src/test/pdfs .codex-work/public-before.json
/usr/bin/python3 scripts/compare_pdf_fix2.py . corpus/pdfjs-src/test/pdfs .codex-work/public-after.json
/usr/bin/python3 scripts/compare_pdf_fix2.py BASELINE_REPO corpus/pdfjs-src/test/pdfs .codex-work/public-tt-before.json --text-tables
/usr/bin/python3 scripts/compare_pdf_fix2.py . corpus/pdfjs-src/test/pdfs .codex-work/public-tt-after.json --text-tables
/usr/bin/python3 -m scripts.probe_pdf_connected_tables PAIRS_DIR .codex-work/connected-after.json --mode pairs --apply
/usr/bin/python3 -m scripts.probe_pdf_connected_tables corpus/pdfjs-src/test/pdfs .codex-work/connected-public-after.json --apply
/usr/bin/python3 -m scripts.probe_pdf_spans PAIRS_DIR --output .codex-work/span-after.json
/usr/bin/python3 -m scripts.probe_pdf_table_boundaries PAIRS_DIR --output .codex-work/boundary-after.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

새 회귀 테스트는 기준 구현에서 **7 failed, 5 passed**, 수정본에서 **12 passed**다.
관련 연결형·점선 테스트는 31개 모두 통과했다. 전체 테스트는 **3,716 passed,
29 skipped, 14 xfailed**이며 Ruff와 공백 검사도 통과했다. 공용 모델·출력 경로,
README·CHANGELOG·SUPPORT_NOTES와 런타임 의존성은 변경하지 않았다.
