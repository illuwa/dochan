# OOXML 리뷰 반영 실물 검증 기록

2026년 10월 2일에 두 독립 리뷰를 반영하고 공개 POI·LibreOffice·HWPX 코퍼스를 읽기 전용으로 재검증했다. 원본 문서를 복사하지 않았으며 README·CHANGELOG·의존성 파일은 수정하지 않았다. 이전 ooxml 보고서의 수치와 판정은 이 최종 기록으로 정정한다.

| 칸 | 구현 여부 | 단위 테스트 이름 | 실물 검증 결과(표본 수·일치율) | 제안 |
| --- | --- | --- | --- | --- |
| XLSX 차트 제목/데이터 | 캐시·참조·chartEx를 구현하고 손상·공유 예산을 보강했다. | `test_chart_infers_missing_cell_coordinates_without_fatal_errors`, `test_embedded_chart_resolver_reuses_sheet_across_charts` 및 기존 차트 테스트다. | POI 26파일·38파트 중 출력 32파트의 값 1,828/1,828개, 제목 16/16개, 캡션 32/32개가 일치했다. 64450.xlsx의 참조 이름·값도 16/16개 일치했다. | 검증한 연결 차트 범위에서 ✅를 제안한다. |
| DOCX 차트 제목/데이터 | 런 앵커와 반복 출력 예산을 구현했다. | `test_docx_repeated_chart_occurrences_share_output_budget`, `test_docx_group_chart_keeps_textbox_siblings_in_order`, `test_damaged_embedded_deflate_keeps_document_body`다. | POI 2파일·8표·248/248셀, 캐시 값 155/155개, 제목 6/6개가 일치했다. | ✅를 제안한다. |
| DOCX 표/그림 캡션 | 최상위 인접 캡션을 결합하고 셀 캡션은 문단으로 유지한다. | `test_docx_cell_caption_stays_original_paragraph`, `test_docx_caption_adjacency_crosses_sdt_only_without_gap`, `test_docx_sequential_captions_skip_already_captioned_target`다. | LO 1,366파일 스캔 중 18파일·활성 Caption/SEQ 30문단을 확인했다. 5파일의 명확한 최상위 인접 캡션 7/7개가 Table/Image에 올바르게 결합했다. 나머지는 아래 한계를 따른다. | 최상위 인접 표·그림 계약에 ✅를 제안한다. |
| DOCX 읽기 순서 | 앵커·텍스트박스·SDT를 처리하고 중복과 단어 결합을 수정했다. | `test_docx_textbox_boundaries_do_not_merge_words`, `test_docx_textbox_image_is_emitted_once`, `test_alignment_detects_duplicate_and_extra_output_tokens`다. | LO 84파일의 원문/출력 완전 토큰열 일치는 62/84(73.81%)다. 원문 텍스트가 있는 70파일만 보면 52/70(74.29%)다. | 기존 ✅ 제안을 철회하고 ⬜를 유지한다. |
| PPTX 표 (중첩 텍스트) | 일반 셀 문단·수식은 보존하지만 셀 안 중첩 Table은 형식 계약에 없다. | 기존 `tests/test_hwpx_reader.py:629`, `test_reads_docx_nested_table_text_inside_parent_cell` 등의 중첩 계약을 확인했다. | POI 997/997셀과 LO 293/293셀은 일반 표 증거다. 중첩 표 증거로 사용하지 않는다. | 기존 ✅ 제안을 철회하고 —를 제안한다. |
| PPTX 수식 | OMML과 수식 전용 번호 문단을 구현했다. | `test_math_only_numbered_paragraph_consumes_and_displays_marker`, `test_pptx_probe_equation_cell_compares_raw_omml`다. | LO 427개 정상 PPTX에서 tdf129372.pptx의 𝜕 1식이 script·LaTeX 1/1 일치했다. | 단순 기호 실물과 구조별 단위 테스트 근거로 ✅를 제안한다. 복잡한 실물 수식은 미검증이다. |
| PPTX 표/그림 캡션 | 일반 도형 텍스트를 유지한다. | picTx·objTx 레이아웃과 개별 Table/Image.caption의 차이를 확인했다. | POI 84개와 LO 427개 정상 PPTX에서 별도 caption 요소는 0개다. | —를 제안한다. |

