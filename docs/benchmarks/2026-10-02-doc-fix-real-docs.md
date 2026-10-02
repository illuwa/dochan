# DOC 리뷰 반영과 실물 재검증

2026년 10월 2일 `illuwa/w-doc`에서 두 독립 리뷰의 P1·P2와 지정 P3를 수정했다. 선택 항목 P3-8·9·12도 수정했다. 전체 테스트는 **1,968 passed, 24 skipped, 14 xfailed**이며 리뷰 전 1,927개에서 41개 늘었다. HEAD의 테스트 단언을 변경하지 않았다.

POI 160개와 LibreOffice 193개를 전수 검사했다. 미분류 단어 손실·감사 예외·새 치명 오류는 모두 0개다. 기능별 실물 검사 37/37, 빠른 문자 런 렌더러와 문자 단위 렌더러의 전체 JSON 비교 353/353이 통과했다. 20개 칸 중 기존 16개의 ✅ 제안을 유지하고 이미지 참조·표/그림 캡션·OCR·컨트롤/스마트 태그 4칸은 미검증 범위 때문에 ⬜를 유지한다. README는 변경하지 않았다.

구조를 읽지 못한 문서의 기존 텍스트 폴백과 여섯 기존 ERR은 그대로 남는다. 네 손상 퍼즈의 단어 차이를 분류한 것은 시각적 복원이나 손상 전 원본 완전성을 증명하지 않는다. 공개 표본 원문을 저장소에 복사하지 않았고 내부 문서는 사용하지 않았다.

## 칸별 실물 증거

아래 POI 테스트 경로는 `poi-scratchpad/src/test/java/org/apache/poi/` 기준이다. 문자열에 대한 내용 일치는 별도 표시가 없으면 공백 정규화 또는 해당 POI 테스트의 포함 단언을 따른다. 그림 바이트 일치는 별도로 명시한다.

