# Strict OOXML 실물 검증

이 보고서는 `ooxml-strict` 작업의 검증 결과다. 파일명은 작업에서 지정한 날짜를 유지했으며, 최종 실행은 한국 시간 2026년 10월 3일에 완료했다. 비교 기준은 변경 전 커밋 `31234597bddc5da4389537f208b77bff8b91be98`이다. README와 공용 모델·출력기는 수정하지 않았다.

## 구현 범위와 표준 대응

`OOXMLPackage.read_xml_part()`가 Strict XML의 요소 이름, 속성 이름, 네임스페이스 선언을 기존 리더가 사용하는 Transitional 이름으로 정규화한다. 관계의 `Type`과 DrawingML `graphicData@uri`도 구조용 URI로 구분해 정규화한다. ZIP 원문, 본문 문자열, 관계 `Target`, 사용자 정의 네임스페이스는 치환하지 않는다. `mc:Choice@Requires`처럼 접두사를 사용하는 값이 계속 동작하도록 선언과 중첩 접두사 재바인딩을 유지한다.

아래 표에서 Strict 접두사는 `http://purl.oclc.org/ooxml/`, Transitional 접두사는 `http://schemas.openxmlformats.org/`이다. ISO/IEC 29500-1의 Strict 계열과 29500-4의 Transitional 계열에 대해 적용한 대응은 다음과 같다.

| Strict 접미사 | Transitional 접미사 |
| --- | --- |
| `wordprocessingml/main` | `wordprocessingml/2006/main` |
| `spreadsheetml/main` | `spreadsheetml/2006/main` |
| `presentationml/main` | `presentationml/2006/main` |
| `drawingml/main` | `drawingml/2006/main` |
| `drawingml/chart` | `drawingml/2006/chart` |
| `drawingml/chartDrawing` | `drawingml/2006/chartDrawing` |
| `drawingml/diagram` | `drawingml/2006/diagram` |
| `drawingml/lockedCanvas` | `drawingml/2006/lockedCanvas` |
| `drawingml/picture` | `drawingml/2006/picture` |
| `drawingml/spreadsheetDrawing` | `drawingml/2006/spreadsheetDrawing` |
| `drawingml/wordprocessingDrawing` | `drawingml/2006/wordprocessingDrawing` |
| `officeDocument/math` | `officeDocument/2006/math` |
| `officeDocument/relationships` | `officeDocument/2006/relationships` |
| `officeDocument/extendedProperties` | `officeDocument/2006/extended-properties` |
| `officeDocument/customProperties` | `officeDocument/2006/custom-properties` |
| `officeDocument/docPropsVTypes` | `officeDocument/2006/docPropsVTypes` |
| `officeDocument/customXml` | `officeDocument/2006/customXml` |
| `officeDocument/bibliography` | `officeDocument/2006/bibliography` |

관계 유형의 기본 대응은 `officeDocument/relationships/<종류>`에서 `officeDocument/2006/relationships/<종류>`로의 변경이다. 예외적으로 `extendedProperties`는 `extended-properties`, `customProperties`는 `custom-properties`가 된다. `officeDocument/relationships/metadata/thumbnail`은 `package/2006/relationships/metadata/thumbnail`에 대응한다. OPC 관계 요소 자체의 `package/2006/relationships`, OPC 콘텐츠 유형, `markup-compatibility/2006`, Dublin Core와 Microsoft 확장 URI는 그대로 둔다.

인터넷에 연결하지 않았으며, 제공된 로컬 코퍼스에서 ISO/ECMA 명세 원문이나 XSD를 찾지 못했다. 따라서 이 결과는 실물 XML·공개 테스트 기대값·합성 회귀 테스트에 근거한 기존 추출 계약의 호환성 검증이다. 전체 XSD 적합성이나 ISO/IEC 29500 전체 기능 구현을 인증한 결과는 아니다. 18개 네임스페이스 대응 모두 합성 테스트로 확인했고, 이 가운데 12종은 실물 Strict XML에서도 관찰했다.

## 값 형식과 안전성

