# HWPX 텍스트 변경 추적 구현 검증

검증일: 2026-09-19. 기준: [revision-spec.md](revision-spec.md)의 XML 독립 gold.
본문·작성자 정보를 추가 수집하지 않았으며, 아래 R2 수치는 구조·진단 집계다.

## 인터페이스

```python
Dochan(file_path, ocr=False, *, include_assets=True, revision_mode="preserve")
HWPReader(file_path, ocr=False, *, include_assets=True, revision_mode="preserve")
HWPXParser().parse(file_path, *, include_assets=True, revision_mode="preserve")
```

- `preserve`: 기존 삽입·삭제 텍스트와 공백·탭을 유지한다. 기본값이다.
  보존 가능한 미지원 revision 진단은 `WARN:`이며 CLI 출력이 가능하다.
- `final`: 검증된 Delete 범위의 텍스트를 제외한다.
- `original`: 검증된 Insert 범위의 텍스트를 제외한다.
- 옵션은 keyword-only이며 parser를 재사용해도 모드·header 참조·진단이 누적되지 않는다.
- 잘못된 모드는 파싱 전에 `ValueError`를 던진다. `Dochan`/`HWPReader`에서
  비기본 모드는 실제 HWPX 패키지만 허용한다. 다른 포맷·모호한 ZIP은
  `ValueError`로 명시적으로 거부한다. 확장자가 달라도 HWPX 패키지이면 허용한다.
- 기존 위치 인자 `file_path`, `ocr`와 `include_assets` 동작을 유지한다.
  CLI·배치 전달과 출력 실패 처리는 [options-validation.md](options-validation.md)에서 검증한다.

## 범위와 오류 정책

`parser.py`는 header 참조를 수집한 뒤 섹션 XML을 모델로 변환하기 전에
`RevisionProjector`를 호출한다. projector는 XML 문서 순서에서 `.text`, marker
`.tail`, 탭·줄바꿈·공백 토큰·`composeText`의 범위를 먼저 검증한다.
검증을 마친 범위만 투영하므로, 끝 마커가 없는 삭제가 뒤쪽 본문을 전부 지우지 않는다.

2011 paragraph/head QName과 대소문자를 구별한다. begin/end의 `(종류, Id)`와
`TcId`, header `trackChange@id/type`을 확인한다. `Id`와 `TcId`가 달라도 정상적으로
연결한다. 범위 상태는 run·동일 본문 흐름의 문단을 넘어서 유지하며, 섹션마다 종료한다.
표 셀·각주·머리글·바닥글·캡션·그리기 텍스트·메모와 미지원 컨테이너는
진입 시점부터 별도의 흐름이다. 첫 문단보다 앞선 마커도 바깥 본문에 유입되지 않는다.
`hp:p/run/t`와 지원하는 텍스트 토큰만 흐름을 공유한다. 마커의 직접 부모로
검증된 위치는 `hs:sec`, `hp:p`, `hp:run`, `hp:t`다. `hp:subList`·`hp:tc` 등
직하 마커는 `marker-position`으로 진단하고 해당 흐름의 투영을 보류한다.

다음은 `Document.errors` / `Dochan.errors`에 `HWPX revision partial [종류]`로
명시한다. preserve는 `WARN:`, final/original은 불완전 투영을 나타내는 `ERR:`다.
따라서 CLI·batch는 preserve 내용을 출력하지만 final/original 실패 시 출력 파일을
게시하거나 기존 파일을 덮어쓰지 않는다. 유형·파트별로 발생 횟수와
첫 문단/run/marker 위치를 집계하여 진단이 문서 길이에 비례해 늘지 않도록 한다.

- 겹침·교차·중첩 범위, 중복 시작, 시작/끝 누락, Id 누락.
- header 참조 누락·종류 불일치·중복, begin/end TcId 불일치.
- `paraend`가 `0`이 아닌 경우(누락·잘못된 값·`1` 포함).
- ParaShape/CharShape, `paraTcId`/`charTcId` 서식 변경과 미지원 이벤트 종류.
- 미지원 namespace, 내용이 있는 빈 마커, `hp:t` 밖의 marker tail,
  변경 범위 안의 개체·컨트롤, 변경 마커가 있는 switch 분기.