| 칸 | 표본 파일(POI 공개 파일명) | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| 표(셀 병합) | `table-merges.doc` | `hwpf/converter/TestAbstractWordUtils.java:42-50`, `TestWordToHtmlConverter.java:86-88`, 원시 TAP | 경계 0·1062·5738·6872·8148·9302와 첫 행 colspan 3·2다. | 4×5 격자, 첫 행 colspan 3·2, 마지막 행 colspan 5가 일치했다. | 통과했다. |
| 표(셀 병합) | `Bug47958.doc` | 첫 표 행 끝 CP55의 TC 0x06e0, CP80·109·147·162·204·213·248·277의 TC 0x06a0 | 같은 경계 7020–11070의 셀이 9행에 걸쳐 이어진다. | 9×5 표에서 (0,4)의 rowspan=9이고 아래 8개 셀의 rowspan=0이다. | 통과했다. |
| 표(중첩 텍스트) | `innertable.doc` | `hwpf/usermodel/TestTableRow.java:42-64`, itap=2 및 inner-cell/row 원시 속성 | 바깥 3×3, 안쪽 2×2이며 셀 안에서 E·표·F 순서다. | 크기와 셀 내부 순서가 모두 일치했다. | 1/1 표본이 통과했다. |
| 서식(bold/italic) | `FloatingPictures.doc` | CHPX FKP 페이지22, CP64·97·171의 `35 08 81`, `36 08 81` | bold, italic, bold+italic 순서다. | 세 위치의 런 플래그가 각각 (참,거짓), (거짓,참), (참,참)이다. | 3/3 위치가 일치했다. |
| 스타일 상속 | `HeaderFooterUnicode.doc` | STSH Heading1 bold, Molière 문단 istd=1, OOXML `styles.xml`의 Heading1 `w:b` | 직접 굵게 명령 없이 제목이 굵어야 한다. | 제목 수준과 bold=True를 복원했다. | 1/1 표본이 통과했다. |
| 이미지 참조 | `two_images.doc`, `PngPicture.doc`, `vector_image.doc`, `pictures_escher.doc`, `Picture_Alternative_Text.doc` | `hwpf/usermodel/TestPictures.java:73-86,123-139,345-362`, PlcfSpa·BStore 원시 바이트 | 각각 2·1·1·2·1개의 실제 이미지 자산이다. | 7개 배치를 복원했다. `vector_image.emf`와 7,348바이트 전체가 일치했다. | 5/5 표본이 통과했다. |
| 이미지 참조 | `testPictures.doc` | `hwpf/usermodel/TestPictures.java:94-115`의 7개 기대 | POI 그림 목록 7개다. | JPG 3개·PNG 2개·WMF 1개로 6개를 복원했다. CP101의 PICF에는 BLIP·FBSE·pib가 없다. | 전체 기능 표본 6개 중 5개 완전 일치, 이 표본 6/7이다. ⬜ 유지한다. |
| 이미지 대체 텍스트 | `Picture_Alternative_Text.doc` | `hwpf/usermodel/TestPictures.java:362`, wzDescription 원시 속성 | `This is the alternative text for the picture.`다. | `Image.alt_text`가 정확히 일치했다. | 1/1 표본이 통과했다. |
| 표/그림 캡션 | `FloatingPictures.doc` | CP4662·4685·4687의 `SEQ Figure`와 캐시 결과 1 | `Figure 1  Spacewalk` 문단을 보존한다. | 문단 텍스트가 정확히 일치했다. | 그림 1/1 통과, 표 캡션은 160개 조사에서 독립 표본을 찾지 못해 미검증이다. ⬜ 유지한다. |
| 이미지 OCR | `Picture_Alternative_Text.doc` | 실물 `Image.run_ocr()` 및 기존 OCR 실행 조건 | 추출된 바이트로 실물 OCR을 실행해야 한다. | `has_data=True`이나 Python 3.9가 기존 최소 버전 3.10 검사에서 차단되어 결과가 빈 문자열이다. | 바이트 전달 합성 테스트만 통과했다. 실물 OCR은 미검증이므로 ⬜ 유지한다. |
| 머리글/바닥글 | `HeaderFooterUnicode.doc`, `ThreeColHeadFoot.doc` | `hwpf/extractor/TestWordExtractor.java:190,199,214,223` | 유로 기호·Molière·탭을 포함한 헤더와 푸터다. | 지정 내용과 표·빈 변형을 보존했다. Unicode 표본은 머리글3·바닥글3이다. | 기능 표본 2/2가 통과했다. 짝 전체의 정확 일치율은 아래에 별도로 기록한다. |
| 머리글/바닥글 | `header_footer_replace.doc`, `Bug53380_2.doc`, `PageSpecificHeadFoot.doc` | PlcfHdd·원시 본문, `hwpf/usermodel/TestHeaderStories.java:147-153` | 표 내부 내용과 MACROBUTTON 표시 문자열·Page 2도 남아야 한다. | `_TEST_` 6곳과 `[Document Title]`, `[Alt+R for Date]`, Page 2를 보존했다. | 표 머리글 누락을 수정하고 통과했다. |
| 각주/미주 | `footnote.doc`, `test-fields.doc` | `hwpf/extractor/TestWordExtractor.java:234,238,248,252`, 원시 하위 문서 CP | 첫 표본 각주 TestFootnote·미주 TestEndnote, 둘째 각주 Fridrich Strba·미주0이다. | 내용·개수·통합 참조 번호를 복원했다. | 2/2 표본이 통과했다. |
| 주석/코멘트 | `footnote.doc`, `test-fields.doc`, `MarkAuthorsTable.doc` | `hwpf/extractor/TestWordExtractor.java:260`, ATRDPre10·GrpXstAtnOwners | 각각 주석1·1·3개와 작성자를 보존한다. | TestComment/Maxim Valyanskiy, 날짜/Fridrich Strba, 주석3개/Ryan Lauck·공백·공백이 일치했다. | 3/3 표본이 통과했다. |
| 변경 추적 | `MarkAuthorsTable.doc` | 원시 CHPX CP1612–1653 삽입, CP434–487 삭제, `hwpf/model/TestRevisionMarkAuthorTable.java:70-74` | 삽입 문장을 남기고 삭제 문장을 빼며 작성자4명을 읽는다. | 삽입 굵게·밑줄을 보존했고 삭제 문장 `The two top level models making up the framework are:`는 출력하지 않았다. 작성자4/4가 일치했다. | 1/1 표본이 통과했다. |
| 컨트롤/스마트 태그 텍스트 | `Bug52583.doc` | `hwpf/converter/TestWordToHtmlConverter.java:60`, NilPICF·FFData | 드롭다운 선택값 riri다. | riri를 출력하고 FORMDROPDOWN 명령을 숨겼다. | 양식 컨트롤은 검증했다. 독립 스마트 태그 표본을 식별하지 못해 복합 칸은 ⬜ 유지한다. |
| 컨트롤 텍스트의 체크박스 사례 | `au.edu.utas.www___data_assets_word_doc_0003_154335_International-Travel-Approval-Request-Form.doc` | 원시 FFData의 iType=1, iRes=25, wDef=0인 12개 레코드 | 선택하지 않은 체크박스12개다. | `[ ]` 12개를 출력했다. | 컨트롤 실물2/2가 통과했다. 스마트 태그 미검증 판정은 유지한다. |
| 텍스트박스/도형 텍스트 | `test-fields.doc`, `Bug46817.doc` | PlcftxbxTxt·PlcfSpa·OfficeArt lTxid, 본문 CP0 및 CP114·394 | 본문·머리글 박스를 각 앵커에서 한 번씩 내보낸다. | 앵커 위치의 텍스트·중첩 표를 보존하고 문서 끝에 중복 출력하지 않았다. | 2/2 표본이 통과했다. |
| 읽기 순서 | `FloatingPictures.doc`, `Bug46817.doc`, `innertable.doc` | CP4625 설명·4653 그림·4655 캡션, 박스 앵커 및 셀 문단 CP | 설명→그림→캡션과 셀 안의 문단→표→문단 순서다. | CP 앵커와 중첩 모델의 순서가 일치했다. | 3/3 표본이 통과했다. 시각적 좌표 순서를 보장하는 판정은 아니다. |
| 빈 행/열 좌표 보존 | `Bug48065.doc`, `58804.doc` | 전자는 CP35–63의 4행·각4셀 TAP, 후자는 8행·각3셀 TAP | 전자의 마지막 행 전체와 열2·3이 비어 있고 후자의 첫 행이 빈 셀이다. | 16개 및 24개 셀 좌표가 유지되었다. | 2/2 표본이 통과했다. |
| 하이퍼링크 | `hyperlink.doc`, `Bug51686.doc` | PlcFld 명령과 캐시 표시 문자열 | 필드 명령을 숨기고 표시문자와 대상을 남긴다. | DOCX와 동일한 `표시문자 <URL>`을 출력했다. | 2/2 표본이 통과했다. |
| 하이퍼링크 URL | `hyperlink.doc`, `Bug51686.doc` | `HYPERLINK` 원시 명령 | testuri.org 및 Apache Tika·POI 대상이다. | 기대 URL이 보존되었다. | 2/2 표본이 통과했다. |
| 내부 하이퍼링크 | `Bug51686.doc` | `HYPERLINK \\l` 원시 명령 | #OnMainHeading·#OnLevel3이다. | 두 링크가 일치했다. | 2/2 링크가 통과했다. |
| 내부 북마크 | `Bug51686.doc` | SttbfBkmk·PlcfBkf·PlcfBkl | OnMainHeading·OnLevel3 이름이다. | 두 마커가 일치했고 관리용 `_` 이름은 숨겼다. | 2/2 북마크가 통과했다. |

