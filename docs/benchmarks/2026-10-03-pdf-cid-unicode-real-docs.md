# ToUnicode 없는 PDF CID 폰트 실물 검증

## 범위와 판정

PDF의 기존 `텍스트` 칸은 README에서 이미 ✅다. 이 작업은 그 칸의 ToUnicode 없는 CID 폰트 경로를 보완했다. README는 수정하지 않았다. 단위 테스트와 공개 실물 검증을 마쳤지만 전체 61개 중 일부만 복원하므로 CID 하위 경로를 전면 지원한다고 판정하지 않는다.

Adobe `pdf2unicode/Adobe-*-UCS2` 원본 다섯 개를 생성 스크립트로 압축했다. 원본 URL, BSD-3-Clause 고지, 각 SHA-256은 `NOTICE`와 `docs/THIRD_PARTY.md`에 기록했다. 생성기는 원본 SHA-256을 검증하고 고지 전문을 생성 모듈 머리말에 넣는다.

수량 측정에는 PDFium(pypdfium2)의 쪽별 텍스트를 썼다. 각 쪽의 공백·제어 문자·사설 영역·U+FFFD를 제외한 문자 다중집합을 비교했다. `일치/출력`에서 재현율 R은 일치/정답, 정밀도 P는 일치/출력이다. 0자로 나눈 비율은 —로 표시한다. PDFium이 같은 잘못된 CID 표를 적용할 수 있어, 글자가 바뀐 문서는 `.codex-work/review-opus/render/`의 렌더 PNG와 출력 문자열을 따로 대조했다. 아래의 PDFium 수치는 의미적 정답률이 아니다.

