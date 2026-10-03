# PDF Encoding CMap 실물 검증 (2026-10-04)

## 범위와 판정 근거

ISO 32000-1 9.7.5·9.7.6.2·9.10.2의 코드 공간, 코드→CID, 원래 코드의 ToUnicode 조회, CID 기준 폭 계산을 검증했다. Adobe `cmap-resources`에서 선택한 인코딩 CMap 61개를 압축했고, 생성 모듈은 451,331바이트다. 원본별 SHA-256과 저작권 줄은 `NOTICE`에, 고정 해시 목록은 `scripts/pdf_predefined_cmap_hashes.json`에 있다. 요청에 적힌 표 118의 59개 목록과 선택한 61개 목록의 정확한 차이는 오프라인에서 공식 표 원문을 대조하지 못해 확정하지 않았다. 61개가 59개와 정확히 일치한다고 주장하지 않는다.

공개 pdf.js 코퍼스의 PDF 983개를 객체 수 제한 없이 조사했다. ToUnicode가 없는 미리 정의된 인코딩 글꼴은 `90ms-RKSJ-H` 5개, `GBKp-EUC-H` 4개, `UniGB-UTF16-H` 3개, `GBK-EUC-H` 3개, `UniJIS-UTF16-H` 3개, `UniCNS-UTF16-H`·`UniJIS-UCS2-H`·`EUC-H`·`H`가 각각 1개였다. `/Encoding` 스트림은 ToUnicode 유무와 무관하게 13개 PDF의 글꼴 14개였고, 그중 ToUnicode 없는 글꼴은 1개였다. 조사 실패는 0개였다. 이 수치는 `python -m scripts.probe_pdf_predefined_cmap corpus/pdfjs-src/test/pdfs <출력.json>`으로 다시 얻을 수 있다.

아래 수치는 PDFium의 쪽별 비공백 문자 다중집합과 dochan 출력의 교집합이다. `일치/실제/정답`으로 쓰며, 재현율은 일치÷정답, 정밀도는 일치÷실제다. PDFium도 Adobe CMap을 사용할 수 있으므로 독립 정답이 아니다. 바뀐 글자는 해당 PDF의 1쪽을 PDFium으로 PNG 렌더링하여 직접 읽고 출력 문자열과 대조했다. 표에 나타난 파일명은 공개 코퍼스의 파일명이다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| PDF Type0 코드→CID·문자, RKSJ | `90ms_rksj_h_sample.pdf` | PDFium PNG 1쪽의 `Hello ASCII`, `日本語テスト` | 두 줄 모두 복원 | 두 줄이 동일하게 출력되고 10/10/16 → 16/16/16 | 통과 |
| PDF Type0 코드→CID·문자, GBKp-EUC | `issue3521.pdf` | PDFium PNG 1쪽의 `我们都是黑体字` | 7자 복원 | 동일한 7자를 출력하고 0/0/7 → 7/7/7 | 통과 |
| PDF Type0 코드→CID·문자, UniGB-UTF16 | `issue8372.pdf` | PDFium PNG 1쪽의 `目录` | 2자 복원 | 동일한 2자를 출력하고 0/0/2 → 2/2/2 | 통과 |
| PDF Type0 코드→CID·문자, GBK-EUC | `issue2128r.pdf` | PDFium PNG 1쪽의 중국어 제목·작성자 행 | 20자 복원 | 두 행의 글자를 출력하고 0/0/20 → 20/20/20 | 통과 |
| PDF Type0 코드→CID·문자, UniJIS-UTF16 | `mixedfonts.pdf` | PDFium PNG 1쪽의 영문 글꼴 예시와 쪽 아래 문구 | 누락 글자 회복 | 일치 279→341자, 실제 289→363자이며 줄바꿈·공백이 다름 | 부분 통과 |
| PDF Type0 코드→CID·문자, UniCNS-UTF16 | `issue19182.pdf` | PDFium PNG 1쪽의 중문 이름 필드 | 이름 글자 회복 | 일치 50→52자, 실제 50→53자 | 부분 통과 |
| PDF Type0 코드→CID·문자, UniJIS-UCS2 | `issue6286.pdf` | PDFium PNG 1쪽의 `好酸球`가 든 두 행 | 누락 행 복원 | 일치 21→42자, 실제 21→42자 | 통과 |
| PDF Type0 코드→CID·문자, EUC-H | `noembed-eucjp.pdf` | PDFium PNG 1쪽의 `あいうえお` | 5자 복원 | 동일한 5자를 출력하고 0/0/5 → 5/5/5 | 통과 |
| PDF Type0 코드→CID·문자, H | `noembed-jis7.pdf` | PDFium PNG 1쪽의 ASCII와 `あいうえお` | 누락 일본어 복원 | 일치 7→12자, 실제 7→12자 | 통과 |
| PDF Type0 세로 CMap | `issue11555.pdf` | PDFium PNG 1쪽의 세로 `abc`와 `あいう` 두 행 | 12자 복원 | 0/0/12 → 12/12/12, 세로 문자 순서가 렌더와 일치 | 통과 |
| PDF 내장 Encoding CMap | `issue11768_reduced.pdf` | PDFium PNG 1쪽의 `cm` | 2자 복원 | 0/0/2 → 2/2/2 | 통과 |
| PDF 내장 Encoding CMap의 비표준 입력 | `bug920426.pdf` | 원시 Encoding 스트림은 `bfchar`를 코드→CID 위치에 사용 | 명세의 `cidchar`·`cidrange`만 적용 | 0/0/17 → 0/0/17 | 범위 밖, 개선 없음 |