## 비교 기준과 실물 표본

차트는 원시 XML의 캐시 값·계열·제목·축 캡션을 실제 문서에서 나온 표와 비교했다. 차트 전수 스캔의 손상/비 ZIP 입력 43개, XLSX의 미연결 파트 4개와 데이터 없는 파트 2개는 성공으로 세지 않았다. XLSX 123233_charts.xlsx는 시트 관계 파일의 대소문자 불일치가 남아 있다. 출력된 명시 제목은 16/16이며 미출력 Revenue를 포함한 전체 명시 제목은 17개다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| XLSX 차트 참조 | `64450.xlsx` | xl/sharedStrings.xml과 sheet1.xml의 저장된 셀 값이다. | 계열 uno부터 ocho까지 8개와 1.0부터 8.0까지 8개다. | 이름 8/8개와 값 8/8개가 일치하고 경고가 없다. | 통과했다. |
| DOCX 캡션 | `TableWithAboveCaptions.docx` | body의 Caption/SEQ 문단 다음에 w:tbl이 직접 온다. | Table 1을 표 위에 결합한다. | Table.caption_text=Table 1, side=TOP이다. | 통과했다. |
| DOCX 캡션 | `FigureAsLabelPicture.docx` | body의 drawing 문단 바로 다음에 SEQ picture 문단이 온다. | picture 1을 그림 아래에 결합한다. | Image.caption_text=picture 1, side=BOTTOM이다. | 통과했다. |
| DOCX 캡션 | `fdo78659.docx` | Table D.6 문단 바로 다음에 w:tbl이 온다. | 표 위 캡션 1개다. | TOP 1/1개가 일치했다. | 통과했다. |
| DOCX 캡션 | `tdf102466.docx` | 각 w:tbl 바로 다음의 Tabla I·II·III 문단이다. | 표 아래 캡션 3개다. | BOTTOM 3/3개가 일치했다. | 통과했다. |
| DOCX 캡션 | `tdf149649.docx` | 두 번째 캡션 Table 1 직전에 body의 w:tbl이 있다. 그림 텍스트는 같은 문단 안이다. | Table 1은 아래에 결합하고 그림 텍스트는 유지한다. | 표 BOTTOM 1/1개가 일치했고 Figure 1Figure 1 텍스트도 남는다. | 인접 표 캡션은 통과했다. 같은 문단 그림 캡션 자동 결합은 지원 범위가 아니다. |
| DOCX 캡션 | `tdf124398_groupshapeChart.docx` | 원시 그룹/텍스트박스의 Caption·SEQ 텍스트다. | Figure 2. Oscillation at the output과 Op-amp frequency response를 유지한다. | 두 텍스트가 남고 임의의 자산 캡션으로 결합하지 않는다. | 원문 보존을 확인했다. 그룹 내부 소속 추론은 미지원이다. |
| DOCX 캡션 | `tdf146984_anchorInShape.docx` | 원시 도형 안 Figure 1: Smiley, Figure 2: Chart, Figure 3: Chart다. | 세 텍스트를 앵커 흐름에 유지한다. | 세 텍스트가 모두 남는다. | 원문 보존을 확인했다. 도형 내부 캡션 자동 결합은 미지원이다. |
| DOCX 셀 캡션 | `tdf164901.docx` | w:tc 내부의 Caption 문단 2개다. | 표/그림으로 옮기지 않고 문단으로 남긴다. | 2/2개가 원래 셀 흐름에 남는다. | 통과했다. |
| DOCX 동일 문단 그림/번호 | `test_msword_hang.docx` | w:t(Drawing ), drawing, SEQ Drawing, w:t(1)의 원시 순서다. | 양쪽 문자를 보존한다. | Drawing 텍스트·그림 참조·Image·1 텍스트로 나뉜다. | 연속 부분 문자열 비교는 실패하지만 문자 손실은 아니다. 캡션 결합 성공으로 세지 않았다. |
| PPTX 수식 | `tdf129372.pptx` | ppt/slides/slide1.xml의 m:oMath/m:t 원시 문자열이다. | 𝜕 1식이다. | script와 latex가 모두 𝜕이며 오류가 없다. | 1/1개가 일치했다. |
| PPTX chartEx | `forum-mso-de-138303.pptx` | cx1 Choice 관계의 chartEx1.xml 캐시다. | Kategorie 1~6의 값 13, 2, 23, -5, 5, 3이다. | 대체 그림 대신 헤더와 데이터 6행이 모두 일치했다. | 통과했다. |
| XLSX/XLS 숨김 시트 | `TwoSheetsOneHidden.xlsx`, `TwoSheetsOneHidden.xls`, `45761.xls` | state/visibility/hidden 메타데이터와 시트 목록이다. | 숨김 상태와 모든 시트 경계를 표시하고 데이터를 보존한다. | 숨김 시트 제목 뒤에 별도 Sheet visibility 줄이 있고 Sheet2 제목도 나온다. 45761.xls의 VeryHiddenSheet는 veryHidden으로 나온다. | 통과했다. |

