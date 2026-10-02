# DOC·PPT·DOCX 최종 감수 수정의 실물 검증

작업 시작 기준은 `1d4f0d1d14580ef029b3867593715aa4509a7db5`다. 공개 POI와 LibreOffice 코퍼스를 읽기만 했으며 원본 파일을 저장소에 복사하지 않았다. 구현은 저장소의 기존 출력 계약과 문서의 원시 레코드·XML 관찰에 근거했다. 외부 프로젝트 구현 코드는 사용하지 않았다. LibreOffice 테스트의 기대값만 정답 근거로 인용했다. README는 수정하지 않았다.

## 칸별 실물 판정

| 칸·지적 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| DOCX 번호 없음 | LO `tdf109063.docx` | 원시 문단의 `numId="0"`은 번호 없음이며 해당 수준 정의도 없다. | 본문과 표를 보존하고 CLI가 0으로 종료해야 한다. | 번호 수준 ERR가 없어졌고 Before·Table을 보존하며 CLI가 0으로 종료했다. | 1/1 통과했다. |
| PPT 손상 구조의 텍스트 복구 | LO `hang-1.ppt`, `hang-5.ppt`, `hang-11.ppt`, `crash-2.ppt` | 원시 TextAtom과 감수 기준 출력에 `I am invisible`이 있다. | 중복 없이 한 번 복구하고 출처와 WARN을 남겨야 한다. | 각 문서에 한 번 나타나며 `#legacy-recovery` 출처와 슬라이드 연계 미확인 WARN이 있다. | 4/4 통과했다. |
| PPT 이미지 참조 | POI `pictures.ppt` | 원시 그림 배치와 Image 모델은 5개다. | Markdown 참조도 5개이며 도형 자리에 나와야 한다. | Image 5개와 Markdown 참조 5개다. TextRun에는 이미지 Markdown이 없다. | 1/1 통과했다. |
| PPT 이미지 참조 | POI `alterman_security.ppt`와 `.pptx` | 이미 지원된 PPTX의 그림 배치는 4개다. | PPT도 Image 4개와 참조 4개여야 한다. | 종전 참조 8개가 4개가 됐고 Image는 4개로 유지됐다. | 1/1 쌍이 통과했다. |
| PPT 이미지 대체 텍스트 | POI `alterman_security.ppt`와 `.pptx` | PPT의 `pibName` 4개와 PPTX의 그림 label을 비교했다. | 설명 4개가 유지되어야 한다. | 4/4 일치했다. PPTX에만 있는 자동 생성 이름 `Picture N`은 비교에서 별도로 분리했다. | 설명 보존은 통과했다. |
| DOC 구조 프로브 | POI DOC 160개와 LO 기능 표본 9개 | 기존 이미지 캡션 모델은 `Image.caption_text`에 캡션을 보관한다. | 기존 37개 검증을 동일한 계약으로 통과해야 한다. | 수정 전 36/37을 재현했고 수정 후 37/37을 통과했다. | 통과했다. |
| DOC 표·그림 캡션 | 공개 DOC 353개 | 원시 Caption 스타일 또는 표시 SEQ와 캡션 본문을 비교했다. | 기존 BOTTOM 캡션 7개가 유지되어야 한다. | 7/7 원문 일치이며 단어 손실·추가가 없다. | 기존 BOTTOM 동작은 통과했다. |
| DOC 숨김 SEQ 캡션 경계 | LO `tdf36711_inlineFrames.doc` 등을 포함한 전체 검색 | 숨김 `SEQ ... \h`는 표시 캡션의 근거가 아니다. | 숨김 필드와 인접 그림·표가 있는 실물에서 오결합하지 않아야 한다. | 합성 테스트는 통과했으나 해당 인접 조건의 양성 실물은 찾지 못했다. | 이 경계는 미검증이다. |
| DOC TOP 캡션 | LO DOC 193개 전체 | Caption/SEQ 후보의 CP와 표·그림 위치를 함께 조사했다. | 그림·표 위의 실제 캡션 표본이 있어야 한다. | 결합 가능한 TOP 표본이 0개였다. `tdf104334.doc`의 끝 문단과 `tdf36711_inlineFrames.doc`의 머리말 후보는 대상이 아니다. | 실물은 미검증이며 해당 근거만으로 체크를 올리지 않는다. |
| DOC 선두 페이지 나누기 | LO `fdo56513.doc` | CP 53의 페이지 나누기 다음 표시 본문을 관찰했다. | 문단 앞에 불필요한 `\n`이 없어야 한다. | `This is another page of the second section`으로 시작하며 WARN/ERR가 없다. | 1/1 통과했다. |
| DOCX SmartArt 텍스트 | POI `strict-smartart.docx` | diagramData 파트의 `dgm:t/a:p/a:r/a:t` 원문은 a·b·c다. | 도형 위치에 a·b·c를 순서대로 내야 한다. | 본문에 a·b·c가 복원됐다. 누락·손상 데이터의 WARN은 합성 입력으로 확인했다. | 실물 1/1이 통과했다. |
| DOCX 위치 탭 | POI `ThreeColFoot.docx` | `word/footer1.xml`의 세 텍스트 사이에 `w:ptab` 두 개가 있다. | `Footer Left\tFooter Middle\tFooter Right`를 보존해야 한다. | 탭 2개를 보존했다. | 1/1 통과했다. |
| DOCX 스타일 상속 | POI `HeaderFooterUnicode.docx`와 `.doc` | `Heading1` 스타일의 `w:b`와 DOC의 같은 제목을 비교했다. | 직접 run 속성 없이도 제목 Molière가 굵어야 한다. | 양쪽 제목의 bold와 Markdown이 일치했다. | 1/1 쌍이 통과했다. |
| PPT 자동 번호 목록 | POI `customGeo.ppt`와 `.pptx` | PPT `StyleTextProp9Atom`의 자동 번호 형식·시작값과 PPTX `buAutoNum` 출력이다. | 슬라이드 1과 20 노트의 번호 목록이 일치해야 한다. | 9/9 문단이 번호와 전체 문자열까지 일치했다. | 통과했다. |
| PPT 내부 하이퍼링크 | LO `tdf168736-1.ppt` | `sd/qa/unit/export-tests-ooxml3.cxx:1194–1204`의 기대값은 nextslide이고 원시 action=3, jump=1이다. | 첫 슬라이드 링크가 슬라이드 2를 가리켜야 한다. | 첫 슬라이드의 대상은 `#PowerPoint Document#slide2`이며 문서 전체에서 링크 4개가 출력됐다. | 1/1 통과했다. |
| PPT 내부 하이퍼링크 | LO `tdf168736-2.ppt` | 같은 테스트 파일 1206–1216행은 슬라이드 2의 대상 `slide1.xml`을 기대한다. 최신 persist 문서의 ExHyperlink 정의는 50개다. | 빈 액션 도형도 저장된 표시명과 내부 대상을 보존해야 한다. | 슬라이드 2에 `Slide 1 <#PowerPoint Document#slide1>`이 있고 최신 정의 50/50개가 출력됐다. | 1/1 통과했다. |
| DOC 컨트롤 텍스트 | POI `Bug52583.doc` | 기존 구조 프로브의 저장된 폼 표시값을 정답으로 삼았다. | `riri`를 보존하고 필드 지시문은 노출하지 않아야 한다. | 구조 프로브에서 통과했다. | 통과했다. |
| DOC 스마트 태그 텍스트 | 아래 표의 공개 DOC 14개 | FactoidInfo·시작/끝 PLC의 CP 범위를 동일 출처의 결과 문단과 비교했다. | 래퍼 메타데이터 없이 표시 텍스트를 보존해야 한다. | 텍스트가 있는 184/184개 범위가 일치했다. 빈 범위 3개는 양성 집계에서 제외했다. | 양성 13개 문서에서 통과했다. |