`table-merges.doc`의 중간 두 행 첫 TC는 모두 0x0060으로 병합 시작이다. 빈 셀이라는 이유로 세로 병합을 추측하지 않았다. 세로 병합의 실제 증거는 별도 `Bug47958.doc`의 시작·연속 플래그다. `testPictures.doc`의 BLIP 없는 도형에 가짜 이미지 경로나 바이트를 만들지 않았다.

## 리뷰 후 추가 실물 검사

LO 경로는 `sw/qa/extras/` 기준이며, POI 원시 바이트와 공개 테스트의 기대값만 참조했다. 동일한 이름의 fdo53985.docx는 표 수가 다른 버전이므로 정답으로 쓰지 않았다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| 중첩 표 | `tdf106799.doc` | LO `ww8import/ww8import.cxx:107-126`, CP0의 itap2 | 바깥 1×1 안에 3×4, 첫 셀 colspan4다. | 호스트 셀 안의 크기와 병합이 일치했다. | 통과했다. |
| 중첩 표·읽기 순서 | `fdo53985.doc` | LO `ww8export/ww8export3.cxx:369-374` | 전체 표 5개이며 시작 표가 호스트 안에 있다. | 최상위4개와 첫 표 셀 내부1개로 총5개다. | 통과했다. |
| 중첩 표 | `Bug51890.doc` | PAPX CP1551-1631의 깊이1→3 | 8×1 표의 (2,0)에 1×2 호스트, 각 셀에 1×1 표다. | 지정 경로의 크기가 모두 일치했다. | 통과했다. |
| 중첩 표·읽기 순서 | `innertable.doc` | POI `TestTableRow.java:42-64` | 3×3의 (1,1)에 E→2×2 표→F다. | 구조와 순서가 일치했다. | 네 중첩 표본 4/4가 통과했다. |
| 변경 추적 | `53446.doc` | CHPX 삭제 행 끝16개와 CP12511-13392 | 삭제 표 골격만 빼고 정상 본문을 보존한다. | 나머지 13×5·13×5·13×4·13×4 표와 정상 본문707자를 보존했다. | 통과했다. |
| 읽기 순서·페이지 경계 | `n750255.doc` | 원시 one/0x0c/two | one과 two가 별도 구역·문단이다. | 단어가 붙지 않고 두 문단으로 남았다. | 통과했다. |
| 이미지 대체 텍스트 | `msobrightnesscontrast.doc` | PlcfSpa CP0/SPID1027, wzDescription | `MSlogo (2)`다. | 떠 있는 이미지의 alt_text가 일치했다. | 통과했다. |
| 이미지 대체 텍스트 | `tdf124601.doc` | PlcfSpa CP4/SPID1027와 CP9/SPID1026, wzDescription | audit/emas 로고 설명과 Rollstuhlfahrer 설명2개다. | 두 설명 전체가 정확히 일치했다. | 떠 있는 표본2/2가 통과했다. 기존 인라인 포함3/3이다. |
| 내부 하이퍼링크 | `tdf81705_outlineLevel.doc` | 원시 필드 CP42/73/106 | `#_Toc68096040`이다. | URL 접미사가 일치했다. | 통과했다. |
| 내부 하이퍼링크 | `tdf56738.doc` | HYPERLINK 캐시 필드53개 | RefHeading 대상53개다. | 대상53개 모두 남았다. | LO2/2, 기존 POI 포함3/3이다. |
| 내부 북마크 | `bnc636128.doc` | SttbfBkmk/PlcfBkf/PlcfBkl | 공개 이름 Text2다. | 표시 이름이 일치했다. | 통과했다. |
| 내부 북마크 | `bordercolours.doc` | 같은 PLC와 공개 이름5개 | ParagraphBorder·BetwixtParagraphBorder·CharBorder·CharShadowBorder·PictureBorder다. | 이름5개가 순서대로 일치했다. | LO2/2, 기존 POI 포함3/3이다. |
| 머리글/바닥글 경계 검증 | `Bug53380_4.doc` | 북마크 끝의 전역 CP와 헤더 스토리 | 정상 머리글 북마크를 오류로 보지 않는다. | invalid end position 오경고가 사라졌다. | 통과했다. |
| 손상 하위 문서의 텍스트 보존 | `clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc` | 비단조 PlcfHdd와 FIB 헤더 CP9150-9520 | PLC 오류를 경고하고 텍스트를 보존한다. | 종류를 추정하지 않는 일반 블록으로 남겼다. | 단어 감사가 통과했다. 정상 레이아웃 판정은 아니다. |

