# DOC 표·그림 캡션 실물 검증

2026년 10월 2일에 공개 DOC 353개를 전수 검사했다. POI document 디렉터리는 대소문자를 구분하지 않은 `.doc` 160개이며, LibreOffice `sw/qa/extras/*/data/*.doc`는 193개다. LibreOffice 표본은 ww8export 166개, ww8import 13개, ooxmlexport 14개다. 코퍼스는 읽기 전용으로 사용했고 원본 파일은 복사하지 않았다.

DOC `표/그림 캡션` 칸은 **✅를 제안한다**. 새 합성 테스트 47개가 통과했고, 실물에서는 그림 캡션 5건과 표 캡션 2건의 결합을 검증했다. README는 수정하지 않았다. 이 7건에는 원본과 같은 내용을 가진 손상·퍼징 파생 파일이 포함되므로 서로 독립적인 레이아웃 7종을 검증했다는 뜻은 아니다.

## 출력 계약과 구현

DOCX 리더의 `_caption_kind`, `_attach_captions`, `_caption_neighbor`와 `test_docx_remaining.py`, `test_docx_review_fixes.py`를 기준으로 기존 `Table.caption`·`Image.caption`에 원래 `Paragraph`를 옮긴다. `caption_side`는 대상 앞이면 `TOP`, 뒤이면 `BOTTOM`이다. 원래 런의 서식과 출처 CP는 보존한다. Markdown과 JSON은 기존 출력기를 사용한다.

STSH의 스타일 이름 `Caption`은 대소문자 구분 없이 인식한다. 이름이 지역화되거나 변경된 내장 캡션 스타일은 STD의 StdfBase 하위 12비트 `sti=34`로 인식한다. 스타일 슬롯 번호 `istd=34`를 캡션으로 간주하는 방식은 사용하지 않는다. `based-on` 상속도 최대 32단계까지 확인한다. 한국어·독일어·일본어 이름과 `sti=34`의 조합은 합성 바이트로 검증했다. 이 지역화 조합의 실물 표본은 발견하지 못했다.

완결된 SEQ 필드의 캐시 결과를 사용하며 필드를 재계산하지 않는다. Table/표는 표에, Figure/그림은 그림에만 결합한다. DOCX처럼 Equation/수식은 제외하며, Tableau 같은 다른 SEQ 식별자는 대상이 유일할 때만 허용한다. 필드 지시문 안에 중첩된 SEQ와 삭제된 필드 시작점은 근거에서 제외한다.

본문 최상위 흐름에서 원본 문단 경계를 유지한다. 빈 문단·본문 문단·수식 등 다른 객체를 건너뛰지 않는다. 양쪽에 후보가 있으면 문단으로 남기며, 앞서 캡션을 얻은 대상은 후보에서 제외한다. 셀·중첩 표·텍스트박스·보조 story·다른 섹션의 대상에는 결합하지 않는다. 캡션 후보 문단 자체에 이미지나 텍스트박스 앵커가 있으면 결합하지 않는다.

## 실물 검증 표

