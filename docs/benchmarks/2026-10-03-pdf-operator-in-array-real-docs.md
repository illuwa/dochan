# 콘텐츠 스트림 배열 안의 연산자

2026-10-03. 공개 pdf.js `operator-in-TJ-array.pdf` 는 `[(Grandes) 0.0 Tc -250.0 (Client\350les,) … ] TJ` 처럼 TJ 배열 안에 `Tc` 연산자를 넣는다.
전에는 배열 파싱이 실패해 본문이 0자였다. 이제 콘텐츠 스트림을 읽을 때만 배열 안의 맨 연산자 단어를 건너뛴다(`true`·`false`·`null` 은 값으로 유지).
객체(사전·xref) 파싱은 전처럼 이런 배열을 거부한다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| PDF 텍스트 · 손상 콘텐츠 | 공개 `operator-in-TJ-array.pdf` | PDFium 텍스트 `Grandes Clientèles, Financements et Marchés` | 같은 글자 | `Grandes Clientèles, Financements et Marchés` | 통과 |
| 회귀 | 공개 pdf.js 983개 | 수정 전 Markdown SHA-256 | 바뀐 문서는 위 1개뿐 | 1/983 변경(위 문서) | 통과 |
