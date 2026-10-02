# DOC·PPT 리뷰 반영의 공개 실물 검증

2026년 10월 3일 `legacy-docppt-fix`의 결과이다. 파일명 날짜는 배정된 기록 경로를 따른다. 리뷰 직전 기준은 `253d3c6`이고, 최초 상속 구현 전 기준은 `f7ceaa1`이다. 두 기준을 구별한다. README·CHANGELOG는 수정하지 않았다. 공개 코퍼스는 읽기 전용으로 사용했으며 다른 프로젝트의 구현 코드는 사용하지 않았다.

## 1~4차 칸별 판정 (5차 정정은 아래에 기록한다)

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| PPT 크기·위첨자 상속 | POI `WithMaster.ppt`, `SampleShow.ppt`, `customGeo.ppt` 등 같은 이름 짝이다. | 독립 PPTX XML의 마스터·레이아웃·문단·런 속성과 PPT 원시 레코드이다. | 대응 문자의 크기와 위첨자가 정답과 같아야 한다. | 최초 기준 대비 크기 8,602→10,982/12,207자, 위첨자 12,477→12,479/12,479자이다. 리뷰 직전과 최종 짝 수치는 같다. | 검증된 크기·위첨자 범위만 ✅를 제안한다. 크기 전체 일치를 주장하지 않는다. |
| PPT 굵게·기울임·밑줄 상속 | POI `slide_master.ppt` 등 원시 레코드와 공개 짝을 조사했다. | 원시 마스터 CF와 독립 PPTX XML을 구분했다. | 새로 바뀐 속성을 외부 짝으로 대조해야 한다. | 원시 레코드는 일치하지만 대응 짝에서 이 세 속성의 변경 문자는 0개이다. | 신규 상속의 외부 검증은 미검증이며 ⬜ 유지이다. 기존 530/550런 근거는 폐기한다. |
| PPT 아래첨자 상속 | 공개 PPT 6개에서 105자 변화가 있다. | 합성 음수 baseline과 원시 마스크를 확인했다. | 새로 바뀐 아래첨자를 실물 정답과 대조해야 한다. | 독립 짝의 아래첨자 값은 전후 모두 같아 신규 변화의 정확성을 입증하지 못했다. | 외부 짝 검증을 주장하지 않으며 ⬜ 유지이다. |
| PPT 합성 라벨 | LO `tdf143315-WordartWithoutBullet.ppt`, `tdf168736-2.ppt`, POI `customGeo.ppt`, `41246-2.ppt`, `bug60345_Jankovic_final_Retreat_2002.ppt`이다. | 도형에서 만든 WordArt·URL·내장 개체 라벨에는 본문 placeholder 텍스트 유형이 없다. | 본문 마스터 크기가 합성 라벨로 번지지 않아야 한다. | 기본 TextBlock 유형을 Other(type4)로 한정했다. 해당 다섯 파일의 크기가 수정됐다. | 세 라벨 유형의 실패 테스트와 실물 전후 비교를 통과했다. |
| PPT Environment Other | POI `2100a8d44da546f97ab7795c500a58bed6cb655d.ppt`, `57272_corrupted_usereditatom.ppt`이다. | Environment type4의 유형 정보를 관찰했다. 전 유형 기본값으로 승격할 명세 근거는 확보되지 않았다. | type4는 type4에만 적용해야 한다. | 두 파일의 220자에서 불필요한 크기 상속을 제거했다. | 범위를 축소했고 7유형의 회귀 테스트를 통과했다. |
| 공용 Markdown 강조 | DOCX `WordWithAttachments.docx`, PPT `tdf169705.ppt`, 공개 HWP/HWPX를 포함한다. | 같은 문서 모델을 기존 작성기의 단일 줄 강조 함수와 수정 작성기에 넣어 전체 출력을 비교했다. | 강조를 각 줄에서 닫고 다시 열되 공백과 다른 서식은 보존해야 한다. | DOCX·PPTX·HWP·HWPX 각 200개에서 강조 분리본의 예상 밖 변화가 0건이다. | 800/800 비교를 통과했다. |
| 표 셀 그림 | POI DOC `58804.doc`, `Bug46220.doc` 및 공개 HWP/HWPX이다. | 동일 Cell의 Image 모델과 기존 `_image_to_md` 출력을 정답으로 삼았다. | 기존 모델의 그림을 셀 안 Markdown에도 표시해야 한다. | 이미 문단에 참조가 있는 inline_reference는 중복 출력하지 않는다. 표 그림 변화는 강조 변화와 분리해 검증했다. | 모델과 출력의 대응을 통과했다. 새 이미지 바이트를 생성한 것은 아니다. |
| DOC 직접 WMF | LO `forcepoint92.doc`이다. | FIB→BTE→CHPX→PICF로 찾은 CP126의 WMF 원시 바이트와 모든 레코드 경계를 비교했다. | 9,372바이트 그림 1개가 유지돼야 한다. | 그림 1개와 SHA-256 `d5eab2e08b5044de3e9be5bf22ed02ebdc5c50acd0af9868b4ee18552156ddb3`가 일치한다. | 1/1 통과이다. 구형 그림 전체 칸은 복합 저장·DIB 미구현이므로 ⬜ 유지이다. |
| DOC 그림 전용·숨은 필드·성능 경계 | 그림만 있는 Word6와 Word97 mm8은 합성 바이트로 재현했다. 숨은 필드 경고 실물은 LO `ofz21385-1.doc`이다. | FIB 버전, 필드 제어 문자, 문자 복사량 계측을 사용했다. | 텍스트 품질과 독립적으로 그림을 복원하고, 명령부 자산을 만들지 않으며, Word97 OLE를 WMF로 오인하지 않아야 한다. | 그림 전용 섹션이 유지되고, Word97 그림 오인이 사라지며, 숨은 필드의 불필요한 PICF 경고가 제거됐다. | 합성 경계는 통과했다. 모든 경계에 대응하는 정상 실물 표본을 확보한 것으로 주장하지 않는다. |
| PPT 확장·DOC 체인·위쪽 캡션·XOR | 초기 작업의 공개 표본과 조사 결과를 유지한다. | 초기 검증 기록을 참조한다. | 검증하지 못한 칸을 체크하지 않아야 한다. | 확장 전체는 부분 구현이며 체인·위쪽 캡션·XOR 정상 실물은 없었다. | 모두 ⬜ 유지이다. |

## PPT 문자 기준 근거 정정

## 문자 기준의 변화

다음 수치는 공백을 포함한 전체 문단에서 각 문자의 속성을 비교한 결과이다. 런 경계의 추가·병합은 변화로 세지 않는다.

| 속성 | 원래 기준 → 리뷰 직전 | 원래 기준 → 최종 |
|---|---:|---:|
| 글꼴 크기 | 78,984자, 110파일 | 78,764자, 108파일 |
| 굵게 False → True | 17,315자 | 17,315자 |
| 굵게 True → False | 54자 | 54자 |
| 기울임 False → True | 1,015자 | 1,015자 |
| 밑줄 False → True | 44자 | 44자 |
| 위첨자 False → True | 147자 | 147자 |
| 아래첨자 False → True | 105자 | 105자 |
| 서식 속성 하나 이상 변경된 파일 | 113개 | 111개 |

