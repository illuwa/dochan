# 공개 코퍼스 오류·경고 전수 수집과 원인 분류

2026년 10월 4일 공개 코퍼스의 지원 형식 9종을 파일마다 독립 Python 프로세스로 읽었다. 파일당 제한은 120초, 동시 작업자는 10개였다. 입력 루트는 `corpus/hwp-public`, `corpus/press-pairs`, `corpus/press-pairs-holdout`, `corpus/pdfjs-src/test/pdfs`, `corpus/poi-src/test-data`, `corpus/lo-src`, `corpus/tika-test-docs` 순서다. 수집 도구는 `scripts/probe_error_sweep.py`이며 원본 본문은 저장하지 않았다. `.codex-work/error-sweep-before.jsonl`에는 오류 목록과 Markdown SHA-256·문자 수만 저장했다.

13,494개 파일에서 수정 전 메시지 1,037건, 메시지 있는 파일 645개, 프로세스 예외와 시간 초과 각 0건이었다. 리뷰 수정 후 전체 메시지는 1,010건이고 메시지 있는 파일은 625개다. PDF 1,599개는 앞선 수정 후, DOCX 1,784개·PPT 221개·XLS 721개는 이번 수정 후 같은 수집기로 각각 다시 실행했다. 코드가 바뀌지 않은 형식은 수정 전 수치를 유지했다. 출력 본문은 저장하지 않고 파일별 Markdown SHA-256·문자 수·오류 목록만 비교했다.

## 형식별 집계

| 형식 | 파일 | 경고·오류가 있는 파일 전→후 | 메시지 전→후 |
| --- | ---: | ---: | ---: |
| HWP | 5523 | 11→11 | 18→18 |
| HWPX | 2253 | 14→14 | 16→16 |
| PDF | 1599 | 254→250 | 356→350 |
| DOC | 492 | 103→103 | 205→205 |
| DOCX | 1784 | 33→30 | 47→43 |
| PPT | 221 | 94→87 | 190→182 |
| PPTX | 545 | 15→15 | 15→15 |
| XLS | 721 | 96→90 | 162→153 |
| XLSX | 356 | 25→25 | 28→28 |

## 원인 판정과 수정

| 유형 | 공개 표본과 독립 근거 | 판정 | 조치·실물 결과 |
| --- | --- | --- | --- |
| PDF 미주 표지 수 한도(수정 전 8문서) | `corpus/press-pairs/156783710.pdf`의 정상 HWPX 짝에는 미주가 없다. `156783589.pdf`의 HWPX 짝은 암호화되어 정답지에서 제외했고, 정상 HWP 짝에서 미주 0개를 확인했다. `156784165.pdf`의 정상 HWPX 짝에는 각주 2개, 미주 0개다. PDF의 숫자 표 셀은 한 페이지에 1,000개 넘게 있어 원시 문자열 검사에 걸렸다. | 정상 문서에서 숫자 셀을 미주 표지로 세던 결함이다. | 기하 조건을 통과한 후보에만 1,000개 한도를 적용했다. 8문서 중 6개에서 허위 경고가 사라졌고 2개는 별도 기하 검사 한도 경고로 바뀌었다. PDF 1,599개의 Markdown 해시는 전부 동일했고 바뀐 문서는 이 8개뿐이다. |
| PDF 미주 기하 검사 한도(수정 후 2문서) | `corpus/press-pairs/156783709.pdf`의 HWPX 짝은 미주 0개이고, `156784165.pdf`의 HWPX 짝은 각주 2개·미주 0개다. 검사량 상한을 임시로 높인 별도 관찰에서는 미주 0개였으나 제품 상한은 유지했다. | 정상 숫자 표에서 경고가 남는 결함 후보다. | 200,000회 보안 상한을 낮추지 않았다. 이 두 문서는 미검증 잔여 과제로 둔다. |
| DOC·XLS OLE 헤더 오류 | 독립 `file` 식별 결과 `word2.doc`는 WinWord 2.0, `testEXCEL_4.xls`는 구형 Excel Worksheet이며 OLE2 파일이 아니다. LO `CVE-2006-2389-1.doc`는 OpenPGP Public Key로 식별됐다. | 이 세 표본은 미지원 변종 또는 확장자 불일치로, OLE2 오류가 정당하다. 같은 메시지 틀의 다른 표본 전체에는 판정을 확장하지 않았다. | 수정하지 않았다. |
| OOXML ZIP 실패 | 공개 `clusterfuzz` DOCX·XLSX·PPTX 각 1개를 표준 라이브러리 `zipfile`로 열면 모두 `BadZipFile`이 발생한다. | 확인한 세 표본은 손상 입력이다. 같은 틀의 나머지는 자동으로 확정하지 않았다. | 수정하지 않았다. |
| PDF 텍스트 없음·이미지 경고 | `bitmap-halftone-skip-grid-template1.pdf`는 독립 `pdftotext` 출력이 1문자(페이지 구분자)이고 `pdfimages -list`에는 JBIG2 이미지가 있다. | 확인한 이 표본은 이미지 기반 경고가 정당하다. 같은 틀 전체 판정은 보류한다. | 수정하지 않았다. |
| DOCX 주 문서 경로 | LO `tdf104713_undefinedStyles.docx`의 `_rels/.rels`는 `word/trial.xml`을 주 문서로 지정하고, 해당 파트에 `w:document` 본문이 있다. | `word/document.xml` 고정 경로 때문에 유효한 문서 전체가 빠지는 결함이다. | 루트 관계의 내부 대상을 안전하게 확인해 읽는다. 이 파일은 오류 1건이 사라지고 Markdown 0→253자로 복구됐다. 다른 DOCX 1,783개의 출력 해시는 같았다. |
| DOCX 번호 시작값 0 | LO `tdf123163-1.docx`, `tdf162746.docx`, `tdf57589_hashColor.docx`의 `word/numbering.xml`에 `w:start w:val="0"`이 있다. | 0은 유효한 시작 정수인데 구현이 범위 오류로 처리했다. | 합성 문서에서 첫 표지 `0.`을 검증했다. 공개 3파일의 오류가 사라졌고 출력 해시는 유지됐다. 최대 번호 상한은 유지했다. |
| PPT 스타일 확장 종료 | POI `customGeo.ppt`, `PictureTypeZero.ppt`에서 스타일 확장 데이터는 완결된 실행 단위 경계에서 끝나며 기본 문단 실행은 더 있다. | 기본 문단마다 확장이 반드시 있다고 가정한 허위 잘림 경고다. | 완결 경계에서 확장이 끝나면 중단하고, 부분 레코드는 계속 경고한다. PPT 221개 중 8개에서 경고가 사라졌고 221개 출력 해시가 모두 같았다. |
| XLS DIMENSION 끝 경계 | POI `3dFormulas.xls`는 행 0:0·열 0:1, `SimpleWithColours.xls`는 행 0:4·열 0:0을 기록한다. `chartx.xls`는 열 끝 256을 사용한다. | 마지막 다음 위치인 `rwMac`·`colMac`과 빈 축의 같은 양끝을 거부한 결함이다. | 유효한 `처음 ≤ 끝 ≤ 형식 최대치`를 허용한다. 8파일에서 9건이 사라졌고 XLS 721개의 출력 해시가 모두 같았다. |

합성 회귀 테스트는 수정 전에 실패하고 수정 뒤 통과했다. 내부 실물 PDF 80개는 앞선 수정 전후 메시지 0건·예외 0건으로 동일했다. 이번 수정에서 공유 모델·출력 코드는 바꾸지 않았다. 전체 테스트 결과는 최종 보고서에 기록한다.

## 메시지 틀 전후 빈도

다음 표는 수집된 모든 틀의 횟수다. 표본 경로는 자동 추출한 최대 세 개이며, 경로를 적었다고 해서 각 파일의 원인을 수동 검증했다는 뜻은 아니다. `손상 의심`은 표본 경로의 퍼징·실패 명칭만을 반영한 미확정 상태다. `보호 후보`도 틀의 문자열에 근거한 미확정 상태다. `미판정`과 `잔여 후보`는 후속 실물 확인이 필요하다. 틀에 속한 표본이 1개뿐이면 표본 2~3개 검증 조건을 충족할 수 없다.

### HWP