- 미지원 마커 위치와 알 수 없는 컨테이너를 가로지르는 범위(`flow-boundary`).
  switch 내부의 투영 보류는 격리된 하위 흐름에도 적용한다.
- 동시에 열린 범위가 128개를 넘는 경우.

불확실한 범위의 원문은 제거하지 않는다. Id 누락처럼 범위를 구분할 수 없는
경우 해당 본문 흐름 전체의 투영을 보류할 수 있다. `errors`가 있는 결과를
완전히 승인/취소된 정답 문서로 취급해서는 안 된다. 작성자 연결과 변경 시각의
의미를 추정하지 않는다.

## 초기 구현 TDD 기록과 회귀 명령

초기 개발 당시 Python 3.9.6에서 아래 명령으로 API 부재에 따른 실패를 확인했다.

```bash
python -m pytest tests/test_hwpx_revisions.py -q --tb=short --maxfail=3
```

결과: `3 failed`, 모두 `revision_mode` keyword 인자 미지원 `TypeError`.
구현 후 revision 전용 테스트는 **93 passed**, 실물 검증도 실행되어 skip은 없었다.

```bash
python -m pytest \
  tests/test_hwpx_revisions.py tests/test_hwpx_reader.py \
  tests/test_hwpx_assets_option.py tests/test_hwpx_regressions.py \
  tests/test_hwpx_zip_bomb_guard.py tests/test_hwpx_invalid_xml_char.py \
  -q --tb=short --maxfail=5
```

결과: **176 passed**. 기존 asset 옵션, charPr ID 참조, 표 셀 파싱,
리소스 제한과 XML 문자 회귀를 포함한 초기 기록이다. 현재의 더 넓은 테스트 결과는
[implementation-progress.md](implementation-progress.md)의 검증 표에 기록한다.
무변경 문서의 기본값·세 모드 동등성은 `test_unchanged_document_is_identical`로
재현한다. 실물 전체에 대한 정확도 증명으로 확대하지 않는다.

## 실물 API 결과

테스트는 spec의 JSON code block을 직접 읽고 파일 SHA-256부터 비교한다.
ZIP/XML을 새 정답으로 재계산하거나 투영 구현을 재사용해 gold를 만들지 않는다.

### R1: hwpxlib-ChangeTrack.hwpx

SHA-256: `05e6384795611406b29302cf62326b6d1f0a9399d2fbc201fcbe459aa730e356`.

`Dochan(...).doc`와 `HWPXParser().parse(...)` 양쪽에서
`doc.find_all("paragraph")[0].text`를 비교했다. 아래 `\t`는 실제 U+0009이며
문단 문자열 끝을 strip하거나 개행을 추가하지 않는다.

| 모드 | spec 키 | API 문단 문자열 (Python repr) | errors |
| --- | --- | --- | ---: |
| preserve | all | `'변경 추적 \t인간은'` | 0 |
| final | accepted | `'변경 \t인간은'` | 0 |
| original | rejected | `'변경 추적 \t'` | 0 |

세 모드 모두 gold와 정확히 일치했다. 이 비교는 텍스트 투영 검증이며,
Markdown/plain-text 렌더러의 공백 정규화나 한글 UI의 승인·취소를 검증하지 않는다.

### R2: admrul-관세조사-운영-훈령.hwpx

SHA-256: `27c559e41150a166213dffb33d2e496e6cc4d50d18a6fc159c4fe77eacf5dff8`.

흐름 격리·진단 심각도 보완 후 세 모드 모두 섹션과 본문을 반환하면서
아래 **7개 진단 항목**을 반환한 기록이다.
R2의 final/original 본문 gold는 없으므로 정확도 통과로 표시하지 않는다.

| 진단 위치/유형 | 발생 수 |
| --- | ---: |
| header의 ParaShape | 19 |
| section의 미지원 titleMark 경계 | 1 |
| section의 시작 마커 누락 | 3 |
| section의 paraend 미지원 | 146 |
| section의 범위 안 개체·컨트롤 | 26 |
| section의 paraTcId 서식 참조 | 22 |
| section의 겹침 | 127 |

| 모드 | 반환 문단 수 | 문단 문자열 길이 합 | 진단 항목 수 |
| --- | ---: | ---: | ---: |
| preserve | 3654 | 102740 | 7 WARN |
| final | 3649 | 101449 | 7 ERR |
| original | 3315 | 94504 | 7 ERR |

