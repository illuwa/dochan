# 변환 속도 비교 — 2026-10-31 재측정 (PDF C 가속·XML C 경로·XLS 캐시 반영 뒤)

2026-10-04 비교(`2026-10-04-speed-comparison.md`)와 같은 방법으로 다시 쟀다: Apple M5 Pro, macOS, Python 3.12.12, 저장소 소스(main c6c4543, 세 PDF C 확장과
XML C 검사기를 `DOCHAN_BUILD_ACCEL=1` 로 빌드), 다른 도구는 저장소 밖 가상환경(PyMuPDF 2.0, pypdf 6.21.4, pdfminer.six 20260107, pdfplumber 0.11.10,
markitdown 0.1.9[all], pyhwp 0.1b15). 표본은 `scripts/bench_converters.py sample` 로 다시 뽑았다(시드 고정, PDF 300·HWP 300·DOCX 300·PPTX 200·XLSX 200·XLS 200).
도구마다 한 프로세스에서 파일별 변환 시간만 재고, 전·후·후·전·전·후 식으로 도구 순서를 바꿔 세 번 돈 뒤 **중앙값**을 적는다. 배수는 두 도구가 모두 성공한 파일만 합산.
장비에 다른 작업이 없는 상태에서 쟀다.

| 형식(표본) | 상대 도구 | 둘 다 성공 | dochan | 상대 | dochan 속도 | 회차별 배수 |
|---|---|---:|---:|---:|---|---|
| HWP (300) | pyhwp | 296 | 3.1초 | 28.9초 | 9.4배 빠름 | 9.38 / 9.36 / 9.26 |
| DOCX (300) | markitdown | 295 | 1.0초 | 5.4초 | 5.4배 빠름 | 5.64 / 4.99 / 5.43 |
| XLSX (200) | markitdown | 181 | 2.5초 | 13.4초 | 5.4배 빠름 | 5.28 / 5.39 / 5.37 |
| XLS (200) | markitdown | 180 | 4.9초 | 14.9초 | 3.1배 빠름 | 3.08 / 3.02 / 3.10 |
| PPTX (200) | markitdown | 194 | 0.8초 | 1.2초 | 1.6배 빠름 | 2.96 / 1.40 / 1.62 |
| PDF (300) | pypdf | 295 | 6.8초 | 20.2초 | 3.0배 빠름 | 2.98 / 2.97 / 2.96 |
| PDF (300) | pdfminer.six | 298 | 6.8초 | 34.0초 | 5.0배 빠름 | 5.03 / 5.00 / 5.05 |
| PDF (300) | pdfplumber | 297 | 6.8초 | 41.0초 | 6.0배 빠름 | 6.08 / 6.04 / 6.02 |
| PDF (300) | markitdown | 298 | 6.8초 | 46.7초 | 6.9배 빠름 | 6.93 / 6.89 / 6.74 |
| PDF (300) | PyMuPDF | 296 | 6.8초 | 1.5초 | **4.6배 느림** | 0.22 / 0.22 / 0.22 |

같은 표본에서 가속을 끈 순수 Python 의 PDF 합계 중앙값은 18.4초다(가속으로 2.7배). 10월 4일의 9.4배 느림이 4.6배 느림이 됐다.
PyMuPDF 1.28 → 2.0 으로 상대 쪽도 빨라졅다(같은 300개 기준 2.3 → 1.5초 추정 — 표본이 달라 직접 비교는 아니다).

- dochan 은 모든 형식에서 실패 0건이다. markitdown 은 XLSX 19·XLS 20·PPTX 6·DOCX 5·PDF 2, pyhwp 4, PyMuPDF 4, pypdf 5, pdfplumber 3, pdfminer.six 2 가 실패했다
  (표본에는 일부러 손상시킨 시험 파일이 섞여 있다).
- XLS 3.1배(10월 4일 2.5배)는 숫자 표시 캐시(`2026-10-31-xls-speed.md`), PPTX 1.6배(1.35배)는 XML C 경로(`2026-10-31-xml-fastpath.md`)의 효과다.
  PPTX 는 회차 편차가 커(1.40~2.96) 내세울 수치가 아니다.
- PyMuPDF 의 `get_text()` 는 글자만 뽑는다. 글꼴·좌표를 포함한 `get_text("dict")` 나 `find_tables()` 와 비교하면 순위가 바뀐다
  (`2026-10-06-pdf-content-interpreter-c.md`). 정확도 비교는 `2026-10-31-quality-vs-competitors.md`.
- 이 수치는 `DOCHAN_BUILD_ACCEL=1` 로 빌드했을 때다. 지금 PyPI 의 순수 Python 휠로는 PDF 가 PyMuPDF 보다 약 12배(18.4 대 1.5초) 느리다. 가속 휠 배포는 PR #24 에서 진행 중이다.

재현: `python -m scripts.bench_converters sample corpus out/` → `run <도구> out/files-<형식>.json out/<형식>-<도구>.json` 을 도구 순서를 바꿔 세 번 → 위 집계는 두 도구 공통 성공 파일 합계의 비율 중앙값.