아래 CP 구간은 시작을 포함하고 끝을 제외한다. 기대값은 현재 모델의 캡션 문자열을 역으로 정답으로 삼지 않고, 변경 전 문단의 표시 문자열과 STSH·PAPX·필드 제어문자·원본 문단 이웃을 대조했다. 같은 이름의 DOCX 짝은 후보 문서 10개 모두에서 발견되지 않았다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| DOC 그림 캡션 | POI `FloatingPictures.doc`이다. | CP 4653–4655는 `0x01` 그림 문단이고, 바로 다음 CP 4655–4700은 `Figure`·SEQ Figure·캐시 `1`·`Spacewalk`로 구성된다. STD 15의 이름은 Caption이며 STSH 오프셋 1202의 첫 바이트는 `22 40`으로, 하위 12비트가 34다. | 앞 그림의 BOTTOM에 `Figure 1  Spacewalk`를 한 번 결합해야 한다. | 해당 그림의 `caption_text`와 `caption_side`가 정확히 일치하며 원래 본문 문단은 제거된다. | 통과했다. |
| DOC 그림 캡션 | POI `53379.doc`이다. | CP 1–35의 EMBED MSDraw 필드 결과에 그림 앵커가 있고, CP 35–60은 Caption 스타일이다. STD 45의 STSH 오프셋 2314에서 `sti=34`를 확인했다. | BOTTOM 캡션은 `MEDICINES CONTROL AGENCY`여야 한다. | 문자열·방향·문단 이동이 일치한다. | 통과했다. |
| DOC 그림 캡션 | POI `Bug53380_3.doc`이다. | 변경 전 표시 문단과 동일한 CP 35–60, Caption/sti 34, 바로 앞 그림 앵커를 관찰했다. | `MEDICINES CONTROL AGENCY`를 BOTTOM에 결합해야 한다. | 기대와 일치한다. | 통과했다. 동일한 내용 계열임을 감안해야 한다. |
| DOC 그림 캡션 | POI `Fuzzed.doc`이다. | CP 4653의 그림 앵커와 CP 4655–4700의 SEQ Figure·Caption을 관찰했다. | `Figure 1  Spacewalk`를 BOTTOM에 결합하고 기존 손상 그림 경고를 유지해야 한다. | 문자열·방향이 일치하고 `truncated or oversized PICF` 경고는 전후 동일하다. | 통과했다. 손상 파생 표본이다. |
| DOC 그림 캡션 | POI `clusterfuzz-testcase-minimized-POIHWPFFuzzer-4892412469968896.doc`이다. | 같은 CP의 원시 그림 앵커·SEQ Figure·Caption을 관찰했다. | `Figure 1  Spacewalk`를 BOTTOM에 결합해야 한다. | 기대와 일치하며 새 오류가 없다. | 통과했다. 퍼징 파생 표본이다. |
| DOC 표 캡션 | POI `au.edu.utas.www___data_assets_word_doc_0003_154335_International-Travel-Approval-Request-Form.doc`이다. | CP 4675–4676은 PAPX의 in_table·row_end가 참인 표 마지막 행 끝이다. 바로 다음 CP 4676–4777은 STD 18 Caption 문단이다. STSH 오프셋 1820의 첫 바이트 `22 40`에서 sti 34를 확인했다. 다음 문단은 별도의 문단이다. | 바로 앞 표에 `Please ensure form is signed by HoS and Dean/HoD prior to forwarding to DVC for DFAT warnings 4 to 5`를 BOTTOM으로 결합해야 한다. | 전체 문자열과 방향이 정확히 일치하고, 뒤따르는 Caption 스타일 문단 3개는 그대로 남는다. | 통과했다. 내용은 표 안내문이지만 명시적 Caption 스타일을 따르는 기존 계약에 해당한다. |
| DOC 표 캡션 | POI `clusterfuzz-testcase-minimized-POIHWPFFuzzer-4951943183990784.doc`이다. | CP 4675–4676의 표 행 끝과 CP 4676–4777의 동일 Caption 문단을 관찰했다. | 위와 동일한 표 캡션을 얻고 기존 FFData·FKP 경고를 유지해야 한다. | 문자열·방향과 기존 경고 목록이 모두 일치한다. | 통과했다. 퍼징 파생 표본이다. |
| DOC 캡션 비결합 | LO ww8export `tdf104334.doc`이다. | CP 20–60은 Caption/sti 34와 STYLEREF 캐시를 가진 문단이지만, 앞은 일반 제목 문단이고 뒤에는 대상이 없다. | `This should be one: 1`을 문단으로 보존해야 한다. | 캡션 결합이 없고 표시 문단을 보존한다. | 통과했다. |
| DOC 캡션 비결합 | POI `test.doc`이다. | 본문에는 결과 구분자 없는 `SEQ CHAPTER` 제어 필드가 있으며 인접 표·그림이 없다. | 캡션으로 옮기지 않고 기존 본문을 보존해야 한다. | 결합과 단어 변화가 모두 없다. | 통과했다. |
| DOC 캡션 비결합 | LO ww8export `tdf36711_inlineFrames.doc`이다. | header story CP 2734–2766, 2767–2799, 2832–2864의 Footer 스타일 문단에 SEQ Chapter와 PAGE가 있다. | 본문 최상위 캡션으로 결합하지 않아야 한다. | 세 문단에 결합과 단어 변화가 없다. | 통과했다. |

353개 중 네이티브 FIB/CLX로 분석 가능한 문서는 329개다. 나머지 24개는 손상·암호화·비네이티브 경로 등의 이유로 구조 스캔 대상에서 제외됐으며 성공적인 캡션 검증으로 계산하지 않았다. 전수 읽기와 단어 회귀 검사는 이 24개도 포함한다. 후보는 10개 문서의 18개 문단이고, 7개를 결합하며 11개를 유지했다. 결합된 7개 문단의 원문 문자열 일치율은 7/7, 100%다.

