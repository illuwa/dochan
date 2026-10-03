# HWPX 문단 안 그림 흐름 실물 검증

HWPX의 `hp:pic`이 문장 가운데 있어도 원래 문단의 텍스트를 하나로 모은 뒤 그림을 낸다. 표·수식·도형은 기존 문단 경계로 둔다. 단위 테스트는 문장 중간·첫머리·복수 그림, 표와 혼합, 링크·서식 런, 표 셀, 캡션과 컨트롤 래퍼를 검증한다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| HWPX 이미지 참조·읽기 순서(문단 안 그림) | `corpus/press-pairs/156783563.hwpx`, 같은 번호의 HWP·PDF | HWP의 해당 문단 텍스트와 PDFium으로 추출한 PDF 문장이 그림 양쪽에서 이어진다. 원본 HWPX의 그림은 `textWrap="SQUARE"`이다. | 그림 앞의 `황기`와 뒤의 `, 참당귀`가 한 문단에 있다. | HWPX 본문 문단 수 10→9, HWP 9. 해당 문단 텍스트가 HWP와 정확히 일치하며 PDF에도 `황기, 참당귀`가 이어진다. 토큰 일치율 0.9848→0.9977. | 통과 |
| HWPX 이미지 참조·읽기 순서(문단 안 그림) | `corpus/press-pairs/156784222.hwpx`, 같은 번호의 HWP·PDF | HWP의 해당 문단 텍스트와 PDFium으로 추출한 PDF 문장이 그림 양쪽에서 이어진다. | 그림 앞의 `함`과 뒤의 `께`가 한 문단에서 `함께`가 된다. | HWPX 본문 문단 수 14→13, HWP 13. 해당 문단 텍스트가 HWP와 정확히 일치한다. PDF에서도 같은 문장이 이어진다. 토큰 일치율 0.9888→0.9950. | 통과 |
| HWPX 이미지 참조·읽기 순서(문단 안 그림) | `corpus/press-pairs/`의 HWP/HWPX 91쌍 | `python -m scripts.compare_hwp_pairs`로 수정 전후를 같은 HWP 출력과 비교했다. | 그림 때문에 생긴 문단 분할만 줄고 다른 짝의 토큰 일치율은 악화하지 않는다. | HWPX 본문 문단 합계 1,964→1,962개, HWP 2,326개. 토큰 일치율이 오른 짝 4개, 낮아진 짝 0개이며 평균 0.9880→0.9883이다. 짝의 다른 구조 차이 때문에 전체 문단 수가 모두 같지는 않다. | 통과 |
| HWPX 이미지 참조·읽기 순서(문단 안 그림) | `corpus/hwp-public/`과 `corpus/press-pairs/`의 HWPX 2,046개 | 이전 버전과 a6509cb의 Markdown·JSON SHA-256 및 모델 추적을 비교했다. 추적에서는 표·셀·수식·머리글·캡션 골격, 이미지 순서와 식별자, 공백 제외 문자를 대조하고 문단 병합을 반영한 그림 위치를 측정했다. | 구조 골격·이미지 순서·공백 제외 글자가 같고 그림 이동은 최대 한 문단이다. | Markdown 209개, JSON 213개의 해시가 바뀌었다. 해석 성공 2,018개 모두 불변식을 지켰고, 그림 위치 변화 729회는 각각 한 문단 이내였다. 예외 28개와 파서 오류 수는 전후 동일했다. | 통과 |
| HWPX 이미지 참조·읽기 순서(문단 안 그림) | 내부 HWP/HWPX 76쌍(이름 비공개) | `python -m scripts.compare_hwp_pairs`의 집계만 비교했다. | 기존 짝의 일치율이 악화하지 않는다. | 평균 토큰 일치율 0.9997→0.9997, 최소 0.9927→0.9927, 표 서명 일치율 0.9987→0.9987, 오류 짝 0→0이다. | 통과 |

공개 HWPX 전체의 변경 파일 목록과 파일별 SHA-256·문자 수·문단 수는 실행 시 `.codex-work/public-before.json`과 `.codex-work/public-after.json`에 기록했다. 이 파일에는 Markdown 본문이나 이미지 바이트를 저장하지 않았다. 후속 프로브는 `python -m scripts.probe_hwpx_picture_flow --output 결과.json --reference 이전결과.json --baseline-code 이전소스 코퍼스경로...`로 실행한다. 기준 소스와 수정 소스의 모델 추적은 변경된 문서만 메모리에서 대조하며 출력 전체는 저장하지 않는다. HWPX는 `include_assets=False`로 그림 참조와 텍스트만 파싱한다. 공개 HWP/HWPX 짝 통계는 `.codex-work/press-before.json`과 `.codex-work/press-after.json`에 있다. 내부 짝은 파일별 이름이나 출력 없이 집계만 확인했다.

