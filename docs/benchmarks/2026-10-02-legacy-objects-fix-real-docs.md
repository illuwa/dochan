# Legacy 내장 개체 리뷰 반영 실물 검증

2026년 10월 2일 `illuwa/w-legacy-objects`에서 읽기 전용 공개 코퍼스로 재검증했다. 최초 작업의 43개 검사를 확장한 최종 프로브는 **64/64**를 통과했다. 이는 파일 수나 전체 수식 지원률이 아니라 독립 기대값·출력 위치·개수 검사 수다. README는 수정하지 않았다.

## 칸별 검증

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| DOC 차트 제목/데이터 | POI DOC 159개와 LibreOffice DOC 193개를 조사했다. | ObjectPool의 Workbook/Book BOF뿐 아니라 CompObj의 MSGraph ProgID와 Graph 이름 스트림도 검사했다. | 본문에 연결할 수 있는 실물 차트가 필요하다. | 총 352개에서 Workbook 개체 6개, 차트 0개, MSGraph 개체 0개였다. 비OLE 파일 2개는 검사 오류로 따로 기록했다. | 미검증이므로 ⬜를 유지한다. |
| PPT 차트 제목/데이터 | `42520.ppt`, `bug61881.ppt`, `37625.ppt`, `bug60345_suba.ppt`이다. | Graph Number/Label, Series, 선택 범위 0x1053/0x1054, SIIndex/Number, SeriesText/ObjectLink를 독립 전사했다. | Graph 4개와 Excel 4개의 표, 제목 3개, 종류와 배치 각각 4개가 일치해야 한다. | 표 8/8, 제목 3/3, 종류 4/4, 배치 4/4가 일치했다. | 검증한 연속 Graph 범위와 BIFF8 활성 차트 범위에서 ✅를 제안한다. |
| DOC 수식 | `Bug61268.doc`, `Bug50936_1.doc`, LibreOffice `tdf79553_lineNumbers.doc`이다. | 원시 CHAR의 typeface·문자 코드와 TMPL 슬롯, EMBED 구분자의 ObjectPool ID를 확인했다. | 대표 식 12개와 본문 연결 12개가 일치해야 한다. | 식 12/12, 연결 12/12가 일치했다. 전체 변환은 42/54개였다. | 검증한 MTEF3 범위에서 ✅를 제안한다. |
| PPT 수식 | `42520.ppt`, `npe.ppt`, `37625.ppt`, `23884_defense_FINAL_OOimport_edit.ppt`이다. | 원시 MTEF2/3/5 CHAR·TMPL과 ExObjRefAtom의 실제 slide ID를 대조했다. | 대표 식 검사 12개와 위치·반복 개수 검사 8개가 일치해야 한다. | 식 12/12, 위치·개수 8/8이 일치했다. 전체 변환은 13/18개였다. | 아래에 명시한 MTEF2/3/5 지원 범위에서 ✅를 제안한다. 전체 MTEF 지원을 뜻하지 않는다. |
| XLS 수식 | POI 동명 XLS/XLSX 36쌍이다. | 기존 XLSX `<f>` 비교 프로브를 다시 실행했다. | 수식이 있는 20쌍의 1,070개를 비교해야 한다. | 정확 974개, 표기 정규화 포함 1,027개가 일치했고 오류는 0개였다. 차이 43개는 그대로였다. | ⬜를 유지한다. |

## 차트·미리보기 결함의 실물 근거

`42520.ppt`의 object 57은 Series가 14점을 선언하고 선택 범위도 14점을 포함한다. 원시 datasheet에 범위 밖 `(0,15)=999`, `(1,15)=777`을 메모리에서 추가해도 출력은 원래 14행으로 유지되었다. 범위 안 점 개수와 Series 선언이 다르면 미리보기를 유지한다. 비연속 선택이나 알려지지 않은 범위 시작값도 추측하지 않는다.

