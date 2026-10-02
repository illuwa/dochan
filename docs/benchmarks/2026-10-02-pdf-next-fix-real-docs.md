# PDF 리뷰 반영 실물 검증

기준 커밋은 `107e18d7725af8cc6680d5ba0e1ca2b931ed8163`이다. 링크·미주(A)를 먼저 분리 검증했으며 수식(B)의 의미 정답과 최종 회귀를 함께 기록했다. 외부 코퍼스는 읽기 전용으로 사용했다. README는 수정하지 않는다.

## 링크·미주(A)

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 미주 | `freeculture.pdf` | Poppler 원시 단어 위치와 21장 미주 정의를 독립 대조했다. | 정의와 참조 222개를 연결하고 장 소제목 21개를 보존한다. | 정의 내용·첫 페이지, 참조 장·번호·페이지·시작 x가 각각 222/222개 일치하고 장 소제목 21/21개를 보존했다. | 공개 경로는 통과했다. 내부 양성 미복원이 남아 ⬜를 유지한다. |
| 링크 | pdf.js 공개 983개다. | 원시 주석 Rect/QuadPoints와 독립 PDFium 글리프 중심을 대조했다. | 연결 문자열이 정확하고 URL 소실이 없어야 한다. | 비교 가능한 주석 678개 중 연결 388개, 보류 290개다. 연결 오류·URL 소실·최종 런 불일치는 0개다. | ⬜를 유지한다. |

A만 적용한 독립 체크아웃에서 전체 테스트는 3,295 passed, 24 skipped, 14 xfailed다. 목차 공백 백트래킹은 마지막 토큰 분리로 제거했다. 미주 위첨자는 HEAD의 0.30em 상승 허용 범위와 em 박스 범위의 합집합을 사용한다. 서로 다른 글꼴의 연속 문단은 본문 열에 있으면 포함한다. 크기 차이만으로 버리지 않으며, 기존 페이지 여백 또는 관측한 본문 열 밖의 교정 표지와 본문 아래의 번호·구역명 바닥글은 보존한다. 장 소제목을 삭제하지 않는다. 링크는 공백만 공유할 때 모호성 연결 집합을 합치지 않는다. 진단 프로브는 시간초과·문서·목록·주석 누락을 별도 상태로 기록한다.


## 수식(B)의 판정과 처리 계약

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 수식 | `bug1937438_af_from_latex.pdf`다. | 객체 53의 AF stream 28을 읽었다. | `\sqrt{x^{2}}=\lvert x\rvert`를 display로 출력하고 inline 3개는 보존한다. | display 1개가 의미 정답과 일치하고 inline 3개를 보존했다. | 확인한 범위는 통과했다. |
| 수식 | `bug1937438_mml_from_latex.pdf`다. | 객체 59 아래 namespace MathML StructElem 60과 MCID를 읽었다. | `c=\sqrt{a^{2}+b^{2}}`만 치환하고 집합 소속 inline은 보존한다. | display 1개와 inline 보존을 확인했다. | 확인한 범위는 통과했다. |
| 수식 | `bug1997343.pdf`다. | AF streams 42·44·46의 토큰·인자·행렬 순서를 읽었다. | 거듭제곱과 mod, 함수 행렬, 행렬 곱 3개를 출력한다. 코드 문장부호·inline·빈 구조는 Equation으로 만들지 않는다. | display 3개가 의미 정답과 일치하고 보존 항목 16개 및 빈 구조 3개를 확인했다. | 확인한 범위는 통과했다. |
| 수식 | `bug2004951.pdf`다. | 객체 35의 Alt가 낭독용 문장임을 확인했다. | LaTeX를 추측하지 않고 글리프를 보존한다. | Equation 0개이며 원래 글리프가 보존됐다. | 의미 수식 성공 표본으로 세지 않는다. |
| 수식 | `bug2009627.pdf`다. | AF streams 26·28을 읽었다. | mod 관계와 행렬 2개를 출력하고 inline 변수는 보존한다. | display 2개가 일치하고 inline 1개가 보존됐다. | 확인한 범위는 통과했다. |
| 수식 | `bug2025674.pdf`다. | AF stream 22를 읽었다. | `a^{2}+b^{2}=c^{2}`를 출력한다. | display 1개가 일치했다. | 확인한 범위는 통과했다. |