| 메시지 틀 | 전 | 후 | 상태 | 자동 추출 표본(최대 3개) |
| --- | ---: | ---: | --- | --- |
| WARN: HWP [chart:implicit_categories] series #: numbered points from # | 8 | 8 | 미판정 | `corpus/hwp-public/hwp/pr360-edward.hwp`, `corpus/hwp-public/hwp/2022년 국립국어원 업무계획.hwp` |
| ERR: 문서 파싱 실패: error('Error -# while decompressing data: invalid stored block lengths') | 2 | 2 | zlib 래핑 변형·지원 보류 | `corpus/hwp-public/hwp/hwpers-minimal_base_template.hwp`, `corpus/hwp-public/hwp/hwpers-converted_output.hwp` |
| WARN: HWP embedded CFB size limit or truncated header | 2 | 2 | 미판정 | `corpus/hwp-public/hwp/nts-260121 “나도 모르게 신고되는 소득“ 국세청 「명의도용 안심차단 서비스」로 예방하세요.hwp`, `corpus/hwp-public/hwp/bitmap.hwp` |
| ERR: 암호화/DRM 문서는 직접 파싱할 수 없음 | 1 | 1 | 보호 후보 | `corpus/hwp-public/hwp/password-12345.hwp` |
| ERR: 지원하지 않는 ZIP 문서 형식 | 1 | 1 | ZIP 중앙 디렉터리 손상 확인 | `corpus/hwp-public/hwpx/ministry-[별표 3] 국가재난관리지원기업 지정 공모 평가 기준 및 평가 방법(제7조 관련)(국가재난관리지원기업 및 국가재난관리물류기업 지정 공모 운영 지침).hwp` |
| WARN: HWP OLE BinData reference missing | 1 | 1 | 미판정 | `corpus/hwp-public/hwp/rhwp-text_footnote_tail_overpagination.hwp` |
| WARN: HWP revision partial [bounds]; revision_mode=preserve; unresolved content preserved | 1 | 1 | 미판정 | `corpus/press-pairs/156784212.hwp` |
| WARN: HWP 그림 #개가 크기 상한을 넘어 생략됨: BinData/BIN#C.bmp | 1 | 1 | 미판정 | `corpus/hwp-public/hwp/2026년 2분기 가축동향조사 결과 보도자료(최종).hwp` |
| WARN: 암호화 문서 → 전처리 필요 | 1 | 1 | 보호 후보 | `corpus/hwp-public/hwp/password-12345.hwp` |

### HWPX

| 메시지 틀 | 전 | 후 | 상태 | 자동 추출 표본(최대 3개) |
| --- | ---: | ---: | --- | --- |
| ERR: 암호화된 HWPX 문서 — 암호가 필요함 | 3 | 3 | 보호 후보 | `corpus/hwp-public/hwpx/encrypt.hwpx`, `corpus/press-pairs/156783589.hwpx`, `corpus/press-pairs/156784075.hwpx` |
| ERR: HWPX 파싱 실패: HWPX mimetype marker is missing | 2 | 2 | 두 ZIP에 marker 없음 확인·규격 해석 보류 | `corpus/hwp-public/hwpx/dummy.hwpx`, `corpus/hwp-public/hwpx/sample.hwpx` |
| WARN: HWPX revision info [duplicate-end] Contents/section#.xml: paragraph##/run##/deleteEnd##; occurrences=#; revision_mode=preserve; adjacent duplicate ignored | 2 | 2 | 미판정 | `corpus/hwp-public/hwpx/korea-mid-30-7_(즉시보도_통전지)농촌진흥청_승용마,_제주_자치경찰단_기마대에_첫_도입(축산원).hwpx`, `corpus/hwp-public/hwpx/admrul-관세조사-운영-훈령.hwpx` |
| WARN: HWPX revision info [formatting] Contents/header.xml: CharShape does not change text projection; occurrences=#; revision_mode=preserve; text projection unchanged | 2 | 2 | 미판정 | `corpus/press-pairs-holdout/156782881.hwpx`, `corpus/press-pairs-holdout/156782882.hwpx` |
| [chart:shared_categories] series #: categories taken from another series (Chart/chart#.xml, chart ##) | 2 | 2 | 미판정 | `corpus/hwp-public/hwpx/rhwp-1790387_prep_final_report.hwpx` |
| 이미지 BinData/image#.bmp 크기 초과: # bytes | 2 | 2 | 미판정 | `corpus/hwp-public/hwpx/2026년 2분기 가축동향조사 결과 보도자료(최종).hwpx`, `corpus/press-pairs/156783682.hwpx` |
| ERR: HWPX invalid table span value | 1 | 1 | 미판정 | `corpus/hwp-public/hwpx/hwpx-mcp-server-hwpx_mcp_test.hwpx` |
| ERR: 유효하지 않은 HWPX 파일 | 1 | 1 | ZIP 중앙 디렉터리 손상 확인 | `corpus/hwp-public/hwpx/nts-20250512 봄 향기 가득한 날, 성실납세에 아름다운 음악으로 보답.hwpx` |
| WARN: HWPX revision info [formatting] Contents/header.xml: ParaShape does not change text projection; occurrences=#; revision_mode=preserve; text projection unchanged | 1 | 1 | 미판정 | `corpus/hwp-public/hwpx/admrul-관세조사-운영-훈령.hwpx` |

### PDF

