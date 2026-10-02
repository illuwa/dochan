# Word 97–2003 DOC 구조 해석 실물 검증

2026년 10월 2일 `illuwa/w-doc` 워크트리에서 검사했다. 리뷰 반영 후 추가 검증과 단어 손실 분류의 최신 정본은 `2026-10-02-doc-fix-real-docs.md`다. 변경 전 기준선은 `2026-10-02-legacy-office-baseline.md`와 동일한 DOC↔DOCX 13쌍을 다시 측정해 재현했다. 공개 POI DOC는 소문자 확장자 159개와 대문자 확장자 1개를 합해 160개다. 공개 원본은 읽기만 했으며 저장소에 복사하지 않았다. 내부 문서 자원은 사용하지 않았다. POI 구현 소스는 가져오거나 번역하지 않았으며 테스트 단언과 원시 스트림을 정답 근거로 사용했다.

## 구현과 출력 계약

FIB 하위 문서 CP, CLX 조각, PAPX/CHPX FKP, SPRM, STSH 기반 스타일을 해석하는 경로를 추가했다. 표의 셀·행 끝, 중첩 깊이, 행별 격자와 병합 플래그를 기존 `Table`·`Cell` 모델로 조립한다. 필드·북마크·각주·미주·주석·머리글·바닥글·텍스트박스·그림은 기존 모델과 출력 경로를 사용한다. 구조 해석이 불가능하거나 예외가 발생하면 경고를 남기고 기존 텍스트 경로로 돌아간다. 암호화 문서는 기존 거부 동작을 유지한다.

DOCX의 실제 출력 계약을 따라 하이퍼링크는 `표시문자 <URL>`, 북마크는 `[bookmark: 이름]`, 각주·미주는 `Footnote`와 참조 런, 주석은 작성자를 가진 `Comment`로 출력한다. 변경 추적은 삽입을 포함하고 삭제를 제외한 최종 텍스트다. 작성자 테이블도 읽지만 공용 모델에 새 변경 이력 필드를 만들지는 않았다. 캡션은 DOCX와 같이 필드 결과를 원래 위치의 일반 문단으로 보존하며, 근거 없이 `Image.caption` 또는 `Table.caption`에 연결하지 않는다.

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

## 안전 상한과 한계

문자 CP는 16,777,216개, 기반 레코드는 200,000개, FC 이진 탐색으로 좁힌 FKP/조각 교차 후보는 2,000,000회, 스타일·표·스토리 깊이는 32단계다. 필드 제어 위치와 일곱 스토리의 합계 필드는 100,000개, 필드 깊이는 64, FFData는 1 MiB로 제한한다. 표 셀은 100,000개로 제한하며 행 패딩 전에 검사한다. 이미지·앵커는 10,000개, 개별 이미지 32 MiB, 누적 디코딩 바이트는 128 MiB다. PAPX 간접 참조는 깊이 32와 1 MiB 및 순환 검사로 제한한다. 긴 문자 런은 CHPX 구간 단위로 처리한다.

PCD PRM 증분 속성과 모든 드문 SPRM을 완전히 해석하지 않는다. 이미지 지원은 OfficeArt PICF mm=100/102와 BStore BLIP에 한정된다. 앵커 없는 텍스트박스는 문서 끝에 남기며, 도형 좌표에 따른 시각적 배치를 재구성하지 않는다. 연결 텍스트박스 체인·모든 섹션별 페이지 배치도 완전한 렌더러 수준으로 해석하지 않는다. 수식 OLE·차트·암호화 해독은 이번 범위 밖이다.

## 재현과 테스트

```sh
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
/usr/bin/python3 -m scripts.compare_office_pairs /path/to/poi/test-data/document --output .codex-work/doc-after-pairs.json
/usr/bin/python3 -m scripts.probe_doc_structures /path/to/poi/test-data/document --baseline .codex-work/doc-before-corpus.json --output .codex-work/doc-real-probe.json
```

전체 테스트는 변경 전 1,867개, 리뷰 수정 후 1,968개가 통과했다. 양쪽 모두 24개 skip과 14개 xfail이 있었으며 HEAD의 기존 단언은 수정하지 않았다. 앞선 작업의 미커밋 표 상한 테스트 한 개는 전체 예외 대신 해당 표만 강등하도록 결함을 바로잡아 기대값을 갱신했다. HEAD 대비 새 합성 테스트 101개는 FIB·FKP·STSH·PLC·PICF·OfficeArt·표 바이트 또는 CP 레코드를 테스트 안에서 조립한다. 코퍼스는 CI에 필요하지 않다. 구현 중 빈 모듈 실패, 헤더 표 누락, 복합 병합, 빠른 저장 스타일, 자원 상한의 실패를 확인한 다음 수정했다.

