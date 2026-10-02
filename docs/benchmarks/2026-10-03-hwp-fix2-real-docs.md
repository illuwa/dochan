# HWP·HWPX 깊은 개요와 셀 제목 오탐 검증

2026년 10월 3일에 공개 코퍼스 전체와 내부 실물 문서 쌍을 검사했다. 이번 작업은 기존 `제목 감지` 칸의 오탐 수정이며 README는 수정하지 않았다. 구현과 실물 확인 범위를 아래에 구분한다. 제목 개수의 변화 자체를 문서 전체의 의미적 정확도로 해석하지 않는다.

## 판정 규칙과 구현

직접 문단 모양의 개요, 개요 스타일 이름, 유효한 직접 문단 모양이 없을 때 상속하는 스타일 개요 모두에서 4~6단계 개요는 글꼴 크기와 관계없이 본문으로 유지한다. 두 형식에 같은 규칙을 적용한다. 1~3단계의 명시적인 개요는 유지한다. 셀 안에서는 글꼴 크기만을 근거로 제목으로 승격하지 않는다. 셀 밖의 개요 정보 없는 문단에는 기존 13pt·16pt·20pt 휴리스틱을 유지한다.

HWP는 셀 파싱 동안 문맥을 저장하고 `finally`에서 복원한다. 중첩 표와 셀 안 도형에도 셀 문맥이 이어지며, 표 다음 문단에는 영향을 주지 않는다. HWPX는 XML의 `hp:tc` 조상을 확인한다. 제목 모델과 Markdown·JSON 출력 경로는 변경하지 않았다.

## 실물 표본 확인

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| HWP 제목 감지: 깊은 개요 | `hangulang-endnote-01.hwp` | 원시 문단·스타일·글자 모양에서 `style_id=5`, `개요 4`, 14pt가 확인됐다. 직접 문단의 heading_type은 3이며 level은 0 기반 3이다. `3bcfc21`에서는 대상 9문단이 본문이었다. | 대상 9문단이 본문이어야 한다. | 수정 전의 H3 9개가 모두 heading_level 0으로 복구됐다. | 9/9 일치로 통과했다. |
| HWP 제목 감지: 셀의 깊은 개요 | `'16년 하반기 정책기반사업 추진계획 재공고 및 사업안내서.hwp` | 원시 문단·스타일·글자 모양에서 `style_id=5`, `개요 4`, 13pt가 확인됐다. 직접 heading_type은 0이며 대상 7문단은 같은 셀 안에 있다. `3bcfc21`에서는 본문이었다. | 대상 7문단이 본문이어야 한다. | 수정 전의 H3 7개가 모두 heading_level 0으로 복구됐다. | 7/7 일치로 통과했다. |
| HWPX 제목 감지: 셀의 글꼴 크기 | `(250813) (보도자료) 2025년 7월중 가계대출 동향.hwpx` | `section0.xml`의 셀 안 문구 ‘보도자료’는 `paraPrIDRef=8`, `styleIDRef=0`, `charPrIDRef=169`이다. `header.xml`에서 paraPr 8의 heading type은 NONE이며 charPr 169의 height는 1400이다. | 개요 지정이 없는 셀 문구는 글꼴 크기로 제목이 되지 않아야 한다. | H3에서 heading_level 0으로 바뀌었다. | 확인한 1문단이 일치했다. |
| HWPX 제목 감지: 깊은 개요 | `footnote-01.hwpx` | `sections[0].elements[14]`에 대응하는 XML 문단은 `paraPrIDRef=22`, `styleIDRef=5`이다. paraPr 22는 BULLET, idRef 3, level 3이며 style 5는 ‘개요 4’ / ‘Outline 4’이다. charPr 10의 height는 1400이다. | 깊은 개요는 14pt여도 본문이어야 한다. | H3에서 heading_level 0으로 바뀌고 텍스트는 동일했다. | 확인한 1문단이 일치했다. |

두 HWP의 지목된 16문단은 기준 커밋에서 수정 전 커밋으로 바뀔 때 정확히 9개와 7개의 제목이 추가된 문단이다. 이번에는 이 16개 외에도 요청한 셀 휴리스틱 차단이 적용되므로 두 파일의 전체 제목 감소량을 16개로 한정하지 않는다. 원시 정보상 직접 OUTLINE 비트가 없는 경우에도 ‘개요 4’라는 스타일 이름 때문에 같은 오탐이 발생했다.