Caption/SEQ 전수 결과는 활성 호환 갈래만 세고 자식 문단을 부모 문단에 중복 계산하지 않았다. 18파일·30문단 중 29개는 정규화한 원문 전체 문자열이 출력에 연속해서 남았다. 나머지 Drawing 1은 이미지 앵커에서 분리되었음을 XML·모델로 직접 확인했다. 결합한 7개와 Equation·일반 캡션·셀·그룹 내부 텍스트를 구분하였으며, 30개 모두를 자산 캡션 성공으로 세지 않았다.

PPTX 수식은 1개의 단순 기호만 실물 검증했다. 분수·첨자 등 구조별 LaTeX 변환은 합성 테스트에서만 검증했다. 원시 수식 script 다중집합은 중복·누락을 잡지만 시각적 위치 정렬을 증명하지 않는다. LibreOffice export-tests-ooxml4.cxx:577은 표본의 존재 근거이며 수식 문자열 자체의 기대값 근거로 쓰지 않았다.

PPTX 표는 POI 20파일·41표·997셀 및 LO 35파일·46표·293셀의 문단·수식 타입과 텍스트를 비교했다. 원시 표마다 출력 표를 한 번만 사용하며 미지원 번호 형식도 분모에 남긴다. POI 정상 PPTX 84개 외 손상 11개, LO 정상 427개 외 CRC 오류 2개는 별도로 기록했다. 중첩 표 계약은 HWP tests/test_parser_hardening_review.py:348, HWPX tests/test_hwpx_reader.py:629, DOCX tests/test_docx_reader.py:1380을 실행해 확인했다. DrawingML a:tc/txBody 일반 셀은 셀 안 a:tbl을 담는 계약이 아니므로 —를 제안한다.

## DOCX 읽기 순서의 완전 정렬

LibreOffice sw/qa/extras/ooxmlexport/data의 DOCX 1,366개 중 1,359개를 XML로 읽었고 7개는 읽을 수 없었다. 텍스트박스·떠 있는 도형·콘텐츠 컨트롤 중 하나가 있는 465개에서, 각 종류별 파일 이름순 전체 구간에 균등하게 배치한 최대 30개를 결과를 보기 전에 선택했다. 합집합은 84개다. 텍스트박스 44개, 떠 있는 도형 59개, 콘텐츠 컨트롤 33개가 포함되며 종류는 겹칠 수 있다.