## 스마트 태그 범위의 독립 검증

DOCX의 기존 `test_reads_docx_text_inside_sdt_and_smart_tag_wrappers`와 같은 계약을 적용했다. DOC에서는 factoid가 본문 CP에 붙은 메타데이터이므로 별도 모델이나 새로운 마크업을 만들지 않는다. 기존 DOC 렌더러가 이미 범위 텍스트를 보존하여 런타임 파서 추가는 필요하지 않았다.

FIB 슬롯 114의 `SttbfBkmkFactoid`, 115의 시작 PLC, 117의 끝 PLC를 읽었다. FactoidInfo는 길이 6으로 기록된 12바이트 구조이며 FBKFD는 6바이트, FBKLD는 4바이트다. FBKFD의 끝 인덱스로 CP 범위를 연결한 후 `WordDocument#cp…` 출처가 같은 문단에서 문자열을 확인했다. 개수·구조 길이·끝 인덱스·CP 범위를 검사한다. 단순히 문서 어딘가에 같은 단어가 있으면 통과하는 방식이 아니다. 제공된 이전 감수의 factoid 스크립트는 슬롯과 stride가 달라 검증 근거로 사용하지 않았다.

| 공개 표본 | 텍스트 범위 | 일치 | 판정 |
|---|---:|---:|---|
| `fdo53985.doc` | 1 | 1 | 통과했다. |
| `tdf79553_lineNumbers.doc` | 33 | 33 | 통과했다. |
| `tscp.doc` | 0 | 0 | 빈 범위만 있어 양성에서 제외했다. |
| `Bug47286.doc` | 2 | 2 | 통과했다. |
| `Bug47287.doc` | 2 | 2 | 통과했다. |
| `Bug51834.doc` | 12 | 12 | 통과했다. |
| `Bug52032_1.doc` | 16 | 16 | 통과했다. |
| `Bug61268.doc` | 33 | 33 | 통과했다. |
| `FloatingPictures.doc` | 25 | 25 | 통과했다. |
| `Fuzzed.doc` | 25 | 25 | 통과했다. |
| `au.edu.utas.www___data_assets_word_doc_0003_154335_International-Travel-Approval-Request-Form.doc` | 2 | 2 | 통과했다. |
| `ca.kwsymphony.www_education_School_Concert_Seat_Booking_Form_2011-12.doc` | 6 | 6 | 통과했다. |
| `clusterfuzz-testcase-minimized-POIHWPFFuzzer-4892412469968896.doc` | 25 | 25 | 통과했다. |
| `clusterfuzz-testcase-minimized-POIHWPFFuzzer-4951943183990784.doc` | 2 | 2 | 통과했다. |