`SimpleChart.xls`를 비롯해 활성 워크시트 자체에 차트가 있는 공개 XLS 17개를 내장 Excel 경로로 검사했다. 모두 새 차트 출력 없이 기존 미리보기를 유지했고 새 경고는 없었다. 이는 해당 스캔에서 읽힌 표본 수이며, 별도의 스캔 오류 21개까지 포함한 전체 XLS 코퍼스 성공률로 해석하지 않는다. 활성 BOUNDSHEET 종류가 차트이거나 ProgID가 Excel.Chart·MSGraph.Chart일 때만 차트 출력으로 진행한다. 데이터 셀이 없는 표는 제목까지 함께 폐기한다. 내부 BRAI는 기존 워크북 파서에 시트를 전달해 해소하며 외부 통합문서는 열지 않는다.

`42474-2.ppt`와 같은 범주 없는 내장 차트의 기본 범주는 1부터 출력한다. 독립 XLS의 기존 출력과 HEAD 단언은 유지하기 위해 `category_start`를 추가했고 DOC/PPT 내장 경로만 1을 전달한다. 따라서 독립 XLS의 0부터 시작하는 기존 동작은 별도 작업으로 남는다.

| 공개 파일 | 원시 압축 관찰 | 기대 | 실제 | 판정 |
|---|---|---|---|---|
| `testPPT_oleWorkbook.ppt` | 선언값과 해제값은 17,920바이트이고 zlib eof가 없다. | 완전한 CFB이면 경고 후 수용해야 한다. | 정상 CFB와 압축 경고를 반환했다. | 통과했다. |
| `badzip.ppt` | 선언값과 해제값은 57,856바이트이고 zlib eof가 없다. | 단독 압축 복구는 가능하지만 Word.Document.12는 처리 대상에서 제외해야 한다. | 복구에 성공했고 문서 출력의 새 OLE 경고는 0개였다. | 통과했다. |
| `bug58733_671884.ppt`, `62d2ecd89aeb715b07072d4f8a8734f4dbeb5c10.ppt` | 각각 614,912바이트가 정확히 해제되고 뒤에 1바이트가 남는다. | 정상 CFB일 때만 경고 후 수용해야 한다. | 두 개체 모두 정상 CFB를 반환했다. | 통과했다. |
| `bug58516.ppt` | ExEmbed의 CString instance 2는 MS_ClipArt_Gallery.5이다. | 새 내장 개체 문구와 OLE 경고를 넣지 않아야 한다. | 새 대체문구 0개, 새 OLE 경고 0개였다. 기존 그림 경고는 보존했다. | 통과했다. |

압축 선언 크기 불일치, 크기 상한 초과, 비CFB 잘림은 계속 거부한다. 단순히 zlib 오류를 무시하는 변경이 아니다. 지원 대상의 실패는 기존 미리보기를 유지한다.

## 수식 기대값 정정과 변환율

`Bug50936_1.doc`의 기존 기대값 4개는 typeface `0x81`인 fnTEXT를 변수로 바꿔 쓰고 있었다. 원시 `02 81` CHAR를 다시 확인해 `\overline{\text{x}}`, `\text{s}_{\text{unexp}}^{\text{2}}`, `s^{\text{2}}(y)`, `\text{s}_{\text{unexp,ln}_{\text{i}}}^{2}`로 정정했다. 이는 결과에 맞춘 임의 변경이 아니라 기존 기대값의 텍스트 의미 누락을 수정한 것이다. 합성 테스트도 연속 fnTEXT, 공백, LaTeX 특수문자, 일반 수학 문자와의 경계를 검증한다.

MTEF2는 CHAR를 1바이트로 읽고 typeface에 따라 해석한다. `npe.ppt`의 C7은 교집합, C4는 원형 곱셈이며 각각 `\cap`, `\otimes`로 검증했다. object 63의 분수·괄호·첨자는 `O\left(T\left[\frac{D}{F}\right](2^{F}-1)\right)`와 일치했다. Symbol의 ASCII처럼 보이는 미등록 문자를 무조건 허용하지 않는다. 설치된 Symbol 폰트의 cmap에서 0x60이 radical extender임을 확인했고, 백틱으로 잘못 출력하지 않도록 실패 테스트를 추가했다. 폰트 파일은 복사하거나 런타임 의존성으로 추가하지 않았다.