Markdown 캡션 출력은 기존 공용 출력기가 공백을 접고 이탤릭으로 표시한다. 따라서 모델에서는 `Figure 1  Spacewalk`의 두 공백과 bold 런을 보존하지만 Markdown은 `*Figure 1 Spacewalk*`다. 공백 정규화 후 변경 전후 캡션 표시 횟수는 7/7에서 동일하다. 이 차이는 DOCX와 공유하는 출력 계약이며 새 출력 형식을 추가하지 않았다.

## 회귀와 방어 검증

TDD의 첫 실행에서는 캡션 결합 테스트 21개가 실패하고 기존 비결합 조건 10개가 통과했다. 구현 뒤 그림 캡션의 모델 탐색 누락을 실패 테스트로 확인해 보완했다. 추가 검토에서 수식과 이미지가 같은 원본 문단에 있는 경우 수식을 건너뛰는 결합을 두 방향의 실패 테스트로 확인했고, 방향별 인접 대상 판정으로 수정했다. 최종 캡션 테스트는 47/47이 통과했다. 기존 테스트 단언은 변경하지 않았다.

STSH는 최대 4,096개 스타일, 상속은 최대 32단계로 제한한다. 손상·절단된 STSH는 `doc.errors`의 WARN으로 남기며 본문을 보존한다. 필드는 기존 Stories의 최대 100,000개·중첩 64단계 제한을 재사용한다. 캡션 결합은 원본 그룹 전체를 별도로 적재하지 않고 이전·현재·다음 그룹만 유지한다. 별도 의존성이나 변환 엔진은 추가하지 않았다.

변경 직전 구조 경로와 비교한 353개에서 단어 발생 횟수의 손실·추가, 신규 오류, 실물 프로브 예외는 모두 0건이다. 기존 `scripts/check_doc_word_preservation.py`도 구조화 이전 기준 `785c0e00e2f718567c3357e3f28f190ff255acc7`과 353개를 비교해 미분류 단어 손실·감사 예외·새 치명적 오류가 모두 0건이었다. 문자별 렌더러와 최적화 렌더러의 전체 JSON은 353/353에서 일치했다. 기존에 설명된 과거 경로 차이는 비현재 piece 텍스트 56,648개, 변경 추적 삭제 3,333개, 필드 지시문 381개, 제어문자 정규화 309개, story 경계 1개, 선택적 하이픈 444개로 유지됐다.

전체 테스트는 **2,968 passed, 24 skipped, 14 xfailed**였으며 30.25초가 걸렸다. 새 캡션 테스트에 skip이나 xfail은 없다. 변경한 Python 파일 5개의 ruff 검사와 `git diff --check`도 통과했다.

## 공유 파일 변경과 남은 검증

공유 파일은 `dochan/model/document.py` 하나를 수정했다. `Document.find_all()`이 기존에는 Table.caption만 순회하고 Image.caption은 순회하지 않아, 실물 그림 캡션 5개 문서의 단어 12개가 탐색 결과에서 빠졌다. Image.caption도 같은 seen 집합·재귀 깊이 제한으로 순회하도록 추가했다. 출력기와 다른 리더의 형식별 규칙은 변경하지 않았다.

실물에서 확인한 결합 방향은 모두 BOTTOM이다. TOP, 지역화 sti 이름, 한국어 SEQ, 상속 스타일, 이미 캡션이 있는 대상, 모호한 이웃, 셀·텍스트박스 배제와 수식 경계는 합성 테스트로 검증했으며 대응 실물은 미검증이다. 같은 문서의 DOCX 짝 비교도 표본 부재로 미검증이다. 이 한계를 제외하고 현재 배정된 표·그림 캡션의 구현과 실물 양성·음성 검증은 완료했다.

재현 명령의 코퍼스 경로는 인자로 전달한다.

```sh
/usr/bin/python3 -m scripts.probe_doc_captions --poi POI_DOCUMENT --lo LO_ROOT --output .codex-work/caption-scan.json
/usr/bin/python3 -m scripts.check_doc_word_preservation --poi POI_DOCUMENT --lo LO_ROOT --baseline-ref 785c0e00e2f718567c3357e3f28f190ff255acc7 --check-renderer-equivalence --output .codex-work/word-preservation.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

수치 원본은 `.codex-work/caption-scan.json`, `.codex-work/word-preservation.json`, `.codex-work/pytest-full.log`에 남겼다. 코퍼스 경로와 내부 문서의 파일명·내용은 테스트 픽스처에 넣지 않았다.