머리글·바닥글은 첫 페이지·짝·홀 변형을 분리된 모델 항목으로 평탄화한다. 실제 페이지별 배치를 계산하지 않는다. U+000C는 기존 JSON 계약을 따라 Section 경계로 보존하며 U+000E는 줄바꿈, U+001E는 하이픈, U+001F는 선택 하이픈 제거로 처리한다.

## 단어 보존 불변식과 전체 차이 분류

`scripts/check_doc_word_preservation.py`는 Git 기준 리비전의 실제 `DOCReader`를 독립 모듈로 읽어 현행 파서와 비교한다. 기본값은 HEAD이며 이번 측정의 고정 리비전은 `785c0e00e2f718567c3357e3f28f190ff255acc7`이다. 문단 안의 서식 run은 합치고, 삽입된 북마크 표시 run만 제외한 문단 텍스트의 대소문자를 구분하는 Unicode `\w+` 다중집합을 사용한다. Markdown 기호 및 HTML 표 태그는 단어로 세지 않는다. 따라서 표의 Markdown/HTML 표현 방식 변화가 실제 본문 손실처럼 보이는 것을 막는다.

POI 160개, LO ww8export 166개·ww8import 13개·ooxmlexport 14개를 합쳐 353개를 읽었다. 구 경로에만 있던 단어가 있는 문서는 61개이며, 모든 발생 횟수에 CP 또는 CLX 근거가 있다. 미분류 단어 0개, 감사 예외 0개, 신규 ERR 문서 0개이다. 수치 원본은 `.codex-work/word-loss-final.json`이다.