리뷰 직전과 최종을 직접 비교하면 글꼴 크기만 2,469자, 7파일에서 달라졌다. 합성 라벨의 본문 상속 제거와 Environment Other 유형 상속 범위 축소에 따른 변화이다. 나머지 다섯 속성과 본문은 동일했다. 원래 기준과 최종의 크기 차이가 220자 줄어든 것은 두 방향 변경을 상쇄한 단순 합이 아니라, 각 최종 문자값을 원래 기준과 다시 대조한 결과이다.

## 독립 PPTX XML 정답

공개 같은 이름 PPT/PPTX 짝 9개 중 비공백 문자를 대응시킬 수 있는 짝은 5개였다. 슬라이드 번호와 앞뒤 공백을 제거한 문단 본문 전체가 같을 때 대응시키고, 반복 문단은 순서대로 한 번씩 사용했다. XML 정답은 `p:sp`의 기본·마스터·레이아웃·문단·런 속성을 직접 해석한다. 표 셀, 노트, 테마의 암시적 속성은 이 정답 분모에 포함하지 않는다. 암호화 PPTX 한 개는 ZIP XML을 직접 읽을 수 없었다. 이 분모는 기존 Dochan PPTX 리더를 정답으로 삼은 `530/550` 런 비교와 다르다.

| 속성 | 원래 기준 | 리뷰 직전 | 최종 |
|---|---:|---:|---:|
| 굵게 | 12,479/12,479 | 12,479/12,479 | 12,479/12,479 |
| 기울임 | 12,479/12,479 | 12,479/12,479 | 12,479/12,479 |
| 밑줄 | 12,479/12,479 | 12,479/12,479 | 12,479/12,479 |
| 글꼴 크기 | 8,602/12,207 | 10,982/12,207 | 10,982/12,207 |
| 위첨자 | 12,477/12,479 | 12,479/12,479 | 12,479/12,479 |
| 아래첨자 | 12,479/12,479 | 12,479/12,479 | 12,479/12,479 |

글꼴 크기 일치율은 70.47%에서 89.96%로 개선되었다. 굵게·기울임·밑줄은 위 짝의 전체 문단에서도 변경 문자가 0개였다. 따라서 높은 일치율은 신규 상속 변경이 옳다는 외부 정답 증거가 아니며 이 세 칸은 미검증으로 남긴다. 그 외 공개 파일의 원시 마스터 레코드와 일치한다는 증거는 외부 짝 검증과 구별해서 기록한다. 새 아래첨자 변경도 짝 정답의 일치율 상승으로 입증하지 못했다.

원 리뷰의 독립 해석기를 그대로 재실행하면 크기 `8,602 → 10,969 / 12,194`가 정확히 재현된다. 원 해석기는 문단 `a:pPr/a:defRPr` 계층을 생략했다. 이번 해석기는 이 계층을 런 직접 속성보다 낮은 우선순위에 반영했다. `customGeo.pptx`의 6번 슬라이드 `Strands` 7자와 `Topics` 6자의 문단 기본 `sz="1800"`이 추가로 확인되므로, 크기 분모와 최종 일치 문자가 각각 13자 증가했다. 나머지 속성 지표는 같았다.

## 공용 Markdown 영향도

강조 수정만 적용한 실제 작성기 분리본과 최종 작성기를 각각 기존 단일 줄 작성기 기반 기대값과 비교했다. DOCX·PPTX는 POI/LibreOffice, HWP·HWPX는 공개 hwp-public에서 선정했다. 파일 경로 정렬 순서, 5 MiB 이하, 비어 있지 않은 성공 출력 200개를 형식별로 확보했다. 오류·형식 불일치·빈 출력은 성공 수에 포함하지 않았다. 파일별 20초 제한을 두었고 목록·해시·제외 사유는 `.codex-work/markdown-review.json`에 보존했다.

| 형식 | 성공 비교 | 강조 수정 문서 | 강조 수정 줄 전/후 | 표 그림 복원 문서 | 최종 동일 문서 | 예상 밖 강조/최종 변화 | 제외 |
|---|---:|---:|---:|---:|---:|---:|---:|
| DOCX | 200 | 1 | 3/3 | 0 | 199 | 0/0 | 17 |
| PPTX | 200 | 0 | 0/0 | 0 | 200 | 0/0 | 23 |
| HWP | 200 | 7 | 75/75 | 119 | 78 | 0/0 | 6 |
| HWPX | 200 | 18 | 622/622 | 136 | 53 | 0/0 | 27 |

강조 수정만으로는 26문서·700줄이 바뀌었고 그 외 차이가 없었다. 표 그림은 별도 수정이므로 강조와 그림의 문서 수를 합산하지 않는다. 최종 출력 역시 예상값과 800/800 일치했다. 이 결과는 출력 회귀 검증이며 모든 Markdown 문법을 외부 렌더러로 확인했다는 뜻은 아니다.

## 공개 DOC·PPT 전체 비교

같은 713개(DOC 492/PPT 221)를 리뷰 직전 HEAD와 수정본으로 변환했다. 기존 문서 실패 96개(DOC 68/PPT 28)는 그대로이고 새 실패·프로브 예외·본문 변경·본문 단어 손실·그림 바이트 변경은 모두 0개이다. 39문서의 측정값이 바뀌었고 674문서는 같았다. Markdown은 DOC 19/PPT 14개, 크기는 PPT 7개에서 바뀌었으며 두 범주가 겹친다. 숨은 필드 명령부의 그림 해석을 건너뛰어 `ofz21385-1.doc`의 PICF 경고 1개가 없어졌다.