| 칸 | 표본 파일 | 정답 근거·기대 문자 수 | 변경 전 일치/출력 (R·P) | 변경 후 일치/출력 (R·P) | 판정·미개선 이유 |
| --- | --- | ---: | ---: | ---: | --- |
| PDF 텍스트, CID | `90ms_rksj_h_sample.pdf` | PDFium 쪽별 다중집합 16자 | 10/10, R 62.5%·P 100.0% | 10/10, R 62.5%·P 100.0% | 비 Identity 90ms-RKSJ-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `PDFJS-7562-reduced.pdf` | PDFium 쪽별 다중집합 5자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 글꼴에서 유효한 Unicode cmap 역대응을 찾지 못했다. |
| PDF 텍스트, CID | `Test-plusminus.pdf` | PDFium 쪽별 다중집합 115자·렌더 `Symbol: ±` | 115/115, R 100.0%·P 100.0% | 115/116, R 100.0%·P 99.1% | 렌더의 ±가 올바르게 복원됐다. PDFium 누락으로 계산상 정밀도만 감소했다. |
| PDF 텍스트, CID | `ThuluthFeatures.pdf` | PDFium 쪽별 다중집합 1440자 | 0/0, R 0.0%·P — | 37/190, R 2.6%·P 19.5% | 일치 문자 37자 증가(일부 글꼴의 경고는 남음). |
| PDF 텍스트, CID | `arial_unicode_en_cidfont.pdf` | PDFium 쪽별 다중집합 38자 | 0/0, R 0.0%·P — | 38/38, R 100.0%·P 100.0% | 일치 문자 38자 증가. |
| PDF 텍스트, CID | `bug1146106.pdf` | PDFium 쪽별 다중집합 34자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | Adobe CID 컬렉션 대응이 없는 CIDFontType0 글꼴이다. |
| PDF 텍스트, CID | `bug1365930.pdf` | PDFium 쪽별 다중집합 3자 | 3/3, R 100.0%·P 100.0% | 3/3, R 100.0%·P 100.0% | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `bug1650302_reduced.pdf` | PDFium 쪽별 다중집합 13자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `bug1771477.pdf` | PDFium 쪽별 다중집합 247자 | 240/957, R 97.2%·P 25.1% | 247/964, R 100.0%·P 25.6% | 일치 문자 7자 증가. |
| PDF 텍스트, CID | `bug920426.pdf` | PDFium 쪽별 다중집합 17자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `cff_bluescale_small_zones.pdf` | PDFium 쪽별 다중집합 3자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | Adobe CID 컬렉션 대응이 없는 CIDFontType0 글꼴이다. |
| PDF 텍스트, CID | `complex_ttf_font.pdf` | PDFium 쪽별 다중집합 510자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 글꼴에서 유효한 Unicode cmap 역대응을 찾지 못했다. |
| PDF 텍스트, CID | `issue11131_reduced.pdf` | PDFium 쪽별 다중집합 7자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 글꼴에서 유효한 Unicode cmap 역대응을 찾지 못했다. |
| PDF 텍스트, CID | `issue11242_reduced.pdf` | PDFium 쪽별 다중집합 7자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue11555.pdf` | PDFium 쪽별 다중집합 12자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 비 Identity 90ms-RKSJ-V 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue11578_reduced.pdf` | PDFium 쪽별 다중집합 7자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue11651.pdf` | PDFium 쪽별 다중집합 14자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue11768_reduced.pdf` | PDFium 쪽별 다중집합 2자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 비 Identity UniJIS-UTF8-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue11915.pdf` | PDFium 쪽별 다중집합 46자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue11922_reduced.pdf` | PDFium 쪽별 다중집합 0자 | 0/0, R —·P — | 0/0, R —·P — | 경고가 사라졌으나 출력·PDFium 일치 수는 불변이다. |
| PDF 텍스트, CID | `issue12418_reduced.pdf` | PDFium 쪽별 다중집합 18자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue13147.pdf` | PDFium 쪽별 다중집합 8자 | 0/0, R 0.0%·P — | 8/8, R 100.0%·P 100.0% | 일치 문자 8자 증가. |
| PDF 텍스트, CID | `issue13343.pdf` | PDFium 쪽별 다중집합 20자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 비 Identity 90ms-RKSJ-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue13916.pdf` | PDFium 쪽별 다중집합 85자 | 20/20, R 23.5%·P 100.0% | 20/20, R 23.5%·P 100.0% | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue15441.pdf` | PDFium 쪽별 다중집합 10자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue15443.pdf` | PDFium 쪽별 다중집합 7자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue15594_reduced.pdf` | PDFium 쪽별 다중집합 5자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue15977_reduced.pdf` | PDFium 쪽별 다중집합 12자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue16176.pdf` | PDFium 쪽별 다중집합 1자·렌더 첫 쪽의 𠮷 | 0/25, R 0.0%·P 0.0% | 0/25, R 0.0%·P 0.0% | 책갈피 영역까지 세는 탐침에서는 불변이지만 본문에 𠮷가 복원됐다. |
| PDF 텍스트, CID | `issue16538.pdf` | PDFium 쪽별 다중집합 634자 | 34/34, R 5.4%·P 100.0% | 634/634, R 100.0%·P 100.0% | 일치 문자 600자 증가. |
| PDF 텍스트, CID | `issue19182.pdf` | PDFium 쪽별 다중집합 52자 | 50/50, R 96.2%·P 100.0% | 50/50, R 96.2%·P 100.0% | 비 Identity UniCNS-UTF16-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue19550.pdf` | PDFium 쪽별 다중집합 15자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue19695.pdf` | PDFium 쪽별 다중집합 6자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue19802.pdf` | PDFium 쪽별 다중집합 966자 | 0/0, R 0.0%·P — | 92/1031, R 9.5%·P 8.9% | 일치 문자 92자 증가. |
| PDF 텍스트, CID | `issue20453.pdf` | PDFium 쪽별 다중집합 25자 | 0/10, R 0.0%·P 0.0% | 0/10, R 0.0%·P 0.0% | 책갈피 영역 비교가 본문 복원을 가리므로 이 수치만으로 성공·실패를 판정하지 않는다. |
| PDF 텍스트, CID | `issue2128r.pdf` | PDFium 쪽별 다중집합 20자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 비 Identity GBK-EUC-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue2537r.pdf` | PDFium 쪽별 다중집합 6자·렌더 `LINE UP` | 0/0, R 0.0%·P — | 0/6, R 0.0%·P 0.0% | 출력 `LINE UP`이 렌더와 일치한다. PDFium의 `/,1(83` 치환이 틀렸다. |
| PDF 텍스트, CID | `issue2884_reduced.pdf` | PDFium 쪽별 다중집합 18자·렌더 `4.6 簡易公募型/公募型競争入札` | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | CIDFontType2 내장 글꼴의 CID를 GID로 사용한다. 잘못 복원한 글자 18자를 버리고 경고한다. |
| PDF 텍스트, CID | `issue3323.pdf` | PDFium 쪽별 다중집합 5자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue3405r.pdf` | PDFium 쪽별 다중집합 0자 | 0/0, R —·P — | 0/0, R —·P — | 내장 글꼴에서 유효한 Unicode cmap 역대응을 찾지 못했다. |
| PDF 텍스트, CID | `issue3521.pdf` | PDFium 쪽별 다중집합 7자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 비 Identity GBKp-EUC-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue4402_reduced.pdf` | PDFium 쪽별 다중집합 22자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue4722.pdf` | PDFium 쪽별 다중집합 11자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue5801.pdf` | PDFium 쪽별 다중집합 74자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue6127.pdf` | PDFium 쪽별 다중집합 11083자 | 10195/10199, R 92.0%·P 100.0% | 10195/10199, R 92.0%·P 100.0% | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue6286.pdf` | PDFium 쪽별 다중집합 42자 | 21/21, R 50.0%·P 100.0% | 21/21, R 50.0%·P 100.0% | 비 Identity UniJIS-UCS2-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue7200.pdf` | PDFium 쪽별 다중집합 0자 | 0/0, R —·P — | 0/0, R —·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue7696.pdf` | PDFium 쪽별 다중집합 8자·렌더 `中國文件中國文件` | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | Adobe 표가 만든 `嘆囈貭鍔嘆囈貭鍔`를 버리고 경고한다. PDFium의 8/8 일치는 날조였다. |
| PDF 텍스트, CID | `issue7835.pdf` | PDFium 쪽별 다중집합 13자 | 13/13, R 100.0%·P 100.0% | 13/13, R 100.0%·P 100.0% | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue8061.pdf` | PDFium 쪽별 다중집합 13자 | 0/0, R 0.0%·P — | 13/13, R 100.0%·P 100.0% | 일치 문자 13자 증가. |
| PDF 텍스트, CID | `issue8372.pdf` | PDFium 쪽별 다중집합 2자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 비 Identity UniGB-UTF16-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue9915_reduced.pdf` | PDFium 쪽별 다중집합 9자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue_cff_unsigned_bbox.pdf` | PDFium 쪽별 다중집합 0자 | 0/0, R —·P — | 0/0, R —·P — | Adobe CID 컬렉션 대응이 없는 CIDFontType0 글꼴이다. |
| PDF 텍스트, CID | `javauninstall-7r.pdf` | PDFium 쪽별 다중집합 112자 | 0/0, R 0.0%·P — | 112/112, R 100.0%·P 100.0% | 일치 문자 112자 증가. |
| PDF 텍스트, CID | `mixedfonts.pdf` | PDFium 쪽별 다중집합 341자 | 279/289, R 81.8%·P 96.5% | 279/289, R 81.8%·P 96.5% | 비 Identity UniJIS-UTF16-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `noembed-eucjp.pdf` | PDFium 쪽별 다중집합 5자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 비 Identity EUC-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `noembed-identity-2.pdf` | PDFium 쪽별 다중집합 12자 | 0/0, R 0.0%·P — | 12/12, R 100.0%·P 100.0% | 일치 문자 12자 증가. |
| PDF 텍스트, CID | `noembed-identity.pdf` | PDFium 쪽별 다중집합 12자 | 7/7, R 58.3%·P 100.0% | 12/12, R 100.0%·P 100.0% | 일치 문자 5자 증가. |
| PDF 텍스트, CID | `noembed-jis7.pdf` | PDFium 쪽별 다중집합 12자 | 7/7, R 58.3%·P 100.0% | 7/7, R 58.3%·P 100.0% | 비 Identity H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `noembed-sjis.pdf` | PDFium 쪽별 다중집합 5자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 비 Identity 90ms-RKSJ-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `vertical.pdf` | PDFium 쪽별 다중집합 8자·렌더 세로쓰기 `あいうえお`·`日本語` | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 같은 가드로 참인 복원 8자를 잃었다. 글꼴 cmap이 없어 안전한 대체 경로를 확인하지 못했다. |

61개 문서 66쪽을 합친 결과, PDFium 기준 문자 수는 16,240자다. 일치 문자는 10,994자에서 11,918자로 증가했다. 문자 다중집합 재현율은 67.70%에서 73.39%로, 정밀도는 93.49%에서 86.47%로 변했다. 이전 코드에서 PDFium 일치가 늘어난 13개 중 렌더에 반하는 2개를 빼면 실제 개선은 11개였다. 현재 가드는 그중 `vertical.pdf`의 참인 복원 1개도 막으므로 최종적으로 10개 개선을 유지한다. 최초 61개 경고 문서 가운데 13개에서는 CID 경고가 모두 사라지고 48개에는 남는다. 처음 상태와 비교해 Markdown 해시가 다른 경고 문서는 13개다.

대표적으로 `javauninstall-7r.pdf`는 일본어 112/112자, `issue16538.pdf`는 634/634자, `arial_unicode_en_cidfont.pdf`는 38/38자를 PDFium과 일치시켰다. `issue19802.pdf`의 라틴어 문장은 렌더와 읽을 수 있는 범위에서 맞지만 PDFium의 치환 결과와 달라 다중집합 일치율이 낮다. `issue2537r.pdf`의 `LINE UP`도 렌더와 맞고 PDFium의 치환 결과는 틀렸다.

### 렌더 근거와 판정 한계

다음 표는 최초 코드에서 글자 출력이 바뀐 16개 문서를 모두 다시 판정한 것이다. PNG는 감수 과정에서 만든 `.codex-work/review-opus/render/`의 첫 쪽 렌더다. PNG는 저장소에 넣지 않는다. 렌더에서 확인한 문자열이나 글자만 정답으로 판단했으며, 쪽 전체의 모든 글자가 정확하다고 주장하지 않는다.

| 공개 문서 | 렌더 PNG | 화면과 현재 출력의 비교 | 판정 |
| --- | --- | --- | --- |
| `Test-plusminus.pdf` | `Test-plusminus_p0.png` | 화면과 출력 모두 `Symbol: ±`다. | PDFium 누락, 참인 복원이다. |
| `ThuluthFeatures.pdf` | `ThuluthFeatures_p0.png` | `Dotless Forms`, `Contextual`, `Ligatures` 등 영문 레이블이 맞다. 아랍어 본문은 복원되지 않았다. | 일부 개선이다. |
| `arial_unicode_en_cidfont.pdf` | `arial_unicode_en_cidfont_p0.png` | `This is an Arial Unicode PDF from OpenOffice.`의 단어와 공백이 맞다. | 개선이다. |
| `bug1771477.pdf` | `bug1771477_top.png` | 화면 상단의 `CORÉEN`, `ANGLAIS` 등이 출력에 있다. 한국어 입력문에는 별도 간격 문제가 남는다. | 일부 개선이다. |
| `issue13147.pdf` | `issue13147_p0.png` | 화면과 출력 모두 `準会場で受験の方`다. | 개선이다. |
| `issue16176.pdf` | `issue16176_p0.png` | 첫 쪽 왼쪽 위 글자 `𠮷`가 본문에 추가됐다. PDFium 다중집합 탐침은 책갈피 영역을 섞어 불변으로 잘못 분류했다. | 본문 개선이다. |
| `issue16538.pdf` | `issue16538_p0.png` | 화면의 일본어 본문이 출력에 복원됐다. | 개선이다. |
| `issue19802.pdf` | `issue19802_p0.png` | 첫 줄의 라틴어 및 확장 문자가 렌더와 출력에서 대응한다. PDFium 치환 문자열과는 다르다. | 일부 개선이다. |
| `issue2537r.pdf` | `issue2537r_p0.png` | 화면과 출력 모두 `LINE UP`이다. | PDFium 불일치지만 참인 복원이다. |
| `issue8061.pdf` | `issue8061_p0.png` | 화면과 출력 모두 `Factuurdatum:`으로 시작한다. | 개선이다. |
| `javauninstall-7r.pdf` | `javauninstall-7r_p0.png` | 화면의 일본어 지시문이 출력에 나타난다. | 개선이다. |
| `noembed-identity-2.pdf` | `noembed-identity-2_p0.png` | 화면과 출력 모두 `あAbstract012`다. | 개선이다. |
| `noembed-identity.pdf` | `noembed-identity_p0.png` | 화면의 일본어와 숫자가 출력에 나타난다. | 개선이다. |
| `issue7696.pdf` | `issue7696_p0.png` | 화면 `中國文件中國文件`과 이전 출력 `嘆囈貭鍔嘆囈貭鍔`가 다르다. 현재 출력은 비고 경고한다. | 이전 결과는 날조이며 현재는 미복원이다. |
| `issue2884_reduced.pdf` | `issue2884_reduced_p0.png` | 화면의 일본어 입찰 문구와 이전 출력의 한자가 다르다. 현재 출력은 비고 경고한다. | 이전 결과는 날조이며 현재는 미복원이다. |
| `vertical.pdf` | `vertical_p0.png`, `vertical_p1.png` | 화면의 세로쓰기 8자를 이전 코드는 복원했지만 현재 가드가 제거했다. | 참인 복원의 손실이다. |

## 회귀·안전 검증

- 기존 CID 경고가 없던 공개 PDF 922개의 Markdown SHA-256은 현재 HEAD 코드와 비교해 922/922개 동일했다. 원래 저장된 측정 JSON과 직접 비교하면 920/922개가 같은데, 예외 2개(`issue9418.pdf`, `operator-in-TJ-array.pdf`)는 현재 HEAD 코드로 같은 입력을 다시 측정해 현재 결과와 동일함을 확인했다. 해시와 길이 요약만 디스크에 저장했다.
- 내부 실물 79쌍의 `compare_pdf_fix2 --mode pairs --jobs 6` 전체 수치 행과 집계가 변경 전후 같았다. 내부 파일명·내용은 기록하지 않았다.
- 손상 글꼴, 과대 `cmap` 그룹 수, 순환 참조, 기존 CID 폰트 누출 방지 테스트를 통과했다. 내장 폰트는 8 MiB, cmap 레코드는 256개, 선택한 하위 표는 8개, format 4 구간은 8,192개, format 12 그룹은 100,000개, 열거 코드는 글꼴당 100,000개로 제한한다. 문서당 서로 다른 내장 글꼴 cmap은 최대 16개 스캔하고 동일 스트림은 캐시한다. 변형 글꼴 1,000건과 무작위 입력 3,000건은 예외 없이 처리했다.
- 내부 79쌍에는 Type0 글꼴이 없어 이 경로의 정답 근거로 삼을 수 없다. 위 79쌍 검사는 다른 PDF 동작이 악화되지 않았는지를 보는 회귀 검사다.

## 남은 범위

이번 공개 표본에서 코드→CID CMap 원본이 필요한 이름은 `90ms-RKSJ-H`, `90ms-RKSJ-V`, `EUC-H`, `GBK-EUC-H`, `GBKp-EUC-H`, `H`, `UniCNS-UTF16-H`, `UniGB-UTF16-H`, `UniJIS-UCS2-H`, `UniJIS-UTF16-H`, `UniJIS-UTF8-H`다. 이 이름에 대응하는 Adobe `cmap-resources` 파일이 추가로 필요하다. `KSCms-UHC-H`는 이번 61개에서 관찰되지 않았으며 해당 표본이 생기면 같은 방식으로 검증해야 한다. 내장 TrueType의 비 Unicode cmap 또는 글꼴 자체가 없는 경우도 남는다.