손실 분류는 파일 이름에 따른 예외를 두지 않는다. 구 경로의 비활성/오해독 텍스트는 유효 PlcPcd의 텍스트에 동일한 구 파서의 정리·모델 생성을 적용한 결과보다 구 출력에 더 많았던 발생 횟수만 허용한다. 변경 추적 삭제는 CHPX 삭제 CP를 제거하기 전후의 완성 단어 차이로 계산한다. 필드, 선택 하이픈, 제어문자, 스토리 경계도 원래 CP에서 변환한 차이만 인정한다. 변환 중 사라졌다가 다시 생긴 단어를 중복으로 면제하지 않도록 최초·최종 다중집합 차이를 분류 예산의 상한으로 사용한다. 부분 삭제 또는 단어 결합으로 생긴 새 완성 단어는 현행 출력에서 충분한 횟수로 확인되어야 한다. 이 확인이 실패하면 해당 문서의 CP 변환 분류를 모두 무효화한다.

손상된 머리글 PLC는 손실 면제 사유가 아니다. 실제 퍼즈 표본에서 헤더 CP 9150..9520이 비단조 PlcfHdd 때문에 빠지는 것을 발견했으며, 파서가 머리글/바닥글 종류를 추정하지 않고 본문 블록으로 보존하도록 수정했다. 이 경우를 손실로 검출하는 합성 테스트를 추가했다.