| 공개 파일 | 바뀐 항목 | 사유 |
|---|---|---|
| `lo-src/sd/qa/unit/data/ppt/novell6655408.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `lo-src/sd/qa/unit/data/ppt/tdf143315-WordartWithoutBullet.ppt` | 크기 | 합성 라벨의 본문 크기 상속을 제거했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf168736-2.ppt` | 크기 | 합성 라벨의 본문 크기 상속을 제거했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf169705.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `lo-src/sw/qa/core/data/ww6/pass/ofz21385-1.doc` | 경고 | 숨은 필드 명령부의 PICF를 읽지 않도록 했다. |
| `lo-src/sw/qa/core/data/ww8/pass/forcepoint-layout-1.doc` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `lo-src/sw/qa/core/data/ww8/pass/forcepoint50-rows-1.doc` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `lo-src/sw/qa/extras/layout/data/tdf124601b.doc` | Markdown | 표 셀 그림 참조 복원이다. |
| `lo-src/sw/qa/extras/layout/data/tdf131707_flyWrap.doc` | Markdown | 표 셀 그림 참조 복원이다. |
| `lo-src/sw/qa/extras/ww8export/data/ooo92948-1.doc` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `lo-src/sw/qa/extras/ww8export/data/tdf162541_notLayoutInCell_paraLeft.doc` | Markdown | 표 셀 그림 참조 복원이다. |
| `lo-src/sw/qa/extras/ww8export/data/tdf162542_notLayoutInCell_charLeft_wrapThrough.doc` | Markdown | 표 셀 그림 참조 복원이다. |
| `lo-src/sw/qa/extras/ww8export/data/tdf37153_considerWrapOnObjPos.doc` | Markdown | 표 셀 그림 참조 복원이다. |
| `lo-src/sw/qa/extras/ww8export/data/tdf91632_layoutInCellD.doc` | Markdown | 표 셀 그림 참조 복원이다. |
| `lo-src/sw/qa/extras/ww8import/data/tdf124601.doc` | Markdown | 표 셀 그림 참조 복원이다. |
| `poi-src/test-data/document/58804.doc` | Markdown | 표 셀 그림 참조 복원이다. |
| `poi-src/test-data/document/Bug46220.doc` | Markdown | 표 셀 그림 참조 복원이다. |
| `poi-src/test-data/document/Bug47958.doc` | Markdown | 표 셀 그림 참조 복원이다. |
| `poi-src/test-data/document/Bug61268.doc` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/document/MarkAuthorsTable.doc` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/document/ProblemExtracting.doc` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/document/ca.kwsymphony.www_education_School_Concert_Seat_Booking_Form_2011-12.doc` | Markdown | 표 셀 그림 참조 복원이다. |
| `poi-src/test-data/document/o_kurs.doc` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/document/ob_is.doc` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/slideshow/2100a8d44da546f97ab7795c500a58bed6cb655d.ppt` | 크기 | Environment Other 범위 축소이다. |
| `poi-src/test-data/slideshow/41246-2.ppt` | Markdown, 크기 | 강조 줄바꿈 경계 수정이다. 합성 라벨의 본문 크기 상속을 제거했다. |
| `poi-src/test-data/slideshow/44770.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/slideshow/53446.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/slideshow/57272_corrupted_usereditatom.ppt` | 크기 | Environment Other 범위 축소이다. |
| `poi-src/test-data/slideshow/60003.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/slideshow/62d2ecd89aeb715b07072d4f8a8734f4dbeb5c10.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/slideshow/bug58718_008495.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/slideshow/bug58718_008558.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/slideshow/bug58733_671884.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/slideshow/bug60345_Jankovic_final_Retreat_2002.ppt` | Markdown, 크기 | 강조 줄바꿈 경계 수정이다. 합성 라벨의 본문 크기 상속을 제거했다. |
| `poi-src/test-data/slideshow/bug61881.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6028723156746240.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |
| `poi-src/test-data/slideshow/customGeo.ppt` | 크기 | 합성 라벨의 본문 크기 상속을 제거했다. |
| `poi-src/test-data/slideshow/iisd_report.ppt` | Markdown | 강조 줄바꿈 경계 수정이다. |

전체 DOC·PPT 목록에도 공용 작성기 분리 검증을 추가했다. 713개 중 기존 파서 실패 96개를 제외한 617개 전체가 기대 출력과 일치했다. DOC 확장자의 실제 DOCX 1개와 빈 출력도 제외하지 않고 별도 계수했다. 결과는 `.codex-work/markdown-legacy-review.json`에 있다.

| 확장자 | 성공 비교 | 강조 수정 문서·줄 | 표 그림 복원 문서 | 최종 동일 | 예상 밖 강조/최종 변화 | 기존 파서 실패 |
|---|---:|---:|---:|---:|---:|---:|
| DOC | 424 | 8문서·49줄 | 11 | 405 | 0/0 | 68 |
| PPT | 193 | 14문서·176줄 | 0 | 179 | 0/0 | 28 |

## 자원 상한과 성능

마커 치환은 원문에서 정규식 위치를 한 번 순회하고 소비한 텍스트만 자른다. 실패 테스트는 시간에 의존하지 않고 문자열 복사량을 계측한다. 1,000마커·113,000자에서 기존 구현의 누적 복사량은 213,012,000자였고, 수정본은 입력 길이의 4배 이내 조건을 통과했다. 아래 시간은 이 기기에서 같은 입력을 3회 실행한 중앙값이며 보편적인 속도 보장은 아니다.

| 마커 수 | 입력 문자 | 기존 시간 | 수정 시간 |
|---|---:|---:|---:|
| 1,000 | 1,013,000 | 0.075068초 | 0.000783초 |
| 2,000 | 2,026,000 | 0.296631초 | 0.001551초 |
| 4,000 | 4,052,000 | 1.242795초 | 0.002505초 |

WMF는 EOF를 포함한 100,000레코드 경계에서 정상 입력을 받아들이고 100,001레코드를 거절하는 테스트로 기존 상한을 확인했다. 경계 테스트는 기존 구현부터 통과했으므로 새 결함 수정으로 세지 않는다. PPT 문단 경계도 기존 구현은 정상이었으며 PF 경계 코드 제거 변이를 실패시키는 테스트를 보강했다.

## 공유 파일 및 테스트 계약

공용 변경은 `dochan/output/markdown.py`의 강조 줄별 출력과 표 셀 Image 출력뿐이다. 공유 모델·reader·conversion·batch·cli와 새 런타임 의존성은 없다. 기존 HEAD 테스트 단언은 하나도 바꾸지 않았다. 기존 `test_doc_legacy_images.py`의 세 합성 입력에서 빈 WordDocument 대신 유효 Word6 FIB를 제공했다. 구형 경로가 버전 검증을 요구하게 되어 테스트 입력에 빠진 형식 식별 정보를 채운 것이며 기대값은 유지했다.

## 재현과 최종 검사

코퍼스 원본은 저장소로 복사하지 않는다. 원시 JSON은 `.codex-work/`에 있고 프로브는 `scripts/`에 있다. 아래 CORPUS에는 공개 코퍼스 루트를 전달한다.

