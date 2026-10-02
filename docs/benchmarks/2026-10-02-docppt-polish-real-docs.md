# DOC·PPT P3 재감수 검증

2026년 10월 2일 `illuwa/w-docppt-polish`에서 통합 기준 `104b796`의 파서를 보존한 뒤 수정 전후를 비교했다. POI와 LibreOffice의 공개 문서만 읽었으며 원본 문서는 저장소로 복사하지 않았다. README와 공용 모델·출력 코드는 변경하지 않았다. 구현은 기존 네이티브 레코드 처리, Microsoft 레코드 구조와 원시 바이트 관찰을 바탕으로 작성했으며 POI 구현 코드는 옮기지 않았다.

## 칸별 실물 검증

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 1. PPT 손상 참조의 본문 보충 | LO `hang-3.ppt` | 같은 파일의 기존 복구 스캔과 TextChars/TextBytes 레코드에서 문장을 확인했다. | `I am invisible`을 한 번 보존하고 불확실한 슬라이드 귀속을 표시해야 한다. | 문장을 한 번 출력한다. provenance는 `PowerPoint Document#legacy-recovery`, slide는 null이고 WARN을 남긴다. | 1/1 일치로 이 복구 동작에 ✅를 제안한다. |
| 2. DOC 섹션·페이지 경계 | POI `HeaderFooterUnicode.doc`, LO `fdo53985.doc`, `n750255.doc`, `tdf121374_sectionHF2.doc` 등 네이티브 구조 329개 | FibRgFcLcb의 PlcfSed에 있는 CP 배열을 직접 풀어 출력 섹션 시작점과 비교했다. | 실제 섹션은 PlcfSed CP에서만 시작해야 한다. 그 밖의 0x0c는 문단 내 줄바꿈이어야 한다. | 329/329 시작점 배열이 일치한다. `HeaderFooterUnicode.doc`는 CP353의 페이지 나누기와 무관하게 한 섹션이다. 필드 표시 결과와 셀 중간의 페이지 나누기는 합성 바이트에서도 한 문단을 유지한다. | 섹션 판정은 100% 일치로 ✅를 제안한다. 필드·셀 내부의 해당 특수 배치는 합성 검증이다. |
| 3. DOC 섹션 수 상한 | 위 329개 공개 구조 표본을 조사했다. 상한 초과 실물은 없었다. | 실측 PlcfSed 최대 레코드 수는 15개이다. 상한 검증은 합성 PLC와 반복 문자열로 수행했다. | 4,096개를 넘으면 WARN을 남기고 나머지 내용을 마지막 섹션에 보존해야 한다. | 축소 예산 합성에서 5개 섹션을 3개로 합치고 본문을 보존했다. `a\x0c` 50만 회는 한 섹션·한 문단·100만 문자이며 단독 측정은 1.519초였다. | 구현과 단위 검증은 완료했다. 상한 초과 실물은 미검증이므로 해당 판정은 ⬜를 유지한다. |
| 4. DOC Symbol·Wingdings | LO `tdf90408.doc` | CP22/56의 CHPX `4f4a0300`은 글꼴 인덱스 3이며 FFN 이름은 Wingdings이다. 원문 글자는 `o`와 `þ`다. LO `sw/qa/extras/ww8export/ww8export4.cxx:293-299`도 checkbox 런과 unchecked 런을 구분한다. | `☐unchecked`, `☑checked`를 출력해야 한다. | 두 문자열이 정확히 일치하며 경고가 없다. | 1문서의 2/2 표시 글리프가 일치한다. 명시적 글꼴 매핑에 ✅를 제안한다. Symbol 그리스 문자와 sprmCSymbol은 합성 검증이며 전체 글꼴 대체 규칙의 완성을 뜻하지 않는다. |
| 5. PPT 마스터 그림 상속 | POI `alterman_security.ppt`와 `.pptx` | PPTX 리더는 레이아웃 그림을 읽지만 슬라이드 마스터는 순회하지 않는다. OOXML 짝의 이미지 배치는 4개이다. | 슬라이드 자체 그림 4개만 남아야 한다. | PPT 이미지가 28개에서 4개로 줄었고 마스터 출처 이미지는 0개이다. | 1/1 짝이 일치한다. 마스터 반복 제거에 ✅를 제안한다. |
| 5. customGeo 차이의 별도 확인 | POI `customGeo.ppt`와 `.pptx` | PPT의 pib 그림 도형 44개는 모두 슬라이드 자체에 있다. OOXML은 일부를 diagram·table·일반 도형으로 저장한다. | 마스터 그림 중복을 없애면서 슬라이드 자체 그림은 보존해야 한다. | PPT는 전후 44개, PPTX는 20개이며 PPT 마스터 그림은 전후 0개이다. | 마스터 상속 회귀는 없다. 44 대 20의 이미지 수를 동등 계약의 일치로 세지 않는다. |
| 6. PPT 큰 블록의 조각 예산 | 공개 PPT 217개를 전수 검사했다. 기존 10만 조각 경계를 넘는 정상 실물은 확인하지 못했다. | 합성 `line\r` 60,000회 뒤 `tail`을 붙여 수정 전의 잘림을 재현했다. | 문단 60,001개와 마지막 `tail`을 보존해야 한다. | 수정 전 50,000개에서 잘렸고 수정 후 60,001개를 보존한다. 블록 사이의 공유 예산도 단위 검증했다. | 구현·합성 검증은 완료했다. 해당 크기 실물은 미검증이므로 ⬜를 유지한다. |
| 7. DOC 북마크 단어 경계 | POI `Bug45877.doc` | 원시 본문은 `Paragraph with table`이며 SG12의 시작 CP는 P 뒤에 있다. `poi-scratchpad/src/test/java/org/apache/poi/hwpf/usermodel/TestProblems.java:267-280`의 공개 회귀 표본이다. | `[bookmark: SG12] ***Paragraph with table***`이어야 한다. | Markdown이 정확히 일치한다. | 1/1 일치로 ✅를 제안한다. |
| 7. DOCX 북마크 단어 경계 | POI `bug59058.docx` | `word/document.xml`의 back-bib1이 첫 문단 말미에 있으며 같은 문단의 w:t 전체를 연결해 비교했다. | 마커를 앞에 놓은 뒤 본문 전체가 XML 원문과 같아야 한다. | 마커 위치와 본문 전체가 일치한다. | 1/1 일치로 ✅를 제안한다. `Bug45877.docx` 짝이 없어 같은 문서 짝 검증이라고 주장하지 않는다. |