또 다른 실제 회귀는 `53446.doc`의 정상 CP12511..13392 문단이 삭제된 표 첫 셀에 합쳐져 버려지는 문제였다. 이 감사로 미분류 106단어가 발견되었으며, 파서가 표 컨텍스트 경계를 넘는 삭제 문단 병합을 막아 고쳤다. 현재 해당 문서의 309개 구 출력 전용 단어는 모두 변경 추적 삭제에 해당한다.

`ProblemExtracting.doc`는 문단 단어 4,345개가 전후 모두 유지되며, Markdown 토큰 감소는 본문 단어 손실을 뜻하지 않는다.

검증 명령은 `/usr/bin/python3 -m scripts.check_doc_word_preservation --poi POI_DOCUMENT --lo LO_ROOT --baseline-ref 785c0e00e2f718567c3357e3f28f190ff255acc7 --output RESULT.json`이다. 코퍼스 경로는 인자로 받으며 원문이나 이미지 파일을 저장소에 복사하지 않는다. 감사 단위 테스트 10개는 `/usr/bin/python3 -m pytest tests/test_doc_word_preservation.py -q -p no:cacheprovider --basetemp=.codex-work/pytest-loss`에서 통과했다.

## 분류 집계

| 분류 | 단어 발생 횟수 |
|---|---:|
| unclassified | 0 |
| 구 경로의 비활성/오해독 텍스트 | 56648 |
| 변경 추적 삭제 | 3333 |
| 필드 명령·표시 복원 | 383 |
| 제어문자 처리에 따른 단어 결합 | 309 |
| 스토리 경계 분리 | 1 |
| 선택 하이픈 제거 | 444 |

## 구 출력 전용 단어가 있는 모든 문서