6문서의 원시 Formula는 33개다. 의미 정답을 가진 display 8개, inline·코드·Alt 보존 항목 22개, 빈 구조 3개로 구분한다. display 소유 조각 90개만 치환했고 보존 Formula 소유 조각 39개와 전체 비소유 조각 640개가 원문과 같다. 비소유 Artifact 95개도 보존했다. 기존의 26/26 주장은 inline·코드·낭독문까지 수식 성공으로 세었으므로 철회한다. 태그 없는 수식과 일부 의미 표현은 미지원이며 PDF 수식 칸은 **⬜ 유지**를 제안한다. 합·적분 첨자는 실물 양성 표본이 없으므로 단위 테스트 검증으로만 보고한다.

`FormulaExtractor`는 표와 각주 소유권이 결정된 뒤 실행한다. 해당 소유 글리프는 표 셀·각주 안에 남긴다. Code·Note·Table 구조 아래 수식도 보존한다. MathML의 `display="block"` 또는 PDF Layout의 `Placement=Block`이 있거나 같은 기준선에 다른 본문이 없는 경우에만 블록 Equation을 만든다. Alt/ActualText만으로 LaTeX를 만들지 않는다. TeX 연관 자료의 내부 달러 구분자와 빈 줄은 거부하며 글리프를 보존한다. Equation의 선택적 `script_format`은 MathML에 `mathml`, TeX에 `latex`를 기록한다. 다른 형식의 기존 JSON에는 필드를 추가하지 않는다.

ParentTree·StructParents가 있으면 해당 페이지에서 Formula 조상만 찾는다. ParentTree가 없으면 제한된 구조 순회를 사용하며 정수 MCID는 구조 노드 예산에 넣지 않는다. 태그 없는 표지를 먼저 순회한 경우 발견한 레코드를 다음 페이지에서도 재사용한다. 12,000개 MCID 뒤 수식과 수식 없는 문서, 12,000개 관계없는 구조 요소가 있는 ParentTree 페이지를 합성 테스트로 확인했다. 전수의 `bug1978317.pdf`에서 종전 Formula 10,000노드 경고는 사라졌다. 안전 상한은 구조 컨테이너 200,000개·깊이 64, Formula 4,096개, 원문 항목 256 KiB·문서 합계 8 MiB다. 이 값은 지원 페이지 수나 명세상 최대치를 주장하지 않는 자원 보호 한도다.

MathML 명령 뒤의 빈 그룹을 없애 첨자를 원래 연산자에 붙인다. 다문자 mi의 정체 기본값, `\sin x`, `\operatorname{mod}`, mtext의 수학 기호 모드, hat·tilde·vec 악센트를 처리한다. 아직 구현하지 않은 mstyle 상속 속성은 조용히 버리지 않고 변환을 거부한다. 이항계수를 분수로 바꾸는 지적은 원문 보존으로 해결했다.

공유 파일 변경은 `dochan/model/equation.py`의 선택적 문자열 필드와 `dochan/output/json_out.py`의 조건부 출력뿐이다. 새 런타임 의존성을 추가하지 않았다. HEAD의 테스트 단언은 변경하지 않았다. 이전 미커밋 수식 테스트는 inline·Alt를 블록으로 만들던 잘못된 계약을 display·선언된 TeX 표본으로 정정했다. MathML 기대 세 건도 잘못된 빈 그룹·함수·첨자를 표준 표현으로 고쳤다.


## 공개 PDF 수식의 의미 정답 근거

정답은 공개 PDF의 원시 AF MathML 및 MathML namespace StructElem의 토큰/인자 순서를 읽어 수작업으로 작성했다. `FormulaExtractor`와 `mathml_to_latex`의 출력에서 정답을 생성하지 않았다. display 수식만 Equation으로 치환하고 inline·Code·Alt-only는 글리프를 보존한다. 원본 수식의 수학적 참거짓은 검증 범위가 아니며, PDF가 실제로 담은 표현을 옮기는지를 검증한다.

공백·mspace의 배치 간격과 첨자가 붙지 않는 안전한 명령 종결만 정규화한다. `\sum{}_{i=1}^{n}`처럼 빈 그룹에 붙는 첨자는 정규화하지 않는다. 이 여섯 표본에는 합/적분 첨자가 없으므로 `\sum_{i=1}^{n}`과 `\int_{0}^{1}`은 합성 단위 테스트에서 별도로 검증해야 한다.