중복·포함 범위와 퍼징 파생 표본이 있으므로 184개의 독립 텍스트를 뜻하지 않는다. 전체 353개 중 손상·비OLE 4개는 구조 스캔 불가로 명시적으로 제외했으며 프로브 오류는 0개였다.

## 출력 계약과 기존 테스트 변경의 근거

PPT 그림은 기존 Image 요소 하나를 도형 위치에서 반환한다. DOCX의 `inline_reference`는 이미 문단에 있는 참조와 Image의 중복 출력을 막는 수단이다. PPT에서는 TextRun에 Markdown을 넣지 않으므로 별도 참조 문단 없이 Image만 내고 기존 Markdown 출력기를 재사용한다. JSON에는 Image 정보만 있고 평문에는 `![…](…)` 문법이 섞이지 않는다. 설명은 `wzDescription` 또는 `pibName`과 `wzName`을 조합한다. PPT에 저장되지 않은 PPTX 자동 생성 이름을 만들어 넣지 않는다.

기존 `test_image_pib_delayed_blip_description_asset_and_ocr`와 `test_ppt_unsupported_equation_keeps_preview_and_surrounding_text`는 그림 참조가 Paragraph에도 존재한다고 단언하여 지적 3의 버그를 고정하고 있었다. 두 테스트에 한해서 그 단언을 Image 위치·단일 Markdown 참조·대체 텍스트로 교체했다. 그림 바이트·자산·OCR·수식 미지원 경고와 앞뒤 본문 보존 단언은 유지했다. DOCX 기존 테스트 단언은 바꾸지 않았다.

PPT 상대 이동은 InteractiveInfoAtom의 next/previous/first/last만 현재 슬라이드 범위 안에서 해석한다. 명시 주소가 없는 표시명은 정확히 `Slide N`이고 실제 슬라이드 개수 안일 때만 내부 대상으로 해석한다. 임의 표시명·매크로·OLE 액션을 링크로 추측하지 않는다. `tdf168736-2.ppt`의 원시 스트림에는 과거 편집본의 중복 정의가 있으므로 감수의 75라는 수치에 맞춰 복원하지 않고 최신 persist 문서의 50개를 정답으로 삼았다.

번호 목록은 저장된 StyleTextProp9 확장을 paragraph style run에 연결하며 기존 PPTX 번호 표기를 재사용한다. 알 수 없는 확장 필드·번호 형식에는 WARN을 남기고 원문을 보존한다. 자동 생성한 번호 접두 run만 표시하여 손상 구조 보충의 중복 비교에서 제외한다. 실제 본문에 들어 있는 숫자를 정규식으로 지우지 않는다. 정상적으로 비어 있는 최신 슬라이드는 과거 텍스트를 되살리지 않으며, 빈 손상 구조나 미해결 참조에 한해서 제한된 복구 경로를 사용한다.

DOCX 스타일은 문서 기본값, 문단 basedOn 체인, 문자 basedOn 체인, 직접 서식 순으로 적용한다. 스타일 단계의 b·i·strike toggle과 직접 false를 구분한다. 기존에 빠졌던 문단 스타일의 굵게·기울임·밑줄·취소선 등이 Markdown에 추가되는 변화는 의도적이다. SmartArt는 데이터 파트 텍스트만 읽으며 그래픽 배치의 시각 재현을 의미하지 않는다. 데이터 파트 128개·합계 16 MiB·출력 1,000,000자와 기존 XML·구조 상한을 적용한다. 이러한 값은 자원 제한이며 표본 수치를 맞추는 조건이 아니다.

