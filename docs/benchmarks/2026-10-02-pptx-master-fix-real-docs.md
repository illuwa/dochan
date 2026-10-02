# PPTX 마스터 상속 리뷰 반영 실물 검증

검증일은 2026-10-03이며, 비교 기준은 `7cd4042`이다. 작업명에 맞춘 기록 파일명은 `2026-10-02-pptx-master-fix-real-docs.md`이다. 상속 규칙의 주 근거는 오케스트레이터가 Microsoft PowerPoint(Mac)에서 AppleScript로 읽은 deck1·deck2의 문단별 글자 크기, 굵게, 기울임, 밑줄과 기준선이다. 제공된 기록은 deck1 11개와 deck2 17개로 총 28개 문단이다. 이전 설명의 12개·17개가 아닌 실제 기록 행 수를 분모로 사용했다.

두 원본 PPTX를 현재 리더로 읽은 결과와 같은 구조를 합성한 단위 테스트 결과 모두 28/28이 실측과 일치했다. PowerPoint 실측은 이 두 덱에 한정된다. 공개 코퍼스 XML 프로브의 결과는 **구현 해석과의 일치**이며, 코퍼스 전체를 PowerPoint에서 확인했다는 뜻이 아니다. 종전의 “독립 대조 100%”를 표시 정답 보증으로 해석하지 않는다.

## PowerPoint 실측 표

표의 값은 `크기(pt), 굵게, 기울임, 밑줄, 위첨자, 아래첨자` 순서이다. 0은 꺼짐이고 1은 켜짐이다. 실측 기준선은 모든 행에서 0이며, 양성 위·아래첨자 상속의 검증 근거로 세지 않았다. 이 덱은 합성 후 PowerPoint에서 측정한 통제 표본이며 공개 코퍼스 파일로 세지 않았다.

| 칸 | 표본 파일·문단 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| 글자 서식 상속 | deck1의 S1_title, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 44.0, 1, 0, 0, 0, 0 | 44.0, 1, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck1의 S2_body, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 28.0, 0, 1, 0, 0, 0 | 28.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck1의 S2_body, 문단 2 | PowerPoint 문단 글꼴 실측이다. | 15.0, 0, 0, 1, 0, 0 | 15.0, 0, 0, 1, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck1의 S3_textbox, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 11.0, 0, 0, 0, 0, 0 | 11.0, 0, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck1의 S4_textbox_pdef, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 24.0, 0, 1, 0, 0, 0 | 24.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck1의 S5_pic, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 28.0, 0, 1, 0, 0, 0 | 28.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck1의 S6_dt, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 11.0, 0, 0, 0, 0, 0 | 11.0, 0, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck1의 S7_defppr, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 28.0, 0, 1, 0, 0, 0 | 28.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck1의 S8_sub, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 28.0, 0, 1, 0, 0, 0 | 28.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck1의 S9_orphan, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 28.0, 0, 1, 0, 0, 0 | 28.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck1의 S10_shape_nontx, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 11.0, 0, 0, 0, 0, 0 | 11.0, 0, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S1_title_layoutlst, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 40.0, 1, 0, 0, 0, 0 | 40.0, 1, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S2_body_masterlst, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 30.0, 0, 1, 0, 0, 0 | 30.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S2_body_masterlst, 문단 2 | PowerPoint 문단 글꼴 실측이다. | 24.0, 0, 0, 0, 0, 0 | 24.0, 0, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S3_body_layoutlst, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 26.0, 0, 1, 0, 0, 0 | 26.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S4_obj, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 30.0, 0, 1, 0, 0, 0 | 30.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S5_tbl, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 30.0, 0, 1, 0, 0, 0 | 30.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S6_chart, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 30.0, 0, 1, 0, 0, 0 | 30.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S7_media, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 30.0, 0, 1, 0, 0, 0 | 30.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S8_dt, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 9.0, 0, 0, 0, 0, 0 | 9.0, 0, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S9_ftr, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 11.0, 0, 0, 0, 0, 0 | 11.0, 0, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S10_sldNum, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 11.0, 0, 0, 0, 0, 0 | 11.0, 0, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S11_textbox_lst, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 17.0, 0, 0, 0, 0, 0 | 17.0, 0, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S12_textbox_lvl2, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 10.5, 0, 0, 0, 0, 0 | 10.5, 0, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S13_body_slidelst_bold, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 30.0, 1, 1, 0, 0, 0 | 30.0, 1, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S14_ph_noattr, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 40.0, 1, 0, 0, 0, 0 | 40.0, 1, 0, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S15_pic, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 30.0, 0, 1, 0, 0, 0 | 30.0, 0, 1, 0, 0, 0 | 통과했다. |
| 글자 서식 상속 | deck2의 S16_shape_lst, 문단 1 | PowerPoint 문단 글꼴 실측이다. | 19.0, 0, 0, 0, 0, 0 | 19.0, 0, 0, 0, 0, 0 | 통과했다. |