## 공개 코퍼스 전체 측정

`scripts/probe_hwp_heading_changes.py`로 공개 코퍼스의 `.hwp`와 `.hwpx` 파일 7,076개를 모두 측정했다. 같은 바이트의 중복 파일도 서로 다른 공개 경로이면 각각 셌다. 확장자별로는 HWP 5,376개와 HWPX 1,700개이며, 매직바이트로 판별한 실제 형식은 HWP 5,389개, HWPX 1,686개, 미확인 1개이다. 따라서 이번 전체 측정의 분모는 앞선 감수의 HWP 623개와 다르다.

각 파일의 SHA-256을 대조하고, 섹션·표 셀·중첩 표·캡션·각주·미주·머리말·꼬리말 문단의 제목을 재귀 집계했다. 같은 모델 객체 참조는 한 번만 센다. 기준과 수정 전 측정은 각 커밋의 `dochan/` 런타임 전체를 별도 디렉터리에서 로드했으며, 제목 함수만 과거 것으로 바꾼 결과가 아니다.

| 실제 형식 | 파일 수 | 기준 `3bcfc21` 제목 수 | 수정 전 `1d4f0d1` 제목 수 | 수정 후 제목 수 | 기준 대비 변화 | 수정 전 대비 변화 |
|---|---:|---:|---:|---:|---:|---:|
| HWP | 5,389 | 227,979 | 228,032 | 87,433 | −140,546 | −140,599 |
| HWPX | 1,686 | 121,232 | 121,220 | 38,365 | −82,867 | −82,855 |
| 미확인 | 1 | 0 | 0 | 0 | 0 | 0 |
| 합계 | 7,076 | 349,211 | 349,252 | 125,798 | −223,413 | −223,454 |

수정 전 대비 제목이 바뀐 파일은 4,998개이다. 제목 223,454개가 본문으로 바뀌었고, 새 제목 추가와 기존 제목의 수준 변경은 각각 0개였다. 이 중 셀 안 제목 감소는 223,368개이며, 셀 밖 감소는 86개이다. 셀 안의 명시적인 제목 5,241개는 유지됐다. 이 수치는 모든 감소 문단의 의미를 사람이 판정했다는 뜻이 아니라 구현 규칙에 따른 출력 변화의 전수 측정이다.

수정 전후 문단 수 2,009,417개와 파일별 문단 수, 오류·경고 목록, 실제 형식 및 처리 예외가 모두 동일했다. 기존 진단이 있는 파일은 53개이며 ERR 진단 43건이 포함된다. 이 파일까지 무오류로 검증됐다고 주장하지 않는다. 처리 예외는 0건이었다.

기준 커밋과 수정 전 커밋 사이에는 이번 수정 외의 기존 변경도 있다. 그 사이 22파일의 제목 정보가 달라졌고 1파일의 문단 수와 진단이 달라졌다. 기준의 전체 문단 수는 1,999,328개였다. 그러므로 기준 대비 총량 차이 전체를 이번 패치만의 결과로 해석하지 않고, 이번 패치의 영향은 수정 전후 비교로 분리했다.

## 내부 문서 쌍 회귀

`/usr/bin/python3 -m scripts.compare_hwp_pairs`에 내부 쌍 디렉터리를 인자로 주어 수정 전후 각각 실행했다. 파일명과 내용은 저장하지 않았고 집계만 비교했다. 76쌍에서 모든 집계가 동일했다.

| 지표 | 수정 전 | 수정 후 |
|---|---:|---:|
| 평균 텍스트 토큰 비율 | 0.9997 | 0.9997 |
| 최소 텍스트 토큰 비율 | 0.9927 | 0.9927 |
| HWPX / HWP 표 수 | 796 / 795 | 796 / 795 |
| 표 구조 일치율 | 0.9987 | 0.9987 |
| 평균 셀 내용 일치율 | 0.9991 | 0.9991 |
| HWPX / HWP 중첩 표 수 | 51 / 51 | 51 / 51 |
| 중첩 표 일치율 | 1.0 | 1.0 |
| 평균 서식 일치율 | 1.0 | 1.0 |
| 오류가 있는 쌍 | 0 | 0 |

기존 표 수 차이와 1 미만의 지표는 그대로 남아 있다. 이 비교는 텍스트·표·서식 회귀가 없다는 집계 근거이며, 두 형식이 같은 휴리스틱을 쓰므로 제목 의미 정확도의 독립 정답지는 아니다.