원시 w:t를 문서 순서로 연결하되 문단·탭·줄바꿈 경계만 공백으로 정규화한다. 삭제 이력과 비활성 AlternateContent 갈래는 제외한다. 출력은 본문·셀·실제로 이동한 캡션을 출력 순서로 읽고 문서 속성·머리글·각주 본문은 제외한다. 이미지의 OCR/대체 설명 자체는 원문 w:t가 아니므로 제외하지만 문단에 생성된 링크 주소·이미지 참조·주석 표지는 지우지 않는다. 정규식 `\w+|[^\w\s]` 토큰열을 difflib.SequenceMatcher(autojunk=False)로 정렬해 삽입·삭제·대체를 모두 센다. 다중집합이나 부분 순서열만으로 성공을 판단하지 않는다.

완전 일치는 62/84파일(73.81%)이다. 원문이 비어 있는 14개를 제외해도 52/70파일(74.29%)이다. 원문 7,305토큰, 출력 8,537토큰 중 순서상 일치한 토큰은 7,303개이고 삭제 2개·추가 1,234개다. 파일별 정렬 점수의 단순 평균은 87.96%다. 최대 문서 tdf81345.docx는 원문 2,427토큰(33.22%)이며 최종 판정은 토큰 수가 아닌 파일별 완전 일치를 사용한다. 생성된 참조 문구 때문에 엄격한 원문 비교에서 실패한 경우도 있으며 이를 원문 손실과 동일시하지 않는다. 두 토큰 차이는 이미지 앞뒤의 단어 경계 대체도 포함한다. 이 검사로 일반적인 읽기 순서 완전 보존을 입증하지 못했으므로 ⬜를 유지한다.

