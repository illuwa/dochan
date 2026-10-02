# PPT 리뷰 반영 실물 검증

2026년 10월 2일 `illuwa/w-ppt`에서 두 독립 리뷰를 재현하고 수정했다. 공개 표본을 읽기 전용으로 사용했으며 저장소에 복사하지 않았다. POI 구현을 번역하지 않았고 기대값·원시 바이트·기존 PPTX 출력 계약을 근거로 삼았다. README 체크는 직접 변경하지 않았다.

## 칸별 실물 검증

아래 Java 경로는 POI 소스의 `poi-scratchpad/src/test/java/org/apache/poi/hslf/` 아래 상대 경로이다. 통과는 표본에서 해당 기능을 확인했다는 뜻이며, 모든 문서·모든 속성의 완전 복원을 뜻하지 않는다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| 표(셀 병합) | `bug60993.ppt`, `table_test.ppt`, `54111.ppt` | 앞의 두 OOXML 짝 출력, `model/TestTable.java:70-105`, 원시 셀 좌표 | 첫 표는 6×3이며 R3C2가 가로 2칸, R5C2가 세로 2칸이다. 다른 표는 각각 6×3, 6×4이다. | 세 표의 격자가 일치했다. 병합 2/2와 `54111` 셀 24/24가 일치했다. | 통과했다. |
| 표(중첩 텍스트) | 해당 실물 표본을 찾지 못했다. | `tests/test_docx_reader.py::test_reads_docx_nested_table_text_inside_parent_cell`, `tests/test_hwpx_reader.py::test_hwpx_nested_table_text_survives_in_cell` | 부모 셀 안의 중첩 표 내용이 살아 있어야 한다. | 일반 셀의 여러 문단은 보존하지만 PPT 중첩 표 실물은 검증하지 못했다. `bug60993`의 여러 줄 셀을 중첩 표 증거로 세지 않았다. | 미검증이며 ⬜를 유지한다. |
| 서식(bold/italic) | `with_textbox.ppt` | `model/TestShapes.java:124-145` | Hello는 bold·italic 32pt, poor boy는 bold 44pt, Times는 bold·italic·underline 16pt이다. | 세 문구의 세 서식 플래그가 3/3 일치했다. 글자 크기와 일반 18pt 런도 원시 서식에서 확인했다. | 통과했다. |
| 이미지 참조 | `pictures.ppt` | `usermodel/TestPictures.java:179-230`, `clock.jpg`, `tomcat.png`, `wrench.emf` | 다섯 슬라이드에 JPEG·PNG·WMF·PICT·EMF가 있다. JPEG·PNG·EMF는 공개 원본 바이트와 같다. | 배치 5/5, 직접 비교한 바이트 3/3이 일치했다. `Image`, `AssetRef`, Markdown 참조를 함께 생성했다. | 통과했다. |
| 이미지 대체 텍스트 | `customGeo.ppt` | OOXML 짝의 `cNvPr@descr`, 원시 OfficeArt `0x0381` 속성 위치 151022·587052 | `ODE_195bktxt.jpg`와 `http://www.ode.state.oh.us/gd/templates/images/ODE/ohio_logo.gif` 설명을 보존한다. | 두 설명 2/2가 `Image.alt_text`에 그대로 들어갔다. | 통과했다. |
| 이미지 OCR | `pictures.ppt` | 추출 PNG와 공개 `tomcat.png`의 바이트 비교 및 실제 `Image.run_ocr()` 호출 | 기존 OCR 경로가 그림 바이트를 받아 인식문을 반환해야 한다. | 바이트는 같았으나 실제 반환값은 빈 문자열이었다. Python 3.9.6에서 기존 OCR의 최소 Python 3.10 조건을 충족하지 못했다. | 미검증이며 ⬜를 유지한다. |
| 텍스트박스/도형 텍스트 | `with_textbox.ppt`, `54880_chinese.ppt` | `extractor/TestExtractor.java:97-105,380-393` | 텍스트박스 네 문구와 `Single byte`, `Mix`, `表`, `ﾊﾝｶｸ`를 보존한다. | 문구 4/4와 문자 검사 4/4가 일치했다. 빈 TextHeader도 아웃라인 인덱스 계산에 남겼다. | 통과했다. |
| 레이아웃 상속 텍스트 | `WithMaster.ppt` | `extractor/TestExtractor.java:318-338` | 일반 마스터 문구가 나오고 마스터 편집 안내 제목은 나오지 않으며 footer는 한 번 나온다. | 포함·제외·footer 개수 검사 3/3이 일치했다. 일반 마스터 문구는 각 슬라이드에 한 번씩 나온다. | 통과했다. |
| 발표자 노트 | `basic_test_ppt_file.ppt`, `42474-1.ppt`, `SampleShow.ppt` | `extractor/TestExtractor.java:72-76,112-117`, `usermodel/TestBugs.java:129-146`, `SampleShow.pptx` 출력 | 노트 네 문구를 각각 올바른 슬라이드에 연결한다. SampleShow의 노트 두 개와 슬라이드 번호도 일치한다. | 앞의 두 파일에서 4/4 노트 연결이 일치하고 SampleShow는 노트 2/2가 완전히 일치했다. | 통과했다. |
| 읽기 순서 | `with_textbox.ppt` | 네 도형의 원시 ClientAnchor top 값 936, 1754, 2352, 3359 | Plain, Hello, poor boy, Times 순서이다. 좌표가 같으면 자식 저장 순서를 유지한다. | 네 도형의 좌표 순서가 4/4 일치했다. | 통과했다. |
| 그룹 도형 | `bug62092.ppt`, `42485.ppt` | `extractor/TestExtractor.java:450-469`, `usermodel/TestBugs.java:180-214`, 원시 그룹 좌표 | bug62092의 텍스트박스 다섯 개, WordArt 두 개, 비그룹 텍스트 하나가 각각 한 번 나온다. | 문구 8/8을 중복 없이 복원했다. 42485에서는 그룹 두 개 안의 텍스트 도형 아홉 개와 좌표 변환도 확인했다. | 통과했다. |
| 하이퍼링크 | `WithLinks.ppt` | `model/TestHyperlink.java:50-92` | 첫 슬라이드의 두 URL과 두 번째 슬라이드의 Jakarta HSSF 표시문을 올바른 범위에 연결한다. | 표시문·슬라이드·대상 검사 3/3이 일치했다. | 통과했다. |
| 하이퍼링크 URL | `WithLinks.ppt`, PPT↔PPTX 8쌍 | 같은 POI 테스트와 OOXML 짝 출력 | 원본 URL을 보존하고 PPTX와 같은 `표시문 <대상>` 표기를 쓴다. | WithLinks 세 대상과 짝 비교 URL 16/16이 일치했다. | 통과했다. |
| 내부 하이퍼링크 | 대상 슬라이드가 확인되는 실물을 찾지 못했다. | 합성 ExHyperlink/InteractiveInfo 테스트만 존재한다. | 정적 슬라이드 ID를 최신 순서의 내부 출처로 연결한다. | 합성 테스트는 통과했다. 전체 표본에서 대상이 명시된 내부 슬라이드 링크와 action=3 이동 표본은 찾지 못했다. | 미검증이며 ⬜를 유지한다. |
| 표/그림 캡션 | 판단을 보류했다. | PPTX 작업의 판단을 따르라는 작업 지시가 적용된다. | 별도의 캡션 모델이 필요한지 공동 판정을 확인해야 한다. | 현재 워크트리에서 PPTX 작업의 확정 판정을 확인하지 못했다. | ⬜를 유지하고 오케스트레이터가 판정한다. |

