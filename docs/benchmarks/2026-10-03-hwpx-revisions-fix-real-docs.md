# HWPX 변경 추적 리뷰 반영 실물 검증

검증일은 2026-10-03이다. `corpus/hwp-public/hwpx`의 공개 문서를 읽기 전용으로 사용했다. 표의 CLI 판정은 `convert --format text --revision-mode final`과 `original`을 각각 실행한 결과다. `scripts/probe_hwpx_revision_review.py`에 코퍼스 경로와 수정 전 모듈을 인자로 주어 재검증했다. 본문 전체는 디스크에 저장하지 않고 문단 수, 글자 수, SHA-256과 진단 요약만 기록했다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 변경 추적 · HWPX | `hwpxlib-ChangeTrack.hwpx` | `docs/benchmarks/hwpx/revision-spec.md`의 원시 XML gold | preserve `변경 추적 \t인간은`, final `변경 \t인간은`, original `변경 추적 \t` | 세 모드의 텍스트가 gold와 일치했다. 진단은 0건이며 final·original CLI 모두 종료 코드 0이었다. | 3/3 모드 일치. |
| 변경 추적 · HWPX | `reader_writer__ChangeTrack.hwpx` | 같은 파일의 원시 XML 변경 범위와 `hwpxlib-ChangeTrack.hwpx`의 gold | 각 모드의 텍스트가 대응 gold와 같아야 한다. | preserve 1문단·10자, final 1문단·7자, original 1문단·7자였다. 진단은 0건이며 CLI 두 모드 모두 종료 코드 0이었다. | 3/3 모드 일치. |
| 변경 추적 · HWPX | `admrul-관세조사-운영-훈령.hwpx` | 원시 XML에서 동일 Id·TcId·paraend의 중복 끝 표지 세 건을 확인했다. 두 표지 사이에는 `</hp:t></hp:run><hp:run ...><hp:t>` 경계만 있으며 내용은 없다. 최종본 화면의 범위 단위 OCR 대조는 삭제 0/38개, 삽입 106/123개가 보였다. 원본 화면은 위치에 따라 불일치하여 정답으로 사용하지 않았다. | preserve 본문·모델·Markdown 불변, 빈 실행 경계 사이 중복 끝 표지는 정보 진단, final·original CLI 종료 코드 0. | preserve 3,654문단·102,740자·SHA-256 `ec5863b402309f855b9307f06c606c1a7f969bc94d7e5855453a22d3bf7deff8`로 불변이었다. final 3,319문단·95,546자, original 3,230문단·92,874자였다. 각 모드 진단은 formatting 1항목(발생 41회)과 duplicate-end 1항목(발생 3회)이며, CLI 두 모드 모두 종료 코드 0이었다. | 보존 불변식, final·original 부분열 불변식 및 CLI 2/2 통과. 범위 단위 최종본 화면 근거는 있으나 문단 병합·속성 승계와 original의 독립 정답은 미검증. |
| 변경 추적 · HWPX | `korea-mid-30-7_(즉시보도_통전지)농촌진흥청_승용마,_제주_자치경찰단_기마대에_첫_도입(축산원).hwpx` | 원시 XML에서 빈 실행 경계 사이 중복 끝 표지 한 건을 확인했다. | 인접 중복은 정보 진단이며 CLI 두 모드 모두 종료 코드 0. | preserve 49문단·1,712자, final 49문단·1,563자, original 49문단·1,550자였다. 각 모드에서 duplicate-end 정보 진단 한 건이 남았고 위치는 `paragraph#18/run#28`이었다. CLI 두 모드 모두 종료 코드 0이었다. | 보존 불변식, final·original 부분열 불변식 및 CLI 2/2 통과. 전체 본문의 독립 정답은 미검증. |

네 문서 모두 preserve의 본문·오류를 제외한 JSON 모델·Markdown이 수정 전 구현과 같았다. final과 original의 본문은 각 preserve 본문에서 대괄호 숫자 표지를 제거한 문자열의 순서 있는 부분열이었고, 문자별 다중집합도 preserve의 부분집합이었다. CLI는 총 8/8회 종료 코드 0이었다. 이 불변식은 불필요한 내용 생성·순서 역전을 막는 검사이며 독립 정답 검증을 대신하지 않는다.

최종본 화면 대조 수치는 독립 리뷰가 기록한 범위 단위 관찰값이다. 변경 없는 문단의 OCR 포착률은 86%였으므로, 삽입 106/123을 파서 정확도 86%라고 해석하지 않는다. `--format text`는 표 안 각주를 모든 모드에서 생략할 수 있어 이 대조의 정답지로 삼지 않았다. 문단을 넘는 시작·끝 범위는 공개 실례가 확인되지 않았으며, 구현 범위에서 제외하고 합성 테스트에서 `ERR:`를 유지했다.

HWP 바이너리 변경 추적 칸은 이 수정의 대상이 아니다. 이전 조사에서 동일 구성의 독립 정답이 없으므로 ⬜ 판정을 유지한다.