Strict XLSX의 `t="d"` 값은 Excel 일련번호로 해석하지 않고 ISO 날짜로 읽는다. 날짜 서식은 기존 `YYYY-MM-DD`, 시간 서식은 기존 24시간 출력과 초 반올림을 사용한다. 일반 서식은 원문을 보존한다. 날짜 수식의 캐시 값에도 기존 수식 접미사를 붙인다. 1900/1904 날짜 체계가 ISO 날짜를 이동시키지 않으며, 시간대가 있는 값은 기록된 시각을 표시하고 UTC 변환을 하지 않는다. 잘못된 날짜는 원문을 남기고 `doc.errors`에 경고한다. Python 3.9에서 거부되는 한 자리·두 자리·긴 소수초도 별도로 처리한다. 기존 Transitional 날짜 출력은 유지한다.

실물에는 `pgSz@w="612pt"`, `tcW@w="81.85pt"`, `tint@val="67%"`, `spcPct@val="90%"` 등도 있다. 현재 리더와 출력 모델은 페이지 치수·셀 물리 폭·색상 변환·줄 간격·회전 렌더링을 계산하지 않는다. 이 속성의 값은 원문 그대로 보존하고 단위를 버리거나 다른 스케일의 정수로 오인하지 않는다. 각도 정수와 백분율의 보존은 합성 테스트로 확인했다. `deg` 접미사 실물은 발견하지 못했다. 이 작업은 해당 시각적 값의 렌더링이나 일반적인 단위 변환을 새로 구현하지 않았으므로 그 기능은 미검증으로 남긴다.

기존 XML 32 MiB·원소 100만 개·ZIP 파트 및 압축 상한을 유지하고, 로컬 네임스페이스 선언 100만 개 상한을 추가했다. 선언은 `iterwalk`의 `start-ns` 이벤트에서만 복사해 상속된 전체 네임스페이스를 노드마다 복제하지 않는다. 트리 복사는 반복 방식이며, UTF-16·복구 파싱·깊은 XML·미해결 엔티티를 포함한 테스트를 통과했다. 외부 엔티티를 확장하지 않는다.

## 실물 검증 표