## 흐름 격리와 진단 심각도 회귀

초기 실패 재현에서는 API 양쪽에서
셀의 `subList` 직하 `deleteBegin Id="d" TcId="2"`와 본문의 끝 마커가 연결되어
`["CELL", "BODYKEEP"]` 대신 `["CELL", "KEEP"]`를 반환하는 실패를 확인했다.
Insert/original 대칭 사례도 동일했다. 실제 R2의 기본 CLI도 exit 1,
stdout 0 bytes였고, preserve의 서식·미완결 범위 진단이 출력을 막았다.

컨테이너 10종의 직접 마커, 안팎의 끝 마커, 서로 다른 형제 흐름,
정상적인 셀·각주 내부의 문단 간 범위와 동일 Id 재사용을 검증했다.
잘못된 위치는 XML 직렬화 결과 전체를 수정 전과 비교해 보존을 확인했다.
flow 격리 후 드러난 switch 보류 전파도 **2 failed**를 먼저 확인한 뒤 보완했다.
기존 차트의 `object` 진단 계약 역시 유지한다.

```bash
python -m pytest tests/ -q --tb=short
```

현재 전체 실행 결과는 [implementation-progress.md](implementation-progress.md)에
기록한다. `test_sublist_marker_cannot_delete_following_body`,
`test_misplaced_markers_preserve_xml_and_diagnose`,
`test_sibling_flows_cannot_pair_markers`,
`test_switch_branches_keep_unestablished_revision_semantics`가 경계 회귀를 재현한다.
기존 xfail은 통과로 계산하지 않는다.

### R2 실제 CLI와 원문 보존

```bash
python -m dochan.cli convert \
  corpus/hwp-public/hwpx/admrul-관세조사-운영-훈령.hwpx --format text
```

| CLI 모드 | exit | stdout UTF-8 bytes | 진단 |
| --- | ---: | ---: | --- |
| 옵션 생략 | 0 | 242633 | 7 WARN |
| preserve | 0 | 242633 | 7 WARN |
| final | 1 | 0 | 7 ERR |
| original | 1 | 0 | 7 ERR |

기본/preserve stdout SHA-256은
`f50fd6398edceeade063381c1d6204b65731c278ea6724fad28ab1713a1bac9e`로 동일하다.
`--format`까지 생략한 기본 Markdown CLI도 exit 0, stdout 279,315 bytes이며
기본 API Markdown과 정확히 일치했다.
preserve API의 집계는 3,654문단·문단 문자열 길이 합 102,740자다.
header와 section0 XML은 projector 실행 전후 직렬화가 바이트 단위로 동일하다.
원본 HWPX SHA-256도 위 R2 값과 일치한다. 합성 CLI·batch 테스트에서는
preserve의 파일 출력과 final/original 실패 시 기존 출력 보존도 확인했다.

R2의 CLI 정책은 `tests/test_hwpx_cli_options.py`의
`test_public_complex_revision_cli_preserves_or_fails_explicitly`, 원본 XML 보존은
`tests/test_hwpx_revisions.py`의 `test_real_complex_preserve_leaves_source_xml_unchanged`로
재현한다. 위 CLI 바이트 수·해시는 당시 로컬 실행 기록이며 모든 집계가 자동 테스트의
고정 단언은 아니다. 비공개 문서 묶음의 출력이나 파일 목록은 공개 근거에 포함하지 않는다.

## 검증 한계

정확한 실물 텍스트 gold는 R1 한 문서다. 문단/run 경계를 넘는 `paraend=0`
범위와 섹션/문단/run 자식 마커는 합성 테스트로 검증했다. 실제 복잡 문서의
문단 합치기·문단 끝 복구, `paraend=1`, 서식 변경 적용/취소, 이동·표 구조 변경은
지원하지 않는다. 투영 후 텍스트가 비는 문단은 기존 parser 규칙대로 생략된다.
R2의 preserve 원문 보존·CLI 출력과 final/original의 명시 실패를 확인했으며,
final/original 전체 본문 정확도는 검증하지 않았다. 지원표·README의 완료 체크를 변경하지 않았다.
