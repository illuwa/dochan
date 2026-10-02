# PPTX 레이아웃·마스터 글자 서식 상속 실물 검증

2026-10-03에 공개 POI·LibreOffice 코퍼스의 PPTX 544개를 검사했다. 비교 기준 HEAD는 `63ab630386f426a6f3d81f738d515f0198d20e04`이다. 코퍼스는 읽기 전용으로 사용했으며 문서를 저장소에 복사하지 않았다. 다른 프로젝트의 구현 코드를 보거나 옮기지 않았다.

## 판정과 범위

슬라이드와 레이아웃의 `p:sp` 텍스트에 속성별 상속을 적용했다. `TextRun.bold`, `italic`, `underline`, `font_size_pt`, `superscript`, `subscript`를 재사용했다. 표 셀, SmartArt, 차트 텍스트와 발표자 노트는 기존 처리 경로를 유지한다. 글꼴, 자동 맞춤 축소, 문단 정렬, 상속된 글머리표, 취소선 상속은 이번 작업 범위가 아니다.

아래 표의 좌표는 슬라이드 번호만 1부터 시작하고 도형·문단·런 인덱스는 0부터 시작한다. 런 인덱스에는 문단 속성 노드도 포함하므로 XML 자식 순번이다. 정답은 원시 XML이며 PPT 리더 출력은 보조 비교값이다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| 굵게 상속 | LO `ShapeLineProperties.pptx` | slide1, 도형0/문단0/런1의 `Green`; master1의 `txStyles` `defRPr b="1"` | bold=true, 32pt이다. | bold=true, 32pt이다. | 통과했다. |
| 기울임 상속 | POI `WithMaster.pptx` | slide1, 도형1/문단0/런0의 `First page subtitle`; layout1의 `defRPr b="1" i="1"` | bold=true, italic=true이다. | 두 속성이 모두 true이다. | 통과했다. |
| 마스터 도형의 크기 | POI `WithMaster.pptx` | slide2, 도형2/문단0/런0의 `Footer from the master slide`; master1의 `defRPr sz="1200"` | 12pt이다. | 12pt이다. | 통과했다. |
| 마스터 txStyles의 크기 | POI `WithMaster.pptx` | slide1의 `First page title`; master1의 titleStyle `defRPr sz="4400"` | 44pt이다. | 44pt이다. | 통과했다. |
| 레이아웃 lstStyle의 크기 | LO `BoldonseFontEmbedded.pptx` | slide1의 `Test`; layout1의 `lstStyle/lvl1pPr/defRPr sz="6000"` | 60pt이다. | 60pt이다. | 통과했다. |
| 프레젠테이션 기본 기울임 | POI `alterman_security.pptx` | slide23, 도형1/문단0/런4의 `Notes`; presentation.xml의 defaultTextStyle `defRPr i="1"` | italic=true이다. | italic=true이다. | 통과했다. |
| 슬라이드 기본 굵게 | POI `bug65228.pptx` | slide1, 도형1/문단0/런1의 `März 2021`; slide의 `defRPr b="1"` | bold=true이다. | bold=true이다. | 통과했다. |
| 밑줄 상속의 켜짐 | 전체 공개 코퍼스 | 상속이 선택한 `defRPr`에서 `u!=none`인 양성 런은 0개였다. | 양성 실물 표본이 필요하다. | 합성 테스트만 통과했다. | 미검증이므로 ✅를 제안하지 않는다. |
| 위·아래첨자 상속의 켜짐 | 전체 공개 코퍼스 | 상속이 선택한 `defRPr`에서 `baseline!=0`인 양성 런은 0개였다. | 양성 실물 표본이 필요하다. | 합성 테스트만 통과했다. | 미검증이므로 ✅를 제안하지 않는다. |
| 직접 위첨자 | POI `WithMaster.pptx` | slide2의 `nd`; 직접 `rPr baseline="30000"` | superscript=true이다. | superscript=true이다. | 직접 지정은 통과했으며 상속 양성으로 세지 않는다. |
| 직접 아래첨자 | LO `n828390.pptx` | slide1의 `R`; 직접 `rPr baseline="-25000"` | subscript=true이다. | subscript=true이다. | 직접 지정은 통과했으며 상속 양성으로 세지 않는다. |

README의 현재 PPTX `서식 (bold/italic)` 칸은 이미 ✅이고 `스타일 상속` 칸은 —이다. README는 수정하지 않았다. 굵게·기울임·크기 상속에는 구현과 실물 근거가 있으나 모든 속성의 상속을 포괄하는 무조건적인 ✅는 제안하지 않는다. 오케스트레이터가 행의 범위를 정하고 양성 표본이 없는 밑줄·위아래첨자 상속을 별도로 표시해야 한다.

## 구현 전 측정