| 코퍼스 | 공개 표본 | 발생 횟수 | 분류와 발생 횟수 |
|---|---|---:|---|
| poi | `51921-Word-Crash067.doc` | 43 | 구 경로의 비활성/오해독 텍스트 43 |
| poi | `53446.doc` | 309 | 변경 추적 삭제 309 |
| poi | `57603-seven_columns.doc` | 2 | 구 경로의 비활성/오해독 텍스트 2 |
| poi | `Bug47731.doc` | 77 | 구 경로의 비활성/오해독 텍스트 77 |
| poi | `Bug50936_3.doc` | 3 | 필드 명령·표시 복원 3 |
| poi | `Bug52032_3.doc` | 1006 | 변경 추적 삭제 1005; 필드 명령·표시 복원 1 |
| poi | `Bug52583.doc` | 1 | 필드 명령·표시 복원 1 |
| poi | `Bug53380_2.doc` | 4 | 필드 명령·표시 복원 4 |
| poi | `Bug53380_4.doc` | 4 | 필드 명령·표시 복원 4 |
| poi | `Bug61268.doc` | 2000 | 변경 추적 삭제 1997; 필드 명령·표시 복원 3 |
| poi | `MarkAuthorsTable.doc` | 19 | 변경 추적 삭제 19 |
| poi | `au.edu.utas.www___data_assets_word_doc_0003_154335_International-Travel-Approval-Request-Form.doc` | 13 | 필드 명령·표시 복원 13 |
| poi | `clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc` | 462 | 필드 명령·표시 복원 220; 제어문자 처리에 따른 단어 결합 242 |
| poi | `clusterfuzz-testcase-minimized-POIHWPFFuzzer-4947285593948160.doc` | 44 | 구 경로의 비활성/오해독 텍스트 44 |
| poi | `clusterfuzz-testcase-minimized-POIHWPFFuzzer-4951943183990784.doc` | 13 | 필드 명령·표시 복원 13 |
| poi | `clusterfuzz-testcase-minimized-POIHWPFFuzzer-5050208641482752.doc` | 43 | 구 경로의 비활성/오해독 텍스트 43 |
| poi | `clusterfuzz-testcase-minimized-POIHWPFFuzzer-5195207308541952.doc` | 52 | 필드 명령·표시 복원 1; 제어문자 처리에 따른 단어 결합 51 |
| poi | `clusterfuzz-testcase-minimized-POIHWPFFuzzer-5440721166139392.doc` | 17 | 스토리 경계 분리 1; 제어문자 처리에 따른 단어 결합 16 |
| poi | `clusterfuzz-testcase-minimized-POIHWPFFuzzer-6610789829836800.doc` | 36 | 필드 명령·표시 복원 36 |
| poi | `empty.doc` | 28 | 구 경로의 비활성/오해독 텍스트 28 |
| poi | `o_kurs.doc` | 55253 | 구 경로의 비활성/오해독 텍스트 55249; 필드 명령·표시 복원 4 |
| poi | `ob_is.doc` | 448 | 필드 명령·표시 복원 4; 선택 하이픈 제거 444 |
| poi | `parentinvguid.doc` | 4 | 필드 명령·표시 복원 4 |
| poi | `rasp.doc` | 10 | 구 경로의 비활성/오해독 텍스트 10 |
| poi | `test.doc` | 5 | 필드 명령·표시 복원 5 |
| poi | `vector_image.doc` | 44 | 구 경로의 비활성/오해독 텍스트 44 |
| lo/ww8export | `bnc821208.doc` | 2 | 구 경로의 비활성/오해독 텍스트 2 |
| lo/ww8export | `fdo68967.doc` | 1 | 필드 명령·표시 복원 1 |
| lo/ww8export | `i120158.doc` | 1 | 필드 명령·표시 복원 1 |
| lo/ww8export | `n757118.doc` | 1 | 필드 명령·표시 복원 1 |
| lo/ww8export | `n757905.doc` | 4 | 구 경로의 비활성/오해독 텍스트 4 |
| lo/ww8export | `page-border.doc` | 42 | 구 경로의 비활성/오해독 텍스트 42 |
| lo/ww8export | `tdf104239_numbering.doc` | 1 | 필드 명령·표시 복원 1 |
| lo/ww8export | `tdf106291.doc` | 58 | 구 경로의 비활성/오해독 텍스트 58 |
| lo/ww8export | `tdf106541_cancelOutline.doc` | 1 | 필드 명령·표시 복원 1 |
| lo/ww8export | `tdf106541_inheritOutlineNumbering.doc` | 1 | 필드 명령·표시 복원 1 |
| lo/ww8export | `tdf108072.doc` | 2 | 구 경로의 비활성/오해독 텍스트 2 |
| lo/ww8export | `tdf114308.doc` | 362 | 구 경로의 비활성/오해독 텍스트 362 |
| lo/ww8export | `tdf115896_layoutInCell.doc` | 4 | 구 경로의 비활성/오해독 텍스트 4 |
| lo/ww8export | `tdf122429_header.doc` | 4 | 필드 명령·표시 복원 4 |
| lo/ww8export | `tdf139495_tinyHeader.doc` | 1 | 필드 명령·표시 복원 1 |
| lo/ww8export | `tdf142760.doc` | 1 | 필드 명령·표시 복원 1 |
| lo/ww8export | `tdf151548_formFieldMacros.doc` | 3 | 필드 명령·표시 복원 3 |
| lo/ww8export | `tdf36711_inlineFrames.doc` | 19 | 필드 명령·표시 복원 19 |
| lo/ww8export | `tdf49102_mergedCellNumbering.doc` | 257 | 구 경로의 비활성/오해독 텍스트 257 |
| lo/ww8export | `tdf79553_lineNumbers.doc` | 1 | 필드 명령·표시 복원 1 |
| lo/ww8export | `tdf80635_pageLeft.doc` | 300 | 구 경로의 비활성/오해독 텍스트 300 |
| lo/ww8export | `tdf81705_outlineLevel.doc` | 3 | 필드 명령·표시 복원 3 |
| lo/ww8export | `tdf90408.doc` | 8 | 필드 명령·표시 복원 8 |
| lo/ww8export | `tdf91687.doc` | 4 | 구 경로의 비활성/오해독 텍스트 4 |
| lo/ww8export | `tdf96277.doc` | 2 | 필드 명령·표시 복원 2 |
| lo/ww8import | `changes-in-footnote.doc` | 3 | 변경 추적 삭제 3 |
| lo/ww8import | `image-lazy-read-0size.doc` | 1 | 구 경로의 비활성/오해독 텍스트 1 |
| lo/ww8import | `tdf121734.doc` | 1 | 구 경로의 비활성/오해독 텍스트 1 |
| lo/ww8import | `tdf122425_1.doc` | 67 | 구 경로의 비활성/오해독 텍스트 67 |
| lo/ww8import | `tdf125281.doc` | 2 | 구 경로의 비활성/오해독 텍스트 2 |
| lo/ooxmlexport | `tdf121374_sectionHF2.doc` | 2 | 필드 명령·표시 복원 2 |
| lo/ooxmlexport | `tdf133643.doc` | 1 | 필드 명령·표시 복원 1 |
| lo/ooxmlexport | `tdf137295.doc` | 2 | 구 경로의 비활성/오해독 텍스트 2 |
| lo/ooxmlexport | `tdf171527_flyInFramePr.doc` | 1 | 필드 명령·표시 복원 1 |
| lo/ooxmlexport | `tdf79435_legacyInputFields.doc` | 15 | 필드 명령·표시 복원 15 |