판정은 기존 README의 HWPX `이미지 참조`와 `읽기 순서` ✅ 유지다. 이 수정은 문단 안 그림의 배치만 다루며 표·수식·도형의 글 속 배치 계약은 변경하지 않는다.

## 후속 정리 (2026-10-04)

기준 코드 43773e2와 후속 수정 코드를 공개 HWP 5,487개 및 HWPX 2,046개에서 각각 Markdown·JSON SHA-256으로 비교했다. 전체 출력은 디스크에 저장하지 않았고, 바뀐 문서의 모델 추적만 메모리에서 대조했다. 변경된 678개 문서의 공개 파일명과 문서별 제목 수준 변화는 [별도 목록](2026-10-04-hwpx-picture-flow-heading-changes.md)에 열거했다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| HWPX 이미지 참조·읽기 순서(중첩 글상자) | 합성 글상자·그룹·그림 전용 글상자 및 공개 HWPX 2,046개 | 글상자 안 문단의 텍스트와 그림은 바깥 문단 뒤쪽 텍스트보다 먼저 나온다. 직접 그림은 기존 순서를 따른다. | 중첩 문단이 이미 배치한 그림만 바깥 문단에서 다시 미루지 않는다. | 글상자·그룹 합성 회귀 테스트가 통과했다. 해석 성공 실물 2,018개에서 이번 수정에 따른 그림 위치 변경은 0건이었다. 이 배치를 직접 확인할 실물 표본은 확보하지 못했다. | 세부 사례 실물 미검증. 기존 일반 이미지 참조·읽기 순서 ✅ 는 이전 실물 근거로 유지 |
| HWPX 제목 감지 | `corpus/hwp-public/hwpx/nts-2024년 귀속 기준경비율 단순경비율.hwpx` 및 공개 HWPX 2,046개 | 글꼴 기반 폴백은 공백 런을 건너뛰고 첫 글자가 있는 런의 크기를 쓴다. | 바뀐 Markdown은 제목 수준 차이만 가진다. | 지정 표본의 `1. 개 요`가 H1→H3으로 복원됐다. Markdown·JSON 각 239개가 바뀌었고, 239개 모두 제목 수준 필드를 제외한 모델 추적이 동일했다. 예외 28개도 전후 동일했다. | 통과 |
| HWP 제목 감지 | `corpus/hwp-public/` 및 `corpus/press-pairs/`의 공개 HWP 5,487개 | HWPX와 같은 첫 실제 글자 런 규칙을 적용한다. | 바뀐 Markdown은 제목 수준 차이만 가진다. | Markdown 436개, JSON 439개가 바뀌었다. 439개 모두 제목 수준 필드를 제외한 모델 추적이 동일했고 예외는 없었다. Markdown은 같고 JSON만 바뀐 3개도 제목 수준 필드만 달랐다. | 통과 |
| HWP·HWPX 짝 비교 | `corpus/press-pairs/`의 공개 91쌍 | `python -m scripts.compare_hwp_pairs`의 전후 지표 | 이번 정리로 기존 짝의 비교 지표가 악화하지 않는다. | 91쌍의 파일별 모든 지표가 동일했다. 평균 토큰 일치율은 전후 0.9883이다. | 통과 |
| HWP·HWPX 짝 비교 | 내부 76쌍(이름 비공개) | `python -m scripts.compare_hwp_pairs`의 집계 | 이번 정리로 기존 짝의 비교 지표가 악화하지 않는다. | 76쌍의 파일별 모든 지표가 동일했다. 평균 토큰 일치율은 전후 0.9997이다. | 통과 |

`test_textbox_picture_stays_before_outer_suffix`, `test_header_footer_picture_stays_with_nested_paragraph`, `test_equation_after_picture_keeps_boundary`, `test_heading_uses_first_nonblank_run`, `test_hwp_font_heading_uses_first_nonblank_run`이 각 경계를 검증한다. 전체 테스트 5,144개가 통과했고 36개를 건너뛰었으며 예상 실패 14개가 있었다. `lxml` 가져오기 시도는 0회였고 `ruff check dochan scripts tests`도 통과했다.
