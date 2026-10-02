# DOCX 재감수 수정 실물 검증

2026년 10월 2일에 `docx-polish` 작업을 검증했다. 대상은 인라인 이미지가 포함된 제목·문단, 이미지 설명과 중복 참조, 반복 차트의 복제 비용이다. README는 수정하지 않았다. 공개 LibreOffice ooxmlexport DOCX 1,366개와 Apache POI document DOCX 130개를 읽기 전용으로 조사했으며 원본 파일은 저장소로 복사하지 않았다.

## 검증 방법과 범위

`785c0e0`의 DOCX 리더·Markdown 렌더러를 기준으로 삼고, 수정 직전 `23624d4`의 같은 두 모듈과 수정 결과를 비교했다. 프로브는 해당 리비전의 두 모듈을 현재 워크트리의 공통 모델·패키지 도우미와 함께 로드한다. 따라서 저장소 전체를 과거 상태로 되돌린 비교와 구별된다. 문단 수는 `Document.find_all('paragraph')`의 재귀 결과이므로 표 셀·머리글·바닥글도 포함한다. 제목 수는 그중 `heading_level > 0`인 문단의 수다.

XML 관찰에서는 `mc:AlternateContent`의 Choice를 선택하고 없을 때만 Fallback을 선택했다. 이미지 위치는 `a:blip`과 VML `v:imagedata`, 설명은 `wp:docPr`, 차트 캐시는 `c:pt/c:v`를 확인했다. POI 구현 코드를 읽거나 번역하지 않았다. 이 기록은 출력 구조와 값의 검증이며 Word 화면 렌더링의 동일성을 주장하지 않는다.

## 칸별 실물 근거

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 제목 감지 | LO `test77219.docx` | `word/document.xml`의 Heading1 문단 안에 VML 이미지 2개와 제목 본문이 있으며, `785c0e0`의 제목 목록을 함께 비교했다. | 두 이미지와 Report:Logbook 본문이 한 제목에 있어야 한다. | 문단 수가 수정 전 24개에서 22개로 복구됐고 제목 13개의 텍스트·수준이 기준과 일치했다. | 1/1 표본이 통과했다. 기존 ✅ 유지를 제안한다. |
| 이미지 참조·문단 읽기 순서 | LO `tdf135595_HFtableWrap_c12.docx` | 원시 XML의 한 w:p 안에서 Lorem ipsum, blip, wraps around 본문이 이어진다. | 이미지 앞뒤를 한 문단으로 이어야 한다. | `Lorem ipsum![BodyImage](word/media/image1.png) wraps around table-header anchored stuff.` 한 문단이 됐다. 참조는 2개에서 1개가 됐다. | 통과했다. |
| 이미지 참조 | LO `tdf160049_anchorMargin15.docx` | 선택된 XML에는 동일 자산을 가리키는 이미지 출현이 6개 있다. | 출현 6개는 보존하고 basename 경로의 추가 참조는 없어야 한다. | 참조가 12개에서 6개가 됐고 6개 모두 word/media 경로를 사용했다. 문단 수는 14개에서 8개가 됐다. | 통과했다. |
| 이미지 참조·대체 텍스트 | POI `bug59058.docx` | 선택된 XML 이미지 18개와 docPr의 descr=tab1, name=Picture 174를 확인했다. | tab1은 이미지 설명에 한 번 나오고 이미지 출현은 18개여야 한다. | `![tab1 Picture 174](word/media/image3.jpeg)`가 됐다. 전체 참조는 29개에서 18개가 됐고 basename 중복은 0개다. | 통과했다. 기존 이미지 참조·대체 텍스트 ✅ 유지를 제안한다. |
| 읽기 순서·텍스트박스 이미지 | LO `testWPGtextboxes.docx`, POI `drawing.docx` | 선택된 XML 이미지 출현은 각각 1개와 16개다. | 텍스트박스의 이미지 참조와 Image 추출이 각각 출현 수와 같아야 한다. | Markdown 참조와 Image 요소가 각각 1개 및 16개다. 수정 전 참조는 각각 2개 및 21개였다. | 2/2 표본이 통과했다. 전체 읽기 순서 칸에 대한 신규 인증은 하지 않는다. |
| 표/그림 캡션의 보존 | LO `FigureAsLabelPicture.docx` | 이미지 다음 Caption 스타일 문단의 텍스트는 picture 1이다. | 이미지 참조는 한 번이고 캡션 모델은 보존돼야 한다. | 참조 1개와 Image.caption의 picture 1, BOTTOM을 확인했다. | 통과했다. 이 작업만으로 전체 캡션 칸을 새로 인증하지 않는다. |
| 이미지 대체 텍스트의 예외 처리 | LO `FileWithInvalidImageLink.docx` | 이미지 관계를 해석하지 못하지만 docPr 설명은 존재한다. | 참조를 만들지 못해도 설명을 버리면 안 된다. | 문단 3개·제목 1개를 보존했고 ole9.gif 설명이 남았다. | 통과했다. |
| 링크 걸린 이미지 | 해당 공개 실물 표본을 찾지 못했다. | 합성 w:hyperlink+r:id 이미지 테스트로 확인했다. | 문단을 나누지 않고 URL을 보존해야 한다. | 합성 테스트는 통과했으나 이 형태의 실물 검증은 하지 못했다. | 실물 미검증이다. 이 항목을 근거로 ✅를 추가하지 않는다. |
| 차트 제목/데이터 | 아래 LO 13개 표본 및 POI `chartex.docx` | LO 차트 원시 XML의 캐시 값 406개를 확인했고, POI 차트 출력은 수정 전후 비교했다. | 캐시 값과 기존 차트 제목·데이터가 보존돼야 한다. | LO 406개 값의 누락은 0개다. POI chartex는 제목 6개·표 6개·문단 225개와 전체 Markdown이 수정 전후 일치했다. | 복제 변경의 회귀 검증은 통과했다. 기존 기능의 전체 지원 범위를 확대하지 않는다. |