## 적용한 규칙과 기존 단언 정정

제목 계열과 type·idx가 모두 없는 자리표시자는 titleStyle을 사용한다. 날짜·바닥글·쪽번호를 제외한 자리표시자는 bodyStyle과 마스터 body 자리표시자를 따른다. 레이아웃에 없는 고아 idx도 이 본문 사슬을 따른다. 날짜·바닥글·쪽번호는 같은 종류의 마스터 자리표시자와 presentation 기본값을 사용한다. 자리표시자가 아닌 글상자·도형은 자신의 lstStyle과 presentation 기본값만 사용한다. 이 경로에서는 otherStyle을 사용하지 않는다.

조상 자리표시자의 안내 문단 pPr/defRPr, rPr, endParaRPr는 상속하지 않는다. 실제 출력 문단 자신의 pPr/defRPr와 런 rPr는 적용한다. 같은 수준에서는 슬라이드, 레이아웃, 마스터 자리표시자, title/body txStyles, presentation 순서로 우선한다. 모든 수준별 lvlNpPr 값을 먼저 고르고, 남은 속성에만 defPPr를 적용한다. 따라서 가까운 defPPr가 먼 lvlNpPr를 덮지 않는다. 문단 lvl=1은 lvl2pPr에 대응한다.

기존 테스트 네 곳의 단언을 정정했다. 자유 글상자의 otherStyle 상속은 deck1 S3/S10을 근거로 제거했고, 안내 문단 기본값 상속은 deck1 S2를 근거로 제거했다. 속성이 없는 자리표시자의 body 기본 가정은 deck2 S14를 근거로 title로 고쳤다. master에서 obj의 정확 type을 body보다 우선하던 단언은 deck2 S4/S5를 근거로 body 우선으로 고쳤다. 각 단언에 실측 근거를 주석으로 남겼다. 이 외 HEAD 테스트의 단언을 완화하지 않았다.

## 공개 문서 검증

대상은 `corpus/poi-src`와 `corpus/lo-src`의 PresentationML 파일 556개이다. 정확히는 PPTX 544개, PPTM 4개, POTX 3개, PPSX 5개이다. 암호화 또는 ZIP/CRC 등으로 원시 XML 전체를 해석하지 못한 파일 16개도 출력 회귀 비교에는 포함했다. 원시 해석이 끝난 파일은 540개이다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| 본문 계열 그림 자리표시자 | LO `pic-placeholder-with-text.pptx` | slide1의 그림 자리표시자와 마스터 bodyStyle의 sz=2800 원시 XML이다. 적용 규칙은 PowerPoint deck2 S15로 확인했다. | 본문은 28pt이다. | 28pt이다. | 구현 해석과 일치했다. |
| 레이아웃 굵게·기울임 | POI `WithMaster.pptx` | slide1의 `First page subtitle`에 대응하는 레이아웃 lstStyle과 bodyStyle 원시 XML이다. | 굵게·기울임이며 32pt이다. | 굵게·기울임이며 32pt이다. | 구현 해석과 일치했다. |
| 제목 크기 | POI `SampleShow.pptx` | slide1의 제목과 master titleStyle sz=4400 원시 XML이다. | 제목은 44pt이다. | 44pt이다. | 구현 해석과 일치했다. |
| 밑줄 양성 상속 | 공개 코퍼스 전체 | 선택된 상속 기본값에 양성 밑줄 표본이 없었다. | 공개 실물 표본이 필요하다. | PowerPoint 통제 표본 deck1 S2의 수준 2와 합성 테스트만 통과했다. | 공개 실물 양성은 미검증이다. |
| 위·아래첨자 양성 상속 | 공개 코퍼스 전체 | 선택된 상속 기본값에 양성 기준선 표본이 없었다. | 공개 실물 표본이 필요하다. | 정수·백분율·명시적 해제를 합성 테스트로 확인했다. | 공개 실물 양성은 미검증이다. |

