# DOC·PPT 문서 속성 리뷰 반영 실물 검증

이 기록은 공개 Apache POI·LibreOffice 코퍼스에서 `99dcf19`와 리뷰 반영 후 출력을 비교한 결과다. 원본 문서를 저장소에 복사하지 않았으며, 문서별 Markdown·JSON은 SHA-256과 오류 요약만 보관했다. 속성값은 원본 OLE 바이트 및 OOXML 짝 출력과 대조했고, 요소 순서는 두 리더가 만든 모델의 인덱스로 대조했다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| DOC 제목·작성자 | `corpus/poi-src/test-data/document/SampleDoc.doc` | `SampleDoc.docx`의 속성 출력과 POI `TestProblems.java:195`의 작성자 기대값 | 제목 `Test Document`, 작성자 `Nick Burch`가 본문 앞에 나온다. | 두 값과 요소 위치가 짝과 일치했다. | 일치 |
| DOC 제목·작성자 | `corpus/poi-src/test-data/document/ThreeColHead.doc` | `ThreeColHead.docx`의 머리글·속성 요소 순서 | 머리글 다음에 작성자, 다음에 본문이 나온다. | DOC·DOCX 모두 머리글 인덱스 0, 작성자 인덱스 1이었다. | 순서 일치 |
| DOC 제목·작성자 | `corpus/poi-src/test-data/document/DiffFirstPageHeadFoot.doc` | 같은 줄기의 DOCX 요소 순서 | 두 머리글 다음에 작성자가 나온다. | DOC·DOCX 모두 머리글 인덱스 0·1, 작성자 인덱스 2였다. | 순서 일치 |
| DOC 제목·작성자 | `corpus/poi-src/test-data/document/documentProperties.doc` | 원본 OLE 속성 바이트와 같은 줄기의 DOCX 출력 | 원본 DOC의 제목·작성자를 출력한다. | 원본의 `This is document title`·`Sergey Vladimirov`를 출력했다. 변환본의 저장값은 서로 다르다. | 원본과 일치 |
| PPT 제목·작성자 | `corpus/poi-src/test-data/slideshow/basic_test_ppt_file.ppt` | POI `TestPOIDocumentScratchpad.java:59`의 작성자 기대값 | `Author: Hogwarts`가 나온다. | 제목 다음에 같은 작성자가 나왔다. | 일치 |
| PPT 제목·작성자 | `corpus/poi-src/test-data/slideshow/SampleShow.ppt` | `SampleShow.pptx`의 속성 출력 | 제목 `SlideShow Sample`, 작성자 `Nick Burch`가 나온다. | 두 값과 요소 위치가 짝과 일치했다. | 일치 |
| PPT 제목·작성자 | `corpus/poi-src/test-data/slideshow/backgrounds.ppt` | 원본 OLE 속성 바이트와 같은 줄기의 PPTX 출력 | 원본 PPT의 제목·작성자를 출력한다. | 원본의 `PowerPoint Presentation`·`Yegor Kozlov`를 출력했다. 변환본의 저장값은 서로 다르다. | 원본과 일치 |

POI DOC 13쌍의 속성 요소 인덱스는 13/13 같았다. 머리글이 있는 7쌍도 모두 머리글 뒤에 제목·작성자를 놓았다. 수정 전에는 7쌍의 위치가 달랐고, 이 중 5쌍은 Markdown 순서도 달랐다. POI PPT 8쌍의 속성 위치는 8/8 같았다. 속성값 사전은 POI DOC 12/13, PPT 7/8, LibreOffice DOC 1/2에서 짝과 같았다. 다른 세 짝은 원본과 변환본에 저장된 값 자체가 다르므로 원본 OLE 속성값을 정답으로 삼았다. 머리글 텍스트의 다른 차이는 이 칸의 속성 위치 판정에 포함하지 않았다.

공개 DOC 490개 중 331개, PPT 220개 중 162개에 속성 문단이 추가되었다. DOC 490/490과 PPT 220/220에서 속성 문단을 제거한 본문 Markdown SHA-256은 기준 커밋과 같았다. XLS 720개에서 Markdown·JSON SHA-256과 오류 목록은 각각 720/720 같았다. DOC 3개와 PPT 12개에서는 손상 속성 스트림 경고, 알 수 없는 코드 페이지 경고 또는 OLE 복구 경고 때문에 오류 목록이 달라졌다. 0바이트 속성 스트림은 경고 없이 건너뛰며, 새 경고 자체를 문서 실패로 취급하지 않는다.

`corpus/poi-src/test-data/slideshow/cryptoapi-proc2356.ppt`는 공개 테스트에 적힌 암호로 본문을 읽을 때 오류 없이 4개 요소를 냈으나, `EncryptedSummary`의 제목·작성자는 내지 않았다. 이 스트림은 암호화된 별도 OLE 컨테이너이므로 현재 PPT 본문·그림의 복호화 함수만 호출해 처리할 수 없다. 암호화 속성의 복호화와 독립 검증은 지원 범위 밖으로 기록한다. 암호가 없거나 틀린 경우에는 평문 속성이 있어도 제목·작성자를 내지 않는 경로를 합성 DOC FIB·PPT 복호 실패 테스트로 검증했다.

감수에서 본문 첫 줄과 제목이 같은 공개 문서 48개를 관찰했다. `WithMaster.ppt`와 `.pptx` 양쪽 모두 같은 중복을 출력하므로 이 중복만을 legacy 속성 결함으로 판정하지 않았다.