POI 경로는 `test-data/spreadsheet/`, LO DOCX 경로는 `sw/qa/extras/ooxmlexport/data/`, LO PPTX 경로는 `sd/qa/unit/data/`를 기준으로 쓴다. 모두 제공된 공개 코퍼스의 파일명이다. 내부 문서는 사용하지 않았다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| DOCX Strict 본문·머리글 | LO `strict.docx` | LO `sw/qa/extras/ooxmlexport/ooxmlexport10.cxx:569–578`, 원시 `word/document.xml`, `word/header1.xml` | `Hello world!`, `This is a header.`와 원시 문단 문자열 5개를 보존해야 한다. | 문단 문자열 5/5를 보존했고 머리글은 기존 HeaderFooter 경로로 출력했다. | 검증 통과다. |
| DOCX Strict 이미지·차트 데이터·수식 | LO `strict.docx` | 원시 이미지 관계, `word/charts/chart1.xml`, 본문의 OMML | 그림 참조, Series 1의 값 1·2·3, 원 면적 수식을 복원해야 한다. | `word/media/image1.gif`, 차트 표의 1·2·3, `A=π{r}^{2}`를 출력했다. | 이 표본의 추출은 통과다. 차트 제목 전체 지원의 근거는 아니다. |
| DOCX Strict 단순·중첩 표 텍스트 | LO `tdf79272_strictDxa.docx` | 원시 Strict `w:t`·`w:tbl` | `2014`, `2015`, 프로젝트 상태 및 중첩 지역 상태 문단 10개를 보존해야 한다. | 10/10을 보존했고 기존 표·중첩 텍스트 표현으로 출력했다. | 텍스트 검증 통과다. 물리적 열 폭은 미검증이다. |
| DOCX Strict 본문·이미지 | LO `tdf116410.docx` | 원시 본문의 `w:t`, 이미지 관계 | 탭을 포함한 설정 설명과 그림 참조를 보존해야 한다. | 문단 문자열 1/1과 `word/media/image1.png`를 출력했다. | 텍스트·그림 참조 검증 통과다. 여백 렌더링은 미검증이다. |
| DOCX Strict 목록 | LO `tdf82065_Ind_start_strict.docx` | 원시 본문 및 numbering 파트 | `RTL with indent`와 기존 글머리표를 출력해야 한다. | `• RTL with indent`를 출력했다. | 검증 통과다. 들여쓰기의 물리적 폭은 미검증이다. |
| DOCX Strict 본문 | LO `tdf150822.docx` | 원시 본문 문단 | `AAAA`, `BBBB`, `CCCC` 3개를 복원해야 한다. | 3/3을 보존했다. | 검증 통과다. |
| DOCX Strict SmartArt 전용 본문 | LO `strict-smartart.docx` | LO `ooxmlexport10.cxx:603–608`의 그룹 도형 기대값, 원시 diagram 관계 | SmartArt 그룹의 내용을 복원해야 한다. 일반 `w:t`는 없다. | 패키지는 열지만 작성자 메타데이터만 출력한다. | 기존 DOCX SmartArt 추출 한계다. 본문 복원 성공으로 세지 않는다. |
| PPTX Strict 텍스트·제목 | LO `strict_ooxml.pptx` | 원시 `ppt/slides/slide1.xml`의 `Title`, `Subtitle` | 한 슬라이드의 두 문자열을 복원해야 한다. | 2/2를 보존했고 기존 제목 모델로 출력했다. | 검증 통과다. |
| PPTX Strict 텍스트·서식 | LO `pptx/tdf119087.pptx` | 원시 `a:t`와 `a:rPr` | `My Test`와 굵은 서식을 보존해야 한다. | `**My Test**`를 출력했다. | 검증 통과다. 색상 렌더링은 판정하지 않았다. |
| XLSX Strict 여러 시트·수식 | POI `SampleSS.strict.xlsx` | 같은 문서 `SampleSS.xlsx`의 출력 | 3개 시트의 Markdown·JSON·경고가 같아야 한다. | 세 항목이 완전히 일치했다. | 검증 통과다. |
| XLSX Strict 공유·rich 문자열 | POI `sample.strict.xlsx` | 같은 문서 `sample.xlsx`의 출력 | 3개 시트의 Markdown·JSON·경고가 같아야 한다. | 세 항목이 완전히 일치했다. | 검증 통과다. |
| XLSX Strict ISO 날짜·수식 | POI `SimpleStrict.xlsx` | `SimpleNormal.xlsx`; `sheet2!A4`의 Strict `t=d, 1990-01-01` 대 Transitional `32874`, 양쪽 `s=1 → numFmtId=14` | 2개 시트 출력 및 날짜 `1990-01-01`이 같아야 한다. | Markdown·JSON·경고가 완전히 일치했다. | 날짜 표본 검증 통과다. 시간·소수초는 합성 테스트만 수행했다. |
| XLSX Strict 기본 셀 | POI `57914.xlsx` | 원시 worksheet와 sharedStrings | `Number`, `Column 1`, `Column 2`와 값 `999999999`, `1`, `1`을 복원해야 한다. | 여섯 셀의 값과 한 시트를 복원했다. | 기본 셀 검증 통과다. |

DOCX의 원시 본문·머리글 문단 문자열은 5개 문서에서 20/20, PPTX 문자열은 2개 문서에서 3/3을 확인했다. 이 검사는 공백을 제거한 원시 문자열이 출력에 보존됐는지를 본다. 모든 요소의 읽기 순서나 중복 부재를 입증하는 검사가 아니다. Strict SmartArt 전용 문서 1개는 텍스트 검증 성공 분모에서 제외하고 별도 실패·한계로 공개한다.

POI `TestXSSFBugs.java:2207–2215`의 Strict 시트 수 테스트는 비활성화되어 있으므로 실행 성공 근거로 인용하지 않았다. `TestXSSFReader.java:245–263`도 당시 Strict 미지원 예외를 기대하므로 기본 셀의 정답 근거로 사용하지 않았다. POI나 LO 구현 코드를 복사·번역하지 않았다.