독립 프로브는 `xml.etree.ElementTree`로 ZIP 안의 XML을 직접 해석한다. 런타임 상속 해석기를 호출하지 않는다. 544개 중 530개는 원시 XML 전체를 읽을 수 있었고, 14개는 ZIP 형식 또는 CRC 오류 때문에 원시 검증에서 제외했다. 아래 수치는 문서를 끝까지 읽은 530개만 분모로 삼는다. 기본값이 존재한다는 사실은 해당 속성이 실제 런에 선택됐다는 뜻은 아니다.

| 기본값 위치 | 하나 이상 있는 덱 | b | i | u | sz | baseline |
|---|---:|---:|---:|---:|---:|---:|
| 마스터 도형·txStyles | 495 | 63 | 19 | 16 | 495 | 19 |
| 레이아웃 | 381 | 346 | 17 | 7 | 380 | 23 |
| 각 단계의 lstStyle | 422 | 370 | 22 | 18 | 421 | 23 |
| presentation defaultTextStyle | 456 | 6 | 7 | 5 | 455 | 2 |
| 슬라이드 기본값 | 20 | 7 | 3 | 3 | 19 | 3 |

원시 XML의 텍스트·필드·줄바꿈 런은 8,205개이며 예상 변경은 8,038개였다. 이 중 `defRPr` 상속 때문에 바뀌는 런은 3,498개이고, 직접 `rPr`의 미지원 속성을 새로 읽어서 바뀌는 런은 4,671개이다. 두 집합에 동시에 속하는 런이 131개이므로 합집합은 8,038개이다. 상속 변화의 속성별 수는 크기 3,369개, 굵게 208개, 기울임 123개이며 서로 중복될 수 있다.

## 상속 해석과 안전성

우선순위가 높은 쪽부터 런의 `rPr`, 해당 문단의 `pPr/defRPr`, 도형의 `lstStyle` 수준별 `defRPr`, 같은 자리표시자의 레이아웃, 마스터 도형, 마스터 `txStyles`, presentation의 `defaultTextStyle`을 선택한다. 각 목록 스타일에서는 `lvl1pPr`부터 `lvl9pPr`까지 해당 수준을 먼저 선택하고 `defPPr`로 누락 속성을 채운다. 속성별로 합성하므로 `b="0"`, `i="0"`, `u="none"`, `baseline="0"`도 상위 값을 명시적으로 해제한다.

형식 근거는 ECMA-376 Part 1의 PresentationML 자리표시자·텍스트 스타일과 DrawingML 텍스트 속성 구조이다. 이 실행에서는 네트워크를 사용하지 않았으며 위 표와 프로브에 기록한 원시 XML로 기대값을 확인했다. 임의의 문서별 예외나 측정치를 맞추기 위한 조건은 넣지 않았다.

슬라이드→레이아웃은 `idx`가 같아야 하며, 같은 인덱스에서 type의 정확 일치와 family 일치 순으로 선택한다. type이 생략됐으면 사용자 작업 지침에 따라 body를 기본으로 삼되, 같은 idx의 레이아웃에서 명시한 type을 찾아 txStyles를 선택한다. 마스터는 정확한 type을 먼저 찾고 `title/ctrTitle`, `body/subTitle/obj` family를 사용한다. 마스터 idx는 레이아웃 idx와 다를 수 있으므로 같은 type의 후보에서 동률을 해소하는 값으로 쓴다. `SampleShow.pptx`에서 레이아웃 날짜 자리표시자 idx=10과 마스터 idx=2가 대응하는 원시 XML을 확인했다.

조상 자리표시자 문단은 같은 수준의 첫 문단의 `pPr/defRPr`만 기본값으로 사용한다. 마스터에 적힌 안내 문구의 `rPr`와 `endParaRPr`는 실제 슬라이드 텍스트의 기본값으로 복사하지 않는다. 기존 수식 분리 과정이 문단 속성 노드를 제거하므로 원본 문단에서 상속을 계산한 뒤 모든 텍스트 조각에 전달한다. 제목 여부와 텍스트 순서는 이번에 바꾸지 않았다.

추가 스타일 로드는 최대 1,024개 파트와 누적 64MiB로 제한한다. 조상 도형·문단 탐색은 누적 100,000노드와 깊이 64로 제한하며 인덱스·수준별 문단 기본값을 캐시한다. 이 수치는 표시 규칙이 아닌 자원 방어 상한이다. 외부 관계를 열지 않고 기존 `OOXMLPackage`의 ZIP·XML 방어를 재사용한다. 손상·누락·상한 초과는 중복되지 않는 `WARN: PPTX text style ...` 진단으로 남기고 가능한 슬라이드 텍스트를 유지한다. XML 주석·처리명령도 별도 실패 테스트로 확인했다.

## 독립 대조와 한계