| 표본 파일 | 원문 토큰 | 출력 토큰 | 일치 토큰 | 완전 일치 | 정렬 점수 |
| --- | ---: | ---: | ---: | --- | ---: |
| `2-id.docx` | 4 | 4 | 4 | 일치했다. | 100.00% |
| `AnchorId.docx` | 4 | 4 | 4 | 일치했다. | 100.00% |
| `FDO75133.docx` | 95 | 95 | 95 | 일치했다. | 100.00% |
| `LinkedTextBoxes.docx` | 699 | 760 | 699 | 불일치했다. | 95.82% |
| `PreserveWfieldTOC.docx` | 16 | 28 | 16 | 불일치했다. | 72.73% |
| `Tdf147485.docx` | 5 | 5 | 5 | 일치했다. | 100.00% |
| `btlr-textbox.docx` | 6 | 6 | 6 | 일치했다. | 100.00% |
| `cell-sdt-redline.docx` | 1 | 1 | 1 | 일치했다. | 100.00% |
| `content-control-shape.docx` | 5 | 5 | 5 | 일치했다. | 100.00% |
| `date-control.docx` | 7 | 7 | 7 | 일치했다. | 100.00% |
| `dml-charheight-default.docx` | 10 | 10 | 10 | 일치했다. | 100.00% |
| `dml-groupshape-capitalization.docx` | 10 | 10 | 10 | 일치했다. | 100.00% |
| `dml-shape-title.docx` | 0 | 2 | 0 | 불일치했다. | 0.00% |
| `dml-textshapeB.docx` | 6 | 6 | 6 | 일치했다. | 100.00% |
| `fdo65295.docx` | 70 | 70 | 70 | 일치했다. | 100.00% |
| `fdo65718.docx` | 77 | 133 | 77 | 불일치했다. | 73.33% |
| `fdo68418.docx` | 0 | 0 | 0 | 일치했다. | 100.00% |
| `fdo73215.docx` | 58 | 58 | 58 | 일치했다. | 100.00% |
| `fdo74110.docx` | 0 | 0 | 0 | 일치했다. | 100.00% |
| `fdo77117.docx` | 1 | 1 | 1 | 일치했다. | 100.00% |
| `fdo78300.docx` | 0 | 0 | 0 | 일치했다. | 100.00% |
| `fdo78658.docx` | 0 | 0 | 0 | 일치했다. | 100.00% |
| `fdo79817.docx` | 8 | 8 | 8 | 일치했다. | 100.00% |
| `fdo79968.docx` | 0 | 13 | 0 | 불일치했다. | 0.00% |
| `fdo81381.docx` | 0 | 13 | 0 | 불일치했다. | 0.00% |
| `fdo81946.docx` | 1 | 1 | 1 | 일치했다. | 100.00% |
| `fdo83044.docx` | 1 | 1 | 1 | 일치했다. | 100.00% |
| `invalid_date_form_field.docx` | 11 | 11 | 11 | 일치했다. | 100.00% |
| `mathtype.docx` | 2 | 16 | 1 | 불일치했다. | 11.11% |
| `mce-wpg.docx` | 2 | 2 | 2 | 일치했다. | 100.00% |
| `n751117.docx` | 0 | 0 | 0 | 일치했다. | 100.00% |
| `n780853.docx` | 5 | 5 | 5 | 일치했다. | 100.00% |
| `nestedAlternateContent.docx` | 2 | 2 | 2 | 일치했다. | 100.00% |
| `preserve_Z_field_TOC.docx` | 15 | 27 | 15 | 불일치했다. | 71.43% |
| `rot180-flipv.docx` | 2 | 2 | 2 | 일치했다. | 100.00% |
| `sdt-alias.docx` | 4 | 4 | 4 | 일치했다. | 100.00% |
| `sdt-date-duplicate.docx` | 5 | 5 | 5 | 일치했다. | 100.00% |
| `sdt_after_section_break.docx` | 1 | 1 | 1 | 일치했다. | 100.00% |
| `tblppr-shape.docx` | 0 | 0 | 0 | 일치했다. | 100.00% |
| `tdf103573.docx` | 10 | 10 | 10 | 일치했다. | 100.00% |
| `tdf104354.docx` | 21 | 21 | 21 | 일치했다. | 100.00% |
| `tdf104823.docx` | 36 | 36 | 36 | 일치했다. | 100.00% |
| `tdf113183.docx` | 0 | 0 | 0 | 일치했다. | 100.00% |
| `tdf114882.docx` | 0 | 0 | 0 | 일치했다. | 100.00% |
| `tdf121659_loseColumnBrNextToShape.docx` | 96 | 96 | 96 | 일치했다. | 100.00% |
| `tdf123243.docx` | 23 | 23 | 23 | 일치했다. | 100.00% |
| `tdf124594.docx` | 79 | 79 | 79 | 일치했다. | 100.00% |
| `tdf124637_sectionMargin.docx` | 181 | 207 | 181 | 불일치했다. | 93.30% |
| `tdf126533_axialAngle.docx` | 1 | 1 | 1 | 일치했다. | 100.00% |
| `tdf131722.docx` | 37 | 37 | 37 | 일치했다. | 100.00% |
| `tdf131776_StrikeoutGroupShapeText.docx` | 8 | 8 | 8 | 일치했다. | 100.00% |
| `tdf131922_LanguageInGroupShape.docx` | 41 | 41 | 41 | 일치했다. | 100.00% |
| `tdf134784.docx` | 7 | 26 | 7 | 불일치했다. | 42.42% |
| `tdf135653.docx` | 0 | 13 | 0 | 불일치했다. | 0.00% |
| `tdf137850_compat14ZOrder.docx` | 1 | 1 | 1 | 일치했다. | 100.00% |
| `tdf137850_compat15ZOrder.docx` | 1 | 1 | 1 | 일치했다. | 100.00% |
| `tdf146984_anchorInShape.docx` | 12 | 64 | 12 | 불일치했다. | 31.58% |
| `tdf148035.docx` | 1 | 1 | 1 | 일치했다. | 100.00% |
| `tdf148671.docx` | 16 | 16 | 16 | 일치했다. | 100.00% |
| `tdf150166.docx` | 30 | 30 | 30 | 일치했다. | 100.00% |
| `tdf153613_textboxAfterPgBreak3.docx` | 8 | 8 | 8 | 일치했다. | 100.00% |
| `tdf154478.docx` | 330 | 525 | 330 | 불일치했다. | 77.19% |
| `tdf154481.docx` | 330 | 525 | 330 | 불일치했다. | 77.19% |
| `tdf158661_blockSDT.docx` | 9 | 9 | 9 | 일치했다. | 100.00% |
| `tdf159158_zOrder_maxLessOne.docx` | 0 | 0 | 0 | 일치했다. | 100.00% |
| `tdf162527_hidden_image.docx` | 195 | 209 | 195 | 불일치했다. | 96.53% |
| `tdf165359_SdtWithInline.docx` | 12 | 74 | 12 | 불일치했다. | 27.91% |
| `tdf167721_chUnits.docx` | 11 | 25 | 11 | 불일치했다. | 61.11% |
| `tdf167721_chUnits2.docx` | 11 | 25 | 11 | 불일치했다. | 61.11% |
| `tdf168988_grabbagDatePicker.docx` | 8 | 8 | 8 | 일치했다. | 100.00% |
| `tdf170602_checkbox_bookmarkEnd.docx` | 9 | 9 | 9 | 일치했다. | 100.00% |
| `tdf36117_verticalAdjustment.docx` | 398 | 398 | 398 | 일치했다. | 100.00% |
| `tdf73499.docx` | 6 | 6 | 6 | 일치했다. | 100.00% |
| `tdf81345.docx` | 2427 | 2478 | 2427 | 불일치했다. | 98.96% |
| `tdf81507.docx` | 18 | 18 | 18 | 일치했다. | 100.00% |
| `tdf90153.docx` | 8 | 8 | 8 | 일치했다. | 100.00% |
| `tdf90697_complexBreaksHeaders.docx` | 1453 | 1806 | 1452 | 불일치했다. | 89.11% |
| `tdf97371.docx` | 1 | 1 | 1 | 일치했다. | 100.00% |
| `testTOCFlag_u.docx` | 44 | 72 | 44 | 불일치했다. | 75.86% |
| `testWPGZOrder.docx` | 24 | 24 | 24 | 일치했다. | 100.00% |
| `test_msword_hang.docx` | 3 | 16 | 3 | 불일치했다. | 31.58% |
| `textbox-wpg-only.docx` | 0 | 0 | 0 | 일치했다. | 100.00% |
| `wpg-nested.docx` | 12 | 12 | 12 | 일치했다. | 100.00% |
| `wrap-tight-through.docx` | 254 | 254 | 254 | 일치했다. | 100.00% |