MTEF5는 ENCODING_DEF, FONT_DEF, EQN_PREFS의 알려진 바이트 구조를 소비한다. preference 숫자는 F로 끝나는 nibble 문자열이며 값들이 바이트를 공유할 수 있다. MTCode가 있는 CHAR의 보조 font-position은 의미 문자를 대체하지 않는다. `37625.ppt`의 object 37은 `(Vehicle\_kms)\times \left(\frac{Emissions}{km}\right)`, object 201은 `(Vehicles)\times \left(Utilisation\right)`와 일치하며 둘 다 slide 24에 배치되었다.

U+EB01·EB02·EB04는 명시적 LaTeX 공백 `{\ }`로 정규화한다. `23884_defense_FINAL_OOimport_edit.ppt`의 EB02를 가진 세 대표 수식과 `Bug50936_1.doc`의 EB04 대표 수식을 원시 문자·슬롯 기준으로 검증했다. **공백 종류별 정확한 폭은 미검증이다.** 로컬에서 Design Science MTEF v3/v5 원문을 찾지 못했고 네트워크 금지를 지켰으므로 원문 대조 완료나 정밀 조판 재현을 주장하지 않는다. 임의로 em 또는 point 폭을 부여하지 않았다. 이 한계는 요청한 명세 기준의 정확한 공백 폭별 매핑에 남아 있다.

| 범위 | 수정 전 | 수정 후 | 남은 실패 |
|---|---|---|---|
| DOC 3파일의 MTEF3 저장소 | 41/54개였다. | 42/54개로 77.78%였다. | 종료 뒤 데이터 2개, PILE 3개, 템플릿 43이 4개, 템플릿 옵션·42·24가 각 1개로 총 12개였다. |
| PPT 4파일의 Equation Native | 1/18개였다. | 13/18개로 72.22%였다. | 문자 장식 옵션 1개, 빈 수식 2개, 미지원 v2 typeface 1개, MATRIX 1개로 총 5개였다. |
| PPT MTEF2 | 0/8개였다. | 6/8개였다. | 미지원 typeface와 MATRIX를 미리보기로 남겼다. |
| PPT MTEF5 | 0/2개였다. | 2/2개였다. | 이 두 표본에서는 실패가 없었다. |
| PPT MTEF3 | 1/8개였다. | 5/8개였다. | 장식 옵션 1개와 빈 수식 2개가 남았다. |

DOC의 EB04 개체 두 개 가운데 하나는 공백을 해석한 뒤 종료 뒤 데이터 결함이 드러나 계속 폴백했다. 따라서 DOC 변환 증가분은 2개가 아니라 1개다. DOC 출력 위치는 반복 배치를 포함해 44곳이다. PPT는 13곳이다. POI PPT 145개와 별도 LibreOffice PPT 72개를 모두 조사했고, 후자의 native 수식은 0개여서 POI의 18개 분모에 섞지 않았다. 암호화·손상 파일의 검사 오류와 문서 경고도 JSON에 남겼다.

## 재현과 한계

코퍼스는 인자로 받은 경로에서 읽기만 한다. 소스 코드·테스트에 실물 표본을 복사하지 않았다. 기대값 근거는 원시 레코드와 기존 OOXML 비교이며, POI·LibreOffice 구현 코드를 번역하지 않았다. 공유 모델·출력 파일, README, CHANGELOG, 의존성은 변경하지 않았다.

```bash
/usr/bin/python3 -m scripts.probe_legacy_objects /Users/illuwa/dev/personal/dochan/corpus --output .codex-work/legacy-objects-fix-real.json
/usr/bin/python3 -m scripts.probe_xls_formula_pairs /Users/illuwa/dev/personal/dochan/corpus/poi-src/test-data/spreadsheet --output .codex-work/xls-formula-pairs-review.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

개체 수·스트림 크기·누적 바이트·레코드 수·출력 크기·재귀 깊이 상한은 유지했다. 미지원 MTEF 템플릿과 행렬, Graph 비연속 범위, 외부 BRAI, 수식 재계산은 지원한다고 주장하지 않는다. 최종 전체 테스트는 **2,608 passed, 24 skipped, 14 xfailed**이며 99.43초가 걸렸다. `.codex-work/full-tests-review.log`에 실행 결과를 보관한다.