원시 XML 런 8,272개 중 명확히 대응하는 7,851개는 여섯 속성이 구현 해석과 일치했다. 불일치는 0개이며, 반복 텍스트가 모호한 389개와 출력에서 제거된 공백 32개는 분모에서 제외했다. 상속 구현 전의 직접 서식 계약 대비 바뀌는 런 중 안전 대조한 굵게는 23개 파일·158개 런, 기울임은 4개 파일·108개 런, 크기는 179개 파일·3,095개 런이다. 이 수치는 이번 HEAD 대비 변경 수와 다른 지표이다.

## HEAD 대비 출력 회귀

556개 전체에서 본문 텍스트 해시 변화, 런 개수 변화, 같은 순번 런의 텍스트 변화는 각각 0개이다. Markdown 변화는 0개이고 JSON은 20개 파일에서 달라졌다. 255개 런의 크기가 바뀌었으며 굵게·기울임·밑줄·위첨자·아래첨자 변화는 각각 0개이다. 공개 문서의 오류·경고 변화도 0개이다.

| 파일 | 크기가 바뀐 런 | 다른 서식 변화 | 사유 |
|---|---:|---|---|
| `lo-src/sd/qa/unit/data/pptx/ShapeTextInflateTop.pptx` | 4 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `lo-src/sd/qa/unit/data/pptx/n778859.pptx` | 1 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `lo-src/sd/qa/unit/data/pptx/pic-placeholder-with-text.pptx` | 1 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `lo-src/sd/qa/unit/data/pptx/tdf125573_FontWorkScaleX.pptx` | 4 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `lo-src/sd/qa/unit/data/pptx/tdf128206.pptx` | 1 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `lo-src/sd/qa/unit/data/pptx/tdf128212.pptx` | 1 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `lo-src/sd/qa/unit/data/pptx/tdf128213-shaperot.pptx` | 1 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `lo-src/sd/qa/unit/data/pptx/tdf128213.pptx` | 1 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `lo-src/sd/qa/unit/data/pptx/tdf136830.pptx` | 1 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `lo-src/sd/qa/unit/data/pptx/tdf140865Wordart3D.pptx` | 1 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `lo-src/sd/qa/unit/data/pptx/tdf50499.pptx` | 1 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `poi-src/test-data/slideshow/2411-Performance_Up.pptx` | 5 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `poi-src/test-data/slideshow/45541_Footer.pptx` | 8 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `poi-src/test-data/slideshow/45541_Header.pptx` | 34 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `poi-src/test-data/slideshow/45545_Comment.pptx` | 21 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `poi-src/test-data/slideshow/PPTWithAttachments.pptm` | 1 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `poi-src/test-data/slideshow/aascu.org_hbcu_leadershipsummit_cooper_.pptx` | 4 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `poi-src/test-data/slideshow/alterman_security.pptx` | 22 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `poi-src/test-data/slideshow/ca.ubc.cs.people_~emhill_presentations_HowWeRefactor.pptx` | 138 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |
| `poi-src/test-data/slideshow/customGeo.pptx` | 5 | 없다. | PowerPoint 실측 상속 규칙을 적용했다. |

