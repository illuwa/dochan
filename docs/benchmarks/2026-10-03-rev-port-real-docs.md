# HWPX 변경 추적 투영의 표준 XML 이식 실물 검증

2026년 10월 3일에 공개 HWPX 네 개를 같은 경로에서 기준 브랜치 `31a9fa5`와 이식본으로 각각 읽었다. `include_assets=False`를 적용하고 preserve, final, original 세 모드에서 Markdown, JSON, 진단 목록을 비교했다. 출력 전문은 저장하지 않고 UTF-8 SHA-256, 문자 수, 진단 목록만 임시 결과에 기록했다. 진단 문자열도 순서와 내용까지 비교했다. 아래 표의 해시는 Markdown과 JSON SHA-256의 앞 16자리이며, 실제와 기대의 전체 64자리 해시도 모두 같다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| HWPX 변경 추적 preserve | `admrul-관세조사-운영-훈령.hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `71de26b428cedd3f`, JSON `52be518e204a49ce`, 진단 2개다. | 세 결과가 모두 같다. | 통과했다. |
| HWPX 변경 추적 final | `admrul-관세조사-운영-훈령.hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `563467d69b86920b`, JSON `4c268754a69d1aed`, 진단 2개다. | 세 결과가 모두 같다. | 통과했다. |
| HWPX 변경 추적 original | `admrul-관세조사-운영-훈령.hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `5554040d79662f3f`, JSON `48ee6f7dfe384d1e`, 진단 2개다. | 세 결과가 모두 같다. | 통과했다. |
| HWPX 변경 추적 preserve | `hwpxlib-ChangeTrack.hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `a604166eff8bb6f5`, JSON `f1808a2948b05080`, 진단 0개다. | 세 결과가 모두 같다. | 통과했다. |
| HWPX 변경 추적 final | `hwpxlib-ChangeTrack.hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `b57e0535d9720a2b`, JSON `bedf5737b046f991`, 진단 0개다. | 세 결과가 모두 같다. | 통과했다. |
| HWPX 변경 추적 original | `hwpxlib-ChangeTrack.hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `5f48b8c88643a836`, JSON `4950f72ee05c0251`, 진단 0개다. | 세 결과가 모두 같다. | 통과했다. |
| HWPX 변경 추적 preserve | `reader_writer__ChangeTrack.hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `a604166eff8bb6f5`, JSON `f1808a2948b05080`, 진단 0개다. | 세 결과가 모두 같다. | 통과했다. |
| HWPX 변경 추적 final | `reader_writer__ChangeTrack.hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `b57e0535d9720a2b`, JSON `bedf5737b046f991`, 진단 0개다. | 세 결과가 모두 같다. | 통과했다. |
| HWPX 변경 추적 original | `reader_writer__ChangeTrack.hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `5f48b8c88643a836`, JSON `4950f72ee05c0251`, 진단 0개다. | 세 결과가 모두 같다. | 통과했다. |
| HWPX 변경 추적 preserve | `korea-mid-30-7_(즉시보도_통전지)농촌진흥청_승용마,_제주_자치경찰단_기마대에_첫_도입(축산원).hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `eab20a798a240c3a`, JSON `fc882ce7fcb8b729`, 진단 1개다. | 세 결과가 모두 같다. | 통과했다. |
| HWPX 변경 추적 final | `korea-mid-30-7_(즉시보도_통전지)농촌진흥청_승용마,_제주_자치경찰단_기마대에_첫_도입(축산원).hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `d3ca20b33731c63d`, JSON `541854528069370f`, 진단 1개다. | 세 결과가 모두 같다. | 통과했다. |
| HWPX 변경 추적 original | `korea-mid-30-7_(즉시보도_통전지)농촌진흥청_승용마,_제주_자치경찰단_기마대에_첫_도입(축산원).hwpx` | lxml 기준 브랜치 `31a9fa5`의 동일 파일 출력이다. | Markdown `f24a2d3a08ce00bf`, JSON `ea5dec46b881810e`, 진단 1개다. | 세 결과가 모두 같다. | 통과했다. |

12개 모드·문서 조합의 기준 및 이식 결과 JSONL 전체 SHA-256은 모두 `8f31ca5d52237d9ea409ea2eb1e8a03a7a3c0c585f5677a236ff941ad7698ff1`이다. JSONL에는 각 출력의 전체 해시와 문자 수, 진단 목록이 들어 있다. 두 공개 파일에서 진단이 남지만 진단의 내용과 순서까지 기준과 같다. 해당 진단을 이식 차이로 분류하지 않는다.

## 변경 추적이 없는 문서의 회귀 비교

공개 `corpus/hwp-public/hwpx`의 HWPX 1,675개를 이식 전 커밋 `7119a5d`와 이식본의 기본 리더로 읽었다. Markdown 전체 해시와 문자 수가 1,675/1,675개에서 같았다. 두 JSONL 결과의 SHA-256은 모두 `60e42889f876e7bb089e139fa4a3fecdbeb5d8c5d7b92e48495ab8f22a7d21d6`이다. 기본 리더를 사용했으므로 `include_assets=False`로 패키지 식별에서 제외되는 세 파일도 같은 조건으로 비교되었다. 파일별 출력 전문은 저장하지 않았다.

`python -m scripts.block_lxml pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp`는 4,712개 통과, 31개 건너뜀, 16개 예상 실패였고 lxml import 시도는 0회였다. `ruff check dochan scripts tests`도 통과했다. README 의 `변경 추적` 행은 HWP·HWPX 모두 ⬜ 이며, 이 이식은 그 판정을 바꾸지 않는다.

## 재현

`scripts/probe_hwpx_revision_port.py`에 `--source-root`, `--corpus`, `--output`을 지정한다. 네 변경 추적 표본은 `--tracked`를 추가하면 세 모드를 측정하고, 전체 코퍼스는 옵션 없이 기본 Markdown을 측정한다. 기준 소스 루트는 각각 `31a9fa5`와 `7119a5d`의 소스다. 결과 파일은 작업용 디렉터리에 보관하고 코퍼스 원본을 복사하지 않는다.

## 감수 후속(2026-10-03)

감수에서 표 셀처럼 흐름이 많은 섹션의 처리 시간이 제곱으로 늘어나는 문제가 나왔다. 문단 병합 후보를 섹션 전체가 아니라 그 흐름의
문단 끝에서만 모으도록 고쳤다. 셀 4,000개 섹션은 수정 전 약 61초, 수정 후 0.1초 미만이다(`test_many_table_cell_flows_merge_linearly`).
억제한 개체의 직속 자식이 부모 맵에 남아 병합 중 예외로 섹션 전체가 사라지던 경우도 `clear()` 전에 부모 정보를 지워 고쳤다
(`test_suppressed_object_children_do_not_keep_stale_parents`). 두 수정 뒤에도 공개 4문서 × 3모드 출력은 이식본과 같다.