| 공개 파일 / Formula 객체 | 의미 정답 또는 원문 보존 기대 | 정답 근거 |
|---|---|---|
| `bug1937438_af_from_latex.pdf` / 42 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 22 |
| `bug1937438_af_from_latex.pdf` / 45 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 24 |
| `bug1937438_af_from_latex.pdf` / 48 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 26 |
| `bug1937438_af_from_latex.pdf` / 53 | `\sqrt{x^{2}}=&#124;x&#124;` | AF stream 28 |
| `bug1937438_mml_from_latex.pdf` / 32 | inline/Code 글리프를 본문에 그대로 보존한다. | namespace MathML StructElem 33 + 원시 MCID 글리프 |
| `bug1937438_mml_from_latex.pdf` / 59 | `c=\sqrt{a^{2}+b^{2}}` | namespace MathML StructElem 60 + 원시 MCID 글리프 |
| `bug1997343.pdf` / 141 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 40 |
| `bug1997343.pdf` / 142 | `n^{p}=n\operatorname{mod}p` | AF stream 42 |
| `bug1997343.pdf` / 145 | `\begin{matrix}\text{(2.1)} & f(x) & =\sin x+\cos x & f^{\prime}(x) & =\cos x-\sin x \\ \text{(2.2)} & g(x) & =2\cos x & g^{\prime}(x) & =-2\sin x\end{matrix}` | AF stream 44 |
| `bug1997343.pdf` / 150 | `(\begin{matrix}1 & 2 \\ 3 & 4\end{matrix})(\begin{matrix}1 & 1 \\ 0 & 1\end{matrix})=(\begin{matrix}1 & 3 \\ 3 & 7\end{matrix})` | AF stream 46 |
| `bug1997343.pdf` / 293 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 48 |
| `bug1997343.pdf` / 294 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 50 |
| `bug1997343.pdf` / 295 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 52 |
| `bug1997343.pdf` / 296 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 54 |
| `bug1997343.pdf` / 297 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 56 |
| `bug1997343.pdf` / 305 | 빈 mrow이므로 Equation을 생성하지 않는다. | AF stream 37 |
| `bug1997343.pdf` / 306 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 22 |
| `bug1997343.pdf` / 307 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 25 |
| `bug1997343.pdf` / 308 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 27 |
| `bug1997343.pdf` / 310 | 빈 mrow이므로 Equation을 생성하지 않는다. | AF stream 37 |
| `bug1997343.pdf` / 311 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 22 |
| `bug1997343.pdf` / 312 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 31 |
| `bug1997343.pdf` / 313 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 35 |
| `bug1997343.pdf` / 314 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 31 |
| `bug1997343.pdf` / 315 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 25 |
| `bug1997343.pdf` / 316 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 33 |
| `bug1997343.pdf` / 318 | 빈 mrow이므로 Equation을 생성하지 않는다. | AF stream 37 |
| `bug1997343.pdf` / 319 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 29 |
| `bug2004951.pdf` / 35 | Alt 낭독 문자열을 수학식으로 해석하지 않고 원래 글리프를 보존한다. | 원시 StructElem Alt |
| `bug2009627.pdf` / 56 | inline/Code 글리프를 본문에 그대로 보존한다. | AF stream 23 |
| `bug2009627.pdf` / 57 | `n^{p}=n\operatorname{mod}p` | AF stream 26 |
| `bug2009627.pdf` / 60 | `(\begin{matrix}1 & 2 \\ 3 & 4\end{matrix})` | AF stream 28 |
| `bug2025674.pdf` / 33 | `a^{2}+b^{2}=c^{2}` | AF stream 22 |

모든 display 기대는 위 표에 고정돼 있다. `bug1997343.pdf` 객체 142와 `bug2009627.pdf` 객체 57의 원문은 합동 기호가 아니라 등호와 `mod`를 사용하므로 기대를 임의로 `\equiv`로 바꾸지 않았다. 함수 행렬은 행/열과 (2.1), (2.2) 레이블을 모두 보존한다. 일반 함수는 `\sin x`, `\cos x`, 나머지 연산은 `\operatorname{mod}`로 표기한다.

다음은 각 정답의 원본 MathML이다. AF는 디코딩한 stream 원문을 그대로 싣고, namespace MathML은 StructElem의 태그·속성과 MCID 소유 글리프를 재조립했다. namespace 자료는 원래 XML 파일이 아니므로 재조립 사실을 구분한다.