```bash
/usr/bin/python3 -m scripts.compare_office_fix2 --source-root . --lists .codex-work/public-docppt.txt --output .codex-work/review-final --workers 6 --timeout 40 --baseline .codex-work/review-baseline/results.json
/usr/bin/python3 -m scripts.probe_doc_legacy_images CORPUS/poi-src CORPUS/lo-src CORPUS/tika-test-docs
/usr/bin/python3 -m scripts.probe_doc_marker_scaling --baseline-source .codex-work/review-head
/usr/bin/python3 -m scripts.probe_markdown_review CORPUS --baseline-ref 253d3c69fd9c1f2a675c47d857b9e6f382749466 --count 200 --output .codex-work/markdown-review.json
/usr/bin/python3 -m scripts.probe_markdown_review CORPUS --baseline-ref 253d3c69fd9c1f2a675c47d857b9e6f382749466 --formats doc ppt --list .codex-work/public-docppt.txt --output .codex-work/markdown-legacy-review.json
/usr/bin/python3 -m scripts.probe_ppt_review_evidence snapshot --source . --list .codex-work/public-docppt.txt --corpus-root CORPUS --output .codex-work/ppt-evidence-final.json
/usr/bin/python3 -m scripts.probe_ppt_review_evidence compare --before .codex-work/ppt-evidence-base.json --after .codex-work/ppt-evidence-final.json --corpus-root CORPUS --output .codex-work/ppt-evidence-review.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

1차 반영 당시 전체 테스트는 **3,332 passed, 24 skipped, 14 xfailed**이며 Ruff와 `git diff --check`도 통과했다. 건너뜀과 기존 예상 실패는 통과로 계산하지 않았다.

## 3차 반영: r2 강조 경계 두 건

이 절은 2026년 10월 3일 `5c149c2`에서 시작한 3차 반영 결과이다. 위 절들은 `253d3c6` 기준 1차 반영의 역사적 기록이다. 이번 제품 변경은 공용 작성기 하나로 한정했고 Opus 지적의 기존 구현은 전체 테스트로 회귀를 확인했다. README 및 이전 Supported Elements 판정은 바꾸지 않았다.

두 P2를 먼저 재현했다. 새 제품 테스트 19개 중 13개가 실패했고, 역슬래시 짝이 이미 맞는 6개는 처음부터 통과했다. 제품 수정 후 19개가 모두 통과했다. 일반 텍스트 줄 끝의 홀수 역슬래시에만 하나를 보충해 닫는 강조 기호를 이스케이프하지 못하게 했다. 짝수 개는 기존 해석을 유지한다. 대괄호·괄호 짝을 두 번의 선형 순회로 찾고, 완성된 이미지·링크 내부 줄바꿈은 강조 분할 경계에서 제외한다. 재귀나 반복적인 나머지 문자열 검색은 없다. 이 함수는 파서가 생성한 인라인 구문을 보존하는 함수이며 완전한 CommonMark 파서라고 주장하지 않는다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| 공용 강조의 역슬래시 경계 | LO `forcepoint-layout-1.doc`이다. | 실제 TextRun과 CommonMark의 역슬래시 이스케이프·강조 구분자 해석을 대조했다. | 원문 역슬래시가 닫는 강조 기호를 이스케이프하지 않아야 한다. | HEAD 대비 닫히지 않은 강조 줄이 16→13이며 이 문서의 출력 3줄만 바뀐다. | 실패 테스트와 공개 실물에서 개선을 확인했다. 새 Supported Elements 칸을 체크하는 작업은 아니다. |
| 이미지·링크 내부 줄바꿈 | DOCX 합성 ZIP의 `wp:docPr descr="first&#10;second"`와 합성 링크를 사용했다. | 실제 DOCXReader가 생성한 굵은 이미지 런 및 CommonMark HTML의 alt 속성이다. | alt는 `first\nsecond`로 남고 강조 기호가 삽입되지 않아야 한다. | 중첩·이스케이프 대괄호, 괄호 URL, 여러 줄 제목을 포함한 5개 구문과 DOCX 경로가 통과했다. | 합성 재현·해석은 통과했다. 선정한 실물에서 해당 결함 표본은 발견하지 못했으므로 이 경계의 실물 검증은 미검증이다. |

### CommonMark 계수 방법과 범위

`markdown-it-py 3.0.0`이 이미 Python 3.9 환경에 설치되어 있어 그 CommonMark 모드를 검증에만 사용했다. 새 설치·네트워크·런타임 의존성은 없다. 표준 라이브러리만으로 만든 간단한 별표 홀짝 검사는 이스케이프·코드·블록 경계·구분자 인접 조건을 실제로 해석하지 못하므로 표준 파서의 결과를 채택했다. 검사기의 16개 테스트에는 기본 렌더러 HTML 해시와 직접 대조한 7개 경계 사례가 포함된다. 참조형 링크의 환경을 누락한 검사기 결함도 2개 실패 테스트로 재현하고 수정했다.

미종결 줄은 CommonMark가 여는 구분자로 인식했으나 짝을 찾지 못해 평문으로 남긴 `*` 또는 `_`가 있는 원문 줄 수이다. 한 줄의 여러 기호는 한 번만 센다. 정상 다중 줄 문단 강조는 0이며 제목의 블록 경계는 실제로 해석한다. 코드와 이스케이프 기호는 제외하고 이미지 alt 내부는 별도 계수한다. 이미지 지표는 렌더링한 HTML의 실제 `img alt` 속성에 `**`가 남은 이미지 수이다. 원문의 평문 별표도 미종결 후보가 될 수 있으므로 이 수치 전체를 작성기 결함 수로 해석하지 않는다. 기존 미종결 잔여는 이번 두 P2 밖의 문제이다.

문서는 현재 리더로 한 번 읽고 같은 모델을 수정본, HEAD `5c149c2`, 1.7.0 `107e18d`의 작성기에 각각 넣었다. 리더의 버전 차이를 섞지 않은 공용 작성기 회귀 검사이며, 과거 버전 리더까지 실행한 종단간 비교는 아니다. 공개 POI·LO·Tika·pdf.js·hwp-public만 사용했다. 내부 문서 경로는 검색하지 않았다. 각 지정 루트의 경로 정렬 순서로 5 MiB 이하 표본에서 비어 있지 않은 정상 출력 200개를 목표로 삼았고 문서마다 20초 제한을 뒀다. 선택 경로, 입력 해시, 출력·HTML 해시, 제외 이유는 `.codex-work/markdown-commonmark-r2.json`에 있다.

| 형식 | 비어 있지 않은 성공 출력 | 제외 | 1.7.0 미종결 줄 | HEAD 미종결 줄 | 수정본 미종결 줄 | 이미지 alt의 ** 포함 수(1.7.0 / HEAD / 수정본) |
|---|---:|---:|---:|---:|---:|---|
| DOCX | 200 | 17 | 38 | 38 | 38 | 0 / 0 / 0 |
| PPTX | 200 | 23 | 11 | 11 | 11 | 0 / 0 / 0 |
| HWP | 200 | 6 | 708 | 700 | 700 | 0 / 0 / 0 |
| HWPX | 200 | 27 | 987 | 981 | 981 | 0 / 0 / 0 |
| PDF | 200 | 141 | 29 | 29 | 29 | 0 / 0 / 0 |
| DOC | 200 | 78 | 496 | 492 | 489 | 0 / 0 / 0 |
| PPT | 179 | 42 | 123 | 81 | 81 | 0 / 0 / 0 |

총 1,379개 비어 있지 않은 출력을 비교했고 두 기준 모두에 대해 미종결 줄 또는 alt 별표 수가 증가한 문서는 0개이다. HEAD 대비 출력이 바뀐 것은 위 DOC 한 개뿐이며 나머지 1,378개는 Markdown 해시가 같다. 미종결 줄 총합은 1.7.0 2,392줄 → HEAD 2,332줄 → 수정본 2,329줄이고 alt 별표 수는 세 버전 모두 0개이다. 합성 이미지 결함의 실물 발생률을 입증한 수치로 쓰지 않는다.

PPT는 보유한 공개 221개 전부를 조사했다. 파서 오류 28개와 빈 출력 14개를 제외하면 179개뿐이므로 **PPT 성공 출력 200개 조건은 충족하지 못했다.** 빈 출력까지 포함한 파싱 성공은 193개이다. 다른 6형식은 각각 성공 출력 200개를 충족했다. 프로브 종료 코드 1은 이 표본 부족을 알리는 것으로, 성공으로 덮어쓰지 않았다. 추가 공개 정상 PPT 표본 확보가 필요하다. 형식별 제외 수는 DOCX 17, PPTX 23, HWP 6, HWPX 27, PDF 141, DOC 78, PPT 42개이며 성공 수에 넣지 않았다.

```bash
/usr/bin/python3 -m scripts.probe_markdown_commonmark corpus --output .codex-work/markdown-commonmark-r2.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

3차 전체 테스트는 **3,367 passed, 24 skipped, 14 xfailed**이다. 새 테스트는 35개이며 기존 HEAD 테스트 파일·단언은 수정하지 않았다. Ruff와 `git diff --check`를 통과했다. 제품 변경은 `dochan/output/markdown.py`뿐이다. 이번 커밋 대상은 이 파일, `scripts/probe_markdown_commonmark.py`, `tests/test_markdown_r2.py`, `tests/test_markdown_commonmark_probe.py`, 이 벤치마크 문서의 총 5개이다. `.codex-work/` 결과와 원본 문서는 커밋 대상이 아니다.


