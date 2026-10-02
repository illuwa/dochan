# A04 HWPX 차트: 실물 XML 조사와 최소 gold

조사일: 2026-09-19. **원형(`pieChart`)과 꺾은선(`lineChart`) 두 유형 확인.**
제목·계열·범주·값은 corpus ZIP의 XML에서 직접 읽었다. dochan 출력,
미리보기 이미지, OLE 렌더링 또는 스프레드시트 재계산을 정답으로 사용하지 않았다.

## 1. 표본 식별·공개 출처·라이선스

두 파일은 edwardkim/rhwp의 공개 차트 테스트 표본이다. 조사일에 커밋
`680111ec7bea2fe11110de18c3676ba5a1cf7847`의 파일을 메모리로 다운로드해
로컬 바이트와 일치함을 확인했다. 로컬 경로는 저장소 루트 기준이다.

| ID | 로컬 경로 | bytes | SHA-256 |
| --- | --- | ---: | --- |
| C1 | `corpus/hwp-public/hwpx/2차원원형.hwpx` | 44410 | `ce4304b8aa4fba79d493647d6fb1204b527bc2aac50c55a94bea9ec67f8994a8` |
| C2 | `corpus/hwp-public/hwpx/꺽은선형.hwpx` | 53347 | `a8a4449c3641c107aadb6e597dbb780b5b7ae3dc50d4a144a2e87075af2fc398` |