## 재현 방법

최종 전체 테스트는 **3142 passed, 24 skipped, 14 xfailed**였으며 ruff와 `git diff --check`도 통과했다. 실패로 고정한 새 회귀 테스트를 먼저 실행한 뒤 구현하여 통과시켰다. 기존 skip·xfail을 해제한 것으로 계산하지 않는다. 그림 BLIP 누락 경고만으로 과거 슬라이드 텍스트를 되살리지 않는 경우도 마지막 회귀 테스트에 포함했다.

| 형식 | 표본 수 | 기준 HEAD의 ERR | 수정 후 ERR | 신규 ERR | Markdown이 바뀐 문서 |
|---|---:|---:|---:|---:|---:|
| DOC | 353 | 6 | 6 | 0 | 18 |
| PPT | 217 | 27 | 27 | 0 | 64 |
| DOCX | 1506 | 27 | 24 | 0 | 142 |

총 2,076개 입력에서 신규 ERR·프로브 예외·시간 초과가 모두 0개였다. DOCX 목록은 LO ooxmlexport 1,366개, POI DOCX 전체 130개, LO ww8export 10개다. 감수 자료에 저장된 `785c0e0`의 DOCX 1,506개 결과와 비교해도 신규 ERR는 0개다. 이 과거 기준은 제공된 측정치를 재사용했고 이번 실행에서 새로 측정한 기준은 작업 시작 HEAD다. `tdf109063.docx`, `tdf61309.docx`, `tdf141966_chapterNumberTortureTest.docx`의 번호 수준 ERR가 해소됐다. 기존 암호·손상 입력의 ERR는 남아 있으므로 모든 문서의 변환 성공을 뜻하지 않는다.

HEAD 대비 DOC 모델 문단 단어 감소는 0개였다. DOCX의 감소 후보 10개 문서·20개 토큰은 탭을 제거하면 종전 붙어 있던 토큰이 모두 재현되므로 위치 탭 복원의 결과임을 확인했다. PPT 감소 후보 56개 문서 중 55개는 종전 이미지 Markdown 문단의 토큰으로 모두 설명된다. `41246-2.ppt`의 나머지 30개 토큰은 기존 `#legacy-recovery` 6개 문단과 슬라이드 11의 동일 내용이 중복되던 경우다. 생성 목록 접두사만 제외하고 공백을 정규화하면 여섯 문단 모두 수정 후 슬라이드 본문과 일치한다. 이 중복 제거까지 반영한 뒤 미설명 토큰은 0개였고, 그림 모델 개수는 217개 전부에서 유지됐다.

별도의 `scripts/check_doc_word_preservation.py`는 구조화 전 리더가 필요한 기존 설계에 따라 `785c0e00e2f718567c3357e3f28f190ff255acc7`을 기준으로 실행했다. DOC 353개에서 미분류 손실 문서·토큰, audit_errors, 신규 fatal이 모두 0개이며 문자별 renderer와 전체 JSON 동일성은 353/353이었다. 기준 대비 줄어든 토큰은 기존 CP·필드·삭제 추적·비본문 바이트 근거로 전부 분류됐다.

Python은 `/usr/bin/python3` 3.9를 사용했다. 모든 테스트 입력은 합성 바이트 또는 합성 OOXML이며 CI가 외부 코퍼스에 의존하지 않는다. 기능 프로브는 코퍼스 경로를 인자로 받는다.

```bash
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
/usr/bin/python3 -m ruff check dochan scripts tests
/usr/bin/python3 -m scripts.probe_office_fix2_ppt --poi /path/to/poi/test-data --lo /path/to/lo-src --output .codex-work/ppt-feature-final.json
/usr/bin/python3 -m scripts.compare_office_fix2 --source-root /path/to/reader --lists /path/to/list-doc.txt /path/to/list-ppt.txt /path/to/list-docx.txt --output .codex-work/corpus-post --baseline .codex-work/corpus-baseline/results.json
```

개별 JSON 수치, 실패 후 통과 기록, 전체 비교와 단어 보존 결과는 `.codex-work/`에 보관한다. DOC 캡션·factoid 프로브의 실행 인자는 각 스크립트의 `--help`에서 확인할 수 있다. 공유 모델·출력 경로·패키지 설정·런타임 의존성은 수정하지 않았다.
