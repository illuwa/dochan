# PPT 구조 해석 실물 검증

2026년 10월 2일 `illuwa/w-ppt` 워크트리에서 Apache POI 공개 `test-data/slideshow`를 읽기 전용으로 검사했다. 표본 파일을 저장소로 복사하지 않았다. 구현에는 기존 OfficeArt 파서와 기존 모델을 사용했으며, POI 구현을 읽거나 번역하지 않았다. POI 테스트의 기대값과 공개 파일의 원시 레코드·좌표를 검증 근거로 사용했다. 네트워크를 사용하지 않았고, 로컬 Microsoft 명세 원문을 확보하지 못했으므로 명세 전체에 대한 적합성 인증을 주장하지 않는다.

최신 `CurrentUserAtom`의 편집 위치에서 `UserEditAtom` 체인을 역순으로 읽고, 지속 객체 ID마다 처음 만난 최신 위치를 채택한다. `DocumentContainer`의 `SlideListWithTextContainer` 인스턴스 0·1·2를 각각 슬라이드·마스터·노트로 연결한다. `PPDrawing`의 OfficeArt 도형, 텍스트 런, 표 프레임, 그림과 링크를 해석한다. 지속 구조를 시작할 수 없으면 기존 텍스트 복구 경로를 사용한다. 개별 참조가 손상된 슬라이드는 목록 위치와 남아 있는 아웃라인을 유지하고 경고한다.

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

## 전체 코퍼스와 짝 비교

145개 `.ppt`에서 문서 단위 미처리 예외는 변경 전후 모두 0개였다. ERR가 있는 파일은 기존의 동일한 8개였으며 새 ERR 파일은 0개였다. 리뷰 반영 후 경고가 있는 파일은 37개였다. 저장된 표시값이 없는 필드를 경고하면서 세 파일이 늘었다. 경고는 손상 레코드, 누락 참조, 지원하지 않는 서식 마스크와 그림 데이터 등을 기록한다. 이 검사는 파싱 생존성과 선택된 기대값을 검증하며 모든 글자에 대한 무회귀 증명은 아니다.

리뷰 반영 후 기능 프로브 34개가 모두 일치했다. 이전 프로브가 POI의 텍스트박스 저장 순서를 출력 계약으로 잘못 가정했던 기대값을 정정했다. POI가 단언한 네 문구의 내용 집합을 검사하고, 별도로 원시 좌표 및 PPTX와 같은 읽기 순서를 검사한다. 구현을 기대값에 맞춰 재정렬하지 않았다.

실제 같은 이름의 PPT↔PPTX 짝은 예상 12쌍이 아니라 8쌍이었다. 제외한 짝은 없으며 측정 오류도 없었다. 평균 토큰 유사도는 0.3129에서 0.6406으로 바뀌었다.

| 공개 PPT 파일 | 변경 전 토큰 유사도 | 변경 후 토큰 유사도 |
|---|---:|---:|
| `SampleShow.ppt` | 0.6429 | 0.9624 |
| `WithMaster.ppt` | 0.3733 | 0.9032 |
| `alterman_security.ppt` | 0.0858 | 0.9458 |
| `backgrounds.ppt` | 0.0351 | 0.0000 |
| `bug58144-headers-footers-2007.ppt` | 0.4308 | 0.6667 |
| `bug60993.ppt` | 0.4762 | 0.8000 |
| `customGeo.ppt` | 0.4589 | 0.8470 |
| `table_test.ppt` | 0.0000 | 0.0000 |

| 지표 | OOXML 정답 수 | PPT 출력 수 | 일치 수 | 회수율 |
|---|---:|---:|---:|---:|
| 슬라이드 | 82 | 82 | 82 | 100.00% |
| 표 | 4 | 3 | 3 | 75.00% |
| 유효 셀 | 62 | 40 | 40 | 64.52% |
| 병합 셀 | 3 | 2 | 2 | 66.67% |
| 서식 런 | 848 | 636 | 524 | 61.79% |
| 그림 배치 | 24 | 72 | 24 | 100.00% |
| 고유 그림 참조 | 12 | 36 | 12 | 100.00% |
| 그림 바이트 보유 배치 | 24 | 72 | 24 | 100.00% |
| 대체 텍스트 완전 일치 | 24 | 17 | 0 | 0.00% |
| 노트 전체 문자열 | 42 | 42 | 38 | 90.48% |
| 링크 URL | 16 | 16 | 16 | 100.00% |