### bug1937438_af_from_latex.pdf / Formula 42

AF stream 22

```xml
<math> <mi>x</mi> </math>
```

### bug1937438_af_from_latex.pdf / Formula 45

AF stream 24

```xml
<math> <mi>y</mi> </math>
```

### bug1937438_af_from_latex.pdf / Formula 48

AF stream 26

```xml
<math> <mi>x</mi> <mo>&gt;</mo> <mi>y</mi> </math>
```

### bug1937438_af_from_latex.pdf / Formula 53

AF stream 28

```xml
<math> <msqrt><msup><mi>x</mi><mn>2</mn></msup></msqrt> <mo>=</mo> <mrow intent="absolute-value($x)"><mo>|</mo><mi arg="x">x</mi><mo>|</mo></mrow> </math>
```

### bug1937438_mml_from_latex.pdf / Formula 32

namespace MathML StructElem 33 + 원시 MCID 글리프

```xml
<math><mi>𝑥</mi><mo>∈</mo><mi mathvariant="normal">ℝ</mi></math>
```

### bug1937438_mml_from_latex.pdf / Formula 59

namespace MathML StructElem 60 + 원시 MCID 글리프

```xml
<math display="block"><mi>𝑐</mi><mo>=</mo><msqrt><mrow><msup><mi>𝑎</mi><mn>2</mn></msup><mo>+</mo><msup><mi>𝑏</mi><mn>2</mn></msup></mrow></msqrt></math>
```

### bug1997343.pdf / Formula 141