## 전수 회귀와 단어 보존

DOC는 POI 160개와 LO 193개를 합한 353개, PPT는 POI와 LO를 합한 217개를 검사했다. 총 570개에서 수정 전후 미처리 예외는 모두 0개이고 새로운 치명적 오류도 0개였다. 기존 ERR 문서는 DOC 7개, PPT 27개로 그대로다. 이 기존 손상·암호화 표본을 성공 문서로 계산하지 않았다.

수정 직전과 비교하면 DOC JSON은 53개, PPT JSON은 25개가 달라졌다. DOC에서 사라진 단어 토큰은 `tdf90408.doc`의 `ounchecked`와 `þchecked` 두 개뿐이며 원시 글꼴이 입증하는 `☐unchecked`와 `☑checked`로 교정됐다. PPT는 21개 문서에서 마스터 이미지 배치 399개를 제거했다. 사라진 1,605개 단어 토큰은 모두 수정 전 `#master` 출처의 Markdown 이미지 표시문에서 나온 토큰이고, 이 표시문을 제외한 단어 손실은 0개였다. 단순한 전체 토큰 수 감소를 본문 손실로 판정하지 않았다.

`scripts/check_doc_word_preservation.py`는 구조화 이전 기준 `785c0e00e2f718567c3357e3f28f190ff255acc7`과 DOC 353개를 비교했다. 미분류 손실 문서·단어, 감사 예외, 새 치명적 오류는 모두 0개였다. 문자별 렌더러와 최적화 렌더러의 전체 JSON 동등성도 353/353에서 일치했다. 설명된 과거 경로 차이는 비현재 piece 텍스트 56,648개, 변경 추적 삭제 3,333개, 필드 지시문 381개, 제어문자 정규화 309개, story 경계 1개, 선택적 하이픈 444개였다. 이 수치는 이번 수정 직전과의 차이와 별도로 구분한다.

최종 전체 테스트는 **2,765 passed, 24 skipped, 14 xfailed**였다. 기존 skip·xfail을 통과로 바꾸지 않았다. 새 테스트를 먼저 실패시킨 뒤 구현했고, 추가 재감수에서 발견한 글머리표 중복, 텍스트상자 경계 공백, 북마크처럼 생긴 일반 표시문 오인도 실패 재현 후 수정했다.

## 결정과 제한

PlcfSed는 12바이트 Sed 레코드와 n+1개의 CP로 해석한다. 마지막 CP는 보조 story를 포함할 수 있어 main story의 끝과 같다고 강제하지 않는다. `tdf121374_sectionHF2.doc`의 배열은 `[0, 0, 1350, 1381]`이다. 같은 CP의 빈 섹션과 main 끝 경계도 허용하며, 내용 없는 중복 모델 섹션은 생성하지 않는다. 잘못된 역순·범위는 WARN으로 강등한다. 실물의 일반 페이지 나누기는 39문서에서 207개를 확인했다.