`test77219.docx`의 Markdown에는 머리글 이미지 2개도 있어서 전체 참조 수는 4개다. 본문 이미지 2개만 센 XML 수와 혼동하지 않았다. 이미지 바이트와 OCR 텍스트 출력은 합성 테스트로 보존을 확인했으며 OCR 인식률을 측정한 것은 아니다.

## LO 전체 비교

기준 `785c0e0` 대비 1,335/1,366개(97.73%)는 문단 수와 제목 수가 모두 같다. 남은 31개의 차이는 차트 제목·데이터 추출 13개, 중첩 표 보존 5개, 텍스트박스 또는 머리글·바닥글 보존 12개, 캡션 결합 1개로 설명된다. 이 차이는 모두 수정 직전에도 있던 기능 개선이며 이미지 때문에 문단을 쪼개는 차이는 남지 않았다. 전체 제목 수가 같은 표본은 1,360개다. 나머지 6개는 차트 제목 4개, 원래 제목 문단 안의 텍스트박스 보존 1개, 중첩 표 제목 보존 1개다.

수정 직전 대비 문단 수가 달라진 표본은 57개이며 모두 불필요한 이미지 경계 분할을 제거한 결과다. 제목 수가 달라진 표본은 0개다. 전체 Markdown이 달라진 표본은 기준 대비 241개, 수정 직전 대비 161개다. 문단·제목 수가 같다는 것을 본문 전체가 같다는 뜻으로 사용하지 않았다.

LO 1,366개 중 18개에는 기존 오류 또는 경고가 남아 있고, 그중 13개는 암호화·손상·미지원 패키지 구조 등으로 본문을 파싱하지 못한다. 이를 성공 표본으로 주장하지 않는다. LO 및 POI 비교에서 수정 때문에 새로 생긴 오류·경고는 0개였다.