- C1 [공개 파일](https://raw.githubusercontent.com/edwardkim/rhwp/680111ec7bea2fe11110de18c3676ba5a1cf7847/samples/chart/%EC%9B%90%ED%98%95/2%EC%B0%A8%EC%9B%90%EC%9B%90%ED%98%95.hwpx)
- C2 [공개 파일](https://raw.githubusercontent.com/edwardkim/rhwp/680111ec7bea2fe11110de18c3676ba5a1cf7847/samples/chart/%EB%9D%BC%EC%9D%B8/%EA%BA%BD%EC%9D%80%EC%84%A0%ED%98%95.hwpx)
- 저장소 [MIT 라이선스](https://github.com/edwardkim/rhwp/blob/680111ec7bea2fe11110de18c3676ba5a1cf7847/LICENSE)를 직접 확인했다.
  라이선스 파일 SHA-256: `1c3a7d5643b163a3ead4965e1bea33b832caee5bfca265efe42afcd7bc696b5b`.
  `corpus/hwp-public/SOURCES.json`의 MIT 표기와 일치한다.
  직접 확인 범위는 해당 커밋의 저장소 라이선스 선언이다. 수집 인덱스의
  표기와 직접 확인을 구분하며, 개별 표본의 모든 권리나 제3자 자료의 권리를
  보증하지 않는다. 이 선언을 다른 corpus 파일까지 적용하지 않는다.

공개 기본 계열명·범주명·수치만 gold에 사용한다. 작성자 메타데이터, 개인 정보,
비공개 원문 또는 문서 전체를 인용하지 않는다.

| 표본 | ZIP 내부 파트 | 비압축 bytes | 원본 파트 바이트 SHA-256 |
| --- | --- | ---: | --- |
| C1 | `Chart/chart1.xml` | 2678 | `d97cfe9edf27f2b41116ac9d6d7102554743972934ebfa098136d688eddd3a26` |
| C1 | `Contents/section0.xml` | 5362 | `22584ed73816f903081321297580a27df51034e9e79b98d1c7728086a33a7c2f` |
| C1 | `Contents/content.hpf` | 2263 | `c946bb78018435ad05989b90fa0f4390ca0af9996b19ec54c7a092ab344e59b1` |
| C2 | `Chart/chart1.xml` | 5223 | `9c869af6b69e6eeba07a1d81e8d15f6ba701367def9baac3c21cb6ab1c0cfb14` |
| C2 | `Contents/section0.xml` | 5362 | `c0a96095623b438360430af726264ee46e6b0483768fe51264fbc13d78c306b0` |
| C2 | `Contents/content.hpf` | 2263 | `f1a7f63287e638411ce974b2c26a46599429a54943e01b65856b70577cd38346` |

## 2. 실제 namespace

| prefix/용도 | 실제 URI |
| --- | --- |
| `hs` section | `http://www.hancom.co.kr/hwpml/2011/section` |
| `hp` 문단·차트·대체 분기 | `http://www.hancom.co.kr/hwpml/2011/paragraph` |
| `opf` HPF manifest/spine | `http://www.idpf.org/2007/opf/` |
| 차트 분기의 요구 namespace 값 | `http://www.hancom.co.kr/hwpml/2016/ooxmlchart` |
| `c` 차트 데이터 | `http://schemas.openxmlformats.org/drawingml/2006/chart` |
| `a` DrawingML 텍스트·표현 | `http://schemas.openxmlformats.org/drawingml/2006/main` |
| `r` relationships 선언 | `http://schemas.openxmlformats.org/officeDocument/2006/relationships` |
| `mc` AlternateContent | `http://schemas.openxmlformats.org/markup-compatibility/2006` |
| `c14` 스타일 선택 분기 | `http://schemas.microsoft.com/office/drawing/2007/8/2/chart` |
| `ho` 한컴 스타일 확장 | `http://schemas.haansoft.com/office/8.0` |

두 표본의 `version.xml`: `application="Hancom Office Hangul"`,
`xmlVersion="1.5"`, `appVersion="12, 0, 0, 535 WIN32LEWindows_10"`.
prefix 문자열만 비교하거나 모든 `chart` local name을 동일 요소로 취급하지 않는다.
`2016/ooxmlchart`는 분기 조건의 **속성값**이고 `hp:chart` 자체의 QName URI는 2011 paragraph다.

## 3. 패키지 참조와 OLE 대체 분기

두 표본에서 다음 구조를 확인했다. 아래는 위치·연결만 표시한 구조도다.

```text
META-INF/container.xml
  rootfile@full-path = Contents/content.hpf
Contents/content.hpf
  manifest/item id=section0 href=Contents/section0.xml
  manifest/item id=ole1 href=BinData/ole1.ole media-type=application/ole isEmbeded=0
Contents/section0.xml
  hs:sec/hp:p/hp:run/hp:switch
    hp:case @hp:required-namespace=http://www.hancom.co.kr/hwpml/2016/ooxmlchart
      hp:chart @chartIDRef=Chart/chart1.xml
    hp:default
      hp:ole @binaryItemIDRef=ole1
Chart/chart1.xml
  c:chartSpace/c:chart/c:plotArea/{c:pieChart | c:lineChart}
```

- `chartIDRef`는 이 표본에서 ZIP 루트 기준 실제 파트 이름이다.
  `Contents/Chart/chart1.xml`로 붙이면 존재하지 않는다. URI처럼 보인다는 이유로 외부 요청하지 않는다.
- HPF manifest에는 **차트 item이 없다**. `chartIDRef`를 manifest ID 또는 OOXML `r:id`로
  간주하면 차트를 놓친다. 별도의 `.rels` 파트도 두 ZIP에 없다.
- 차트와 default OLE는 같은 객체 `id`를 쓴다: C1 `1117817544`, C2 `1117814268`.
  두 분기를 모두 독립 객체로 출력하면 동일 위치를 중복 표현하게 된다.
  차트를 읽을 수 있을 때 case를 선택한다는 후속 구현 정책을 권고하되,
  전체 `hp:switch` 선택 규격은 이 두 사례만으로 확정하지 않는다.
- `BinData/ole1.ole`가 실제 존재한다(C1 271364 bytes, C2 276996 bytes).
  `isEmbeded="0"`과 실제 내장 파트가 공존한다. 이 속성의 의미는 **미확정**이며
  값만 보고 외부 객체라 단정하지 않는다. OLE 내부 데이터와 XML 캐시의 일치도는 검사하지 않았다.
- 두 `hp:chart`에는 `hp:sz`, `hp:pos`, `hp:outMargin`만 있고,
  크기는 width=32250, height=18750이다. 본 gold는 레이아웃이 아니라 XML 데이터용이다.

한컴 공식 [ChartType.cpp L74–87](https://github.com/hancom-io/hwpx-owpml-model/blob/1453388472c703a4b299a0834f425cdac16644b9/OWPML/Class/Para/ChartType.cpp#L74)은
문자열 속성 `chartIDRef`를 읽고 쓰며,
[NamespacePrefix.cpp L41](https://github.com/hancom-io/hwpx-owpml-model/blob/1453388472c703a4b299a0834f425cdac16644b9/OWPML/Base/NamespacePrefix.cpp#L41)은
위 2016 namespace를 정의한다. 이는 실제 관찰과 일치하지만 모든 경로 해석 규칙의 규격 증명은 아니다.

## 4. 차트·제목·계열·캐시·축

아래 XPath의 `plot`은 `/c:chartSpace/c:chart/c:plotArea`, `ser`는 선택한
차트 유형 요소의 직계 `c:ser`다.

| 의미 | 정확한 상대 경로·관찰 |
| --- | --- |
| 유형 | C1 `plot/c:pieChart`, C2 `plot/c:lineChart`; 파일명으로 추정하지 않음 |
| 제목 | `/c:chartSpace/c:chart/c:title`은 존재하지만 `c:tx`·`a:t`는 없음 |
| 제목 스타일 | `c:title/c:txPr/a:p`는 빈 텍스트 서식; 실제 제목 문자열로 취급하지 않음 |
| 계열 식별·순서 | `ser/c:idx/@val`, `ser/c:order/@val` |
| 계열 이름 참조 | `ser/c:tx/c:strRef/c:f` |
| 이름 캐시 | `ser/c:tx/c:strRef/c:strCache/c:pt[@idx]/c:v` |
| 범주 참조·캐시 | `ser/c:cat/c:strRef/{c:f,c:strCache}` |
| 숫자 참조·캐시 | `ser/c:val/c:numRef/{c:f,c:numCache}` |
| 캐시 개수 | 각 cache의 `c:ptCount/@val`; 이름 1, 범주·숫자 각각 4 |
| 숫자 형식 | `c:numCache/c:formatCode`는 모두 `General` |
| 캐시 포인트 키 | `c:pt/@idx`는 이름 `0`, 범주·값은 `0,1,2,3`; 현재 순서와 일치 |

`c:strRef`는 참조식과 마지막 사용 문자열 캐시를 함께 담고,
`c:numCache`는 마지막 표시 숫자 데이터를 담는다는 Microsoft의
[StringReference](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.stringreference?view=openxml-3.0.1),
[NumberingCache](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.numberingcache?view=openxml-3.0.1)
설명과 대조했다. 따라서 아래는 **저장된 캐시의 gold**다. 연결 원본의 최신 값이라는 보장은 없다.
`c:f`는 수식 문자열로 보존하며 계산하거나 링크를 따라가지 않는다.

두 파일 모두 `autoTitleDeleted=0`이지만 명시적 제목 텍스트는 없다.
gold의 `title=null`은 “명시적 XML 제목 없음”이며 한글 화면의 자동 제목 표시 여부는 **미확정**이다.
계열명 `판매`를 차트 제목으로 복사하지 않는다. 범례는 `legendPos=r`이다.
`plotVisOnly=0`, `dispBlanksAs=gap`도 존재하지만 빈 포인트의 실물 동작은 이번 gold 범위 밖이다.

C1에는 `c:catAx`, `c:valAx`, 차트의 `c:axId`가 없다. C2는 `grouping=standard`,
계열 3개이며 다음 연결이 있다.

| 요소 | `c:axId/@val` | `c:crossAx/@val` | `c:axPos/@val` | 제목 |
| --- | --- | --- | --- | --- |
| `plot/c:catAx` | `444446900` | `790693022` | `b` | `c:title` 없음 |
| `plot/c:valAx` | `790693022` | `444446900` | `l` | `c:title` 없음 |

`lineChart/c:axId` 두 값은 위 축 ID와 일치한다. 양 축 `c:scaling/c:orientation=minMax`,
`c:delete=0`, `c:crosses=autoZero`; 값 축 `c:numFmt`는 `formatCode=General`, `sourceLinked=1`이다.
축의 최솟값·최댓값을 캐시에서 새로 계산하여 원본 지정값처럼 기록하지 않는다.

## 5. XML에서 독립 도출한 최소 gold

숫자는 `c:v`의 문자열을 그대로 보존한다(`2`를 `2.0`으로 바꾸지 않음).
배열 위치는 포인트 `idx=0..3` 순서다. 다음 JSON은 전체 데이터 계열 캐시를 포함한다.

```json
{
  "C1": {
    "sample": "2차원원형.hwpx",
    "sha256": "ce4304b8aa4fba79d493647d6fb1204b527bc2aac50c55a94bea9ec67f8994a8",
    "part": "Chart/chart1.xml",
    "type": "pieChart",
    "title": null,
    "series": [
      {
        "idx": "0", "order": "0", "name": "판매",
        "name_formula": "Sheet1!$B$1",
        "category_formula": "Sheet1!$A$2:$A$5",
        "value_formula": "Sheet1!$B$2:$B$5",
        "categories": ["1 분기", "2 분기", "3 분기", "4 분기"],
        "values": ["10", "3.5", "1.5", "1.2"]
      }
    ],
    "axis_ids": []
  },
  "C2": {
    "sample": "꺽은선형.hwpx",
    "sha256": "a8a4449c3641c107aadb6e597dbb780b5b7ae3dc50d4a144a2e87075af2fc398",
    "part": "Chart/chart1.xml",
    "type": "lineChart",
    "title": null,
    "series": [
      {
        "idx": "0", "order": "0", "name": "계열 1",
        "name_formula": "Sheet1!$B$1",
        "category_formula": "Sheet1!$A$2:$A$5",
        "value_formula": "Sheet1!$B$2:$B$5",
        "categories": ["항목 1", "항목 2", "항목 3", "항목 4"],
        "values": ["4.3", "2.5", "3.5", "4.5"]
      },
      {
        "idx": "1", "order": "1", "name": "계열 2",
        "name_formula": "Sheet1!$C$1",
        "category_formula": "Sheet1!$A$2:$A$5",
        "value_formula": "Sheet1!$C$2:$C$5",
        "categories": ["항목 1", "항목 2", "항목 3", "항목 4"],
        "values": ["2.4", "4.4", "1.8", "2.8"]
      },
      {
        "idx": "2", "order": "2", "name": "계열 3",
        "name_formula": "Sheet1!$D$1",
        "category_formula": "Sheet1!$A$2:$A$5",
        "value_formula": "Sheet1!$D$2:$D$5",
        "categories": ["항목 1", "항목 2", "항목 3", "항목 4"],
        "values": ["2", "2", "3", "5"]
      }
    ],
    "axis_ids": ["444446900", "790693022"]
  }
}
```

## 6. 외부 참조 정책·미확정 범위

두 표본에는 `.rels`, `c:externalData`, `r:id`, XLSX 파트가 없다.
`Sheet1!…` 참조식만으로 외부 파일이나 OLE 내부 시트의 실재·연결을 확정하지 않는다.
루트의 `r` namespace 선언은 관계 사용의 증거가 아니다.

조사에서 도출한 구현 정책(실물 규격의 관찰과 구분):

- ZIP 내부의 정확한 참조 파트만 제한된 크기로 읽는다. 외부 URL·절대 경로·경로 탈출,
  중복 이름·누락 파트는 오류/미지원 상태로 보존하고 임의의 다른 chart 파트를 선택하지 않는다.
- 캐시가 있으면 출처를 `cache`로 구분한다. 외부 통합 문서 접근·수식 실행·OLE 실행은 하지 않는다.
- 없는 cache를 빈 계열이나 0으로 대체하지 않는다. 누락 `idx`는 누락으로 보존하고,
  `ptCount` 불일치·중복 `idx`·숫자 변환 실패를 정상 데이터로 위장하지 않는다.
- branch 중복을 피하며 제목·계열·축·캐시 상태를 별도로 다룬다.

`numLit/strLit`, 다단계 범주, 산점도의 `xVal/yVal`, 혼합 차트, 보조 축,
외부 relationship, 캐시 없는 참조, 캐시와 원본의 충돌, 명시적 rich-text 제목은
**이 두 표본의 gold로 미검증**이다. `c14:style`, `ho:hncChartStyle`의 수치 의미와
OLE 대체 렌더링·자동 제목 규칙도 **미확정**이다.
두 파일의 스타일 확장은 관찰상 `layoutIndex=-1`, `colorIndex=0`, `styleIndex=0`이며,
차트 데이터와 별개로 기록한다.

## 7. 검증 방법·판정

선정 ZIP의 해시와 파트 해시를 확인한 뒤, 표준 라이브러리 `zipfile`·
`xml.etree.ElementTree`로 QName, switch 경로, `chartIDRef` 대상의 존재,
manifest/OLE 연결, 유형, 명시적 제목 부재, 계열별 참조식·`ptCount`·`idx`·값,
축 ID와 교차 참조를 확인했다. 문서 JSON gold를 다시 읽어 XML에서 얻은 값과 비교했다.
한컴 공식 공개 모델과 OOXML 캐시 설명은 구조 의미의 보조 근거이며
gold 수치의 출처는 위 SHA-256으로 식별되는 XML 자체다.

**A04의 두 유형 데이터 조사 조건은 충족.** 이 조사만으로 라이브러리 전체 구현,
전체 XSD 적합성, 원본 시트 최신성 또는 한글 UI의 시각적 동일성을 검증한 것은 아니다.
현재 구현 검증은 [chart-validation.md](chart-validation.md)와
[chart-integration-validation.md](chart-integration-validation.md)에 기록한다.

저장소 루트에서 다음 명령으로 공개 표본의 해시·독립 XML gold와 구현을 비교한다.

```bash
python -m pytest tests/test_hwpx_charts.py -q -k public_corpus --tb=short
python -m pytest tests/test_hwpx_chart_integration.py -q -k 'public_documents or many_chart_real' --tb=short
```

`python`은 의존성이 설치된 프로젝트 환경의 인터프리터다. 원본 corpus가 없으면
실물 테스트는 skip하므로 성공으로 세지 않는다. 사양 JSON과 표본·파트 SHA-256은
독립 정답 대조를 위한 고정 자료로 유지한다.