## 공용 Markdown과 의도된 출력 변화

HWPX는 공개 hwp-public 전체의 소문자·대문자 확장자를 포함한 1,700개다. hwpx 디렉터리 1,675개와 hwp 디렉터리 25개를 합쳤다. 같은 파싱 결과에 HEAD의 Markdown 렌더러와 최종 렌더러를 각각 적용해 출력 차이를 계산했다. 읽기 실패 예외는 0개이며 기존 문서 경고가 있는 표본도 분모에서 빼지 않았다. 이 검사는 렌더러 변경의 영향 측정이며 1,700개 파서의 의미 정확성 인증은 아니다.

별표·밑줄·물결·백틱 및 이스케이프를 상쇄하거나 끝 강조 표지를 삼킬 수 있는 역슬래시만 이스케이프한다. 꺾쇠와 대괄호는 원문 그대로 둔다. HEAD 대비 HWPX 6/1,700파일의 26줄이 달라졌다. 변경 줄은 difflib의 각 비일치 구간에서 이전/이후 줄 수 중 큰 값을 더한 수다. Opus가 이전 패치에서 측정한 46파일·154줄 수치는 최종 수치가 아니다.

XLS 417개에서는 9파일·38줄이 달라졌고 예외 실패는 0개다. XLSX·XLS가 내는 Provenance.hidden 및 visibility를 같은 계약으로 사용한다. 예를 들어 `## Country Master (2)` 다음의 별도 문단 `*Sheet visibility: hidden*`은 실제 시트 이름과 상태를 구별한다. 숨김 시트가 하나라도 있으면 기본 이름의 일반 시트에도 제목을 내므로 두 시트의 내용이 같은 숨김 섹션으로 합쳐지지 않는다. 숨김 시트 데이터는 계속 출력한다.