| 공개 표본 | 문단 수: 기준 → 수정 | 제목 수: 기준 → 수정 | 차이의 근거 |
| --- | --- | --- | --- |
| Chart_BorderLine_Style.docx | 1 → 22 | 0 → 0 | 차트 데이터 표와 제목을 추출한 차이이다. |
| Chart_Plot_BorderLine_Style.docx | 1 → 12 | 0 → 0 | 차트 데이터 표와 제목을 추출한 차이이다. |
| FDO76312.docx | 24 → 25 | 2 → 2 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |
| FigureAsLabelPicture.docx | 3 → 2 | 0 → 0 | 그림 캡션을 Image.caption에 결합한 차이이다. |
| chart-dupe.docx | 1 → 37 | 0 → 0 | 차트 데이터 표와 제목을 추출한 차이이다. |
| chart-prop.docx | 1 → 22 | 0 → 0 | 차트 데이터 표와 제목을 추출한 차이이다. |
| chart-size.docx | 2 → 12 | 0 → 0 | 차트 데이터 표와 제목을 추출한 차이이다. |
| chart.docx | 2 → 23 | 0 → 0 | 차트 데이터 표와 제목을 추출한 차이이다. |
| date_field_in_shape.docx | 1 → 2 | 0 → 0 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |
| dkvert.docx | 1 → 2 | 0 → 0 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |
| fdo76098.docx | 35 → 47 | 0 → 1 | 차트 데이터 표와 제목을 추출한 차이이다. |
| fdo76316.docx | 3 → 21 | 0 → 0 | 중첩 표 구조를 보존한 차이이다. |
| fdo78474.docx | 2 → 14 | 0 → 1 | 차트 데이터 표와 제목을 추출한 차이이다. |
| fdo78957.docx | 2 → 3 | 0 → 0 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |
| fdo80097.docx | 26 → 45 | 0 → 0 | 중첩 표 구조를 보존한 차이이다. |
| mce-nested.docx | 4 → 5 | 1 → 1 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |
| tdf119800.docx | 3 → 4 | 0 → 0 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |
| tdf123873.docx | 2 → 44 | 0 → 0 | 차트 데이터 표와 제목을 추출한 차이이다. |
| tdf124398_groupshapeChart.docx | 3 → 68 | 0 → 1 | 차트 데이터 표와 제목을 추출한 차이이다. |
| tdf128207.docx | 1 → 77 | 0 → 2 | 차트 데이터 표와 제목을 추출한 차이이다. |
| tdf131288.docx | 1 → 22 | 0 → 0 | 차트 데이터 표와 제목을 추출한 차이이다. |
| tdf137655.docx | 27 → 28 | 0 → 1 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |
| tdf143269_zeroSizeEmbeddings.docx | 2 → 21 | 1 → 1 | 차트 데이터 표와 제목을 추출한 차이이다. |
| tdf149546.docx | 1 → 2 | 0 → 0 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |
| tdf153891.docx | 2 → 5 | 0 → 0 | 중첩 표 구조를 보존한 차이이다. |
| tdf158349_SDTstreamStateStack.docx | 103 → 106 | 0 → 0 | 중첩 표 구조를 보존한 차이이다. |
| tdf160077_layoutInCellB.docx | 20 → 21 | 9 → 11 | 중첩 표 구조를 보존한 차이이다. |
| tdf164065.docx | 2 → 3 | 1 → 1 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |
| tdf89165.docx | 5 → 6 | 1 → 1 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |
| tdf92724_continuousBreaksComplex.docx | 5 → 6 | 0 → 0 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |
| wpg-nested.docx | 4 → 5 | 1 → 1 | 텍스트박스 또는 머리글·바닥글의 텍스트를 보존한 차이이다. |

## 차트 실물 값 확인

다음 표는 원시 차트 캐시의 각 문자열이 추출된 문단·표 셀에 포함되는지 확인한 결과다. 반복 값의 개수를 정확히 비교하거나 그래프의 시각적 모양을 비교한 지표는 아니다.

| 공개 표본 | 원시 캐시 값 수 | 출력에서 누락된 값 수 | 판정 |
| --- | --- | --- | --- |
| Chart_BorderLine_Style.docx | 27 | 0 | 통과했다. |
| Chart_Plot_BorderLine_Style.docx | 9 | 0 | 통과했다. |
| chart-dupe.docx | 52 | 0 | 통과했다. |
| chart-prop.docx | 27 | 0 | 통과했다. |
| chart-size.docx | 3 | 0 | 통과했다. |
| chart.docx | 27 | 0 | 통과했다. |
| fdo76098.docx | 9 | 0 | 통과했다. |
| fdo78474.docx | 18 | 0 | 통과했다. |
| tdf123873.docx | 54 | 0 | 통과했다. |
| tdf124398_groupshapeChart.docx | 41 | 0 | 통과했다. |
| tdf128207.docx | 90 | 0 | 통과했다. |
| tdf131288.docx | 27 | 0 | 통과했다. |
| tdf143269_zeroSizeEmbeddings.docx | 22 | 0 | 통과했다. |