## Transitional 회귀와 테스트

POI 후보 577개와 LO 후보 1,807개, 합계 2,384개를 읽기 전용으로 스캔했다. Strict는 DOCX 6개, PPTX 2개, XLSX 4개였다. 비교 가능한 Transitional 2,318개는 Markdown·JSON·경고를 함께 직렬화한 SHA-256 지문이 전후 100% 동일했다.

| 구분 | 비교 수 | 동일 수 |
| --- | ---: | ---: |
| Transitional DOCX | 1,480 | 1,480 |
| Transitional PPTX | 510 | 510 |
| Transitional XLSX | 328 | 328 |
| 합계 | 2,318 | 2,318 |

나머지 비Strict 후보 54개는 ZIP으로 열 수 없는 53개와 30초 상한을 넘긴 `spreadsheet/poc-shared-strings.xlsx` 1개다. 이들의 예외 결과도 전후 같았지만 문서 출력 일치 분모에는 포함하지 않는다. 읽힌 문서 중 기존 경고가 있는 문서도 분모에 포함했고 경고까지 비교했다. Strict XLSX 4개는 기존 부분 지원으로 이미 읽히던 표본이라 출력이 그대로이며, DOCX 6개와 PPTX 2개는 출력이 달라졌다. SmartArt 파일에서 늘어난 작성자 문자열은 본문 복원으로 계산하지 않는다.

새 합성 테스트 51개는 18종 네임스페이스, 관계 예외, DOCX 표·각주·머리글·수식·차트·그림, PPTX AlternateContent·링크·노트, XLSX 날짜·스트리밍·1904 체계·소수초, Transitional 날짜 불변, 깊이·선언 상한·UTF-16·엔티티 안전성을 확인한다. 최초 27개 실패를 확인한 뒤 구현했고, 후속 날짜·상한·엔티티 회귀도 실패를 먼저 확인했다.

기존 `test_probe_primary_result_does_not_pass_empty_unsupported_body`는 Strict를 미지원 형식으로 사용했다. 이 작업으로 Strict가 읽히면서 그 전제가 사라졌으므로 표본 네임스페이스만 `urn:dochan:test:unsupported-wordprocessingml`로 바꾸었다. 기존 세 단언은 전부 그대로 유지했다. 별도 읽기 순서 오라클 `scripts/verify_ooxml_docx.py`는 여전히 Transitional 원시 QName을 전제로 하므로 이 작업의 Strict 읽기 순서 판정 근거로 사용하지 않았다.

최종 전체 테스트 명령은 다음과 같다. 결과는 3,072개 통과, 24개 건너뜀, 14개 예상 실패이며 예상 밖 실패는 없다.

```bash
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

실물 지문과 독립적인 원시 문자열·Transitional 짝 비교는 다음 명령으로 재현한다. 최초 실행에서 `--baseline` 없이 기준 결과를 저장하고, 변경 후 아래처럼 비교한다. 코퍼스 경로는 모두 인자로 받으며 원본을 수정하거나 저장소로 복사하지 않는다.

```bash
/usr/bin/python3 -m scripts.probe_ooxml_strict \
  /Users/illuwa/dev/personal/dochan/corpus/poi-src/test-data \
  /Users/illuwa/dev/personal/dochan/corpus/lo-src \
  --output .codex-work/after.json --baseline .codex-work/before.json
```

원시 실행 결과는 `.codex-work/before.json`, `.codex-work/after.json`, `.codex-work/full-tests.txt`에 남겼다. README의 DOCX 읽기 순서나 차트 제목/데이터 등 별도 미지원 칸을 이번 증거만으로 일괄 ✅로 바꾸는 것은 제안하지 않는다. Strict 기본 추출 호환성은 위 표의 검증된 계약 범위에서 통과하며, SmartArt 전용 본문·시각적 단위 렌더링·실물 없는 각주/노트/소수초 등은 구분해 남긴다.