파일·슬라이드·파트·텍스트 키로 모호하지 않게 대조할 수 있는 7,793개 런은 여섯 모델 속성이 모두 일치했다. 동일 텍스트의 서식을 위치별로 구분할 수 없는 384개 런은 일치율 분모에서 제외했으며 28개 공백 런은 대응하는 출력이 없었다. 반복 텍스트를 서식에 맞춰 골라서 100%라고 판정하지 않았다.

초기 다중집합 대조에서는 8,173개가 일치했고 출력에서 제거된 공백 런이 32개였다. 그중 변경 대상은 29개여서 예상 변경 8,038개와 실제 변경 8,009개의 차이를 설명한다. 최종 엄격 대조에서는 공백 일부도 반복 텍스트의 모호한 그룹에 포함되므로 제외 집계가 달라진다. 모호한 그룹은 별도로 기록하며 전 런의 위치별 일치라고 주장하지 않는다.

독립 프로브는 `.//p:sp`를 조사하므로 AlternateContent의 선택되지 않은 분기가 있는 다른 입력에 대해서는 런타임과 대상 범위가 다를 수 있다. 명시적 type과 idx가 충돌한 실물 `slide-section-test.pptx`의 다섯 자리표시자는 모두 빈 문단이었다. 이런 후보는 프로브와 런타임 모두 거절한다. type이 생략된 `formatting-bullet-indent.pptx`에서는 idx를 통해 레이아웃 title에 연결했다. 현재 코퍼스에서 안전 대조한 런의 속성 불일치는 0개였으며, 이 한계를 합성 테스트의 상속 규칙 검증과 분리했다.

## PPT 짝 보조 비교

같은 이름의 PPT/PPTX 12쌍을 조사했다. 상속 전은 작업 시작 HEAD의 PPT 리더이고 상속 후는 `illuwa/w-legacy-docppt` 워크트리의 구현 스냅샷이다. 해당 브랜치의 커밋 HEAD와 아직 커밋되지 않은 워크트리 변경을 구분해 기록했다. 양쪽 형식에서 같은 텍스트가 여러 번 나오는 경우 모든 출현의 서식이 같을 때만 비교했으며, 정답은 계속 PPTX 원시 XML로 두었다.

| 공개 짝 이름 | 비교 가능 텍스트 | PPT 상속 전 일치 | PPT 상속 후 일치 | 해석 |
|---|---:|---:|---:|---|
| SampleShow | 7 | 1 | 7 | 제목 44pt와 본문 32pt가 원시 XML과 일치한다. |
| WithMaster | 7 | 2 | 7 | 레이아웃 굵게·기울임과 위첨자 지정이 일치한다. |
| alterman_security | 145 | 48 | 72 | 나머지 73개는 기울임이 다르므로 PPT를 정답으로 쓰지 않았다. |
| bug58144-headers-footers-2007 | 3 | 1 | 3 | 공통 텍스트의 여섯 속성이 일치한다. |
| customGeo | 206 | 111 | 170 | 나머지 36개는 크기가 달라 PPT를 정답으로 쓰지 않았다. |
| backgrounds, bug60993, loopNoPause, table_test, tdf105150, tdf115394, tdf79082 | 0 | 비교 불가 | 비교 불가 | 현재 범위에서 안전하게 대응시킬 공통 텍스트가 없었다. |

## 전체 출력 회귀

544개 모두 HEAD와 Markdown·JSON·본문 텍스트 SHA-256을 비교했다. 본문 텍스트 해시 변화는 **0개**이고 런 개수 변화도 **0개**이다. 서식 변화는 253개 파일의 8,009개 런이며 Markdown 28개와 JSON 254개가 달라졌다. JSON의 추가 1개는 손상된 마스터 CRC에 대한 경고가 추가된 파일이다. 크기만 바뀌는 경우 현재 Markdown 출력에는 차이가 없지만 JSON에는 반영된다.

| 변경 속성 | 실제 변경 런 수 |
|---|---:|
| font_size_pt | 8,007 |
| bold | 255 |
| italic | 125 |
| underline | 1 |
| superscript | 15 |
| subscript | 4 |

제목 문단에서 bold이며 줄바꿈이 들어 있는 런은 56개였으나 전부 공백만 있는 줄바꿈 런이었다. 현재 작성기는 이런 런에 강조 마커를 붙이지 않는다. `run.text.strip()` 내부에 줄바꿈이 남아 `**`가 줄을 넘는 실제 대상은 **0개 파일·0개 런·0줄**이었다. 출력 작성기는 수정하지 않았다.

각 변경 런의 속성별 근거 단계는 `.codex-work/pptx-master-final-probe/changed-runs.jsonl`에 남겼다. `evidence`는 slide/layout/master/txStyles/default를, `evidence_nodes`는 `rPr` 또는 `defRPr` 및 원본 XML 파트를 구분한다. 예상 변경에는 기존 공백 제거 대상도 포함되어 있으며 실제 파일별 변경은 아래 표와 `regression.json`에 기록했다.