## 성능과 기존 짝 측정

540,001 CP의 같은 합성 단일 문단에서 문자 단위 처리 1.065614초와 런 단위 처리 0.033329초를 측정했다. 출력은 동일했다. 단일 반복 참고치이며 모든 문서의 성능 보장으로 확대하지 않는다. FKP는 FC 정렬과 이진 탐색을 사용하고, Data는 실제 간접 PAPX·그림이 필요할 때 읽는다. 실제 코퍼스 353개에서 두 렌더러의 전체 JSON이 일치했다.

DOC↔DOCX 13쌍은 리뷰 후에도 평균 토큰 유사도 0.7677, format_runs 92/81/57, headers 11/11/6, footers 11/11/4로 이전 측정과 같다. 구 텍스트 경로의 평균 유사도는 0.7234였다. 이 짝 측정은 해당 지표의 비교일 뿐 실물 기능 표본 검사를 대신하지 않는다.

## 재현 명령과 변경 범위

```sh
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
/usr/bin/python3 -m scripts.probe_doc_structures POI_DOCUMENT --lo-corpus LO_ROOT --output .codex-work/doc-fix-probe.json
/usr/bin/python3 -m scripts.check_doc_word_preservation --poi POI_DOCUMENT --lo LO_ROOT --baseline-ref 785c0e00e2f718567c3357e3f28f190ff255acc7 --check-renderer-equivalence --output .codex-work/word-loss-final.json
/usr/bin/python3 -m scripts.compare_office_pairs POI_DOCUMENT --output .codex-work/doc-fix-pairs.json
```

각 코퍼스 경로는 인자다. 감사는 단어별 발생 횟수, CP 범위, CLX 해시, 필드 명령, 정규화 뒤 남아야 하는 완성 단어를 JSON에 기록한다. 미분류 단어, 새 ERR, 감사 예외 또는 렌더러 차이가 있으면 종료 코드1을 반환한다. 분석은 순서를 무시하는 단어 다중집합 검사이므로 읽기 순서는 별도 중첩·혼합 요소 표본 검사로 판단한다.

공유 모델·출력·OfficeArt·README·CHANGELOG·AGENTS·버전·의존성을 변경하지 않았다. 커밋 금지 지침에 따라 작업을 워크트리에 남겼다. 기존 미커밋 표 상한 테스트의 ValueError 기대는 해당 표만 문단으로 강등해야 하는 결함을 고정하고 있었으므로 수정했다. HEAD의 기존 테스트는 변경하지 않았다.
