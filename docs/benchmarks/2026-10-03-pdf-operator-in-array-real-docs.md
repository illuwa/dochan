# 콘텐츠 스트림 배열 안의 연산자와 깨진 xref·Root 복구

2026-10-03. 공개 pdf.js `operator-in-TJ-array.pdf` 는 `[(Grandes) 0.0 Tc -250.0 (Client\350les,) … ] TJ` 처럼 TJ 배열 안에 `Tc` 연산자를 넣는다.
전에는 배열 파싱이 실패해 본문이 0자였다. 이제 콘텐츠 스트림을 읽을 때만 배열 안의 맨 연산자 단어를 건너뛴다(`true`·`false`·`null` 은 값으로 유지).
객체(사전·xref) 파싱은 전처럼 이런 배열을 거부한다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| PDF 텍스트 · 손상 콘텐츠 | 공개 `operator-in-TJ-array.pdf` | PDFium 텍스트 `Grandes Clientèles, Financements et Marchés` | 같은 글자 | `Grandes Clientèles, Financements et Marchés` | 통과 |
| 회귀 | 공개 pdf.js 983개 | 수정 전 Markdown SHA-256 | 바뀐 문서는 위 1개뿐 | 1/983 변경(위 문서) | 통과 |

## 깨진 증분 갱신의 xref·Root

공개 pdf.js `issue9418.pdf` 는 증분 갱신 xref 가 객체 1 을 헤더가 없는 오프셋(17)으로 가리키고, 그 갱신의 `/Root 1 0 R` 은 카탈로그가 아니라 Info 사전이다.
전에는 `카탈로그(Root)를 찾지 못함` 으로 0자였다. 이제 xref 오프셋이 객체 헤더를 가리키지 않으면(전에는 다른 객체 번호를 가리킬 때만) 한 번 객체 스캔으로 재구성하고,
객체 스트림 항목은 스캔이 못 보므로 유지한다. Root 가 `/Pages` 없는 사전이면 스캔으로 `/Type /Catalog` 를 찾는다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| PDF 텍스트 · 깨진 xref | 공개 `issue9418.pdf` | PDFium 텍스트(`Scale`, `Project`, `Date`, `Sheet`, `Revision/Issue`, `Project Name and Address`, `Firm Name …`) | 같은 낱말 | 180자, 위 낱말 포함 | 통과 |
| 회귀 | 공개 pdf.js 983개 | 수정 전 Markdown SHA-256 | 바뀐 문서는 위 1개뿐 | 1/983 변경 | 통과 |