## 4차 반영: Opus P2-1·P3-1·P3-2·P3-3

2026년 10월 3일 깨끗한 `1bc7aae`에서 시작했다. 해당 리비전의 리더와 작성기 전체를 기준으로 최종 리더·작성기를 종단간 비교했다. 이전 절은 각 당시 리비전의 역사적 수치이며, 이번 결과는 이 절이 최종 기록이다. README와 CHANGELOG는 수정하지 않았다. r2의 역슬래시와 여러 줄 이미지·링크 회귀도 전체 테스트에서 통과했다.

네 항목의 최초 합성 테스트는 21개 실패와 7개 통과였다. 코드 스팬은 같은 길이의 백틱을 미리 색인하여 내부 줄바꿈을 보존한다. 이스케이프된 여는 백틱, 코드 안의 역슬래시와 대괄호, 불일치 길이·미종결 백틱도 검증했다. 재귀나 반복적인 접미부 검색 없이 입력 길이에 비례하여 처리한다.

P3-1의 모든 경계 기호를 일괄 이스케이프하는 시도는 실물에서 기존 인라인 강조와 인접 런의 해석을 바꿨다. 이 회귀를 추가 합성 테스트 6개 실패로 확인하고 수정했다. 최종 정책은 `* la Formation,`처럼 기호 안쪽이 공백이라 강조 구분자가 될 수 없는 경계만 이스케이프하는 것이다. TextRun에는 파서가 생성한 Markdown과 인접 런까지 이어지는 구분자가 있으므로 `*title*`, `_label_`, `*reference`, `note*`, 기호만 있는 런은 보존한다. 이는 평문임이 보장된 캡션과 다른 조건이며, 표본 이름에 따른 예외는 없다.

파일명과 데이터가 모두 없는 Image는 가짜 `image` 목적지를 만들지 않고 제공된 설명·OCR·캡션을 보존한다. 공용 이미지 함수에서 처리하므로 표 셀과 최상위 그림 모두 같다. 파일명이나 데이터 중 하나가 있으면 기존 참조 계약을 유지한다. TextHeaderAtom이 없거나 잘린 PPT 블록은 Body(1) 대신 Other(4)를 사용하고, 정상 헤더와 명시적 CF는 그대로 적용한다.

| 칸·지적 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| P2-1 여러 줄 코드 스팬 | 공개 결함 표본은 확인하지 못했다. | 합성 TextRun과 CommonMark HTML의 code 내용을 대조했다. | `run` 뒤의 코드 `a b`에 강조 기호가 섞이지 않아야 한다. | 여러 길이 백틱·역슬래시·중첩 링크·미종결 입력 테스트가 통과했다. | 단위 검증은 통과했고 실물 결함 재현은 미검증이다. |
| P3-1 원문 별표와 강조 기호 결합 | POI `41246-2.ppt`이다. | 원래 기울임 TextRun 및 CommonMark 렌더 결과를 대조했다. | `* la Formation,` 등 원문 목록 3줄의 별표를 보존하고 기울임을 적용해야 한다. | 세 줄 모두 원문 별표 하나를 포함한 em 요소로 렌더된다. | 실물과 단위 테스트가 통과했다. |
| P3-2 빈 셀 그림 참조 | 공개 `36417406_gyeoljae.hwpx`, `36395325_gyeoljae_consulting.hwpx`, `36389301_결재문서본문_직장훈련계획_덧말.hwpx`, `36398366_결재문서본문_PC 셧다운 제외 및 초과근무 인정 요청(데이터전략과).hwpx`이다. | 네 모델 모두 filename이 비고 image_data가 0바이트인 것을 확인했다. | 자산 없는 가짜 이미지 참조가 없어야 한다. | 160개 중 4개 문서의 끊긴 참조가 4→0이며 다른 그림은 보존된다. | 4/4 실물과 단위 테스트가 통과했다. |
| P3-3 헤더 없는 PPT의 Body 상속 | 공개 PPT 221개를 비교했다. | 합성 TextBytesAtom·TextCharsAtom, 정상·잘린 헤더 및 Body/Other 마스터 바이트를 대조했다. | 헤더가 없으면 Other 서식을 적용하고 명시적 CF를 유지해야 한다. | 합성 입력은 통과했고 실물의 모델 문자 서식 변화는 0개였다. | 합성 검증은 통과했다. 영향받는 실물 표본은 미검증이다. |

### 최종 공개 표본 비교

Opus와 같은 공개 루트인 `hwp-public`, `lo-src`, `poi-src`, `pdfjs-src`, `tika-test-docs`, `generated`만 검색했다. 내부 문서는 검색하지 않았다. 5 MiB 이하 파일의 코퍼스 상대 경로를 SHA-1 오름차순으로 정렬하고 DOC 491개·PPT 221개 전부와 DOCX·PPTX·XLSX·HWP·HWPX·PDF 각각 160개를 선정했다. 보관된 Opus 스크립트의 PDF 170개 대신 이번 명시 지시인 160개를 적용하여 총 1,672개가 된다. 성공 문서를 채울 때까지 표본을 교체하는 방식이 아니다.

| 형식 | 선정·비교 | 정상·비어 있지 않은 해당 형식 | 오류 기록 문서 | 빈 출력 | 형식 불일치 | 변경 | 본문 손실 단어 | 별표 증가 묶음 | 빈 그림 참조 전→후 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DOCX | 160 | 157 | 0 | 3 | 0 | 0 | 0 | 0 | 0→0 |
| PPTX | 160 | 149 | 4 | 11 | 0 | 0 | 0 | 0 | 0→0 |
| XLSX | 160 | 149 | 11 | 8 | 1 | 0 | 0 | 0 | 0→0 |
| HWP | 160 | 156 | 2 | 4 | 0 | 3 | 0 | 0 | 0→0 |
| HWPX | 160 | 153 | 1 | 4 | 2 | 4 | 0 | 0 | 4→0 |
| PDF | 160 | 108 | 2 | 52 | 0 | 0 | 0 | 0 | 0→0 |
| DOC | 491 | 401 | 68 | 88 | 10 | 4 | 0 | 0 | 0→0 |
| PPT | 221 | 179 | 28 | 42 | 9 | 6 | 0 | 0 | 0→0 |

오류·빈 출력·형식 불일치는 겹칠 수 있으므로 더하지 않는다. 호출 예외는 양쪽 모두 0개이며, 파서 오류 기록이 늘어난 문서도 0개이다. 정상·비어 있지 않은 해당 형식은 1,452개이고, 선정 1,672개 전부가 정상이라는 주장은 하지 않는다.

**렌더 본문 손실은 0단어·0문서이고, 떠도는 `*` 묶음 증가는 0개이며, 자산 없는 그림 참조는 4→0개이다.** 출력이 바뀐 것은 17개이고 나머지 1,655개는 전체 Markdown SHA-256이 같다. 본문은 markdown-it-py 3.0.0의 CommonMark에 표·취소선을 켠 HTML에서 추출하고, 이미지 alt는 본문에서 분리했다. Opus와 같이 공백 단위 단어에서 별표와 역슬래시를 제거한 빈도 차이로 손실을 센다. 원시 HTML 블록의 본문도 포함한다. 별표 증가는 빈 줄로 나눈 변경 묶음을 정렬한 뒤 각 묶음의 실제 렌더 본문 별표 수 증가로 세며, 다른 묶음의 감소로 상쇄하지 않는다. 빈 그림 참조는 빈 목적지 또는 `image` 목적지에 대응하는 이름 없는 이미지 데이터가 없는 경우이다. 외부 URL의 접근 가능성을 검사했다는 뜻은 아니다.