## 지정 표본의 쪽별 합계

지정된 20개 파일 25쪽 전체의 일치/실제/정답은 **10,517/12,249/14,156 → 10,686/12,431/14,156**이다. 재현율은 74.29%→75.49%, 정밀도는 85.86%→85.96%다. 크기가 큰 기존 추출 본문도 합계에 포함하므로, 이 전체 수치만으로 새 CMap 글꼴의 성공률을 판단하지 않는다.

| 공개 PDF | 이전 일치/실제/정답 | 이후 일치/실제/정답 | 관찰 |
| --- | ---: | ---: | --- |
| `90ms_rksj_h_sample.pdf` | 10/10/16 | 16/16/16 | 누락 일본어 회복 |
| `issue13343.pdf` | 0/0/20 | 20/20/20 | RKSJ 글자 회복 |
| `noembed-sjis.pdf` | 0/0/5 | 5/5/5 | RKSJ 글자 회복 |
| `issue3521.pdf` | 0/0/7 | 7/7/7 | GBKp-EUC 글자 회복 |
| `file_pdfjs_test.pdf` | 5826/7395/7873 | 5826/7395/7873 | 기존 출력과 다중집합 동일, 대상 글꼴의 독립 기여를 확인하지 못함 |
| `issue14438.pdf` | 4240/4377/4275 | 4240/4377/4275 | 기존 출력과 다중집합 동일, 대상 글꼴의 독립 기여를 확인하지 못함 |
| `issue8372.pdf` | 0/0/2 | 2/2/2 | UniGB-UTF16 글자 회복 |
| `issue19360.pdf` | 23/23/23 | 23/23/23 | 이미 모든 정답 글자가 출력됨 |
| `issue2128r.pdf` | 0/0/20 | 20/20/20 | GBK-EUC 글자 회복 |
| `issue15262.pdf` | 35/51/53 | 35/51/53 | 대상 글꼴의 독립 기여를 확인하지 못함 |
| `mixedfonts.pdf` | 279/289/341 | 341/363/341 | 글자 회복, 공백·부가 텍스트 차이 남음 |
| `issue19182.pdf` | 50/50/52 | 52/53/52 | 중문 이름 글자 회복, 추가 1자 남음 |
| `issue6286.pdf` | 21/21/42 | 42/42/42 | 누락 행 회복 |
| `noembed-eucjp.pdf` | 0/0/5 | 5/5/5 | EUC-H 글자 회복 |
| `noembed-jis7.pdf` | 7/7/12 | 12/12/12 | H 글자 회복 |
| `bug1019475_1.pdf` | 18/18/1371 | 18/18/1371 | 글자 수 개선 없음, 공백 배치가 바뀜 |
| `bug920426.pdf` | 0/0/17 | 0/0/17 | 비표준 Encoding 스트림이라 매핑하지 않음 |
| `issue10519_reduced.pdf` | 8/8/8 | 8/8/8 | 글자는 기존에 모두 추출됨 |
| `issue11768_reduced.pdf` | 0/0/2 | 2/2/2 | 내장 UTF-8 CMap의 붙어 있는 토큰과 4바이트 코드 공간을 처리함 |
| `issue11555.pdf` | 0/0/12 | 12/12/12 | 세로 CMap 글자 회복 |