4,096개는 명세상 최대치가 아니라 방어용 출력 상한이다. 실물 최대 15개를 스펙 수치라고 일반화하지 않았다. 상한 이후 텍스트를 버리지 않고 마지막 섹션에 합치며, 일반 페이지 나누기 자체는 섹션을 할당하지 않는다. PPT 조각 작업량은 기존 텍스트 크기 제한에 맞춘 문서 공유 8 MiB 예산으로 관리한다. 기존 문자·출력 런·문단 상한도 유지한다.

손상 PPT의 보충은 최신 slide/notes/master 참조를 복구하지 못했을 때만 수행한다. CString 메타데이터와 식별 가능한 마스터 편집 안내문은 제외하며 제목·링크·글머리표·줄바꿈으로 생기는 중복을 제거한다. 복구 스캔은 64 MiB, 레코드 100,000개, 텍스트 8 MiB와 문서의 남은 출력 예산으로 제한한다. 보충 내용에는 과거 편집 텍스트가 섞일 가능성이 있으므로 최신 슬라이드로 단정하지 않고 출처와 경고를 남긴다.

`customGeo.ppt`의 슬라이드 7–13과 14는 Diagram, 15는 Rectangle, 28은 Table, 41·42·44는 Title 도형에 pib를 갖는다. 예를 들어 OOXML 슬라이드 7은 그림 0개와 diagram 1개, 14는 그림 0개와 diagram 2개, 15는 그림 1개와 일반 도형 13개, 28은 그림 1개와 table 1개다. 이미지 수 20개에 맞추는 임의 필터는 넣지 않았다.

DOC와 DOCX의 실제 북마크는 해당 출력 문단 앞에 배치한다. 본문 런과 서식은 유지하며 텍스트상자 경계 공백은 북마크 재배치 이후 계산한다. 내부 표식 속성으로 실제 북마크를 구분하므로 MACROBUTTON의 `[bookmark: literal]` 같은 일반 표시문을 옮기지 않는다. 기존 문자열 표기 규약과 모델을 그대로 쓴다.

공유 글꼴 매핑에서 알 수 없는 글꼴·문자는 그대로 보존한다. LO `tdf90408B.doc`의 PUA F06F는 명시적 CHPX·스타일 글꼴 인덱스가 없어 추측 변환하지 않았다. sprmCSymbol 실물 검증과 기본 글꼴 대체 규칙은 남은 검증 범위다. 외부 런타임 의존성은 추가하지 않았다.

기존 테스트 두 개는 PlcfSed 없는 0x0c를 섹션·문단 경계로 기대하여 바로 이 P3 버그를 고정하고 있었다. `test_section_mark_is_paragraph_boundary`는 `test_page_break_without_section_plc_is_inline`으로, `test_doc_review_page_break_preserves_words_and_sections`는 `test_doc_review_page_break_preserves_words_in_paragraph`로 바꾸고 기대값을 수정했다. 실제 섹션 경계 동작은 별도의 합성 PlcfSed 테스트로 강화했다. 다른 기존 단언은 변경하지 않았다.

## 재현

코퍼스 경로는 인자로 받는다. `POI_TEST_DATA`는 POI의 test-data 디렉터리이고 `LO_ROOT`는 LibreOffice 소스 루트다. 수정 전 비교에는 작업 시작 때 저장한 `.codex-work/polish-baseline`을 `--source-root`로 지정했다.

```bash
/usr/bin/python3 -m scripts.probe_docppt_polish --poi POI_TEST_DATA --lo LO_ROOT --kind doc --verify-sections --verify-features --output .codex-work/doc-after.json
/usr/bin/python3 -m scripts.probe_docppt_polish --poi POI_TEST_DATA --lo LO_ROOT --kind ppt --verify-features --output .codex-work/ppt-after.json
/usr/bin/python3 -m scripts.check_doc_word_preservation --poi POI_TEST_DATA/document --lo LO_ROOT --baseline-ref 785c0e00e2f718567c3357e3f28f190ff255acc7 --check-renderer-equivalence --output .codex-work/word-preservation.json
/usr/bin/python3 -m scripts.check_doc_font_bookmark_polish --poi-document POI_TEST_DATA/document --lo-ww8 LO_ROOT/sw/qa/extras/ww8export/data
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

원시 결과와 수정 전후 비교는 `.codex-work/doc-before.json`, `doc-after.json`, `ppt-before.json`, `ppt-after.json`, `before-after-comparison.json`, `word-preservation.json`, `fonts-bookmarks-real.json`, `section-raw-evidence.json`에 있다. 전체 테스트 로그는 `.codex-work/full-tests.log`에 있다. 이 작업 산출물은 Git에서 제외한다.
