# ToUnicode 없는 PDF CID 폰트 실물 검증

## 범위와 판정

PDF의 기존 `텍스트` 칸은 README에서 이미 ✅다. 이 작업은 그 칸의 ToUnicode 없는 CID 폰트 경로를 보완했다. README는 수정하지 않았다. 단위 테스트와 공개 실물 검증을 마쳤지만 전체 61개 중 일부만 복원하므로 CID 하위 경로를 전면 지원한다고 판정하지 않는다.

Adobe `pdf2unicode/Adobe-*-UCS2` 원본 다섯 개를 생성 스크립트로 압축했다. 생성 모듈은 394,594바이트다. 원본 URL, BSD-3-Clause 고지, 각 SHA-256은 `NOTICE`와 `docs/THIRD_PARTY.md`에 기록했다.

독립 정답지는 PDFium(pypdfium2)으로 추출한 쪽별 텍스트다. 각 쪽의 공백·제어 문자·사설 영역·U+FFFD를 제외한 문자 다중집합을 비교했다. `일치/출력`에서 재현율 R은 일치/정답, 정밀도 P는 일치/출력이다. 0자로 나눈 비율은 —로 표시한다. 아래 표의 PDFium 출력도 일부 문서에서는 깨져 있으므로 일치율이 곧 추출 텍스트의 의미적 정확도는 아니다.

| 칸 | 표본 파일 | 정답 근거·기대 문자 수 | 변경 전 일치/출력 (R·P) | 변경 후 일치/출력 (R·P) | 판정·미개선 이유 |
| --- | --- | ---: | ---: | ---: | --- |
| PDF 텍스트, CID | `90ms_rksj_h_sample.pdf` | PDFium 쪽별 다중집합 16자 | 10/10, R 62.5%·P 100.0% | 10/10, R 62.5%·P 100.0% | 비 Identity 90ms-RKSJ-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `PDFJS-7562-reduced.pdf` | PDFium 쪽별 다중집합 5자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 글꼴에서 유효한 Unicode cmap 역대응을 찾지 못했다. |
| PDF 텍스트, CID | `Test-plusminus.pdf` | PDFium 쪽별 다중집합 115자 | 115/115, R 100.0%·P 100.0% | 115/116, R 100.0%·P 99.1% | CID 복원 1자가 PDFium 문자 집합에 없어 정밀도가 감소했다. |
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
| PDF 텍스트, CID | `issue16176.pdf` | PDFium 쪽별 다중집합 1자 | 0/25, R 0.0%·P 0.0% | 0/25, R 0.0%·P 0.0% | 경고가 사라졌으나 출력·PDFium 일치 수는 불변이다. |
| PDF 텍스트, CID | `issue16538.pdf` | PDFium 쪽별 다중집합 634자 | 34/34, R 5.4%·P 100.0% | 634/634, R 100.0%·P 100.0% | 일치 문자 600자 증가. |
| PDF 텍스트, CID | `issue19182.pdf` | PDFium 쪽별 다중집합 52자 | 50/50, R 96.2%·P 100.0% | 50/50, R 96.2%·P 100.0% | 비 Identity UniCNS-UTF16-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue19550.pdf` | PDFium 쪽별 다중집합 15자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue19695.pdf` | PDFium 쪽별 다중집합 6자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue19802.pdf` | PDFium 쪽별 다중집합 966자 | 0/0, R 0.0%·P — | 92/1031, R 9.5%·P 8.9% | 일치 문자 92자 증가. |
| PDF 텍스트, CID | `issue20453.pdf` | PDFium 쪽별 다중집합 25자 | 0/10, R 0.0%·P 0.0% | 0/10, R 0.0%·P 0.0% | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue2128r.pdf` | PDFium 쪽별 다중집합 20자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 비 Identity GBK-EUC-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue2537r.pdf` | PDFium 쪽별 다중집합 6자 | 0/0, R 0.0%·P — | 0/6, R 0.0%·P 0.0% | CID 복원으로 6자를 얻었으나 PDFium의 치환 문자열과 불일치한다. |
| PDF 텍스트, CID | `issue2884_reduced.pdf` | PDFium 쪽별 다중집합 18자 | 0/0, R 0.0%·P — | 15/18, R 83.3%·P 83.3% | 일치 문자 15자 증가. |
| PDF 텍스트, CID | `issue3323.pdf` | PDFium 쪽별 다중집합 5자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue3405r.pdf` | PDFium 쪽별 다중집합 0자 | 0/0, R —·P — | 0/0, R —·P — | 내장 글꼴에서 유효한 Unicode cmap 역대응을 찾지 못했다. |
| PDF 텍스트, CID | `issue3521.pdf` | PDFium 쪽별 다중집합 7자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 비 Identity GBKp-EUC-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue4402_reduced.pdf` | PDFium 쪽별 다중집합 22자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue4722.pdf` | PDFium 쪽별 다중집합 11자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue5801.pdf` | PDFium 쪽별 다중집합 74자 | 0/0, R 0.0%·P — | 0/0, R 0.0%·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue6127.pdf` | PDFium 쪽별 다중집합 11083자 | 10195/10199, R 92.0%·P 100.0% | 10195/10199, R 92.0%·P 100.0% | 내장 TrueType/Unicode cmap이 없어 GID→Unicode를 확인할 수 없다. |
| PDF 텍스트, CID | `issue6286.pdf` | PDFium 쪽별 다중집합 42자 | 21/21, R 50.0%·P 100.0% | 21/21, R 50.0%·P 100.0% | 비 Identity UniJIS-UCS2-H 코드→CID 표가 없어 복원하지 못했다. |
| PDF 텍스트, CID | `issue7200.pdf` | PDFium 쪽별 다중집합 0자 | 0/0, R —·P — | 0/0, R —·P — | 사용 가능한 코드→CID 또는 GID→Unicode 대응을 확인하지 못했다. |
| PDF 텍스트, CID | `issue7696.pdf` | PDFium 쪽별 다중집합 8자 | 0/0, R 0.0%·P — | 8/8, R 100.0%·P 100.0% | 일치 문자 8자 증가. |
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
| PDF 텍스트, CID | `vertical.pdf` | PDFium 쪽별 다중집합 8자 | 0/0, R 0.0%·P — | 8/8, R 100.0%·P 100.0% | 일치 문자 8자 증가. |