| 메시지 틀 | 전 | 후 | 상태 | 자동 추출 표본(최대 3개) |
| --- | ---: | ---: | --- | --- |
| WARN: #페이지: 텍스트 없음 — 스캔 이미지로 추정 (이미지 추출 불가) | 129 | 129 | 미판정 | `corpus/press-pairs-holdout/156783096.pdf`, `corpus/pdfjs-src/test/pdfs/bitmap-halftone-skip-grid-template1.pdf`, `corpus/pdfjs-src/test/pdfs/bitmap-refine.pdf` |
| WARN: #페이지: 텍스트 없음 — 이미지 기반(OCR 옵션으로 추출 가능) | 63 | 63 | 미판정 | `corpus/press-pairs/156783589.pdf`, `corpus/press-pairs/156783680.pdf`, `corpus/press-pairs/156783692.pdf` |
| WARN: 폰트 F#: ToUnicode 없는 CID 폰트 — 해당 텍스트를 추출할 수 없음 | 20 | 20 | 미판정 | `corpus/pdfjs-src/test/pdfs/cff_bluescale_small_zones.pdf`, `corpus/pdfjs-src/test/pdfs/issue_cff_unsigned_bbox.pdf`, `corpus/pdfjs-src/test/pdfs/issue7696.pdf` |
| WARN: xref 스트림 파싱 실패 — 객체 스캔으로 대체 | 16 | 16 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue15893_reduced.pdf`, `corpus/pdfjs-src/test/pdfs/xref_command_missing.pdf`, `corpus/pdfjs-src/test/pdfs/PDFBOX-3148-2-fuzzed.pdf` |
| ERR: 암호화된 문서 — PDF 암호가 없거나 틀림 또는 미지원 암호화 방식 | 12 | 12 | 보호 후보 | `corpus/pdfjs-src/test/pdfs/issue15893_reduced.pdf`, `corpus/pdfjs-src/test/pdfs/issue6010_1.pdf`, `corpus/pdfjs-src/test/pdfs/issue21579.pdf` |
| WARN: 암호화된 PDF — 빈 암호로 열 수 없음 또는 미지원 방식 | 11 | 11 | 보호 후보 | `corpus/pdfjs-src/test/pdfs/issue15893_reduced.pdf`, `corpus/pdfjs-src/test/pdfs/issue6010_1.pdf`, `corpus/pdfjs-src/test/pdfs/issue21579.pdf` |
| WARN: 폰트 C#_#: ToUnicode 없는 CID 폰트 — 해당 텍스트를 추출할 수 없음 | 11 | 11 | 미판정 | `corpus/pdfjs-src/test/pdfs/bug1650302_reduced.pdf`, `corpus/pdfjs-src/test/pdfs/issue2884_reduced.pdf`, `corpus/pdfjs-src/test/pdfs/issue13916.pdf` |
| WARN: PDF 미주 표지 수 한도 초과 — 참조 복원 생략 | 8 | 0 | 수정 | `corpus/press-pairs/156783589.pdf`, `corpus/press-pairs/156783710.pdf`, `corpus/press-pairs/156783912.pdf` |
| WARN: startxref 를 찾지 못함 — 객체 스캔으로 대체 | 8 | 8 | 미판정 | `corpus/pdfjs-src/test/pdfs/scan-bad.pdf`, `corpus/pdfjs-src/test/pdfs/issue19800.pdf`, `corpus/pdfjs-src/test/pdfs/issue15590.pdf` |
| WARN: 페이지 트리를 찾지 못함 | 7 | 7 | 미판정 | `corpus/pdfjs-src/test/pdfs/GHOSTSCRIPT-698804-1-fuzzed.pdf`, `corpus/pdfjs-src/test/pdfs/operator_list_cycle.pdf`, `corpus/pdfjs-src/test/pdfs/issue19484_1.pdf` |
| WARN: PDF 링크 목적지를 페이지로 풀지 못함 | 6 | 6 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue2462.pdf`, `corpus/pdfjs-src/test/pdfs/bug1529502.pdf`, `corpus/pdfjs-src/test/pdfs/issue10640.pdf` |
| WARN: 객체 # 파싱 실패: 사전 키는 이름이어야 함 | 5 | 5 | 두 표본의 중복 닫는 괄호 확인·나머지 미판정 | `corpus/press-pairs/156784146.pdf`, `corpus/press-pairs-holdout/156782882.pdf`, `corpus/pdfjs-src/test/pdfs/issue11549_reduced.pdf` |
| WARN: 폰트 Type#TTF#: ToUnicode 없는 CID 폰트 — 해당 텍스트를 추출할 수 없음 | 5 | 5 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue11915.pdf` |
| WARN: PDF 카탈로그(Root)를 찾지 못함 | 4 | 4 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue18986.pdf`, `corpus/pdfjs-src/test/pdfs/poppler-742-0-fuzzed.pdf`, `corpus/pdfjs-src/test/pdfs/REDHAT-1531897-0.pdf` |
| WARN: FlateDecode 실패: Error -# while decompressing data: incorrect header check | 3 | 3 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue19484_1.pdf`, `corpus/pdfjs-src/test/pdfs/issue19484_2.pdf`, `corpus/pdfjs-src/test/pdfs/REDHAT-1531897-0.pdf` |
| WARN: startxref 오프셋이 파일 범위 밖 — 객체 스캔으로 대체 | 3 | 3 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue9252.pdf`, `corpus/pdfjs-src/test/pdfs/close-path-bug.pdf`, `corpus/pdfjs-src/test/pdfs/bug1795263.pdf` |
| WARN: xref 오프셋 불일치 — 객체 스캔으로 재구성 | 3 | 3 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue20516.pdf`, `corpus/pdfjs-src/test/pdfs/poppler-395-0-fuzzed.pdf`, `corpus/pdfjs-src/test/pdfs/issue7229.pdf` |
| WARN: xref 항목 손상 — 객체 스캔으로 대체 | 3 | 3 | 미판정 | `corpus/pdfjs-src/test/pdfs/PDFBOX-4352-0.pdf`, `corpus/pdfjs-src/test/pdfs/poppler-937-0-fuzzed.pdf`, `corpus/pdfjs-src/test/pdfs/outline_goto_action.pdf` |
| WARN: 스캔 복구는 객체 스트림(/ObjStm) 안 객체를 새로 찾지 못함 — 일부 객체가 누락될 수 있음 | 3 | 3 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue17147.pdf`, `corpus/pdfjs-src/test/pdfs/Brotli-Prototype-FileA.pdf`, `corpus/pdfjs-src/test/pdfs/REDHAT-1531897-0.pdf` |
| WARN: 폰트 F#.#: ToUnicode 없는 CID 폰트 — 해당 텍스트를 추출할 수 없음 | 3 | 3 | 미판정 | `corpus/pdfjs-src/test/pdfs/PDFJS-7562-reduced.pdf`, `corpus/pdfjs-src/test/pdfs/complex_ttf_font.pdf` |
| WARN: 폰트 TT#: ToUnicode 없는 CID 폰트 — 해당 텍스트를 추출할 수 없음 | 3 | 3 | 미판정 | `corpus/pdfjs-src/test/pdfs/ThuluthFeatures.pdf` |
| WARN: ASCII#Decode 실패 | 2 | 2 | 손상 의심 | `corpus/pdfjs-src/test/pdfs/PDFBOX-3148-2-fuzzed.pdf`, `corpus/pdfjs-src/test/pdfs/poppler-90-0-fuzzed.pdf` |
| WARN: FlateDecode 실패: Error -# while decompressing data: incorrect data check | 2 | 2 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue11651.pdf`, `corpus/pdfjs-src/test/pdfs/issue13316_reduced.pdf` |
| WARN: PDF 스트림이 해제 한도를 초과하여 잘림 | 2 | 2 | 한 표본의 이미지 스트림 확인·다른 표본 미판정 | `corpus/press-pairs/156783715.pdf`, `corpus/press-pairs-holdout/156783096.pdf` |
| WARN: 폰트 F#: ToUnicode 없는 CID 폰트 — 일부 문자의 대응을 확인할 수 없음 | 2 | 2 | 미판정 | `corpus/pdfjs-src/test/pdfs/bug920426.pdf`, `corpus/pdfjs-src/test/pdfs/issue11768_reduced.pdf` |
| ERR: PDF 헤더(%PDF-)를 찾지 못함 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/bug1606566.pdf` |
| WARN: ASCIIHexDecode 실패 | 1 | 1 | 손상 의심 | `corpus/pdfjs-src/test/pdfs/poppler-90-0-fuzzed.pdf` |
| WARN: Encoding CMap 코드가 코드 공간 밖이거나 잘림 — CID # 사용 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue11768_reduced.pdf` |
| WARN: Encoding CMap에 코드→CID 대응이 없음 — CID # 사용 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/bug920426.pdf` |
| WARN: FlateDecode 실패: Error -# while decompressing data: invalid bit length repeat | 1 | 1 | 손상 의심 | `corpus/pdfjs-src/test/pdfs/poppler-90-0-fuzzed.pdf` |
| WARN: FlateDecode 실패: Error -# while decompressing data: invalid code -- missing end-of-block | 1 | 1 | 손상 의심 | `corpus/pdfjs-src/test/pdfs/poppler-90-0-fuzzed.pdf` |
| WARN: FlateDecode 실패: Error -# while decompressing data: invalid distance too far back | 1 | 1 | 손상 의심 | `corpus/pdfjs-src/test/pdfs/poppler-90-0-fuzzed.pdf` |
| WARN: PDF Form 순환 참조 — 해당 Form 건너뜀 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue19800.pdf` |
| WARN: PDF Form 확장 한도 — 해당 Form 건너뜀 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/bug1721218_reduced.pdf` |
| WARN: PDF 선분 수 한도(#) 초과 — 일부 괘선 생략 | 1 | 1 | 미판정 | `corpus/press-pairs/156784075.pdf` |
| WARN: PDF 주석 개수 한도 초과 — 일부만 추출 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/bug1978317.pdf` |
| WARN: startxref 오프셋 손상 — 객체 스캔으로 대체 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue6069.pdf` |
| WARN: trailer Root 가 카탈로그가 아님 — 스캔한 카탈로그 사용 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue9418.pdf` |
| WARN: 객체 # 파싱 실패: 오프셋 #: 간접 객체 헤더가 아님 — 객체 스캔으로 재구성 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue9418.pdf` |
| WARN: 객체 # 파싱 실패: 잘못된 숫자 토큰: b'E' | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/PDFBOX-4352-0.pdf` |
| WARN: 객체 # 파싱 실패: 잘못된 숫자 토큰: b'R' | 1 | 1 | 손상 의심 | `corpus/pdfjs-src/test/pdfs/poppler-742-0-fuzzed.pdf` |
| WARN: 암호화된 PDF — Encrypt 사전을 찾지 못함 | 1 | 1 | 보호 후보 | `corpus/pdfjs-src/test/pdfs/PDFBOX-4352-0.pdf` |
| WARN: 지원하지 않는 PDF 필터: BrotliDecode | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/Brotli-Prototype-FileA.pdf` |
| WARN: 페이지를 찾지 못함 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/poppler-85140-0.pdf` |
| WARN: 폰트 FF#: ToUnicode 없는 CID 폰트 — 해당 텍스트를 추출할 수 없음 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue20453.pdf` |
| WARN: 폰트 OCHAIconsBounded: ToUnicode 없는 CID 폰트 — 해당 텍스트를 추출할 수 없음 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/bug1146106.pdf` |
| WARN: 폰트 tf#: ToUnicode 없는 CID 폰트 — 해당 텍스트를 추출할 수 없음 | 1 | 1 | 미판정 | `corpus/pdfjs-src/test/pdfs/issue11651.pdf` |
| WARN: PDF 미주 기하 검사 수 한도(#) 초과 — 미주 복원 생략 | 0 | 2 | 잔여 후보 | `corpus/press-pairs/156784165.pdf`, `corpus/press-pairs/156783709.pdf` |

### DOC

| 메시지 틀 | 전 | 후 | 상태 | 자동 추출 표본(최대 3개) |
| --- | ---: | ---: | --- | --- |
| ERR: DOC OLE 파일 열기 실패: OLE/CFB: not an OLE# structured storage file | 40 | 40 | 미판정 | `corpus/poi-src/test-data/document/word2.doc`, `corpus/lo-src/sw/qa/core/data/ww8/fail/CVE-2006-2389-1.doc`, `corpus/lo-src/sw/qa/core/data/ww8/fail/CVE-2005-0941-1.doc` |
| WARN: DOC FKP run table is invalid | 30 | 30 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5195207308541952.doc`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-6610789829836800.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: inaccessible directory branch omitted (/) | 14 | 14 | 미판정 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5440721166139392.doc`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-4892412469968896.doc`, `corpus/lo-src/sw/qa/core/data/ww6/pass/ofz21385-1.doc` |
| WARN: DOC FKP property payload is invalid | 12 | 12 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5195207308541952.doc`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-6610789829836800.doc` |
| ERR: 문서 파싱 실패: CFBError('OLE/CFB: CFB invalid mini sector size or cutoff') | 11 | 11 | 미판정 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5832867957309440.doc`, `corpus/lo-src/sw/qa/core/data/ww6/fail/ofz45140-1.doc`, `corpus/lo-src/sw/qa/core/data/ww6/pass/ofz42330-1.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain points outside allocation table (/) | 11 | 11 | 미판정 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5195207308541952.doc`, `corpus/lo-src/sw/qa/core/data/ww6/pass/ofz21168-1.doc`, `corpus/lo-src/sw/qa/core/data/ww6/pass/crash-1.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: invalid directory entry omitted (/) | 6 | 6 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5074346559012864.doc`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5418937293340672.doc` |
| ERR: DOC stream validation failed: WordDocument size mismatch: declared=#, read=# bytes | 5 | 5 | 손상 의심 | `corpus/lo-src/sw/qa/core/data/ww6/pass/crash-7.doc`, `corpus/lo-src/sw/qa/core/data/ww6/pass/crash-1.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/hang-3.doc` |
| ERR: DOC WordDocument stream read 실패: OLE/CFB: CFB duplicate sector allocation or cyclic chain | 4 | 4 | 손상 의심 | `corpus/lo-src/sw/qa/core/data/ww6/pass/hang-1.doc`, `corpus/lo-src/sw/qa/core/data/ww6/pass/crash-4.doc`, `corpus/lo-src/sw/qa/core/data/ww8/fail/hang-2.doc` |
| ERR: DOC 암호로 보호된 문서입니다 (FIB fEncrypted) | 4 | 4 | 보호 후보 | `corpus/poi-src/test-data/document/PasswordProtected.doc`, `corpus/poi-src/test-data/document/password_password_cryptoapi.doc`, `corpus/poi-src/test-data/document/password_tika_binaryrc4.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream read failed (WordDocument) | 4 | 4 | 손상 의심 | `corpus/lo-src/sw/qa/core/data/ww6/pass/hang-1.doc`, `corpus/lo-src/sw/qa/core/data/ww6/pass/crash-4.doc`, `corpus/lo-src/sw/qa/core/data/ww8/fail/hang-2.doc` |
| ERR: DOC stream validation failed: #Table size mismatch: declared=#, read=# bytes | 3 | 3 | 미판정 | `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz47205-1.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/hang-1.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz18554-1.doc` |
| ERR: 지원하지 않는 OLE 스트림 구조 | 3 | 3 | 미판정 | `corpus/lo-src/sw/qa/core/data/ww8/pass/hang-2.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz46457-1.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz53457-1.doc` |
| WARN: DOC fields: unterminated field; text retained | 3 | 3 | 미판정 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5195207308541952.doc`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz57592-1.doc` |
| WARN: DOC structure unavailable; text fallback | 3 | 3 | 손상 의심 | `corpus/lo-src/sw/qa/core/data/ww8/pass/crash-1.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/hang-9.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/hang-8.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain points outside allocation table (WordDocument) | 3 | 3 | 미판정 | `corpus/lo-src/sw/qa/core/data/ww6/pass/crash-7.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/hang-3.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz18414-1.doc` |
| WARN: embedded OLE preview retained: Unsupported MTEF template # | 3 | 3 | 미판정 | `corpus/poi-src/test-data/document/Bug50936_1.doc`, `corpus/lo-src/sw/qa/extras/ww8export/data/tdf79553_lineNumbers.doc` |
| WARN: DOC STSH header is invalid | 2 | 2 | 미판정 | `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz38011-1.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/crash-3.doc` |
| WARN: DOC bookmarks: non-monotonic PLC positions | 2 | 2 | 미판정 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-6610789829836800.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz57592-1.doc` |
| WARN: DOC caption styles: invalid STSH limits | 2 | 2 | 미판정 | `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz38011-1.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/crash-3.doc` |
| WARN: DOC font table: unterminated FFN name | 2 | 2 | 미판정 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz38011-1.doc` |
| WARN: DOC headers: non-monotonic PLC positions | 2 | 2 | 미판정 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc`, `corpus/poi-src/test-data/document/HeaderFooterProblematic.doc` |
| WARN: DOC table entry # is outside stream | 2 | 2 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5440721166139392.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/crash-3.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: inaccessible FAT suffix omitted (/) | 2 | 2 | 미판정 | `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz46457-1.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz53457-1.doc` |
| WARN: OfficeArt truncated record at # | 2 | 2 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5440721166139392.doc`, `corpus/lo-src/sw/qa/core/data/ww8/pass/hang-6.doc` |
| ERR: DOC #Table stream read 실패: this file is not a stream | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5418937293340672.doc` |
| WARN: DOC FKP page outside stream | 1 | 1 | 미판정 | `corpus/lo-src/sw/qa/core/data/ww8/pass/forcepoint-layout-1.doc` |
| WARN: DOC caption styles: truncated STD | 1 | 1 | 미판정 | `corpus/poi-src/test-data/document/testCroppedPictures.doc` |
| WARN: DOC caption styles: truncated STD length | 1 | 1 | 미판정 | `corpus/lo-src/sw/qa/extras/ww8export/data/tdf112535.doc` |
| WARN: DOC field PLC header: non-monotonic PLC positions | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc` |
| WARN: DOC field PLC main: non-monotonic PLC positions | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-6610789829836800.doc` |
| WARN: DOC font table: invalid FFN length | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5440721166139392.doc` |
| WARN: DOC form field: FFData type disagrees with field instruction | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-4951943183990784.doc` |
| WARN: DOC form field: invalid FFData PICF | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-6610789829836800.doc` |
| WARN: DOC image PICF location outside Data stream | 1 | 1 | 미판정 | `corpus/lo-src/sw/qa/extras/ooxmlexport/data/tdf134619_numberingProps.doc` |
| WARN: DOC image truncated or invalid OfficeArtContent | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc` |
| WARN: DOC image truncated or oversized PICF | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/Fuzzed.doc` |
| WARN: DOC image unparsed OfficeArtContent tail | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc` |
| WARN: DOC malformed SummaryInformation ignored | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc` |
| WARN: DOC malformed SummaryInformation property ignored | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5195207308541952.doc` |
| WARN: DOC section PLC has invalid first CP | 1 | 1 | 미판정 | `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz38011-1.doc` |
| WARN: DOC unknown SummaryInformation code page #; using cp# | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5050208641482752.doc` |
| WARN: DOC 본문 텍스트가 비어 있습니다 | 1 | 1 | 손상 의심 | `corpus/lo-src/sw/qa/core/data/ww8/pass/crash-1.doc` |
| WARN: DRM/IRM 보호 문서 — 보호된 본문은 읽을 수 없으며 호환 안내문만 표시될 수 있습니다. | 1 | 1 | 보호 후보 | `corpus/tika-test-docs/testWORD_protected_drm.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream size exceeds available sectors (#Table) | 1 | 1 | 미판정 | `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz47205-1.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream size exceeds available sectors (WordDocument) | 1 | 1 | 손상 의심 | `corpus/lo-src/sw/qa/core/data/ww6/pass/crash-1.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain does not match declared size (#Table) | 1 | 1 | 손상 의심 | `corpus/lo-src/sw/qa/core/data/ww8/pass/hang-1.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain does not match declared size (/) | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain does not match declared size (WordDocument) | 1 | 1 | 미판정 | `corpus/lo-src/sw/qa/core/data/ww8/pass/forcepoint50-grfanchor-1.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain points outside allocation table (#Table) | 1 | 1 | 미판정 | `corpus/lo-src/sw/qa/core/data/ww8/pass/ofz18554-1.doc` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated stream payload (/) | 1 | 1 | 손상 의심 | `corpus/lo-src/sw/qa/core/data/ww6/pass/crash-7.doc` |
| WARN: embedded OLE preview retained: Unexpected data after MTEF END | 1 | 1 | 미판정 | `corpus/poi-src/test-data/document/Bug50936_1.doc` |
| WARN: embedded OLE preview retained: Unsupported MTEF character U+EB# | 1 | 1 | 미판정 | `corpus/lo-src/sw/qa/core/layout/data/tdf122894-4.doc` |
| WARN: embedded OLE preview retained: Unsupported MTEF record # | 1 | 1 | 미판정 | `corpus/poi-src/test-data/document/Bug50936_1.doc` |
| WARN: embedded OLE preview retained: Unsupported MTEF template options | 1 | 1 | 미판정 | `corpus/poi-src/test-data/document/Bug61268.doc` |

### DOCX

| 메시지 틀 | 전 | 후 | 상태 | 자동 추출 표본(최대 3개) |
| --- | ---: | ---: | --- | --- |
| WARN: DOCX image part not found: word/media/image#.jpg | 14 | 14 | ZIP에 이미지 14개 없음 확인 | `corpus/lo-src/sw/qa/extras/layout/data/tdf123163-1.docx` |
| ERR: DOCX package parse failed: File is not a zip file | 7 | 7 | 손상 의심 | `corpus/poi-src/test-data/document/crash-517626e815e0afa9decd0ebb6d1dee63fb9907dd.docx`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-5313273089884160.docx`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-5569740188549120.docx` |
| ERR: 암호화된 문서 — 암호가 필요하거나 암호가 올바르지 않습니다. | 7 | 7 | 보호 후보 | `corpus/poi-src/test-data/document/bug53475-password-is-solrcell.docx`, `corpus/poi-src/test-data/document/bug53475-password-is-pass.docx`, `corpus/lo-src/sw/qa/extras/ooxmlexport/data/Encrypted_MSO2010_abc.docx` |
| ERR: DOCX package parse failed: Bad magic number for central directory | 6 | 6 | 손상 의심 | `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-5166796835258368.docx`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-6442791109263360.docx`, `corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-4791943399604224.docx` |
| ERR: DOCX package parse failed: "There is no item named '<name>' in the archive" | 4 | 3 | 주 문서 경로 결함 1건 수정·확장자만 DOCX인 ODT 3건 잔존 | `corpus/lo-src/sw/qa/extras/uiwriter/data/tdf132596.docx`, `corpus/lo-src/sw/qa/extras/ooxmlexport/data/tdf171025_pageAfter.docx`, `corpus/lo-src/sw/qa/extras/ooxmlexport/data/tdf171038_pageAfter.docx` |
| ERR: DOCX numbering value limit exceeded (start value) | 3 | 0 | 시작값 0 허용으로 수정 | `corpus/lo-src/sw/qa/extras/layout/data/tdf123163-1.docx`, `corpus/lo-src/sw/qa/extras/ooxmlexport/data/tdf162746.docx`, `corpus/lo-src/sw/qa/extras/ooxmlexport/data/tdf57589_hashColor.docx` |
| WARN: DOCX SmartArt text unavailable: word/diagrams/data#.xml | 3 | 3 | 미판정 | `corpus/lo-src/sw/qa/extras/ooxmlexport/data/fdo73227.docx`, `corpus/lo-src/sw/qa/extras/ooxmlexport/data/tdf135906.docx`, `corpus/lo-src/sw/qa/extras/ooxmlexport/data/fdo77718.docx` |
| ERR: DOCX package parse failed: package part could not be decoded: word/styles.xml: Error -# while decompressing data: invalid distance too far back | 1 | 1 | 미판정 | `corpus/lo-src/sw/qa/extras/uiwriter/data/ofz18563.docx` |
| WARN: DOCX image part not found: word/media/image#.jpeg | 1 | 1 | 미판정 | `corpus/lo-src/sw/qa/extras/uiwriter/data/tdf157131.docx` |
| WARN: DOCX image part not found: word/media/image#.png | 1 | 1 | 미판정 | `corpus/lo-src/sw/qa/extras/ooxmlexport/data/footer-margin-lost.docx` |

### PPT

| 메시지 틀 | 전 | 후 | 상태 | 자동 추출 표본(최대 3개) |
| --- | ---: | ---: | --- | --- |
| WARN: OfficeArt truncated record at # | 34 | 34 | 미판정 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6032591399288832.ppt`, `corpus/poi-src/test-data/slideshow/62d2ecd89aeb715b07072d4f8a8734f4dbeb5c10.ppt`, `corpus/poi-src/test-data/slideshow/2cade576206d5bf9a89479446973deeda5a9b549.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: invalid directory entry omitted (/) | 11 | 11 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4983252485210112.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6416153805979648.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4624961081573376.ppt` |
| WARN: PPT incomplete structure supplemented with legacy text; slide association unverified | 11 | 11 | 미판정 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6032591399288832.ppt`, `corpus/poi-src/test-data/slideshow/missing_core_records.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4630915954114560.ppt` |
| WARN: PPT malformed SummaryInformation ignored | 9 | 9 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6032591399288832.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6710128412590080.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-5962760801091584.ppt` |
| ERR: PPT OLE 파일 열기 실패: OLE/CFB: not an OLE# structured storage file | 8 | 8 | 미판정 | `corpus/lo-src/sd/qa/unit/data/ppt/fail/CVE-2010-0033-1.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/CVE-2006-3660-1.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/EDB-39395-1.ppt` |
| WARN: PPT text truncated style | 8 | 0 | 스타일 확장 종료 경계 수정 | `corpus/poi-src/test-data/slideshow/PictureTypeZero.ppt`, `corpus/poi-src/test-data/slideshow/customGeo.ppt`, `corpus/poi-src/test-data/slideshow/br.com.diversas.palestras_Nelson_20-_20Temas_20Diversos_20XXXVI_pmrg_462538ba7a204-programa_alianca_12-04-2007.ppt` |
| ERR: 암호화된 문서 PPT: 암호가 없거나 올바르지 않거나 암호화 구조가 손상되었습니다 | 6 | 6 | 보호 후보 | `corpus/poi-src/test-data/slideshow/ppt_with_png_encrypted.ppt`, `corpus/poi-src/test-data/slideshow/Password_Protected-np-hello.ppt`, `corpus/poi-src/test-data/slideshow/Password_Protected-hello.ppt` |
| WARN: PPT Current User stream unavailable: Current User size mismatch: declared=#, read=# bytes | 6 | 6 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4983252485210112.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6192650357112832.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-5018229722382336.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: inaccessible directory branch omitted (/) | 5 | 5 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6032591399288832.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6710128412590080.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/crash-3.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain points outside allocation table (/) | 5 | 5 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6192650357112832.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-5018229722382336.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6360479850954752.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain points outside allocation table (Current User) | 5 | 5 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4983252485210112.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6192650357112832.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-5018229722382336.ppt` |
| WARN: PPT field has no saved display value; meta-character omitted | 5 | 5 | 미판정 | `corpus/poi-src/test-data/slideshow/npe.ppt`, `corpus/poi-src/test-data/slideshow/datetime.ppt`, `corpus/poi-src/test-data/slideshow/headers_footers_2007.ppt` |
| WARN: PPT slide persist reference missing | 5 | 5 | 미판정 | `corpus/poi-src/test-data/slideshow/2100a8d44da546f97ab7795c500a58bed6cb655d.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6032591399288832.ppt`, `corpus/poi-src/test-data/slideshow/missing_core_records.ppt` |
| ERR: PPT stream validation failed: PowerPoint Document size mismatch: declared=#, read=# bytes | 4 | 4 | 손상 의심 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-2.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-15.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-17.ppt` |
| ERR: 암호화된 문서 — 복호화 크기 상한을 초과했습니다. | 4 | 4 | 보호 후보 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4624961081573376.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIFuzzer-5681320547975168.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4838893004128256.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain points outside allocation table (PowerPoint Document) | 3 | 3 | 손상 의심 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-2.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-15.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-17.ppt` |
| WARN: OfficeArt invalid delayed or embedded BLIP | 3 | 3 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6032591399288832.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-5306877435838464.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6028723156746240.ppt` |
| WARN: PPT master slide reference missing | 3 | 3 | 미판정 | `corpus/poi-src/test-data/slideshow/7ffe3cabb976ebc593dfe2f9461bdeac980a626c.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-19.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-12.ppt` |
| WARN: PPT picture BLIP unavailable for pib # | 3 | 3 | 미판정 | `corpus/poi-src/test-data/slideshow/bug60345_paperfigures.ppt`, `corpus/poi-src/test-data/slideshow/bug60345_Jankovic_final_Retreat_2002.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6028723156746240.ppt` |
| ERR: 문서 파싱 실패: CFBError('OLE/CFB: CFB invalid mini sector size or cutoff') | 2 | 2 | 미판정 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6614960949821440.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/ofz7469-leak-1.ppt` |
| ERR: 지원하지 않는 OLE 스트림 구조 | 2 | 2 | 미판정 | `corpus/poi-src/test-data/slideshow/pp40only.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/ofz14989-1.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream read failed (?SummaryInformation) | 2 | 2 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6192650357112832.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-5018229722382336.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream size exceeds available sectors (?SummaryInformation) | 2 | 2 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6192650357112832.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-5018229722382336.ppt` |
| WARN: OfficeArt invalid metafile deflate | 2 | 2 | 미판정 | `corpus/poi-src/test-data/slideshow/bug60345_paperfigures.ppt`, `corpus/poi-src/test-data/slideshow/bug60345_Jankovic_final_Retreat_2002.ppt` |
| WARN: OfficeArt truncated FOPT complex data | 2 | 2 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6028723156746240.ppt`, `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-19.ppt` |
| WARN: PPT OutlineTextRefAtom index out of range | 2 | 2 | 미판정 | `corpus/poi-src/test-data/slideshow/2cade576206d5bf9a89479446973deeda5a9b549.ppt`, `corpus/poi-src/test-data/slideshow/6afff8111a22b118d1ed4eba5007c153de0b0ad7.ppt` |
| WARN: PPT SummaryInformation unavailable: OLE/CFB: CFB duplicate sector allocation or cyclic chain | 2 | 2 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6192650357112832.ppt`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-5018229722382336.ppt` |
| WARN: PPT invalid CurrentUserAtom; using legacy text recovery | 2 | 2 | 미판정 | `corpus/poi-src/test-data/slideshow/PPT95.ppt`, `corpus/poi-src/test-data/slideshow/bug56240.ppt` |
| WARN: embedded OLE unsupported MS Graph noncontiguous datasheet selection | 2 | 2 | 미판정 | `corpus/poi-src/test-data/slideshow/37625.ppt`, `corpus/poi-src/test-data/slideshow/53446.ppt` |
| WARN: embedded OLE unsupported embedded workbook version | 2 | 2 | 미판정 | `corpus/poi-src/test-data/slideshow/ParagraphStylesShorterThanCharStyles.ppt`, `corpus/poi-src/test-data/slideshow/44770.ppt` |
| ERR: PPT PowerPoint Document stream read 실패: this file is not a stream | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6416153805979648.ppt` |
| ERR: 문서 파싱 실패: CFBError('OLE/CFB: CFB invalid live directory entry type') | 1 | 1 | 손상 의심 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-18.ppt` |
| ERR: 암호화된 문서 — 암호 정보가 손상되었습니다. | 1 | 1 | 보호 후보 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIFuzzer-6411649193738240.ppt` |
| ERR: 암호화된 문서 — 암호 패키지 길이가 잘못되었습니다. | 1 | 1 | 보호 후보 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIFuzzer-5429732352851968.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream read failed (Pictures) | 1 | 1 | 미판정 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/ofz21531-1.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream size exceeds available sectors (/) | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4983252485210112.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream size exceeds available sectors (EncryptedPackage) | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIFuzzer-5429732352851968.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream size exceeds available sectors (PowerPoint Document) | 1 | 1 | 미판정 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/ofz37370-1.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain points outside allocation table (?SummaryInformation) | 1 | 1 | 손상 의심 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-12.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated stream payload (/) | 1 | 1 | 미판정 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/ofz21531-1.ppt` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated stream payload (Current User) | 1 | 1 | 미판정 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/ofz21531-1.ppt` |
| WARN: OfficeArt truncated FOPT fixed table | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4630915954114560.ppt` |
| WARN: PPT Current User stream unavailable: this file is not a stream | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6710128412590080.ppt` |
| WARN: PPT Pictures stream unavailable: OLE/CFB: CFB duplicate sector allocation or cyclic chain | 1 | 1 | 미판정 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/ofz21531-1.ppt` |
| WARN: PPT Pictures stream unavailable: Pictures exceeds per-stream limit: # > # bytes | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-5306877435838464.ppt` |
| WARN: PPT Pictures stream unavailable: this file is not a stream | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6032591399288832.ppt` |
| WARN: PPT SummaryInformation unavailable: SummaryInformation size mismatch: declared=#, read=# bytes | 1 | 1 | 손상 의심 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-12.ppt` |
| WARN: PPT UserEditAtom cycle; older edits ignored | 1 | 1 | 미판정 | `corpus/poi-src/test-data/slideshow/57272_corrupted_usereditatom.ppt` |
| WARN: PPT invalid persistent object offset or size | 1 | 1 | 손상 의심 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-3.ppt` |
| WARN: PPT text master style level count limit exceeded | 1 | 1 | 손상 의심 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/crash-1.ppt` |
| WARN: PPT text master style tab count limit exceeded | 1 | 1 | 미판정 | `corpus/poi-src/test-data/slideshow/cf5f6fde99a8b3ea5a4946c258b7abad6f30b0c5.ppt` |
| WARN: PPT text style tab count limit exceeded | 1 | 1 | 손상 의심 | `corpus/lo-src/sd/qa/unit/data/ppt/pass/hang-8.ppt` |
| WARN: PPT text unsupported paragraph style mask | 1 | 1 | 미판정 | `corpus/poi-src/test-data/slideshow/2cade576206d5bf9a89479446973deeda5a9b549.ppt` |
| WARN: PPT unexpected persistent object type # | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6032591399288832.ppt` |
| WARN: XLS chart unresolved BRAI external workbook reference | 1 | 1 | 미판정 | `corpus/poi-src/test-data/slideshow/bug60345_suba.ppt` |
| WARN: embedded OLE PPT preview retained: invalid compressed storage | 1 | 1 | 미판정 | `corpus/poi-src/test-data/slideshow/bug60345_suba.ppt` |
| WARN: embedded OLE preview retained: Empty MTEF equation | 1 | 1 | 미판정 | `corpus/poi-src/test-data/slideshow/23884_defense_FINAL_OOimport_edit.ppt` |
| WARN: embedded OLE preview retained: Unsupported MTEF CHAR options | 1 | 1 | 미판정 | `corpus/poi-src/test-data/slideshow/23884_defense_FINAL_OOimport_edit.ppt` |
| WARN: embedded OLE preview retained: Unsupported MTEF record # | 1 | 1 | 미판정 | `corpus/poi-src/test-data/slideshow/npe.ppt` |
| WARN: embedded OLE preview retained: Unsupported MTEF v# typeface | 1 | 1 | 미판정 | `corpus/poi-src/test-data/slideshow/npe.ppt` |

### PPTX

| 메시지 틀 | 전 | 후 | 상태 | 자동 추출 표본(최대 3개) |
| --- | ---: | ---: | --- | --- |
| ERR: PPTX package parse failed: File is not a zip file | 6 | 6 | 미판정 | `corpus/poi-src/test-data/slideshow/Divino_Revelado.pptx`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-6071540680032256.pptx`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-5611274456596480.pptx` |
| ERR: PPTX package parse failed: Bad magic number for central directory | 5 | 5 | 손상 의심 | `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-6435650376957952.pptx`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-6372932378820608.pptx`, `corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-5463285576892416.pptx` |
| ERR: PPTX package parse failed: Bad CRC-# for file '<name>' | 2 | 2 | 손상 의심 | `corpus/lo-src/sd/qa/unit/data/pptx/fail/ofz46160-1.pptx`, `corpus/lo-src/sd/qa/unit/data/pptx/fail/ofz35597-1.pptx` |
| ERR: 암호화된 문서 — 암호가 필요하거나 암호가 올바르지 않습니다. | 1 | 1 | 보호 후보 | `corpus/tika-test-docs/testPPT_protected_passtika.pptx` |
| WARN: PPTX text style part could not be read | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/slideshow/crash-57308ca363f5b71763c489d1b432aff009d4bc4f.pptx` |

### XLS

| 메시지 틀 | 전 | 후 | 상태 | 자동 추출 표본(최대 3개) |
| --- | ---: | ---: | --- | --- |
| ERR: XLS OLE 파일 열기 실패: OLE/CFB: not an OLE# structured storage file | 26 | 26 | 미판정 | `corpus/poi-src/test-data/spreadsheet/testEXCEL_4.xls`, `corpus/poi-src/test-data/spreadsheet/testEXCEL_3.xls`, `corpus/lo-src/sc/qa/unit/data/xls/tdf158483.xls` |
| WARN: XLS formula B#: unknown variable function # | 17 | 17 | 미판정 | `corpus/poi-src/test-data/spreadsheet/60405.xls` |
| WARN: XLS formula A#: unknown variable function # | 13 | 13 | 미판정 | `corpus/poi-src/test-data/spreadsheet/60405.xls` |
| ERR: XLS DIMENSION range out of bounds: rows=#:#, cols=#:# | 9 | 0 | 같은 양끝과 마지막 다음 위치 허용으로 수정 | `corpus/poi-src/test-data/spreadsheet/3dFormulas.xls`, `corpus/poi-src/test-data/spreadsheet/47251_1.xls`, `corpus/poi-src/test-data/spreadsheet/LIBRE_OFFICE-94379-0.zip-57.xls` |
| WARN: XLS drawing client anchor out of bounds | 8 | 8 | 두 표본의 원시 앵커 초과 확인·나머지 미판정 | `corpus/poi-src/test-data/spreadsheet/12843-1.xls`, `corpus/poi-src/test-data/spreadsheet/29982.xls`, `corpus/poi-src/test-data/spreadsheet/ar.org.apsme.www_Form%20Inscripcion%20Curso%20NO%20Socios.xls` |
| ERR: XLS stream validation failed: Workbook size mismatch: declared=#, read=# bytes | 7 | 7 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-6483562584932352.xls`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5175219985448960.xls`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4819588401201152.xls` |
| WARN: XLS chart truncated BIFF record | 7 | 7 | 미판정 | `corpus/poi-src/test-data/spreadsheet/cf9f845e73447b092477d0472402a5baea4b8c9f.xls`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4657005060816896.xls`, `corpus/poi-src/test-data/spreadsheet/61300.xls` |
| WARN: XLS chart unsupported BRAI formula without cache | 7 | 7 | 미판정 | `corpus/poi-src/test-data/spreadsheet/52527.xls`, `corpus/poi-src/test-data/spreadsheet/25183.xls`, `corpus/poi-src/test-data/spreadsheet/26100.xls` |
| ERR: XLS OLE 파일 열기 실패: OLE/CFB: CFB truncated data or offset outside file | 6 | 6 | 미판정 | `corpus/lo-src/sc/qa/unit/data/xls/tdf144732.xls`, `corpus/lo-src/sc/qa/unit/data/xls/tdf72470.xls`, `corpus/lo-src/sc/qa/unit/data/xls/pass/ofz49713-1.xls` |
| ERR: XLS Workbook 은 암호로 보호되어 있습니다 (FILEPASS) | 6 | 6 | 보호 후보 | `corpus/poi-src/test-data/spreadsheet/51832.xls`, `corpus/poi-src/test-data/spreadsheet/xor-encryption-abc.xls`, `corpus/poi-src/test-data/spreadsheet/35897-type4.xls` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream size exceeds available sectors (Workbook) | 6 | 6 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-6483562584932352.xls`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4819588401201152.xls`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5889658057523200.xls` |
| WARN: OLE/CFB 컨테이너 손상 복구: invalid directory entry omitted (/) | 4 | 4 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5786329142919168.xls`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5175219985448960.xls`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4657005060816896.xls` |
| WARN: OfficeArt truncated record at # | 4 | 4 | 미판정 | `corpus/poi-src/test-data/spreadsheet/cf9f845e73447b092477d0472402a5baea4b8c9f.xls`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5436547081830400.xls`, `corpus/poi-src/test-data/spreadsheet/46137.xls` |
| WARN: XLS drawing truncated BIFF record | 4 | 4 | 미판정 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4657005060816896.xls`, `corpus/poi-src/test-data/spreadsheet/61300.xls`, `corpus/lo-src/sc/qa/unit/data/xls/pass/crash-6.xls` |
| ERR: 문서 파싱 실패: CFBError('OLE/CFB: CFB invalid mini sector size or cutoff') | 3 | 3 | 미판정 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-6137883240824832.xls`, `corpus/lo-src/sc/qa/unit/data/xls/pass/ofz14120-1.xls`, `corpus/lo-src/sc/qa/unit/data/xls/pass/ofz5527-1.xls` |
| ERR: XLS LABELSST cell out of bounds: row=#, col=# | 2 | 2 | 손상 의심 | `corpus/lo-src/sc/qa/unit/data/xls/pass/crash-3.xls`, `corpus/lo-src/sc/qa/unit/data/xls/pass/crash-2.xls` |
| ERR: XLS cell limit exceeded: # > # | 2 | 2 | 미판정 | `corpus/poi-src/test-data/spreadsheet/44593.xls`, `corpus/poi-src/test-data/spreadsheet/ex45698-22488.xls` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain points outside allocation table (/) | 2 | 2 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5175219985448960.xls`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4651309315719168.xls` |
| WARN: XLS chart unresolved BRAI external sheet | 2 | 2 | 미판정 | `corpus/lo-src/sc/qa/unit/data/xls/chartx2.xls`, `corpus/lo-src/sc/qa/unit/data/xls/chartx.xls` |
| WARN: XLS drawing BIFF record count limit exceeded | 2 | 2 | 미판정 | `corpus/poi-src/test-data/spreadsheet/44593.xls`, `corpus/poi-src/test-data/spreadsheet/ex45698-22488.xls` |
| WARN: XLS malformed SummaryInformation ignored | 2 | 2 | 미판정 | `corpus/poi-src/test-data/spreadsheet/cf9f845e73447b092477d0472402a5baea4b8c9f.xls`, `corpus/poi-src/test-data/spreadsheet/poi-fuzz.xls` |
| ERR: XLS Book 은 암호로 보호되어 있습니다 (FILEPASS) | 1 | 1 | 보호 후보 | `corpus/poi-src/test-data/spreadsheet/60284.xls` |
| ERR: XLSX package parse failed: Bad CRC-# for file '<name>' | 1 | 1 | 손상 의심 | `corpus/lo-src/sc/qa/unit/data/xls/fail/forcepoint-group-range-1.xls` |
| ERR: 문서 파싱 실패: CFBError('OLE/CFB: CFB cyclic or duplicate directory entry') | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5816431116615680.xls` |
| ERR: 지원하지 않는 OLE 스트림 구조 | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5786329142919168.xls` |
| ERR: 지원하지 않는 ZIP 문서 형식 | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/rde.imf.ru_sites_default_files_rde_documents_vodootvedenie_2020.xlsb.xls` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream size exceeds available sectors (/) | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4734163573080064.xls` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain points outside allocation table (?SummaryInformation) | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4657005060816896.xls` |
| WARN: OLE/CFB 컨테이너 손상 복구: truncated chain points outside allocation table (Workbook) | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5175219985448960.xls` |
| WARN: OfficeArt invalid delayed or embedded BLIP | 1 | 1 | 미판정 | `corpus/lo-src/sc/qa/unit/data/xls/emptyAnchor.xls` |
| WARN: XLS PtgTbl without valid TABLE record; cached value retained | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/44958_1.xls` |
| WARN: XLS SummaryInformation unavailable: SummaryInformation exceeds per-stream limit: # > # bytes | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/61300.xls` |
| WARN: XLS SummaryInformation unavailable: SummaryInformation size mismatch: declared=#, read=# bytes | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4657005060816896.xls` |
| WARN: XLS chart unresolved BRAI external workbook reference | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/florida_data.ashx.xls` |
| WARN: XLS drawing image data unavailable for pib # | 1 | 1 | 미판정 | `corpus/lo-src/sc/qa/unit/data/xls/emptyAnchor.xls` |
| WARN: XLS formula A#: unsupported or truncated PtgElf token; expression omitted | 1 | 1 | 미판정 | `corpus/lo-src/sc/qa/unit/data/xls/forum-mso-de-49320.xls` |
| WARN: XLS formula invalid NAME record | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/cf9f845e73447b092477d0472402a5baea4b8c9f.xls` |
| WARN: XLS formula invalid SupBook: truncated extra data | 1 | 1 | 손상 의심 | `corpus/lo-src/sc/qa/unit/data/xls/pass/crash-7.xls` |
| WARN: XLS formula unresolved external sheet index | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/56450.xls` |
| WARN: XLS formula unresolved external workbook reference | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/external_name.xls` |
| WARN: XLS invalid TABLE at E#: TABLE record length must be # bytes | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/44958_1.xls` |
| WARN: XLS 시트 '#' 격자가 상한을 넘어 #행 x #열로 잘렸습니다 | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/SharedFormulaTest.xls` |
| WARN: XLS 시트 'Sheet#' 격자가 상한을 넘어 #행 x #열로 잘렸습니다 | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/51535.xls` |
| WARN: spreadsheet formatted numeric value is out of range: nan | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/49761.xls` |

### XLSX

| 메시지 틀 | 전 | 후 | 상태 | 자동 추출 표본(최대 3개) |
| --- | ---: | ---: | --- | --- |
| ERR: XLSX package parse failed: File is not a zip file | 7 | 7 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIXSSFFuzzer-6123461607817216.xlsx`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-6594557414080512.xlsx`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-5542865479270400.xlsx` |
| ERR: XLSX package parse failed: Bad magic number for central directory | 6 | 6 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-5025401116950528.xlsx`, `corpus/poi-src/test-data/spreadsheet/crash-274d6342e4842d61be0fb48eaadad6208ae767ae.xlsx`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIXSSFFuzzer-6448258963341312.xlsx` |
| ERR: 암호화된 문서 — 암호가 필요하거나 암호가 올바르지 않습니다. | 3 | 3 | 보호 후보 | `corpus/poi-src/test-data/spreadsheet/protected_passtika.xlsx`, `corpus/tika-test-docs/testEXCEL_protected_passtika.xlsx`, `corpus/tika-test-docs/testEXCEL_protected_passtika_2.xlsx` |
| ERR: XLSX package parse failed: Bad CRC-# for file '<name>' | 2 | 2 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIXSSFFuzzer-5265527465181184.xlsx`, `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIXSSFFuzzer-5937385319563264.xlsx` |
| ERR: DOCX package parse failed: Bad magic number for file header | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIFuzzer-5040805309710336.xlsx` |
| ERR: XLSX dense cell limit exceeded: # > # | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/65016.xlsx` |
| ERR: XLSX invalid cell reference: B | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/invalid_cell_reference.xlsx` |
| ERR: XLSX package parse failed: duplicate package part name: xl/worksheets/sheet#.xml | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/duplicate-filename.xlsx` |
| ERR: XLSX row reference out of bounds: # | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/poc-shared-strings.xlsx` |
| ERR: XLSX sheet XML parse failed: xl/worksheets/sheet#.xml: package XML element limit exceeded: xl/worksheets/sheet#.xml | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/LIBRE_OFFICE-116306-0.xlsx` |
| ERR: XLSX streaming cell limit exceeded: more than # cells | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/LIBRE_OFFICE-116306-0.xlsx` |
| ERR: 암호화된 문서 — 암호 패키지 길이가 잘못되었습니다. | 1 | 1 | 보호 후보 | `corpus/poi-src/test-data/spreadsheet/crash-9bf3cd4bd6f50a8a9339d363c2c7af14b536865c.xlsx` |
| WARN: OLE/CFB 컨테이너 손상 복구: stream size exceeds available sectors (EncryptedPackage) | 1 | 1 | 손상 의심 | `corpus/poi-src/test-data/spreadsheet/crash-9bf3cd4bd6f50a8a9339d363c2c7af14b536865c.xlsx` |
| WARN: XLSX cell text limit exceeded (# characters, repeated shared strings); later cell text omitted | 1 | 1 | 미판정 | `corpus/poi-src/test-data/spreadsheet/poc-shared-strings.xlsx` |

## 독립 리뷰 A~M 판정

| 후보 | 관찰한 바이트·패키지 근거 | 최종 판정 |
| --- | --- | --- |
| A PDF 사전 키 | `156784146.pdf`의 객체 21과 `156782882.pdf`의 객체 270에서 URI 문자열 뒤에 `))`가 있고 다음 토큰은 `/S`다. 문자열 닫는 괄호가 하나 남으므로 ISO 32000 사전 키 구문에 맞지 않는다. | 확인한 두 경고는 정당하다. 같은 틀의 나머지 세 건은 미판정이다. |
| B PDF 해제 한도 | `156783715.pdf`의 압축 길이 2,734,096바이트인 `/Subtype /Image` 스트림은 RGB 3598×5089×8비트다. 예상 원시 픽셀 54,930,666바이트가 50MiB 한도를 넘는다. PDF Markdown은 2,909자이며 HWPX 짝은 4,235자다. | 제한된 것은 이미지 XObject다. 본문 스트림 잘림의 근거는 없으며 한도는 유지한다. 다른 한 건은 미판정이다. |
| C 확장자 불일치 ZIP | 해당 `.hwp`는 `PK`로 시작하지만 표준 `zipfile`도 중앙 디렉터리를 찾지 못한다. | 읽을 수 있는 HWPX/OOXML 패키지가 아니므로 현재 실패가 타당하다. XLSB 확장자 불일치도 미지원 변종으로 남긴다. |
| D HWPX ZIP | 해당 8,639,368바이트 파일에는 ZIP 종료 레코드 `PK 05 06`가 없다. 표준 `zipfile.is_zipfile`도 거짓이다. | 손상된 ZIP으로 판정한다. |
| E HWPX marker | `dummy.hwpx`와 `sample.hwpx`에는 섹션 XML과 `content.hpf`가 있지만 `mimetype` 엔트리가 없다. | 콘텐츠 일부는 읽을 수 있으나 marker 없는 패키지를 OWPML 정규 패키지로 허용할 명세 근거를 이번 오프라인 조사에서 확인하지 못했다. 관대한 복구는 보류한다. |
| F HWP 압축 | 두 HWP의 `FileHeader` 압축 비트는 1이다. `DocInfo`와 `BodyText/Section0`은 `78 9c`로 시작하며 zlib 래핑 해제는 되지만 기존 raw DEFLATE 해제는 실패한다. | 다른 생성기의 압축 변형을 확인했다. 한컴 규격의 허용 여부와 문서별 총 해제 예산 설계가 확인되기 전에는 폴백을 추가하지 않는다. |
| G DOCX 주 부품 | 오류 4건 중 3건은 `mimetype=application/vnd.oasis.opendocument.text`이거나 `content.xml`을 가진 확장자 불일치 ODT다. `tdf104713_undefinedStyles.docx`는 루트 관계가 실제 `word/trial.xml`을 가리킨다. | 유효한 OOXML 한 건을 고쳤다. 나머지 세 건은 DOCX 본문 부품이 없어 유지한다. |
| H DOCX 번호 시작값 | 세 LO 표본 모두 `word/numbering.xml`에 `w:start w:val="0"`을 담는다. | 0을 허용해 경고 3건을 제거했다. 실제 Markdown 해시는 세 건 모두 같다. |
| I DOCX 이미지 | `tdf123163-1.docx` 관계는 `word/media/image1.jpg`부터 `image14.jpg`를 참조하지만 ZIP에는 `/media/` 부품이 하나도 없다. | 이 14건의 경고는 대상 부품 부재를 정확히 알린다. 다른 이미지 경고는 미판정이다. |
| J PPT 스타일 | `customGeo.ppt`와 `PictureTypeZero.ppt`의 StyleTextProp9Atom 읽기는 각각 완결된 12·16·24·28·36·42바이트 경계에서 끝나며 기본 문단 실행만 더 남는다. | 완결 경계는 잘림이 아니다. 수정 뒤 8건이 사라졌고 출력 해시는 모두 같다. |
| K XLS DIMENSION | `3dFormulas.xls` 등의 `rwMac` 또는 `colMac`은 빈 축에서 시작과 같고 `chartx.xls`의 `colMac`은 256이다. 값은 마지막 사용 위치 다음의 배타적 경계다. | 같은 양끝과 최대 경계를 허용해 9건을 제거했다. 출력 해시는 모두 같다. |
| L XLS 함수 번호 | `60405.xls`의 번호 32811 등은 `0x8000` 이상의 값이다. 현재 [MS-XLS] Ftab 자료에는 0x0000~0x017B만 있고 POI 테스트는 `Macro1`·`Macro2` 텍스트만 단언한다. | Cetab 명령 번호와 일반 함수의 대응을 확인하지 못해 미판정으로 남긴다. 임의로 상위 비트를 지우지 않는다. |
| M XLS 그림 앵커 | `29982.xls`의 원시 ClientAnchor에는 `dy=612`가 있어 현재 256 경계를 넘고, `12843-1.xls`의 일부 앵커에는 열 값 2417 이상이 있다. | 두 표본에서 경고 조건은 실제 바이트와 일치한다. Excel의 특수 배치 의미와 나머지 여섯 표본은 미판정이므로 경고를 유지한다. |

## 판정 한계와 남은 일

이번 실행은 지원 확장자 9종 전체를 수집했지만, 254개 전후 합집합 메시지 틀의 모든 표본 2~3개를 독립 도구와 원시 구조로 열어보지는 못했다. 위의 미판정·후보 상태를 확정 판정으로 사용하면 안 된다. PDF xref 스트림 대체 16건, XLS 그림 앵커의 나머지 표본, Cetab 함수 번호, marker 없는 HWPX와 zlib 래핑 HWP의 규격 판단이 남았다. PDF 미주 기하 검사 경고가 남은 두 문서는 공간 후보 선별을 개선하되 검사량 상한을 유지해야 한다. README의 Supported Elements 상태는 이 오류 정리만으로 바꾸지 않는다.

수집 파일은 `.codex-work/` 아래에만 있고 저장소에 공개·내부 원본 문서를 복사하지 않았다. 실물 전후 비교는 해시·문자 수·오류 목록으로만 수행했다.