AF stream 40

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"> <mi>𝑝</mi> </math>
```

### bug1997343.pdf / Formula 142

AF stream 42

```xml
<math display="block" xmlns="http://www.w3.org/1998/Math/MathML"> <msup> <mi>𝑛</mi> <mi>𝑝</mi> </msup> <mo lspace="0.278em" rspace="0.278em">=</mo> <mi>𝑛</mi> <mspace width="1.000em"/> <mi mathvariant="normal"> mod </mi> <mspace width="0.167em"/> <mspace width="0.167em"/> <mi>𝑝</mi> </math>
```

### bug1997343.pdf / Formula 145

AF stream 44

```xml
<math display="block" xmlns="http://www.w3.org/1998/Math/MathML"> <mtable class="align" columnalign="left right left right left" columnspacing="0 0 .8em 0" displaystyle="true" intent=":system-of-equations"> <mtr> <mtd intent=":equation-label"> <mtext> (2.1) </mtext> </mtd> <mtd intent=":pause-medium"> <mi>𝑓</mi> <mo lspace="0" rspace="0" stretchy="false">(</mo> <mi>𝑥</mi> <mo lspace="0" rspace="0" stretchy="false">)</mo> </mtd> <mtd> <mo lspace="0.278em" rspace="0.278em">=</mo> <mi mathvariant="normal"> sin </mi> <mspace width="0.167em"/> <mi>𝑥</mi> <mo lspace="0.222em" rspace="0.222em">+</mo> <mi mathvariant="normal"> cos </mi> <mspace width="0.167em"/> <mi>𝑥</mi> </mtd> <mtd intent=":pause-medium"> <msup> <mi>𝑓</mi> <mo lspace="0" rspace="0">′</mo> </msup> <mo lspace="0" rspace="0" stretchy="false">(</mo> <mi>𝑥</mi> <mo lspace="0" rspace="0" stretchy="false">)</mo> </mtd> <mtd> <mo lspace="0.278em" rspace="0.278em">=</mo> <mi mathvariant="normal"> cos </mi> <mspace width="0.167em"/> <mi>𝑥</mi> <mo lspace="0.222em" rspace="0.222em">−</mo> <mi mathvariant="normal"> sin </mi> <mspace width="0.167em"/> <mi>𝑥</mi> </mtd> </mtr> <mtr> <mtd intent=":equation-label"> <mtext> (2.2) </mtext> </mtd> <mtd intent=":pause-medium"> <mi>𝑔</mi> <mo lspace="0" rspace="0" stretchy="false">(</mo> <mi>𝑥</mi> <mo lspace="0" rspace="0" stretchy="false">)</mo> </mtd> <mtd> <mo lspace="0.278em" rspace="0.278em">=</mo> <mn>2</mn> <mspace width="0.167em"/> <mi mathvariant="normal"> cos </mi> <mspace width="0.167em"/> <mi>𝑥</mi> </mtd> <mtd intent=":pause-medium"> <msup> <mi>𝑔</mi> <mo lspace="0" rspace="0">′</mo> </msup> <mo lspace="0" rspace="0" stretchy="false">(</mo> <mi>𝑥</mi> <mo lspace="0" rspace="0" stretchy="false">)</mo> </mtd> <mtd> <mo lspace="0.278em" rspace="0">=</mo> <mo lspace="0.278em" rspace="0">−</mo> <mn>2</mn> <mspace width="0.167em"/> <mi mathvariant="normal"> sin </mi> <mspace width="0.167em"/> <mi>𝑥</mi> </mtd> </mtr> </mtable> </math>
```

### bug1997343.pdf / Formula 150

AF stream 46

```xml
<math display="block" xmlns="http://www.w3.org/1998/Math/MathML"> <mrow> <mo fence="true" lspace="0" rspace="0" symmetric="true">(</mo> <mspace width="-4.981pt"/> <mrow> <mspace width="4.981pt"/> <mtable> <mtr> <mtd> <mn>1</mn> </mtd> <mtd> <mn>2</mn> </mtd> </mtr> <mtr> <mtd> <mn>3</mn> </mtd> <mtd> <mn>4</mn> </mtd> </mtr> </mtable> <mspace width="4.981pt"/> </mrow> <mspace width="-4.981pt"/> <mo fence="true" lspace="0" rspace="0" symmetric="true">)</mo> </mrow> <mspace width="0.167em"/> <mrow> <mo fence="true" lspace="0" rspace="0" symmetric="true">(</mo> <mspace width="-4.981pt"/> <mrow> <mspace width="4.981pt"/> <mtable> <mtr> <mtd> <mn>1</mn> </mtd> <mtd> <mn>1</mn> </mtd> </mtr> <mtr> <mtd> <mn>0</mn> </mtd> <mtd> <mn>1</mn> </mtd> </mtr> </mtable> <mspace width="4.981pt"/> </mrow> <mspace width="-4.981pt"/> <mo fence="true" lspace="0" rspace="0" symmetric="true">)</mo> </mrow> <mo lspace="0.278em" rspace="0.278em">=</mo> <mrow> <mo fence="true" lspace="0" rspace="0" symmetric="true">(</mo> <mspace width="-4.981pt"/> <mrow> <mspace width="4.981pt"/> <mtable> <mtr> <mtd> <mn>1</mn> </mtd> <mtd> <mn>3</mn> </mtd> </mtr> <mtr> <mtd> <mn>3</mn> </mtd> <mtd> <mn>7</mn> </mtd> </mtr> </mtable> <mspace width="4.981pt"/> </mrow> <mspace width="-4.981pt"/> <mo fence="true" lspace="0" rspace="0" symmetric="true">)</mo> </mrow> </math>
```

### bug1997343.pdf / Formula 293

AF stream 48

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"> <mi>𝑛</mi> <mo lspace="0.278em" rspace="0.278em">&gt;</mo> <mn>2</mn> </math>
```

### bug1997343.pdf / Formula 294

AF stream 50

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"> <mi>𝑎</mi> </math>
```

### bug1997343.pdf / Formula 295

AF stream 52

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"> <mi>𝑏</mi> </math>
```

### bug1997343.pdf / Formula 296

AF stream 54

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"> <mi>𝑐</mi> </math>
```

### bug1997343.pdf / Formula 297

AF stream 56

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"> <msup> <mi>𝑎</mi> <mi>𝑛</mi> </msup> <mo lspace="0.222em" rspace="0.222em">+</mo> <msup> <mi>𝑏</mi> <mi>𝑛</mi> </msup> <mo lspace="0.278em" rspace="0.278em">=</mo> <msup> <mi>𝑐</mi> <mi>𝑛</mi> </msup> </math>
```

### bug1997343.pdf / Formula 305

AF stream 37

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mrow intent="_newline"></mrow></math>
```

### bug1997343.pdf / Formula 306

AF stream 22

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mo style="font-family:monospace">(</mo></math>
```

### bug1997343.pdf / Formula 307

AF stream 25

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mo style="font-family:monospace">)</mo></math>
```

### bug1997343.pdf / Formula 308

AF stream 27

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mo style="font-family:monospace">{</mo></math>
```

### bug1997343.pdf / Formula 310