그림 지표의 회수율 100%는 과잉 출력을 부정하지 않는다. PPT 마스터 그림을 각 슬라이드에 배치하면서 PPTX 리더보다 많은 배치를 출력했다. `customGeo`에는 OOXML 표 두 개 중 한 개만 복원되어 표·셀·병합 회수율이 완전하지 않다. 추가 한 개의 구조와 원본 짝의 차이는 후속 확인 대상으로 남긴다. 명시적 문자 서식은 복원하지만 마스터 문자 서식 전체를 상속하지 않으므로 서식 회수율도 제한된다.

대체 텍스트의 0/24는 설명이 전부 소실됐다는 뜻이 아니다. 기존 PPTX 리더는 설명과 도형 이름을 합쳐 alt에 넣지만 PPT는 원시 `wzDescription`만 넣는다. 위의 원시 설명 두 개가 정확히 보존되는지 별도로 검증했다. 노트의 남은 네 불일치에는 순서와 서식 표기가 포함된다. 예를 들어 headers-footers 표본은 PPTX가 `1 Notes footer Notes header`, PPT가 좌표 순서의 `Notes header Notes footer 1`을 출력한다.

`backgrounds.ppt`의 최신 슬라이드 네 개에서는 본문 텍스트가 없어 빈 슬라이드 네 개가 나온다. 이전 경로가 마스터 편집 안내 등까지 모았던 결과와 달라 유사도가 내려갔다. `table_test`는 빈 셀 표를 복원했지만 비교기의 텍스트 유사도는 계속 0이다. 이 두 수치를 개선율을 높이기 위해 제외하지 않았다.

## 재현과 검증 경계

다음 명령은 지정된 Python 3.9 환경에서 실행한다.

```sh
/usr/bin/python3 -m scripts.probe_ppt_corpus \
  --corpus corpus/poi-src/test-data/slideshow \
  --output .codex-work/ppt-corpus-final.json --verify-features
/usr/bin/python3 -m scripts.compare_office_pairs \
  corpus/poi-src/test-data/slideshow \
  --output .codex-work/ppt-pairs-final.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

단위 픽스처는 모두 테스트 코드에서 바이트를 조립한다. 최신 편집 우선, 순환 편집 차단, 손상 지속 객체, 노트 연결, 아웃라인 인덱스, UTF-16 런, 그룹 좌표·반전, 병합, 링크, BLIP와 OCR 연결을 검사한다. OCR 단위 테스트의 대체 함수는 호출 계약만 검증하며 실제 인식 성공의 근거로 쓰지 않았다. 기존 테스트의 단언은 변경하지 않았다.

레코드 총수 100,000개, 지속 객체 파싱 바이트 합계 128MiB, 편집 체인 4,096개, 그룹 깊이 32, 출력 도형·문단 각각 100,000개, 문서 출력 8,388,608자, 표당 격자 100,000칸과 문서 누적 200,000칸, 그림 배치 10,000개를 상한으로 둔다. OfficeArt 공용 BLIP의 이미지 바이트 제한도 적용한다. 링크 대상과 그림 설명의 출력 증폭도 문자 예산에 포함한다.

리뷰 반영 후 최종 전체 테스트는 1,944개 통과, 24개 건너뜀, 기존 예상 실패 14개이며 실제 실패는 0개이다. `git diff --check`도 통과했다. 공유 모델·OfficeArt·비교기는 변경하지 않았다. 공유 Markdown 출력기에 PPT 인접 동일 서식 런만 병합하는 처리를 추가했으며 모델의 글자 크기는 보존한다. README 체크는 변경하지 않았으며 지원 제안의 확정은 오케스트레이터가 수행한다.

리뷰별 재현과 최종 POI·LibreOffice 검증은 `2026-10-02-ppt-fix-real-docs.md`에 기록했다.