DOCX의 셀 안 표는 HWPX와 같은 Table 객체로 유지한다. Cell.text의 기본 중첩 열 구분자는 탭이고 행 구분자는 줄바꿈이다. Markdown의 중첩 열은 ` / `, 행은 ` ; `이며 셀의 문단 사이는 공백으로 접는다. 이전 DOCX의 단순 문단 평탄화보다 구조가 보존되면서 구분자가 바뀌는 의도된 출력 변화다. 셀 캡션은 Table/Image.caption으로 옮기지 않으므로 원래 셀 문단과 Markdown·평문에 남는다.

form_footnotes.docx의 이미지는 HEAD에서 셀 안 참조와 본문 끝 참조가 각각 하나였다. 최종 결과는 같은 이미지 객체 1개를 원래 셀 안에 두고 셀 참조 1개를 남긴다. 본문 끝 별도 이미지 블록을 없앤 것은 앵커를 벗어난 중복 출력을 제거한 변화다. 반복 이미지 OCR은 기존 SHA-256+언어 키의 256항목 LRU를 사용하고 관련 기존 테스트 5개가 통과했으므로 새 캐시를 추가하지 않았다.

## 한계와 재현

chartEx clusteredColumn·paretoLine 및 txData 셀 연결 제목은 단위 테스트를 통과했지만 대응 실물은 찾지 못했다. 거품 크기, 자동 제목, 산포 X/Y 축 의미 및 막대+산포 혼합의 추가 표시 계약도 실물 미검증이다. 57181.xlsm chart1.xml 범주에는 formatCode=h:mm과 42213.291666666664 등의 직렬값이 있다. 같은 원시 XML을 HEAD와 최종 _chart_series_table에 넣은 31행은 같으므로 날짜 표시 미적용은 기존 변환 동작이다. 다만 HEAD의 전체 리더는 해당 차트시트를 출력하지 않았으므로 전체 문서 출력이 같다고 주장하지 않는다. 숫자 서식 표시 변환은 남은 일이다.

DOCX·PPTX의 캐시 없는 내장 통합문서와 손상 DEFLATE 입력은 바이트를 조립한 합성 테스트로 검증했다. 이를 Office 실물 파일의 캐시 없는 내장 통합문서 검증으로 세지 않았다. 범용 읽기 순서, 그룹 내부 캡션의 소속 추론, 복잡한 실물 OMML도 남아 있다.

```sh
/usr/bin/python3 -m scripts.probe_ooxml_charts <POI-test-data> --output .codex-work/chart-fix-probe.json
/usr/bin/python3 -m scripts.verify_ooxml_docx <POI-test-data/document>
/usr/bin/python3 -m scripts.verify_ooxml_docx <LO-sw/qa/extras/ooxmlexport/data>
/usr/bin/python3 -m scripts.probe_ooxml_pptx <POI-test-data/slideshow>
/usr/bin/python3 -m scripts.probe_ooxml_pptx <LO-sd/qa/unit/data> --recursive
/usr/bin/python3 -m scripts.probe_ooxml_markdown <hwp-public> --spreadsheet-corpus <POI-test-data/spreadsheet> --output .codex-work/markdown-fix-probe.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

최종 전체 테스트는 1,922 passed, 24 skipped, 14 xfailed였고 ruff와 git diff --check가 통과했다. HEAD의 기존 테스트 단언은 바꾸지 않았다. 앞선 미커밋 테스트 중 셀 캡션 소실·과도한 기호 이스케이프·이름 뒤 숨김 상태 혼합을 고정하던 기대값만 사용자 결정에 맞게 정정했다. 커밋하지 않았으며 묶음 제안은 .codex-work/report.md에 있다.