공유 모델·출력·공용 OfficeArt·README·버전·릴리스 파일은 변경하지 않았다. 구현 파일 외에는 재현 스크립트와 이 보고서만 추가했다. 커밋하지 않았으며 변경을 워크트리에 남겼다.

## DOC↔DOCX 전후 측정

아래 값은 동일한 측정기로 얻은 원시 집계다. `documentProperties.doc`는 기준선에서 내용이 다른 짝으로 확인했으나 수치를 올리기 위해 이번 집계에서 제외하지 않았다. 정답 분모가 없는 각주·그림·표 지표로 지원 여부를 판정하지 않았다.

| 지표 | 변경 전 | 변경 후 |
|---|---:|---:|
| DOC 짝 수 / 새 파싱 실패 | 13 / 0 | 13 / 0 |
| 평균 토큰 유사도 | 0.7234 | 0.7677 |
| format_runs 정답·후보·일치 | 92·93·63 | 92·81·57 |
| headers 정답·후보·일치 | 11·0·0 | 11·11·6 |
| footers 정답·후보·일치 | 11·0·0 | 11·11·4 |
| tables 정답·후보·일치 | 0·7·0 | 0·3·0 |
| cells 정답·후보·일치 | 0·48·0 | 0·9·0 |
| merged_cells 정답·후보·일치 | 0·0·0 | 0·1·0 |

| 공개 짝 이름(.doc ↔ .docx) | 변경 전 유사도 | 변경 후 유사도 |
|---|---:|---:|
| `51921-Word-Crash067.doc` | 0.0000 | 0.0000 |
| `DiffFirstPageHeadFoot.doc` | 0.7152 | 0.9091 |
| `FancyFoot.doc` | 0.9474 | 0.9474 |
| `HeaderFooterUnicode.doc` | 0.8586 | 0.9843 |
| `NoHeadFoot.doc` | 0.9589 | 0.9589 |
| `PageSpecificHeadFoot.doc` | 0.7755 | 0.8027 |
| `SampleDoc.doc` | 0.9254 | 0.9254 |
| `SimpleHeadThreeColFoot.doc` | 0.8034 | 0.9231 |
| `ThreeColFoot.doc` | 0.9109 | 0.9109 |
| `ThreeColHead.doc` | 0.8515 | 0.9109 |
| `ThreeColHeadFoot.doc` | 0.8235 | 0.8739 |
| `capitalized.doc` | 0.8333 | 0.8333 |
| `documentProperties.doc` | 0.0000 | 0.0000 |

문단 스타일을 상속하지 않는 현재 DOCX 리더 때문에 실제로 굵은 Molière와 HEADING TEXT가 DOCX 모델에서는 굵지 않게 출력된다. DOC STSH 및 OOXML 원시 스타일의 굵게를 확인했으므로 서식 회수율을 맞추기 위해 이를 지우지 않았다. DOC의 탭·공백 및 표 머리글 내용도 POI 단언과 원시 바이트에 존재한다. DOCX 모델이 셀 문자를 붙이거나 헤더 표 내용을 누락한 차이는 전후 수치에 남겼다.

## 전체 160개 회귀 검사

160개에서 미처리 예외는 0개이며, 문서 수준 ERR은 변경 전후 모두 6개로 새 치명 오류는 0개다. 암호화 3개, OLE가 아닌 옛 Word 파일 1개, 손상 스트림 2개가 기존 실패 대상이다. 토큰 수는 Markdown의 공백 분리 수이므로 표 구분선·파이프·링크·서식 마커도 포함한다. 감소율만으로 원문 손실을 단정하지 않았다.

24개에서 Markdown 토큰 수가 변경 전의 65% 미만이었다. 이는 조사 대상을 찾는 참고 수치이며 지원 판정이나 파서 조건이 아니다. 리뷰 후에는 별도로 POI 160개와 LO 193개에 대해 문단 단어 다중집합을 검사했다. 미분류 손실은 0개다. 파일별 CP·CLX 분류는 `2026-10-02-doc-fix-real-docs.md`에 기록했다.