제목에 굵은 마커가 있는 Markdown 줄은 두 버전 모두 136줄이고, `****` 연속 마커는 두 버전 모두 30회이다. 이 수치는 556개 전체를 대상으로 한다. `alterman_security.pptx`의 원문 별표를 포함할 수 있으므로 연속 마커를 모두 작성기 결함이라고 단정하지 않는다. 본문 문자열 안 줄바꿈을 가로지르는 굵은 제목 런은 0개이다. 공용 작성기는 변경하지 않았다.

## 손상 입력과 자원 방어

고정 레이아웃 문구를 공유하는 합성 1,100장 덱은 기존 HEAD에서 1,021장만 문구를 보존했으나 수정 후 1,100/1,100장에 보존했다. 슬라이드 본문도 1,100/1,100장에 남았다. 스타일 파트·바이트 예산이 0인 테스트에서도 레이아웃 문구를 유지했다. 레이아웃 콘텐츠 로드를 선택적 스타일 예산에서 분리했으며 OOXMLPackage의 ZIP/XML 상한은 계속 적용한다. 스타일 한계 경고가 나는 문서의 모든 서식 보존까지 보장하지는 않는다.

스타일 탐색은 XML 파트마다 100,000노드와 깊이 64로 제한한다. 같은 파트를 다시 읽은 트리도 노드 예산을 공유하며, 다른 파트는 독립적인 예산을 사용한다. lstStyle은 첫 탐색에서 예산을 적용하고 수준별·기본값별 결과를 캐시한다. 같은 누락 수준을 반복 조회해도 손상된 자식 목록을 다시 훑지 않는다. 시간 단언 대신 방문 수와 경고를 검증하는 단위 테스트를 두었다.

동일한 손상 lstStyle N개와 문단 N개를 둔 단회 실측에서 HEAD의 N=8,000/16,000은 각각 0.9566초/3.9751초였다. 수정 후에는 0.1790초/0.3437초였으며 문단 8,000개/16,000개가 보존됐다. 이 수치는 해당 로컬 합성 입력의 관측치이며 일반 처리량 보증은 아니다.

baseline의 정수와 백분율을 같은 단위로 정규화하여 0% 해제와 음수 아래첨자를 처리한다. idx는 0~4,294,967,295의 정수 키로 비교하여 01·+1을 1과 동일하게 취급하고 범위 밖 값은 경고 후 매칭하지 않는다. 잘못된 밑줄 값은 경고 후 무시한다. 레이아웃 관계의 경로 이탈 입력은 패키지 밖을 읽지 않고 WARN을 남기며 본문을 유지한다. 이 경로는 상속 구현 전에는 문서 ERR이었고, 기존 HEAD부터 WARN으로 강등됐다. 이번에는 콘텐츠 경고를 스타일 경고와 구분했다.

## 재현과 판정 범위

`python -m scripts.probe_pptx_master corpus/poi-src corpus/lo-src --output .codex-work/pptx-master-fix-final --baseline .codex-work/pptx-master-fix-head-556/head.json`으로 코퍼스 대조를 재현한다. HEAD 스냅샷은 구현 수정 전에 만들었고, 기존 544개 스냅샷의 모든 출력 해시·런과 일치함을 확인했다. 레거시 보조 실행은 sys.executable을 사용한다. 새 런타임 의존성·공유 모델·공유 출력 파일은 추가하거나 수정하지 않았다.

PowerPoint 실측 28개 문단은 `test_powerpoint_measured_deck1`과 `test_powerpoint_measured_deck2`에서 합성한다. 전체 테스트는 3359 passed, 24 skipped, 14 xfailed로 끝났고, lint와 로컬 경로 검사도 통과했다. 굵게·기울임·크기는 실측 범위를 명시한 지원을 제안하며, 공개 양성 실물이 없는 밑줄·위아래첨자 상속은 미검증으로 남긴다. README는 수정하지 않았다.