`bug60993.ppt`의 표는 PPDrawing 위치 35134에 있다. 셀 경계 x는 `[1148,2149,4561,6268]`, y는 `[764,998,1231,1635,2295,2529,2763]`이다. spid 2058의 사각형은 두 열을, spid 2063의 사각형은 두 행을 덮는다. 표 격자는 실제 셀 경계로 만들었다. 별도의 행 높이 배열과 경계 간 1단위 차이를 임의 허용오차로 맞추지 않았다.

## 리뷰 지적별 검증

| 지적 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| P1 지속 디렉터리 반복 처리 | 합성 중복 ID·40편집 입력이다. | 디렉터리 오프셋과 모든 항목을 합산한다. | 재방문과 전역 예산으로 중단한다. | 100만 항목 입력은 경고 후 0.0442초에 종료했다. | 통과했다. |
| P1 빈 그룹·댓글 탐색 증폭 | 합성 빈 그룹 100개와 동일 객체 100참조이다. | 처리 횟수를 계측했다. | 동일 도형·댓글 트리를 재탐색하지 않는다. | 캐시와 전역 방문 예산을 적용했다. | 통과했다. |
| P2 손상 슬라이드 참조 | 합성 최신 편집·누락 ID이다. | 최신 persist 객체 바이트가 정답이다. | Recovered와 최신 마스터·노트를 보존하고 Old edit는 제외한다. | 모두 일치했다. 후보가 여럿이면 추정하지 않는다. | 통과했다. |
| P2 주석 | `WithComments.ppt`, `45543.ppt`, LibreOffice `pass/hang-22.ppt`이다. | `extractor/TestExtractor.java:254-274`와 원시 CString instance 0·1, PPTX 출력 계약이다. | 본문 다섯 구절과 작성자 두 명을 보존한다. | 7/7 검사와 여러 줄 단일 Paragraph 검사가 통과했다. | 통과했다. |
| P2 링크 위치 | 합성 ExHyperlink의 instance 1·3이다. | 리뷰가 제시한 LocationAtom과 합성 원시 바이트이다. | 외부 주소의 앵커와 현재 문서 위치를 보존한다. | URL#section 및 내부 slide 대상이 일치했다. | 단위 검증만 통과했으며 실물 location 표본은 미확보다. |
| P2 텍스트 메모리 증폭 | 합성 700만 문자이다. | tracemalloc의 추가 할당을 실측했다. | 문자당 정수 배열을 없애고 빈 조각도 제한한다. | CR 반복 약 14MB, abCR 반복 약 29MB이며 조각 100,000개에서 경고했다. | 통과했다. |
| P3 필드 문자 | `datetime.ppt`, `npe.ppt`이다. | 원시 MC 레코드와 npe 14번 슬라이드의 Star Reduction 설명이다. | datetime 필드 13개와 npe 필드 51개를 제거하며 npe의 실제 별표 셀 15개는 보존한다. | 필드 표식이 사라지고 실제 셀 15개는 모두 14번 슬라이드에 남았다. | 통과했다. 저장값 없는 동적 날짜의 표시 자체는 미검증이다. |
| P3 치환 뒤 범위 | 합성 10번 슬라이드이다. | UTF-16 링크·문단 구간을 직접 조립했다. | 번호 확장 뒤 링크 전체와 글머리표를 보존한다. | `10`과 `• Link <https://example.com>`가 일치했다. | 통과했다. |
| P3 마스터 바닥글 | `headers_footers.ppt` 및 합성 PPT·PPTX 짝이다. | `model/TestHeadersFooters.java:82-89`, PPTXReader.read와 레이아웃 placeholder 필터이다. | PPTX와 같이 상속 placeholder를 제외하며 직접 저장된 도형 필드는 표시한다. | 두 형식 모두 상속 바닥글을 제외했다. 로컬 저장 필드는 합성 검사에서 치환했다. | 누락 현상은 재현되지만 출력 계약 위반이라는 해석은 반박한다. |
| P3 WordArt | `41246-2.ppt`, `bug60345_Jankovic_final_Retreat_2002.ppt`, LibreOffice `tdf143315-WordartWithoutBullet.ppt`이다. | 원시 OfficeArt 0x00C0이다. 각 FOPT 위치는 75287, 91752·91900·92044·92188, 63420이다. | Fin, SEA 두 개, STAg 두 개, בדיקה를 추출한다. | 세 표본의 문자열과 개수가 모두 일치했다. | 통과했다. |
| P3 인접 서식 | `42474-2.ppt`이다. | 원시 Given X = logb(x) 문구와 글자 크기별 런이다. | 연속된 bold 표기를 한 번만 감싼다. | Markdown 검사 1/1이 통과하고 모델 글자 크기도 유지했다. | 통과했다. |
| P3 제목 앞 개행 | `54111.ppt`이다. | 원시 제목의 앞쪽 수직 탭이다. | 제목은 Table sample이어야 한다. | 검사 1/1이 통과했다. | 통과했다. |
| P3 앞쪽 공백 | `bug60345_suba.ppt`이다. | 원시 문단의 정렬용 공백이다. | 본문이 Markdown 코드 블록으로 바뀌지 않아야 한다. | 네 칸 공백·탭으로 시작하는 문단이 0개이다. | 통과했다. |
| P3 확장 서식 마스크 | 합성 알려진 런 뒤 미지원 마스크이다. | 이미 해석 완료한 PF·CF 바이트 경계이다. | 모르는 런 때문에 이전 정상 서식까지 버리지 않는다. | 이전 정상 런과 PF를 보존하고 이후는 경고와 일반 텍스트로 복구했다. | 전체 폐기 결함은 수정했다. 확장 필드의 길이와 정상 해석은 미검증이다. |
| P3 Symbol·Wingdings | `49541_symbol_map.ppt`, `with_textbox.ppt`, `60003.ppt`이다. | `usermodel/TestBugs.java:508-516`, 원시 fontRef·D8 글머리와 설치 글꼴의 문자 대응이다. | ≥75 years 및 ➢ 글머리 1개·2개이다. | 검사 3/3이 일치했다. | 통과했다. |
| P3 Reader 연결 테스트 | Current User·Pictures를 노출하는 합성 FakeOle이다. | 실제 PPTReader.read 호출이다. | 최신 편집과 지연 PNG 바이트를 받는다. | 기존 코드에서 이미 통과하며 회귀 테스트를 추가했다. | 구현 결함은 재현되지 않았다. |