AF stream 37

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mrow intent="_newline"></mrow></math>
```

### bug1997343.pdf / Formula 311

AF stream 22

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mo style="font-family:monospace">(</mo></math>
```

### bug1997343.pdf / Formula 312

AF stream 31

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mo style="font-family:monospace">"</mo></math>
```

### bug1997343.pdf / Formula 313

AF stream 35

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mo style="font-family:monospace">,</mo></math>
```

### bug1997343.pdf / Formula 314

AF stream 31

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mo style="font-family:monospace">"</mo></math>
```

### bug1997343.pdf / Formula 315

AF stream 25

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mo style="font-family:monospace">)</mo></math>
```

### bug1997343.pdf / Formula 316

AF stream 33

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mo style="font-family:monospace">;</mo></math>
```

### bug1997343.pdf / Formula 318

AF stream 37

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mrow intent="_newline"></mrow></math>
```

### bug1997343.pdf / Formula 319

AF stream 29

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"><mo style="font-family:monospace">}</mo></math>
```

### bug2004951.pdf / Formula 35

원시 StructElem Alt

```xml
Alt: cube root of , x plus y end cube root 
```

### bug2009627.pdf / Formula 56

AF stream 23

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML"> <mi>𝑝</mi> </math>
```

### bug2009627.pdf / Formula 57

AF stream 26

```xml
<math display="block" xmlns="http://www.w3.org/1998/Math/MathML"> <msup> <mi>𝑛</mi> <mi>𝑝</mi> </msup> <mo lspace="0.278em" rspace="0.278em">=</mo> <mi>𝑛</mi> <mspace width="1.000em"/> <mi mathvariant="normal"> mod </mi> <mspace width="0.167em"/> <mspace width="0.167em"/> <mi>𝑝</mi> </math>
```

### bug2009627.pdf / Formula 60

AF stream 28

```xml
<math display="block" xmlns="http://www.w3.org/1998/Math/MathML"> <mo fence="true" lspace="0" rspace="0" symmetric="true">(</mo> <mspace width="-4.981pt"/> <mrow> <mspace width="4.981pt"/> <mtable> <mtr> <mtd> <mn>1</mn> </mtd> <mtd> <mn>2</mn> </mtd> </mtr> <mtr> <mtd> <mn>3</mn> </mtd> <mtd> <mn>4</mn> </mtd> </mtr> </mtable> <mspace width="4.981pt"/> </mrow> <mspace width="-4.981pt"/> <mo fence="true" lspace="0" rspace="0" symmetric="true">)</mo> </math>
```

### bug2025674.pdf / Formula 33

AF stream 22

```xml
<math display="block" xmlns="http://www.w3.org/1998/Math/MathML"> <msup> <mi>𝑎</mi> <mn>2</mn> </msup> <mo lspace="0.222em" rspace="0.222em">+</mo> <msup> <mi>𝑏</mi> <mn>2</mn> </msup> <mo lspace="0.278em" rspace="0.278em">=</mo> <msup> <mi>𝑐</mi> <mn>2</mn> </msup> </math>
```


## 최종 전수 회귀

2026년 10월 3일에 HEAD와 최종 작업본을 각각 기본·text_tables 모드에서 983개씩 다시 실행했다. 네 실행 모두 983/983개를 완료했고 예외·시간초과는 0개다. 각 모드에서 Markdown 변경 9문서, JSON 변경 10문서였다. 수식 5문서, 미주 1문서, 링크 4문서가 본문 변경에 해당하며 `bug1997343.pdf`는 수식과 링크에 중복된다. `bug2004951.pdf`는 Alt 치환을 철회하여 HEAD의 본문으로 돌아왔다.

| 기본 모드 지표 | HEAD | 최종 |
| --- | ---: | ---: |
| Markdown 문자 수 | 2,190,148 | 2,195,958 |
| 평문 문자 수 | 2,096,986 | 2,096,398 |
| U+FFFD | 348 | 348 |
| ERR | 13 | 13 |
| WARN | 323 | 324 |
| 섹션 | 1,910 | 1,910 |
| 표 | 250 | 250 |
| 빈 Markdown 문서 | 294 | 294 |
| 미주 | 0 | 222 |

text_tables의 표는 427→427개로 같고 Markdown 문자는 2,206,373→2,212,216개, 평문 문자는 2,095,917→2,095,307개다. 각 모드의 ERR·U+FFFD·표·섹션 수는 HEAD와 같다.