| 공개 DOC 파일 | 변경 전 토큰 | 리뷰 후 토큰 | 조사 결과 |
|---|---:|---:|---|
| `47304.doc` | 11 | 3 | 이중 공백을 표로 추측하던 파이프·구분선이 제거되었다. 본문 문구는 보존했다. |
| `51921-Word-Crash067.doc` | 17 | 0 | CLX 본문은 빈 문단이다. 기존 바이너리 잡음이 제거되었다. |
| `52420.doc` | 126 | 71 | 탭·다중 공백을 표로 추측하던 구분선이 제거되었다. |
| `53446.doc` | 4508 | 2763 | 변경 추적 삭제와 삭제 표 골격을 제외했다. 정상 본문 707자는 표 경계 회귀 수정 후 보존되었다. |
| `58804.doc` | 111 | 67 | 한 줄의 27열 추정을 실제 8행3열로 바꾸어 파이프 수가 감소했다. |
| `Bug46817.doc` | 273 | 176 | 텍스트박스 표를 본문 앵커의 셀 내부로 이동했다. 중복 말미 출력을 제거했다. |
| `Bug47731.doc` | 28 | 4 | EMBED 필드 명령과 바이너리 잡음 대신 실제 EMF 그림4개를 출력했다. |
| `Bug47958.doc` | 735 | 374 | 실제 행 격자·병합을 복원하여 추정 표의 불필요한 열 구분선이 감소했다. |
| `Bug52583.doc` | 17 | 4 | FORMDROPDOWN 명령·추정 표 대신 선택값 riri를 복원했다. |
| `Bug53380_2.doc` | 19 | 10 | MACROBUTTON 명령 대신 표시 문자열 둘과 Page2를 보존했다. |
| `Bug53380_4.doc` | 19 | 11 | MACROBUTTON 표시와 정상 머리글 북마크를 보존했다. 북마크 오경고는 제거했다. |
| `ProblemExtracting.doc` | 13112 | 7523 | 문단 단어는 전후 모두 4,345개다. 표 HTML/Markdown 표현 변화이며 단어 손실은 없다. |
| `ca.kwsymphony.www_education_School_Concert_Seat_Booking_Form_2011-12.doc` | 573 | 354 | 실제 TAP 격자와 필드 결과를 사용했다. 기존 표 구분선·필드 명령을 원문 토큰으로 세지 않았다. |
| `clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc` | 2680 | 376 | 손상 구조 경고를 유지한다. 최신 CP 기반 감사에서 삭제·필드·제어문자 변환으로 차이를 분류했고 미분류 단어는 없다. 시각적 완전성은 검증하지 않았다. |
| `clusterfuzz-testcase-minimized-POIHWPFFuzzer-4947285593948160.doc` | 18 | 0 | FIB/CLX의 실제 본문은 빈 문단이다. 이전 스트림 잡음 출력과 구분했다. |
| `clusterfuzz-testcase-minimized-POIHWPFFuzzer-5050208641482752.doc` | 17 | 0 | FIB/CLX의 실제 본문은 빈 문단이다. 이전 스트림 잡음 출력과 구분했다. |
| `clusterfuzz-testcase-minimized-POIHWPFFuzzer-5195207308541952.doc` | 1567 | 752 | 손상 구조 경고를 유지한다. 최신 CP 기반 감사에서 삭제·필드·제어문자 변환으로 차이를 분류했고 미분류 단어는 없다. 시각적 완전성은 검증하지 않았다. |
| `clusterfuzz-testcase-minimized-POIHWPFFuzzer-5440721166139392.doc` | 52 | 28 | 손상 구조 경고를 유지한다. 최신 CP 기반 감사에서 삭제·필드·제어문자 변환으로 차이를 분류했고 미분류 단어는 없다. 시각적 완전성은 검증하지 않았다. |
| `clusterfuzz-testcase-minimized-POIHWPFFuzzer-6610789829836800.doc` | 695 | 270 | 손상 구조 경고를 유지한다. 최신 CP 기반 감사에서 삭제·필드·제어문자 변환으로 차이를 분류했고 미분류 단어는 없다. 시각적 완전성은 검증하지 않았다. |
| `empty.doc` | 17 | 0 | 실제 빈 문서다. 바이너리 잡음을 출력하지 않는다. |
| `gh-issue-1126.doc` | 44 | 14 | 탭 정렬을 표로 오인하던 구분선을 제거하고 탭 자체를 보존했다. |
| `header_footer_replace.doc` | 20 | 12 | 머리글4곳·바닥글1곳·본문1곳의 _TEST_를 모두 보존했다. 표 출력 방식 차이다. |
| `o_kurs.doc` | 105047 | 663 | 휴리스틱 후보의 대량 바이너리 잡음을 제거하고 FIB의 실제 CP 범위만 읽었다. |
| `vector_image.doc` | 22 | 1 | 바이너리 잡음 대신 원본과 바이트 일치하는 EMF1개를 출력했다. |

원래 보고서의 손상 퍼즈 네 문서 “텍스트 손실 여부 미확정”은 최신 감사에서 CP·CLX 기반 차이 분류로 갱신했다. 이는 공개 실물의 시각적 재현이나 손상 이전 원문을 복원했다는 뜻이 아니다.

> 2026-10-03 덧붙임: 이 기록 이후 암호화 작업에서 DOC 의 XOR·RC4·RC4 CryptoAPI 복호화가 추가됐다(`docs/benchmarks/2026-10-02-crypto-real-docs.md`). 위의 "암호화 문서는 기존 거부 동작을 유지한다" 는 이 기록 시점의 사실이다.