## 반복 차트 성능

20,000점 차트를 500회 참조하는 합성 DOCX를 만들어 각 버전을 별도 프로세스에서 교대로 3회 측정했다. macOS `ru_maxrss`는 프로세스 최대 RSS의 바이트 값으로 읽었다. 기존 제한을 바꾸지 않아 두 버전 모두 차트 4개, 셀 160,008개를 출력하고 `WARN: DOCX chart output cell budget exceeded`를 한 번 기록했다. 첫 값 0과 마지막 값 19999도 동일했다. 500개 모두를 출력한 측정이 아니다.

| 측정 | 수정 전 중앙값 | 수정 후 중앙값 |
| --- | --- | --- |
| DOCX read 시간 | 5.016초 | 2.772초 |
| 프로세스 최대 RSS | 388.41 MiB | 330.64 MiB |

동일 세션의 이 측정에서 시간은 약 44.7%, 최대 RSS는 약 14.9% 줄었다. 다른 시스템의 8.1초·397MB 보고와 수치를 직접 비교하지 않는다. 범용 deepcopy를 모델 구조에 맞는 경량 복제로 바꾸고, 이미 파싱한 차트의 출력 셀 수는 한 번만 계산한다. 불변 문자열만 공유하며 셀·런·캡션·출처 객체는 각 참조가 독립적으로 가진다. 따라서 반환 모델을 수정할 때 다른 참조가 바뀌지 않으며 find_all의 객체 중복 제거 계약도 유지된다. 단일 160,008셀 출력의 메모리 자체를 없앤 것은 아니다.

## 재현 명령

저장소 루트에서 Python 3.9로 실행한다. 모든 코퍼스 경로는 인자로 전달한다.

```bash
/usr/bin/python3 -m scripts.probe_docx_polish corpus/lo-src/sw/qa/extras/ooxmlexport/data .codex-work/lo-base.json --revision 785c0e0
/usr/bin/python3 -m scripts.probe_docx_polish corpus/lo-src/sw/qa/extras/ooxmlexport/data .codex-work/lo-before.json --revision 23624d4
/usr/bin/python3 -m scripts.probe_docx_polish corpus/lo-src/sw/qa/extras/ooxmlexport/data .codex-work/lo-fixed.json
/usr/bin/python3 -m scripts.probe_docx_polish corpus/poi-src/test-data/document .codex-work/poi-fixed.json
/usr/bin/python3 -m scripts.probe_docx_polish corpus/poi-src/test-data/document .codex-work/chart-before.json --chart-benchmark --revision 23624d4
/usr/bin/python3 -m scripts.probe_docx_polish corpus/poi-src/test-data/document .codex-work/chart-fixed.json --chart-benchmark
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

## 기존 테스트 단언 변경의 근거

`test_docx_inline_image_heading_is_not_repeated`는 한 XML 문단을 제목과 본문 두 문단으로 쪼갠 `[1, 0]`을 기대하고 있었다. LO `test77219.docx`의 원시 Heading1 문단과 기준 출력이 이를 반증하므로 `[1]` 및 전체 문단 텍스트 일치로 강화했다.

`test_docx_inline_image_does_not_repeat_numbering` 역시 이미지 뒤 after를 별도 문단으로 기대했다. 합성 입력에는 w:p가 두 개뿐이며 이미지의 존재는 새 문단을 만들 근거가 아니다. 번호 1의 전체 문단과 번호 2의 다음 문단, 총 두 문단을 확인하도록 고쳤다. 다른 기존 테스트 단언은 바꾸지 않았다.

## 최종 테스트 결과

최종 코드로 지정된 전체 테스트 명령을 실행해 2,549개가 통과했고 24개는 건너뛰었으며 14개는 기존 예상 실패로 남았다. 실행 시간은 104.17초였고 일반 실패는 0개다. 새 합성 회귀 테스트는 8개이며 최초 핵심 재현 5개가 수정 전 실패하는 것을 확인한 뒤 구현했다. 추가로 깨진 이미지 관계의 설명 소실과 반복 차트의 가변 셀 공유도 각각 실패를 확인하고 보완했다. `git diff --check`도 통과했다.