동일 출력이며 이미지 여는 구문이 없는 경우는 동일성으로 회귀 0을 증명하고 불필요한 재렌더를 생략했다. 특히 POI `poc-shared-strings.xlsx`는 12,579,810,358바이트의 동일 Markdown을 생성했다. 전체 바이트 SHA-256과 이미지 여는 구문의 부재를 스트리밍으로 재검증했으며, 대용량 렌더링은 60초 제한 후 중단했다. 이 파일을 렌더 검증 성공으로 세지 않는다. 약 25.2GB의 양쪽 중간 파일을 삭제했고, 프로브는 이후 16 Mi 문자보다 큰 출력의 본문을 저장하지 않고 전체 해시·빈 출력 여부·이미지 여는 구문 유무만 기록한다. 해당 크기에서 출력이 달라지거나 이미지 구문이 있으면 비교를 실패로 처리한다. XLSX의 기존 출력 팽창 문제는 이번 소유 범위 밖이며 별도 조치가 필요하다.

### 변경 문서와 이유

| 공개 표본 경로 | 변화 이유 |
|---|---|
| `hwp-public/hwp/nts-260721 국세청, 기간제 근로자 4,000명 2차 채용, 체납 실태확인 실시. 국가재정은 튼튼하게, 일자리는 더 많이(최종).hwp` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `hwp-public/hwp/고용노동부_2018-07-11_7.11 사회적경제박람회 보도자료(관계부처합동).hwp` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `hwp-public/hwp/고용노동부_2016-10-18_10.18 3분기 남성 육아휴직 및 육아기 근로시간 단축 이용 실태(여성고용정책과).hwp` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `hwp-public/hwpx/36395325_gyeoljae_consulting.hwpx` | 파일명과 데이터가 없는 셀 그림 참조를 제거했다. |
| `hwp-public/hwpx/36389301_결재문서본문_직장훈련계획_덧말.hwpx` | 파일명과 데이터가 없는 셀 그림 참조를 제거했다. |
| `hwp-public/hwpx/36417406_gyeoljae.hwpx` | 파일명과 데이터가 없는 셀 그림 참조를 제거했다. |
| `hwp-public/hwpx/36398366_결재문서본문_PC 셧다운 제외 및 초과근무 인정 요청(데이터전략과).hwpx` | 파일명과 데이터가 없는 셀 그림 참조를 제거했다. |
| `poi-src/test-data/document/ob_is.doc` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `poi-src/test-data/document/parentinvguid.doc` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `lo-src/sw/qa/extras/ooxmlexport/data/tdf121374_sectionHF2.doc` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `poi-src/test-data/document/Bug46610_3.doc` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `poi-src/test-data/slideshow/41246-2.ppt` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `poi-src/test-data/slideshow/alterman_security.ppt` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6028723156746240.ppt` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `poi-src/test-data/slideshow/bug58718_008558.ppt` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf168786.ppt` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |
| `poi-src/test-data/slideshow/bug61881.ppt` | 공백에 붙어 강조 구분자가 될 수 없는 원문 경계 기호를 이스케이프했다. |

### 기존 칸 재검증과 최종 검사

공개 PPT 221개 모델 스냅샷을 다시 검사했다. 직전 검증본 대비 문자 서식 변화와 본문 불일치는 0개이다. 같은 이름 PPT/PPTX 9쌍 중 비공백 정답이 있는 5쌍에서 크기 10,982/12,207자, 굵게·기울임·밑줄·위첨자·아래첨자는 각각 12,479/12,479자를 유지한다. 새 상속 변화의 외부 정답 검증을 추가한 것은 아니므로 기존 미검증 칸은 그대로다. DOC 그림 프로브도 다시 실행하여 492개 중 Word6/95 33개, 정상 직접 WMF 1파일 1개를 유지했다. `forcepoint92.doc`의 9,372바이트와 SHA-256이 원시값과 1/1 일치한다. 비교 표의 DOC 491개는 5 MiB 상한을 적용한 수이다.

전체 결과는 **3,418 passed, 24 skipped, 14 xfailed**이다. 새 테스트 51개는 모두 실행됐다. 기존 HEAD 테스트 파일과 단언은 바꾸지 않았다. Ruff와 diff 공백 검사도 통과했다. 공유 제품 변경은 `dochan/output/markdown.py` 하나이며, 전용 파서 변경은 `dochan/office_binary/ppt_text.py`의 기본 텍스트 유형이다. 새 모델·새 출력 형식·런타임 의존성은 추가하지 않았다.