61개 문서 66쪽을 합친 결과, PDFium 기준 문자 수는 16240자다. 일치 문자는 10994자에서 11949자로 증가했다. 문자 다중집합 재현율은 67.70%에서 73.58%로, 정밀도는 93.49%에서 86.48%로 변했다. 정밀도 하락에는 PDFium 자체가 깨진 글자를 반환하는 `issue19802.pdf`, `ThuluthFeatures.pdf`, `issue2537r.pdf`가 포함된다. 13개 문서에서 일치 문자가 늘었고 15개 문서에서 공백 등을 제외한 문자 출력 수가 달라졌다. Markdown 해시는 경고 집단의 16개 문서에서 달라졌다. 최초 61개 경고 문서 가운데 16개의 CID 경고가 모두 사라졌으며 45개에는 미복원 글꼴 경고가 남았다.

대표적으로 `javauninstall-7r.pdf`는 일본어 112/112자, `issue16538.pdf`는 634/634자, `arial_unicode_en_cidfont.pdf`는 38/38자를 PDFium과 일치시켰다. 반면 `issue19802.pdf`는 dochan 쪽에 읽을 수 있는 라틴어 문장이 나타나지만 PDFium 문자열에는 제어 문자가 섞인 치환 결과가 있어 다중집합 일치율이 낮다. `issue2537r.pdf`에서도 dochan의 단어와 PDFium의 기호 치환 결과가 일치하지 않는다. 이런 표본은 원시 글꼴 매핑 근거와 함께 따로 해석해야 한다.

## 회귀·안전 검증

- 기존 CID 경고가 없던 공개 PDF 922개의 Markdown SHA-256은 변경 전후 922/922개 동일했다. 해시와 길이 요약만 디스크에 저장했다.
- 내부 실물 79쌍의 `compare_pdf_fix2 --mode pairs --jobs 6` 전체 수치 행과 집계가 변경 전후 같았다. 내부 파일명·내용은 기록하지 않았다.
- 손상 글꼴, 과대 `cmap` 그룹 수, 순환 참조, 기존 CID 폰트 누출 방지 테스트를 통과했다. 내장 폰트는 8 MiB, cmap 레코드는 256개, 선택한 하위 표는 8개, format 4 구간은 8,192개, format 12 그룹은 4,096개, 열거 코드는 하위 표당 100,000개로 제한한다.

## 남은 범위

이번 공개 표본에서 코드→CID CMap 원본이 필요한 이름은 `90ms-RKSJ-H`, `90ms-RKSJ-V`, `EUC-H`, `GBK-EUC-H`, `GBKp-EUC-H`, `H`, `UniCNS-UTF16-H`, `UniGB-UTF16-H`, `UniJIS-UCS2-H`, `UniJIS-UTF16-H`, `UniJIS-UTF8-H`다. 이 이름에 대응하는 Adobe `cmap-resources` 파일이 추가로 필요하다. `KSCms-UHC-H`는 이번 61개에서 관찰되지 않았으며 해당 표본이 생기면 같은 방식으로 검증해야 한다. 내장 TrueType의 비 Unicode cmap 또는 글꼴 자체가 없는 경우도 남는다.