## preserve 바이트 예산

`reader.py`를 조사한 결과 FileHeader·DocInfo·ViewText·BodyText 폴백·BinData가 이미 동일한 `stream_budget` 객체를 공유했다. ViewText를 시도한 뒤 BodyText를 읽으면 두 스트림의 실제 읽기 바이트가 합산된다. 예산이 새로 생기거나 초기화되는 경로는 없으므로 공유 파일은 수정하지 않았다.

`test_preserve_fallback_shares_cumulative_stream_budget`는 합성 OLE 입력으로 누적 크기와 예산이 정확히 같을 때 폴백이 성공하고, 예산이 1바이트 작으면 BodyText 스트림을 열기 전에 거부되는 것을 확인한다. 읽은 ViewText의 비용을 환불하지 않는 것이 누적 I/O 상한의 의미에 맞는다. 이 검증은 합성 경계 테스트이며 대용량 실물의 예산 소진 시험은 아니다.

## 단위 테스트와 기존 단언 변경 근거

새 테스트 파일의 최초 실행은 24개 실패와 11개 통과로 오탐을 재현했다. 수정 후 전체 테스트는 **3,133 passed, 24 skipped, 14 xfailed**였고 `ruff check dochan scripts tests`와 `git diff --check`가 통과했다.

`test_deep_outline_stays_body_in_both_formats`는 직접 개요·스타일 이름·스타일 기본 개요의 4~6단계를 14pt와 20pt에서 확인한다. `test_cell_font_fallback_is_disabled_and_context_restored`는 1~2단계 중첩 셀의 14pt·16pt·20pt 문단과 표 다음 문단을 확인한다. `test_explicit_shallow_heading_survives_inside_cells`는 명시적인 1~3단계 제목의 보존을 확인한다. 본문 결과는 기존 Markdown과 JSON 출력에서도 검사한다.

`tests/test_hwp_polish.py`의 `test_deep_direct_outline_falls_back_to_font`와 `tests/test_hwpx_heading_priority.py`의 `test_hwpx_deep_direct_outline_uses_font_fallback`는 이번 오탐인 깊은 개요의 글꼴 크기 승격을 기대값으로 고정하고 있었다. 공개 HWP의 지목 16문단, 기준 `3bcfc21`의 본문 출력, 사용자가 지정한 두 형식의 동일 규칙을 근거로 이 두 테스트만 본문 기대값과 이름으로 변경했다. 나머지 기존 단언은 변경하지 않았다.

## 재현 방법

코퍼스와 과거 런타임은 커밋하지 않는다. 과거 런타임은 `git archive <커밋> dochan`으로 작업 디렉터리에 풀고 다음과 같이 측정할 수 있다. 각 실행의 `--source-root`는 지정한 커밋의 런타임 또는 최종 워크트리를 가리킨다.

```bash
/usr/bin/python3 scripts/probe_hwp_heading_changes.py scan "$PUBLIC_CORPUS" \
  --source-root "$BASELINE_ROOT" --label 3bcfc21 --output baseline.json
/usr/bin/python3 scripts/probe_hwp_heading_changes.py scan "$PUBLIC_CORPUS" \
  --source-root "$BEFORE_ROOT" --label 1d4f0d1 --output before.json
/usr/bin/python3 scripts/probe_hwp_heading_changes.py scan "$PUBLIC_CORPUS" \
  --label fixed --output final.json
/usr/bin/python3 scripts/probe_hwp_heading_changes.py diff baseline.json final.json \
  --output baseline-final.json
/usr/bin/python3 scripts/probe_hwp_heading_changes.py diff before.json final.json \
  --output before-final.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

프로브는 파일명과 제목을 기록하므로 공개 코퍼스에만 사용한다. 스캔 JSON에는 대상 파일 해시와 실행 런타임 소스 해시가 들어간다.

HWP 표본의 원시 판정 입력은 `inspect PUBLIC_FILE --source-root BEFORE_ROOT --output basis.json`으로 확인할 수 있다. HWPX는 ID가 배열 위치와 같다는 보장이 없으므로 ZIP 안의 `header.xml`과 해당 섹션 XML의 참조 ID를 직접 대조했다. 최종 스캔의 런타임 소스 111개 해시가 최종 워크트리와 일치하는 것도 확인했다.