JSON만 달라진 `issue20516.pdf`는 새 구조 접근으로 기존 xref 손상을 발견한 경고 1개다. 원시 xref에서 객체 11의 오프셋이 0이며 실제로 파일 머리의 객체 3을 가리킨다. 리더의 기존 재스캔 경고가 추가됐고 Markdown은 같다. 종전 `bug1978317.pdf`의 Formula 순회 한도 경고는 사라졌다. 그 밖의 경고 변경은 없다.

내부 79쌍은 익명 쌍별 모든 숫자와 집계가 HEAD와 완전히 같다. 평균 머리글/바닥글 적중률 0.9913, 오탐 0, 줄 결합 정확도 0.9378(7,658건), 평균/최소 토큰 비율 0.9754/0.8410, HWPX/PDF 표 845/886개, 평균 셀 적중률 0.9116, 구조/병합 일치율 0.6485/0.9191, 중첩 일치율 0.3636이다. 내부 파일명·본문은 기록하지 않았다.

최종 링크 프로브는 기본·text_tables 양쪽에서 983문서, 일치 388개, 보류 290개, 경계 오류·URL 소실·최종 런 불일치 0개다. 원래 보류 306개의 원인은 Form 텍스트 미추출 165개, 경계 잘림 74개, 실제 글자 없음 39개, 불확실 기하 9개, 다른 목적지 겹침 3개, 회복한 독립 주석 16개로 그대로다. 미주는 정의·참조 222개와 소제목 21개를 재확인했다. 참조 양 끝 좌표까지 일치하는 것은 216/222개이며, 6개 폭 차이를 완전 일치로 주장하지 않는다.

수식 밖 Artifact는 무조건 지우지 않는다. 이 정책 때문에 `bug1937438_mml_from_latex.pdf`의 MCID 밖 근호 Artifact는 별도의 원문 조각으로 남는다. Equation의 의미 정답은 맞지만 시각 장식의 중복 없는 완전 배치를 주장하지 않는다. 표 셀·각주·Form 수식의 의미 모델 변환, 태그 없는 수식과 미지원 MathML, TeX 전용 실물은 아직 미검증이다. 따라서 수식·각주/미주·본문 링크 세 칸 모두 ⬜ 유지다.

전체 테스트는 3,389 passed, 24 skipped, 14 xfailed다. Ruff와 `git diff --check`도 통과했다. skip·xfail을 지원 성공으로 세지 않았다.

## 재현 명령

`PDFJS_DIR`과 `PAIRS_DIR`은 읽기 전용 코퍼스 경로다. 아래 명령은 저장소 루트에서 Python 3.9로 실행한다. `BASELINE_REPO`는 원래 HEAD의 별도 체크아웃이다. 서로 다른 버전·모드의 출력 파일은 구분한다.

```sh
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
/usr/bin/python3 scripts/compare_pdf_fix2.py BASELINE_REPO PDFJS_DIR .codex-work/review-head-default.json
/usr/bin/python3 scripts/compare_pdf_fix2.py . PDFJS_DIR .codex-work/review-final-default.json
/usr/bin/python3 scripts/compare_pdf_fix2.py BASELINE_REPO PDFJS_DIR .codex-work/review-head-tables.json --text-tables
/usr/bin/python3 scripts/compare_pdf_fix2.py . PDFJS_DIR .codex-work/review-final-tables.json --text-tables
/usr/bin/python3 scripts/compare_pdf_fix2.py . PAIRS_DIR .codex-work/fix-verified-pairs.json --mode pairs
/usr/bin/python3 -m scripts.probe_pdf_formulas PDFJS_DIR --output .codex-work/b-formulas.json
/usr/bin/python3 -m scripts.probe_pdf_endnotes PDFJS_DIR
/usr/bin/python3 -m scripts.probe_pdf_link_boundaries PDFJS_DIR --output .codex-work/fix-links.json --baseline .codex-work/links-before-next.json --timeout 60
/usr/bin/python3 -m scripts.probe_pdf_link_boundaries PDFJS_DIR --output .codex-work/fix-links-tables.json --baseline .codex-work/links-before-next.json --text-tables --timeout 60
/usr/bin/python3 -m scripts.probe_pdf_link_deferrals PDFJS_DIR --baseline .codex-work/links-before-next.json --after .codex-work/fix-links.json --output .codex-work/fix-link-causes.json
```