## 재현 명령과 산출물

```sh
/usr/bin/python3 -m scripts.probe_pptx_master \
  corpus/poi-src \
  corpus/lo-src \
  --output .codex-work/pptx-master-final-probe \
  --baseline .codex-work/pptx-master-baseline.json \
  --legacy-worktree <PPT 상속 구현 브랜치 작업 트리>
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

HEAD 스냅샷은 구현 전에 저장했다. 원시 사전 측정은 `.codex-work/pptx-master-raw-preimplementation.json`, 최종 집계와 검증 제외 목록은 `pptx-master-final-probe/summary.json`과 `validation.json`, PPT 원시 참고 출력과 비교표는 같은 폴더의 `legacy-pairs.json`과 `legacy-comparison.json`에 있다. 코퍼스 내용과 이 중간 산출물은 커밋하지 않는다.

최종 전체 테스트는 **3319 passed, 24 skipped, 14 xfailed**로 끝났으며 신규 합성 테스트는 38개이다. `ruff check dochan scripts tests`와 `git diff --check`도 통과했다. 기존 테스트의 단언은 수정하지 않았다.

## 변경 파일별 회귀 표

아래 경로는 공개 코퍼스 루트 기준이다. 속성별 런 수는 중복될 수 있다. 변경되지 않은 나머지 290개 파일도 전체 비교에 포함했다.

| 공개 파일 | Markdown 변경 | JSON 변경 | 바뀐 런 | 사유 | XML 근거 단계 |
|---|---:|---:|---:|---|---|
| `lo-src/sd/qa/unit/data/BoldonseFontEmbedded.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | layout |
| `lo-src/sd/qa/unit/data/TextDistancesInsets3.pptx` | 아니오 | 예 | 39 | font_size_pt 39개 | txStyles |
| `lo-src/sd/qa/unit/data/TextFittingComparisonWithMSO_1.pptx` | 아니오 | 예 | 1072 | font_size_pt 1072개 | slide |
| `lo-src/sd/qa/unit/data/TextFittingComparisonWithMSO_2.pptx` | 아니오 | 예 | 378 | font_size_pt 378개 | slide |
| `lo-src/sd/qa/unit/data/TextFittingComparisonWithMSO_3.pptx` | 아니오 | 예 | 366 | font_size_pt 366개 | slide |
| `lo-src/sd/qa/unit/data/TextFittingComparisonWithMSO_TopBottomMiddleAlignment.pptx` | 아니오 | 예 | 15 | font_size_pt 15개 | slide |
| `lo-src/sd/qa/unit/data/n759180.pptx` | 아니오 | 예 | 7 | font_size_pt 7개 | slide |
| `lo-src/sd/qa/unit/data/n819614.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/n902652.pptx` | 아니오 | 예 | 6 | font_size_pt 6개 | txStyles |
| `lo-src/sd/qa/unit/data/ppt/placeholder-priority.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | layout |
| `lo-src/sd/qa/unit/data/pptx/3columns.pptx` | 아니오 | 예 | 397 | font_size_pt 397개 | layout |
| `lo-src/sd/qa/unit/data/pptx/NumberedList-12ab-ab-34.pptx` | 아니오 | 예 | 9 | font_size_pt 9개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/ShapeLineProperties.pptx` | 예 | 예 | 37 | bold 24개, font_size_pt 37개 | txStyles, layout, slide |
| `lo-src/sd/qa/unit/data/pptx/ShapePlusImage.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | slide |
| `lo-src/sd/qa/unit/data/pptx/ShapeTextInflateTop.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/TextFittingStored.pptx` | 아니오 | 예 | 107 | font_size_pt 107개 | txStyles, slide |
| `lo-src/sd/qa/unit/data/pptx/accent-color.pptx` | 아니오 | 예 | 5 | font_size_pt 5개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/bnc584721_1_2.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/bnc584721_4.pptx` | 아니오 | 예 | 12 | font_size_pt 12개 | master, txStyles |
| `lo-src/sd/qa/unit/data/pptx/bnc862510_6.pptx` | 아니오 | 예 | 7 | font_size_pt 7개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/bnc862510_7.pptx` | 아니오 | 예 | 5 | font_size_pt 5개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/bnc870233_1.pptx` | 예 | 예 | 2 | bold 1개, font_size_pt 2개, italic 1개 | layout |
| `lo-src/sd/qa/unit/data/pptx/bnc880763.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/bnc887230.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/bnc904423.pptx` | 예 | 예 | 36 | bold 36개, font_size_pt 36개 | txStyles, layout |
| `lo-src/sd/qa/unit/data/pptx/bullet-indent.pptx` | 아니오 | 예 | 11 | font_size_pt 11개 | slide |
| `lo-src/sd/qa/unit/data/pptx/bulletColor.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/bulletMarginAndIndent.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/content-placeholder-cases.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/crop-position.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/custgeom-nofill-path.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | layout |
| `lo-src/sd/qa/unit/data/pptx/custgeom-overlapping-contours.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | layout |
| `lo-src/sd/qa/unit/data/pptx/custgeom-placeholder.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | layout |
| `lo-src/sd/qa/unit/data/pptx/customxml.pptx` | 아니오 | 예 | 5 | font_size_pt 5개 | slide |
| `lo-src/sd/qa/unit/data/pptx/fdo83751.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/font-scale.pptx` | 아니오 | 예 | 5 | font_size_pt 5개 | slide, txStyles |
| `lo-src/sd/qa/unit/data/pptx/formatting-bullet-indent.pptx` | 아니오 | 예 | 14 | font_size_pt 14개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/group.pptx` | 아니오 | 예 | 26 | font_size_pt 26개 | slide |
| `lo-src/sd/qa/unit/data/pptx/hyperlinkOnImage.pptx` | 아니오 | 예 | 5 | font_size_pt 5개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/hyperlinktest.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | slide |
| `lo-src/sd/qa/unit/data/pptx/layout-clrmap-override.pptx` | 아니오 | 예 | 6 | font_size_pt 6개 | slide |
| `lo-src/sd/qa/unit/data/pptx/master-slides.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | layout |
| `lo-src/sd/qa/unit/data/pptx/multicol.pptx` | 아니오 | 예 | 28 | font_size_pt 28개 | slide |
| `lo-src/sd/qa/unit/data/pptx/multiplelayoutfooter.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | master |
| `lo-src/sd/qa/unit/data/pptx/n778859.pptx` | 아니오 | 예 | 16 | font_size_pt 16개 | slide, txStyles |
| `lo-src/sd/qa/unit/data/pptx/n828390.pptx` | 예 | 예 | 3 | font_size_pt 3개, subscript 1개 | txStyles, slide |
| `lo-src/sd/qa/unit/data/pptx/n828390_2.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | slide, txStyles |
| `lo-src/sd/qa/unit/data/pptx/n828390_3.pptx` | 예 | 예 | 5 | font_size_pt 5개, subscript 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/n83889.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/n862510_1.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide |
| `lo-src/sd/qa/unit/data/pptx/n862510_4.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/n90255.pptx` | 아니오 | 예 | 10 | font_size_pt 10개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/numfmt.pptx` | 아니오 | 예 | 9 | font_size_pt 9개 | slide |
| `lo-src/sd/qa/unit/data/pptx/ooxtheme.pptx` | 아니오 | 예 | 13 | font_size_pt 13개 | layout, txStyles |
| `lo-src/sd/qa/unit/data/pptx/open-as-read-only.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/paraMarginAndIndentation.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/pic-placeholder-with-text.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/picture-placeholder-one-layout.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | layout |
| `lo-src/sd/qa/unit/data/pptx/presLeftAlign.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/rightToLeftParagraph.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide |
| `lo-src/sd/qa/unit/data/pptx/shape-soft-edges.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/shape-text-glow-effect.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/shape-text-rotate.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/slide-section-test.pptx` | 아니오 | 예 | 8 | font_size_pt 8개 | slide |
| `lo-src/sd/qa/unit/data/pptx/slide-sections.pptx` | 예 | 예 | 51 | bold 6개, font_size_pt 51개 | layout, txStyles, slide |
| `lo-src/sd/qa/unit/data/pptx/slidenum_field.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/smartart-picture-strip.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf100065.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf102261_testParaTabStopDefaultDistance.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf103347.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf103477.pptx` | 아니오 | 예 | 12 | font_size_pt 12개 | layout, txStyles, slide |
| `lo-src/sd/qa/unit/data/pptx/tdf103800.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf104201.pptx` | 아니오 | 예 | 14 | font_size_pt 14개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf104722.pptx` | 아니오 | 예 | 6 | font_size_pt 6개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf104786.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf104788.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf104789.pptx` | 아니오 | 예 | 5 | font_size_pt 5개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf106638.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | slide, master |
| `lo-src/sd/qa/unit/data/pptx/tdf111786.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf111789.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf112334.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf113198.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf113818-swivel.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf113822underline.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf114845_rotateShape.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf114848.pptx` | 예 | 예 | 47 | font_size_pt 47개, bold 2개 | txStyles, slide, master, layout |
| `lo-src/sd/qa/unit/data/pptx/tdf114913.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf115394-zero.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | layout |
| `lo-src/sd/qa/unit/data/pptx/tdf115394.pptx` | 아니오 | 예 | 8 | font_size_pt 8개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf116350-texteffects.pptx` | 아니오 | 예 | 20 | font_size_pt 20개 | txStyles, slide |
| `lo-src/sd/qa/unit/data/pptx/tdf118776.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf119087.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | 손상 master |
| `lo-src/sd/qa/unit/data/pptx/tdf119118.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf119187.pptx` | 아니오 | 예 | 9 | font_size_pt 9개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf119649.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf120028.pptx` | 예 | 예 | 12 | font_size_pt 12개, bold 8개 | slide, txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf123684.pptx` | 아니오 | 예 | 6 | font_size_pt 6개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf124457.pptx` | 아니오 | 예 | 8 | font_size_pt 8개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf125071.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | layout, txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf125573_FontWorkScaleX.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf126234.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf126324.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf127129.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf128206.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf128212.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf128213-shaperot.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf128213.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf128550.pptx` | 아니오 | 예 | 7 | font_size_pt 7개 | txStyles, layout |
| `lo-src/sd/qa/unit/data/pptx/tdf128684.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf129686.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf130058.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | master |
| `lo-src/sd/qa/unit/data/pptx/tdf131390.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | layout, txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf131554.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf132282.pptx` | 예 | 예 | 7 | font_size_pt 7개, bold 6개 | layout |
| `lo-src/sd/qa/unit/data/pptx/tdf134862.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf135843_export.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | master, slide |
| `lo-src/sd/qa/unit/data/pptx/tdf136830.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf137367.pptx` | 아니오 | 예 | 12 | font_size_pt 12개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf138148.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf140852.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide, txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf140865Wordart3D.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf141704.pptx` | 아니오 | 예 | 38 | font_size_pt 38개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf142590.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | layout, txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf142645.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | layout |
| `lo-src/sd/qa/unit/data/pptx/tdf142648.pptx` | 아니오 | 예 | 38 | font_size_pt 38개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf142716.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf142913.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | layout, txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf142915.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf143126.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf143129.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | txStyles, slide |
| `lo-src/sd/qa/unit/data/pptx/tdf143624.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf144616.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf144918.pptx` | 아니오 | 예 | 8 | font_size_pt 8개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf145162.pptx` | 아니오 | 예 | 16 | font_size_pt 16개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf146223.pptx` | 아니오 | 예 | 9 | font_size_pt 9개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf147121.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf147586.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf148685.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf148810_PARA_OUTLLEVEL.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf148965.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf148966.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf149314.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf149588_transparentSolidFill.pptx` | 아니오 | 예 | 5 | font_size_pt 5개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf149961-autofitIndentation.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf150719.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | layout |
| `lo-src/sd/qa/unit/data/pptx/tdf150770.pptx` | 아니오 | 예 | 28 | font_size_pt 28개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf151547-transparent-white-text.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf153036_resizedConnectorL.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf154363.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf157216.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf157285.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | layout |
| `lo-src/sd/qa/unit/data/pptx/tdf157529.pptx` | 아니오 | 예 | 6 | font_size_pt 6개 | slide, txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf157740.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf158512.pptx` | 아니오 | 예 | 67 | font_size_pt 67개 | layout, txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf160487.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf160490.pptx` | 아니오 | 예 | 9 | font_size_pt 9개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf160591.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf162283.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf165261.pptx` | 아니오 | 예 | 7 | font_size_pt 7개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf165321.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf165341.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | default |
| `lo-src/sd/qa/unit/data/pptx/tdf165732.pptx` | 아니오 | 예 | 10 | font_size_pt 10개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf168835.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | slide, txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf169524.pptx` | 아니오 | 예 | 12 | font_size_pt 12개, bold 2개 | slide, master |
| `lo-src/sd/qa/unit/data/pptx/tdf169781.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf169825_vertical_layouts.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf44223.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf50499.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf51340.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf54037.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf59323.pptx` | 아니오 | 예 | 9 | font_size_pt 9개 | master |
| `lo-src/sd/qa/unit/data/pptx/tdf65724.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf79082.pptx` | 아니오 | 예 | 10 | font_size_pt 10개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf89927.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf89928-blackWhiteEffectThreshold.pptx` | 아니오 | 예 | 6 | font_size_pt 6개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf90626.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf91378.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf92222.pptx` | 아니오 | 예 | 6 | font_size_pt 6개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf93097.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/tdf93868.pptx` | 아니오 | 예 | 6 | font_size_pt 6개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf95932.pptx` | 예 | 예 | 4 | bold 2개, font_size_pt 4개 | layout |
| `lo-src/sd/qa/unit/data/pptx/tdf96061.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide |
| `lo-src/sd/qa/unit/data/pptx/tdf98603.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide |
| `lo-src/sd/qa/unit/data/pptx/testShapeAutofit.pptx` | 아니오 | 예 | 26 | font_size_pt 26개 | txStyles |
| `lo-src/sd/qa/unit/data/pptx/trailing-paragraphs.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/sd/qa/unit/data/strict_ooxml.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | 손상 master |
| `lo-src/sd/qa/unit/data/theme.pptx` | 아니오 | 예 | 9 | font_size_pt 9개 | txStyles |
| `lo-src/sd/qa/unit/tiledrendering/data/tdf81754.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/svx/qa/unit/data/0-width-text-wrap.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/svx/qa/unit/data/3d_rotated_text.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/svx/qa/unit/data/auto-height-multi-col-shape.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide, txStyles |
| `lo-src/svx/qa/unit/data/clip-vertical-overflow.pptx` | 아니오 | 예 | 39 | font_size_pt 39개 | txStyles |
| `lo-src/svx/qa/unit/data/shadow-scale-origin.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/svx/qa/unit/data/tdf126060_3D_Z_Rotation.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `lo-src/svx/qa/unit/data/tdf145004_gap_by_ScaleX.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | slide |
| `lo-src/svx/qa/unit/data/tdf148000_CurvedTextWidth.pptx` | 아니오 | 예 | 10 | font_size_pt 10개 | slide |
| `lo-src/svx/qa/unit/data/tdf148000_EOLinCurvedText.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | slide |
| `lo-src/svx/qa/unit/data/tdf150020-shadow-alignment.pptx` | 아니오 | 예 | 9 | font_size_pt 9개 | txStyles |
| `lo-src/svx/qa/unit/data/tdf165521_fixedCellHeight.pptx` | 아니오 | 예 | 7 | font_size_pt 7개 | slide |
| `poi-src/test-data/slideshow/2411-Performance_Up.pptx` | 아니오 | 예 | 301 | font_size_pt 301개 | txStyles, slide, master |
| `poi-src/test-data/slideshow/45541_Footer.pptx` | 예 | 예 | 69 | font_size_pt 69개, bold 3개 | txStyles, slide |
| `poi-src/test-data/slideshow/45541_Header.pptx` | 예 | 예 | 95 | font_size_pt 95개, bold 3개 | txStyles, slide |
| `poi-src/test-data/slideshow/45545_Comment.pptx` | 예 | 예 | 76 | font_size_pt 76개, bold 3개 | txStyles, slide |
| `poi-src/test-data/slideshow/49386-null_dates.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `poi-src/test-data/slideshow/56812.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `poi-src/test-data/slideshow/60810.pptx` | 예 | 예 | 262 | bold 31개, font_size_pt 262개 | layout, slide, txStyles, master |
| `poi-src/test-data/slideshow/ArtisticEffectSample.pptx` | 예 | 예 | 6 | font_size_pt 6개, bold 1개 | txStyles, slide, layout |
| `poi-src/test-data/slideshow/KEY02.pptx` | 아니오 | 예 | 10 | font_size_pt 10개 | layout, slide |
| `poi-src/test-data/slideshow/LIBRE_OFFICE-100610-0.pptx` | 아니오 | 예 | 11 | font_size_pt 11개 | slide |
| `poi-src/test-data/slideshow/OverlappingRelations.pptx` | 아니오 | 예 | 6 | font_size_pt 6개 | txStyles |
| `poi-src/test-data/slideshow/SampleShow.pptx` | 아니오 | 예 | 7 | font_size_pt 7개 | txStyles, slide |
| `poi-src/test-data/slideshow/WithMaster.pptx` | 예 | 예 | 8 | font_size_pt 8개, bold 4개, italic 4개, superscript 1개 | txStyles, layout, slide, master |
| `poi-src/test-data/slideshow/aascu.org_hbcu_leadershipsummit_cooper_.pptx` | 예 | 예 | 173 | italic 1개, font_size_pt 173개, bold 50개, superscript 1개 | slide, txStyles, master |
| `poi-src/test-data/slideshow/aascu.org_workarea_downloadasset.aspx_id=5864.pptx` | 예 | 예 | 382 | font_size_pt 382개, superscript 6개, bold 5개, underline 1개 | slide, default, txStyles |
| `poi-src/test-data/slideshow/ae.ac.uaeu.faculty_nafaachbili_GeomLec1.pptx` | 예 | 예 | 118 | font_size_pt 118개, bold 10개, superscript 1개 | layout, slide, txStyles |
| `poi-src/test-data/slideshow/alterman_security.pptx` | 예 | 예 | 216 | italic 116개, font_size_pt 216개 | slide, default, master, txStyles |
| `poi-src/test-data/slideshow/aptia.pptx` | 예 | 예 | 65 | font_size_pt 65개, bold 9개 | slide, txStyles |
| `poi-src/test-data/slideshow/at.ecodesign.www_downloads_Vertiefungsvortrag_elektronik.pptx` | 아니오 | 예 | 153 | font_size_pt 153개 | slide, txStyles |
| `poi-src/test-data/slideshow/au.asn.aes.www_conferences_2011_presentations_Fri_20Room4Level4_20930_20Maloney.pptx` | 예 | 예 | 247 | bold 30개, font_size_pt 247개 | layout, txStyles, master, slide |
| `poi-src/test-data/slideshow/backgrounds.pptx` | 아니오 | 예 | 16 | font_size_pt 16개 | txStyles |
| `poi-src/test-data/slideshow/bar-chart.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `poi-src/test-data/slideshow/bug58144-headers-footers-2007.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles, master |
| `poi-src/test-data/slideshow/bug60499.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `poi-src/test-data/slideshow/bug62513.pptx` | 아니오 | 예 | 140 | font_size_pt 140개 | txStyles, slide, layout |
| `poi-src/test-data/slideshow/bug62736.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | layout |
| `poi-src/test-data/slideshow/bug63290.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | slide |
| `poi-src/test-data/slideshow/bug64693.pptx` | 아니오 | 예 | 6 | font_size_pt 6개 | layout |
| `poi-src/test-data/slideshow/bug65228.pptx` | 예 | 예 | 3 | bold 2개, font_size_pt 3개 | master, slide |
| `poi-src/test-data/slideshow/bug65523.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `poi-src/test-data/slideshow/bug65673.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | layout |
| `poi-src/test-data/slideshow/ca.ubc.cs.people_~emhill_presentations_HowWeRefactor.pptx` | 아니오 | 예 | 889 | font_size_pt 889개 | layout, slide, master, txStyles |
| `poi-src/test-data/slideshow/copy-slide-demo.pptx` | 아니오 | 예 | 2 | font_size_pt 2개 | layout |
| `poi-src/test-data/slideshow/crash-57308ca363f5b71763c489d1b432aff009d4bc4f.pptx` | 아니오 | 예 | 0 |  마스터 CRC 경고를 추가했다. | 손상 master |
| `poi-src/test-data/slideshow/customGeo.pptx` | 예 | 예 | 334 | font_size_pt 334개, bold 10개 | txStyles, slide, master, layout |
| `poi-src/test-data/slideshow/ececapstonespring2012.pptx` | 아니오 | 예 | 144 | font_size_pt 144개 | slide |
| `poi-src/test-data/slideshow/highlight-test-case.pptx` | 아니오 | 예 | 10 | font_size_pt 10개 | txStyles |
| `poi-src/test-data/slideshow/keyframes.pptx` | 아니오 | 예 | 486 | font_size_pt 486개 | slide, layout, default |
| `poi-src/test-data/slideshow/layouts.pptx` | 예 | 예 | 61 | font_size_pt 61개, bold 5개 | txStyles, layout, master |
| `poi-src/test-data/slideshow/line-chart.pptx` | 아니오 | 예 | 4 | font_size_pt 4개 | txStyles |
| `poi-src/test-data/slideshow/minimal-gradient-fill-issue.pptx` | 아니오 | 예 | 12 | font_size_pt 12개 | txStyles |
| `poi-src/test-data/slideshow/pie-chart.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `poi-src/test-data/slideshow/placeholder-layout-color.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | layout |
| `poi-src/test-data/slideshow/pptx2svg.pptx` | 예 | 예 | 33 | font_size_pt 33개, superscript 1개, subscript 1개 | txStyles, slide |
| `poi-src/test-data/slideshow/radar-chart.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `poi-src/test-data/slideshow/rain.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | layout |
| `poi-src/test-data/slideshow/sample.pptx` | 아니오 | 예 | 8 | font_size_pt 8개 | txStyles |
| `poi-src/test-data/slideshow/scatter-chart.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `poi-src/test-data/slideshow/shapes.pptx` | 아니오 | 예 | 7 | font_size_pt 7개 | txStyles |
| `poi-src/test-data/slideshow/smartart-simple.pptx` | 아니오 | 예 | 8 | font_size_pt 8개 | slide |
| `poi-src/test-data/slideshow/templatePPTWithOnlyOneText.pptx` | 아니오 | 예 | 1 | font_size_pt 1개 | txStyles |
| `poi-src/test-data/slideshow/testPPT.pptx` | 아니오 | 예 | 16 | font_size_pt 16개 | txStyles |
| `poi-src/test-data/slideshow/text-highlight.pptx` | 아니오 | 예 | 3 | font_size_pt 3개 | txStyles |
| `poi-src/test-data/slideshow/themes.pptx` | 예 | 예 | 27 | font_size_pt 27개, bold 2개, italic 3개 | txStyles, layout |
| `poi-src/test-data/slideshow/with_japanese.pptx` | 예 | 예 | 37 | font_size_pt 35개, superscript 5개, subscript 1개 | slide |