```bash
/usr/bin/python3 -m scripts.probe_legacy_docppt_r4 select CORPUS .codex-work/r4-samples.json
/usr/bin/python3 -m scripts.probe_legacy_docppt_r4 snapshot CORPUS BASE_SOURCE .codex-work/r4-samples.json .codex-work/r4-before
/usr/bin/python3 -m scripts.probe_legacy_docppt_r4 snapshot CORPUS . .codex-work/r4-samples.json .codex-work/r4-after-final
/usr/bin/python3 -m scripts.probe_legacy_docppt_r4 compare .codex-work/r4-before .codex-work/r4-after-final .codex-work/r4-final-comparison.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

`BASE_SOURCE`는 `1bc7aae`의 dochan 소스를 풀어 둔 경로이고 `CORPUS`는 읽기 전용 공개 코퍼스 루트 인자이다. 선택 경로·입력 해시·리비전별 출력 해시와 오류 계수는 `.codex-work/r4-samples.json`, `r4-before/records.json`, `r4-after-final/records.json`에 있다. 최종 판정은 `r4-final-comparison.json`, PPT 재검증은 `r4-ppt-pairs.json`, DOC 그림 재검증은 `r4-doc-images.json`, 실패 증거는 `r4-red.txt`와 `r4-corpus-red.txt`에 있다.


## 5차: PowerPoint 실측 회귀 재분류와 Other 상속 수정

2026년 10월 3일 `4fadf4c`를 수정 전 기준으로 삼았다. 제공된 15건을 다시 조사하니 실제 회귀는 2건이고, 13건은 기존 불일치 목록의 절단 때문에 생긴 회귀 오탐이었다. 실제 회귀 2건을 수정했다. 원래 지목된 15개 문단 모두가 PowerPoint와 일치한다고 주장하지 않는다. 기존 불일치 13건은 수정 전후 모두 남아 있으며 아래에서 별도로 반박한다.

### 비교 목록 절단의 재현과 판정 정정

제공된 `seq_oracle.py`의 `compare()`는 불일치를 최대 400건 모으지만, `main()`은 버전별 결과에 `mismatches[:40]`만 저장한다. 이 저장 목록끼리 차집합을 구하면 base의 41번째 이후 불일치가 없던 것으로 취급된다. 실제 base `11058e3`와 수정 전 `4fadf4c`를 같은 PowerPoint 저장값에 다시 대조했다. 아래 첫 세 파일의 전체 base 불일치는 각각 97·183·75건이었다. 각 파일의 굵게·기울임 전체 목록을 보존하면 해당 13건은 양쪽 모두 불일치한다.

| 표본 파일 | 최초 회귀 주장 | 전체 목록에서 확인한 실제 회귀 | 조치와 판정 |
|---|---:|---:|---|
| `23884_defense_FINAL_OOimport_edit.ppt` | 기울임 6건이었다. | 0건이다. | base와 수정 전 모두 첫 런 기울임이 False이다. 기존 불일치를 회귀로 분류한 지적을 반박한다. |
| `41246-1.ppt` | 굵게 5건이었다. | 0건이다. | base와 수정 전 모두 첫 런 굵게가 False이다. 기존 불일치를 회귀로 분류한 지적을 반박한다. |
| `42474-2.ppt` | 굵게 2건이었다. | 0건이다. | 63·64번 슬라이드 모두 양쪽 첫 런 굵게가 False이다. 기존 불일치를 회귀로 분류한 지적을 반박한다. |
| `45776.ppt` | 굵게 1건이었다. | 1건이다. | Other의 Environment 기본값을 복구하여 해결했다. 별도의 기존 크기 2건·굵게 1건도 같은 수정으로 해결됐다. |
| `bug45124.ppt` | 굵게 1건이었다. | 1건이다. | Other의 Environment 기본값을 복구하여 해결했다. |

제공된 AppleScript는 `font of pg`로 문단 범위의 속성을 읽고, 비교기는 첫 비공백 런을 사용한다. 중간 단어만 강조된 문단도 있으므로 이 13건은 문자별 PowerPoint 측정으로 다시 확인해야 한다. 이 측정 범위 차이가 모든 잔여 불일치의 확정 원인이라고 단정하지 않는다. 첫 런을 문단 전체의 강조 여부로 바꾸거나 문서별 예외를 넣어 숫자만 맞추지 않았다.

### 원시 CF와 상속 계층

[MS-PPT의 문자 서식 예제](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-ppt/d88c020e-6702-4be6-9f54-220106a971d6)는 fontStyle 필드의 존재와 속성 비트의 유효성을 구분한다. 현재 `_character_properties`, `read_master_styles`, `render_text`는 이미 속성별 마스크를 적용하고 있었다. 슬라이드·마스터·Environment 각각에서 한 속성만 덮고 다른 두 속성을 상속하는 합성 18건이 수정 전부터 통과했다. 따라서 이 조건을 다시 바꾸지 않았다.

실제 결함은 마스터 Other(type 4)를 문서 Environment Other 위에 덮는 계층 선택이었다. [StyleTextPropAtom](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-ppt/a9a5fa71-238d-491e-acc7-fa1fffd5f100)은 placeholder의 마스터 상속을 명시하고, [TextMasterStyleAtom](https://learn.microsoft.com/en-au/openspecs/office_file_formats/ms-ppt/5febad27-0c48-4f98-b655-562b986f5874)은 텍스트 유형별 기본값을 구분한다. Microsoft의 구형 바이너리 명세 78쪽 검색 색인에도 Other의 저장 위치를 Environment로 구분한 설명이 있다. 이 위치 규칙과 두 파일의 PowerPoint 실측을 근거로 MainMaster(type 1016)의 Other만 기본값 병합에서 제외했다. Environment와 로컬 CF는 기존 속성별 마스크 규칙을 그대로 따른다.

`bug45124.ppt`의 Environment Other 레코드는 스트림 452, CF 마스크는 500 위치에 있으며 `mask=0xEFFFFF`, `fontStyle=0x0003`, 크기 20pt이다. 마스터 Other 레코드는 7183, CF는 7231 위치이고 같은 마스크에 `fontStyle=0`, 크기 18pt이다. 슬라이드 CFRun은 49714 위치에서 `mask=0x430006`, `fontStyle=0x0005`, 크기 36pt이다. bold 마스크가 없으므로 Environment의 True를 상속하며, italic 마스크는 켜져 있고 값은 0이므로 False가 된다. underline은 True이다. 최종 `(bold, italic, underline, size)=(True, False, True, 36)`이 PowerPoint와 일치한다.

`45776.ppt`의 Environment Other 레코드는 690, CF는 738 위치에 있으며 `mask=0xEFFFFF`, `fontStyle=0x0001`, 크기 11pt이다. 마스터 Other 레코드 6889·42573에는 `fontStyle=0`, 크기 18pt가 있다. `$$PICTURE$$`의 CFRun은 109709 위치에서 `mask=0x00000C00`, `fontStyle=0x0C01`이다. bold 비트의 유효성은 없으므로 원시 fontStyle의 bit 0을 직접 켜는 대신 Environment의 굵게를 상속한다. 최종 굵게 True·11pt가 PowerPoint와 일치한다.

아래는 원래 15건의 첫 비공백 문자에 대응하는 CFRun이다. 위치는 `PowerPoint Document` 스트림에서 CFRun 시작 바이트를 센 값이다. 동일 payload가 여러 번 저장된 경우 가능한 위치를 함께 적으며 한 위치라고 단정하지 않는다. fontStyle 없음은 마스크 하위 16비트가 0이라 필드가 없다는 뜻이다.

| 표본 파일 | 슬라이드·문단 앞부분 | CFRun 위치 | mask | fontStyle | 판정 |
|---|---|---|---|---|---|
| `23884_defense_FINAL_OOimport_edit.ppt` | 22번, Extensively analyzed by Phel | 290352 | `0x800` | `0x800` | 기존 불일치이며 회귀 오탐이다. |
| `23884_defense_FINAL_OOimport_edit.ppt` | 24번, This is almost periodic in T | 29810 | `0x20000` | 없다. | 기존 불일치이며 회귀 오탐이다. |
| `23884_defense_FINAL_OOimport_edit.ppt` | 27번, What happens when we reduce  | 31395·32407 | `0x20000` | 없다. | 기존 불일치이며 회귀 오탐이다. |
| `23884_defense_FINAL_OOimport_edit.ppt` | 28번, What happens when we reduce  | 31395·32407 | `0x20000` | 없다. | 기존 불일치이며 회귀 오탐이다. |
| `23884_defense_FINAL_OOimport_edit.ppt` | 28번, We can increase the effectiv | 346232 | `0x20000` | 없다. | 기존 불일치이며 회귀 오탐이다. |
| `23884_defense_FINAL_OOimport_edit.ppt` | 30번, Original Source: GPS Risk As | 360070 | `0x20005` | `0x5` | 기존 불일치이며 회귀 오탐이다. |
| `41246-1.ppt` | 16번, SUN's JVM has a default impl | 11101 | `0x0` | 없다. | 기존 불일치이며 회귀 오탐이다. |
| `41246-1.ppt` | 18번, JVM_OnLoad(JavaVM *jvm, char | 40421 | `0x60000` | 없다. | 기존 불일치이며 회귀 오탐이다. |
| `41246-1.ppt` | 18번, // get jvmpi interface point | 40451 | `0x60000` | 없다. | 기존 불일치이며 회귀 오탐이다. |
| `41246-1.ppt` | 18번, if ((jvm->GetEnv((void **)&j | 40481 | `0x60000` | 없다. | 기존 불일치이며 회귀 오탐이다. |
| `41246-1.ppt` | 20번, You can setup triggers for s | 12006 | `0x0` | 없다. | 기존 불일치이며 회귀 오탐이다. |
| `42474-2.ppt` | 63번, .01 .02 .03 .04 .05 .06 p | 198324·199573 | `0x10000` | 없다. | 기존 불일치이며 회귀 오탐이다. |
| `42474-2.ppt` | 64번, .01 .02 .03 .04 .05 .06 p | 198324·199573 | `0x10000` | 없다. | 기존 불일치이며 회귀 오탐이다. |
| `45776.ppt` | 1번, $$PICTURE$$ | 109709 | `0xc00` | `0xc01` | 실제 회귀를 수정했다. |
| `bug45124.ppt` | 1번, THIS TEXT WILL BECOME NOT BO | 49714 | `0x430006` | `0x5` | 실제 회귀를 수정했다. |

### 실물 판정과 전체 지표

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| PPT Other 굵게 상속 | `45776.ppt`, `bug45124.ppt`이다. | 저장된 PowerPoint 실측 3문단과 Environment·슬라이드 CF 원시 바이트이다. | 굵게 True가 상속되어야 한다. | 실제 회귀 2건과 기존 불일치 1건, 합계 3/3문단이 일치한다. | 합성·실물 통과이며 확인한 Other 굵게 범위는 ✅ 근거로 제안한다. |
| PPT Other 크기 상속 | `45776.ppt`, `bug52297.ppt`이다. | 앞 파일의 저장된 실측 2문단과 뒤 파일의 요약에 남은 명시 정답 2문단이다. | 각각 11pt·14pt여야 한다. | 4/4문단이 일치한다. | 확인한 Other 크기 범위는 ✅ 근거로 제안한다. |
| PPT 기울임·밑줄 신규 상속 | 38개 요약 및 5개 원문 실측을 사용했다. | 수정 전후 첫 런 속성과 기존 합성 테스트이다. | 기존 일치 수가 줄지 않아야 한다. | 기울임 1,525/1,537, 밑줄 1,537/1,537을 유지한다. | 회귀 없음이다. 새로 바뀐 기울임·밑줄 실물은 0개이므로 신규 상속 전체의 검증을 주장하지 않는다. |
| 공개 PPT 본문 | 기존 선정 목록의 공개 PPT 221개이다. | 수정 전후 문단 순서·본문 및 문자별 서식 스냅숏이다. | 본문 변화와 호출 예외 증가가 0개여야 한다. | 본문 불일치 0개, 호출 예외 0개, 문서 오류 목록 변화 0개이다. | 221/221 통과이다. |

38개 전체는 5개·677문단의 원문 실측을 직접 재대조하고, 나머지 33개는 수정 전후 첫 런 속성을 비교했다. 그중 32개는 동일하며 `bug52297.ppt`의 변경 2문단은 요약에 남아 있는 PowerPoint 크기 14pt와 유일하게 대응한다. 따라서 아래 최종 수치는 38개를 PowerPoint로 다시 열어 측정한 값이 아니라, 저장 실측의 오프라인 재대조와 변경분 검증으로 갱신한 값이다. 정답을 복원할 수 없는 변경은 0건이었다.

| 속성 | base `11058e3` | 수정 전 `4fadf4c` | 5차 최종 |
|---|---:|---:|---:|
| 크기 | 1,123/1,537 | 1,527/1,537 | 1,531/1,537 |
| 굵게 | 1,486/1,537 | 1,521/1,537 | 1,524/1,537 |
| 기울임 | 1,522/1,537 | 1,525/1,537 | 1,525/1,537 |
| 밑줄 | 1,535/1,537 | 1,537/1,537 | 1,537/1,537 |
| 첨자 | 1,537/1,537 | 1,537/1,537 | 1,537/1,537 |

모든 속성이 두 기준 이상이다. 새 검사기는 불일치 전체와 정규화된 전체 문구를 저장하며, 표시용 40자 접두사 충돌은 정답으로 채택하지 않는다. 55개 불일치 중 앞 40개만 개선한 합성 사례에서 가짜 회귀가 0개임을 확인했다.

공개 221개에서는 크기 324자·4파일, 굵게 115자·3파일이 바뀌었고 기울임·밑줄·첨자는 0자이다. 본문은 전부 동일하며 Markdown은 3파일만 바뀌었다. 같은 이름 PPT/PPTX 9쌍 중 비공백 정답을 대응시킨 5쌍의 크기 10,982/12,207자와 나머지 다섯 속성 12,479/12,479자는 유지한다.

| 변경 표본 파일 | 문자별 변화 | 사유와 실측 범위 |
|---|---|---|
| `45543.ppt` | 크기 172자가 바뀌었다. | 마스터 Other의 18pt 대신 Environment의 24pt를 적용한다. 이 파일은 PowerPoint 38개 목록 밖이므로 원시 바이트 근거만 있다. |
| `45776.ppt` | 굵게 44자·크기 38자가 바뀌었다. | Environment의 굵게·11pt를 복구한다. 슬라이드 2문단은 PowerPoint 실측과 일치한다. |
| `52244.ppt` | 굵게 28자·크기 45자가 바뀌었다. | Environment의 굵게·12pt를 적용한다. 이 파일은 PowerPoint 38개 목록 밖이므로 원시 바이트 근거만 있다. |
| `bug45124.ppt` | 굵게 43자가 바뀌었다. | Environment의 굵게를 상속한다. 슬라이드 1문단은 PowerPoint 실측과 일치한다. |
| `bug52297.ppt` | 크기 69자가 바뀌었다. | Environment의 14pt를 적용한다. 슬라이드 2문단이 요약의 명시 정답과 일치한다. |

### 검증 재실행

```bash
/usr/bin/python3 -m scripts.probe_ppt_r5_oracle --corpus-root CORPUS --oracle .codex-work/powerpoint/ppt-regress-powerpoint.json --summary .codex-work/powerpoint/ppt38-summary.json --base BASE_SOURCE --before BEFORE_SOURCE --after . --output .codex-work/r5-oracle-final.json
/usr/bin/python3 -m scripts.probe_ppt_review_evidence snapshot --source BEFORE_SOURCE --list PUBLIC_LIST --corpus-root CORPUS --output .codex-work/r5-corpus-before.json
/usr/bin/python3 -m scripts.probe_ppt_review_evidence snapshot --source . --list PUBLIC_LIST --corpus-root CORPUS --output .codex-work/r5-corpus-after.json
/usr/bin/python3 -m scripts.probe_ppt_review_evidence compare --before .codex-work/r5-corpus-before.json --after .codex-work/r5-corpus-after.json --corpus-root CORPUS --output .codex-work/r5-corpus-comparison.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

`BASE_SOURCE`는 `11058e3`, `BEFORE_SOURCE`는 `4fadf4c`의 dochan 패키지 스냅숏이다. `CORPUS`와 `PUBLIC_LIST`는 각각 읽기 전용 코퍼스 루트와 기존 공개 표본 목록 인자이다. 최초 실패는 `r5-red.txt`의 3 failed·18 passed이고, 검증기 최초 실패는 `r5-oracle-red.txt`에 있다. 전체 테스트·Ruff·공백 검사의 최종 결과는 작업 보고서와 `r5-full-tests.txt`에 남긴다. 기존 HEAD 단언, README, CHANGELOG, 공유 모델·출력 파일은 변경하지 않았다.

5차 최종 전체 테스트는 **3,442 passed, 24 skipped, 14 xfailed**이다. 신규 테스트 24개가 모두 실행됐고, Ruff와 diff 공백 검사도 통과했다.