마스터 바닥글의 `per-slide footer`와 `custom date format`은 HeaderFooterContainer의 CString에 실제 존재하지만, 이를 표시하는 도형은 마스터 placeholder이다. 현재 PPTX 리더는 상속 레이아웃의 모든 placeholder를 제외한다. 따라서 이 한 항목은 오케스트레이터의 같은 출력 계약 지시에 따라 누락을 고의로 유지했다. 합성 OOXML을 실제 PPTXReader.read로 읽어 같은 결과를 확인했으며, 임의로 일반 본문 문단을 추가하지 않았다.

확장 마스크 pp10ext·pp11ext·newEA/cs는 POI 145개와 LibreOffice 67개의 현재 표본에서 확인하지 못했다. 네트워크를 사용하지 않았고 로컬 명세도 확보하지 못했으므로 속성 길이를 추정해 건너뛰지 않는다. 정상 완료한 이전 런의 보존은 검증했지만 해당 확장 속성의 정상 지원이라고 주장하지 않는다.

## 최종 전수 결과

POI 145개와 LibreOffice 67개에서 미처리 예외는 각각 0개이며, ERR 파일은 이전과 동일한 8개와 14개이다. 신규 ERR 파일은 없다. POI 경고 파일은 34개에서 37개로 늘었고 LibreOffice 경고 파일은 11개로 유지했다. 새 경고는 저장된 표시값이 없는 필드이다. LibreOffice 경로의 실제 파일은 직계 29개, pass 37개, fail 1개이며 총 67개이다. 리뷰의 72개를 실측 수치로 사용하지 않았다.