## 회귀와 한계

추가한 합성 테스트는 가변 코드 분할, CID 범위·문자·notdef, 미리 정의된 부모, ToUnicode의 원래 코드 조회, CIDSystemInfo 불일치, 단일 바이트 0x20의 Tw, CID 기준 가로·세로 폭, 잘린 코드, 순환 부모, 큰 입력, 무작위 입력을 검사한다.

공개 PDF 983개의 변경 전후 Markdown SHA-256 비교에서 965개는 동일하고 18개가 달랐다. 새 글자가 회복되며 바뀐 13개는 `90ms_rksj_h_sample.pdf`, `issue11555.pdf`, `issue11768_reduced.pdf`, `issue13343.pdf`, `issue19182.pdf`, `issue2128r.pdf`, `issue3521.pdf`, `issue6286.pdf`, `issue8372.pdf`, `mixedfonts.pdf`, `noembed-eucjp.pdf`, `noembed-jis7.pdf`, `noembed-sjis.pdf`다. 다른 5개인 `bug1019475_1.pdf`, `issue10519_reduced.pdf`, `issue13242.pdf`, `issue20232.pdf`, `issue9534_reduced.pdf`는 모두 내장 Encoding CMap을 쓰며, 코드→CID 폭 적용에 따른 공백·배치가 달라졌다. 이 5개의 비공백 문자 다중집합 일치 수는 각각 변경 전후 동일했다. `issue13242.pdf`의 Markdown 길이는 3,204자에서 2,922자로 줄었지만 비공백 문자 2,442자는 변경 전후 모두 PDFium과 일치했다. 대체 문자 총수는 1,173개로 동일했다.

내부 실물 79쌍은 `scripts.compare_pdf_fix2`의 `--mode pairs --jobs 6`으로 변경 전후를 각각 측정했다. 79개 모두 완료했고, **79개 문서의 모든 수치 행과 집계가 동일**했다. 주요 집계는 머리글·바닥글 적중 0.9913, join 정확도 0.9378, 평균 토큰 비율 0.9754, 표 셀 적중 0.9152, 병합 일치 0.9277로 양쪽이 같았다. 내부 파일명과 본문은 기록하지 않았다.

전체 테스트는 `/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp`로 5,052개 통과, 33개 건너뜀, 14개 예상 실패를 확인했다. CID 폭 회귀 테스트 1개를 추가한 뒤 `/usr/bin/python3 -m scripts.block_lxml pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp`로 5,053개 통과, 33개 건너뜀, 14개 예상 실패를 확인했고 lxml import 시도는 0회였다. `ruff check dochan scripts tests`, `git diff --check`, 로컬 절대 경로 검사도 통과했다. 생성기를 다시 실행한 결과 451,331바이트의 모듈이 현재 파일과 바이트 단위로 일치했다.