기존 기능 검사 34/34와 추가 리뷰 검사 18/18이 통과했다. 기존 POI 저장 순서 검사는 PPTX의 좌표 읽기 순서 계약과 달랐으므로 내용 집합 검사로 정정했고 별도의 좌표 순서 검사를 유지했다. 문단 및 서식 런 개수는 공백·필드 정리에 따라 달라지므로 기능 개수 변화만으로 회귀를 판정하지 않았다. 표·셀·그림·링크·노트·슬라이드 개수는 감소하지 않았다. 감소가 있는 POI 38파일은 앞공백 정규화와 비슬라이드번호 필드 치환만 메모리상 비활성화한 대조실험에서 모두 감소가 사라졌다. 이 대조는 전체 145개에 수행했고 `.codex-work/ppt-fix-decrease-audit.json`에 기록했다. 이 전수 검사는 생존성과 선택된 정답을 검증하며 모든 글자에 대한 무회귀 증명을 의미하지 않는다.

PPT↔PPTX 8쌍을 재실행했고 예외 0개, 평균 토큰 유사도 0.6406318918로 기존 결과가 유지되었다. 슬라이드는 82/82, 표 3/4, 셀 40/62, 병합 2/3, 서식 런 524/848, 링크 URL 16/16, 노트 38/42이다. 그림은 PPT 72개와 PPTX 24개로 이전의 과잉 배치 가능성이 그대로 남아 있다. 전체 수치는 `2026-10-02-ppt-real-docs.md`와 최종 JSON에 기록했다.

전체 단위 테스트는 1,944개 통과, 24개 건너뜀, 기존 예상 실패 14개이며 실제 실패는 0개이다. 기존 HEAD 테스트 단언을 변경하지 않았다. 공유 변경은 `dochan/output/markdown.py`의 PPT 전용 인접 서식 병합뿐이며 모델 런과 글자 크기는 보존한다. 새 의존성을 추가하지 않았다.

## 재현 명령

```sh
/usr/bin/python3 -m scripts.probe_ppt_corpus --corpus corpus/poi-src/test-data/slideshow --output .codex-work/ppt-fix-poi-final.json --verify-features
/usr/bin/python3 -m scripts.probe_ppt_corpus --corpus corpus/lo-src/sd/qa/unit/data/ppt --recursive --output .codex-work/ppt-fix-lo-final.json
/usr/bin/python3 -m scripts.probe_ppt_review --poi corpus/poi-src/test-data/slideshow --lo corpus/lo-src/sd/qa/unit/data/ppt --output .codex-work/ppt-fix-review-final.json
/usr/bin/python3 -m scripts.compare_office_pairs corpus/poi-src/test-data/slideshow --output .codex-work/ppt-fix-pairs-final.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

최종 테스트 로그는 `.codex-work/ppt-fix-full-tests-final.log`이다. 문서의 한계는 중첩 표·실제 OCR·내부 이동 링크의 실물 미검증, 동적 날짜의 표시값 미확보, 마스터 전체 문자 서식 상속, 확장 서식 마스크의 정상 해석이다. 이 한계를 숨기기 위해 README 칸을 올리지 않았다.
