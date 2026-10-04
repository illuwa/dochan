# 변환 속도 비교 — 같은 파일·같은 환경에서 다른 도구와

## 조건

2026년 10월 4일, Apple M5 Pro(15코어) macOS 26.6.2, Python 3.12.12 에서 쟀다. 다른 무거운 작업이 없는 상태에서 같은 측정을 세 번 반복해 **중앙값**을 적는다.
dochan 은 1.15.0 직전 코드(저장소 소스)를 같은 파이썬으로 읽었다. 다른 도구는 저장소 밖 가상환경에 설치한 PyMuPDF 1.28.2, pypdf 6.19.0, pdfminer.six 20260107,
pdfplumber 0.11.10, markitdown 0.1.8, pyhwp 0.1b15 다. 이 도구들은 비교 대상일 뿐 dochan 의 의존성이 아니다.

표본은 공개 코퍼스에서 시드 고정(20261004) 무작위로 골랐다: PDF 300(정책브리핑 보도자료·pdf.js), HWP 300·HWPX 300(공개 HWP 코퍼스), DOCX 300·PPTX 200·XLSX 200·XLS 200(Apache POI·LibreOffice).
도구마다 한 프로세스에서 한 번 불러온 뒤 파일별 변환 시간(벽시계)만 쟀고(프로세스 시작·모듈 불러오기 제외), 파일당 60초 상한을 뒀다. 결과에는 시간·상태·출력 글자 수만 저장했다.
비교 배수는 **두 도구가 모두 성공한 파일만** 합산해 구했다.

    python -m scripts.bench_converters sample corpus out/
    python -m scripts.bench_converters run dochan out/files-pdf.json out/pdf-dochan.json
    python -m scripts.bench_converters run pymupdf out/files-pdf.json out/pdf-pymupdf.json
    python -m scripts.bench_converters report out/

## 결과

| 형식(표본) | 상대 도구 | 둘 다 성공 | dochan | 상대 | dochan 속도 |
|---|---|---:|---:|---:|---|
| HWP (300) | pyhwp | 296 | 3.6초 | 31.0초 | 8.7배 빠름 |
| DOCX (300) | markitdown | 295 | 1.1초 | 5.7초 | 5.0배 빠름 |
| XLSX (200) | markitdown | 181 | 2.8초 | 14.2초 | 5.1배 빠름 |
| XLS (200) | markitdown | 180 | 6.6초 | 16.8초 | 2.5배 빠름 |
| PPTX (200) | markitdown | 194 | 0.9초 | 1.3초 | 1.35배 빠름 |
| PDF (300) | markitdown | 298 | 20.0초 | 50.1초 | 2.5배 빠름 |
| PDF | pdfplumber | 297 | 20.0초 | 45.3초 | 2.2배 빠름 |
| PDF | pdfminer.six | 298 | 20.0초 | 35.6초 | 1.8배 빠름 |
| PDF | pypdf | 295 | 20.0초 | 22.0초 | 1.1배 빠름 |
| PDF | PyMuPDF | 296 | 20.0초 | 2.1초 | **9.4배 느림** |

세 번의 배수는 거의 같았다(예: HWP 8.70·8.94·8.43, DOCX 4.93·4.99·5.02, PyMuPDF 대비 9.49·9.41·9.25).

dochan 의 파일별 시간(세 번의 중앙값):

| 형식 | 중앙값 | p95 | 최대 | 표본 합계 |
|---|---:|---:|---:|---:|
| HWP | 3.5ms | 39ms | 0.47초 | 3.6초 |
| HWPX | 8.2ms | 82ms | 0.46초 | 6.6초 |
| DOCX | 2.1ms | 14ms | 0.07초 | 1.2초 |
| PPTX | 1.9ms | 9ms | 0.29초 | 1.0초 |
| XLSX | 0.9ms | 46ms | 0.75초 | 3.1초 |
| XLS | 1.1ms | 77ms | 1.80초 | 6.6초 |
| PDF | 5.2ms | 185ms | 3.42초 | 20.0초 |

HWPX 는 견줄 도구가 없어 dochan 수치만 있다.

변환 실패(예외·시간 초과): dochan 은 모든 형식에서 0건이다. markitdown 은 XLSX 19·XLS 20·PPTX 6·DOCX 5·PDF 2, pyhwp 는 4, PyMuPDF 4, pypdf 5, pdfplumber 3, pdfminer.six 2 였다
(표본에는 일부러 손상시킨 시험 파일이 섞여 있다). dochan 은 손상 파일에서 예외 대신 `doc.errors` 진단을 남긴다.

## 해석과 한계

- **HWP·Office 는 빠르다.** 무거운 일(압축 해제·XML 파싱·바이너리 레코드 해석)을 표준 라이브러리의 C 코드가 하고, 외부 의존성 없이 필요한 부분만 읽는다.
- **PDF 는 C 엔진보다 느리다.** PyMuPDF 는 C 로 쓴 엔진이고 dochan 은 순수 파이썬이다. PDF 는 글자·선의 좌표만 담고 있어 줄·공백·읽기 순서·표를 다시 조립해야 하고,
  내용 스트림 해석을 파이썬으로 한다. dochan 은 글자뿐 아니라 표·제목·링크·각주까지 복원하므로 하는 일의 양도 다르다. PyMuPDF 는 AGPL 이라 dochan(MIT)이 가져다 쓸 수 없다.
  순수 파이썬 도구(pypdf·pdfminer.six·pdfplumber·markitdown)보다는 1.1~2.5배 빠르다.
- **PDF 의 꼬리가 길다.** 중앙값은 5.2ms 지만 벡터 그림이 많은 쪽이나 수백 쪽 문서는 수 초가 걸린다. 내용 스트림 전용 스캐너와 경로 처리 최적화(출력 해시 동일)를 별도 브랜치에서
  진행 중이며, 전체 PDF 2,120건 합계 기준 390.5 → 242.6초(1.6배), 이 표본 300개 기준 20.0 → 18.1초다. 아직 배포 전이다.
- **PPTX 의 1.35배는 차이가 작다.** 내세울 수치가 아니다.
- **출력이 같은 일을 하는 것은 아니다.** 도구마다 뽑는 내용(글자만 / 표·제목 포함)이 달라 속도만으로 우열을 말할 수 없다. 이 표는 "같은 파일을 넣었을 때 걸리는 시간"만 보여 준다.
- **측정은 조용한 기계에서 여러 번.** 다른 작업과 함께 한 번 잰 값은 HWP 11.7배·PPTX 2.9배로 달랐다. 그 값은 쓰지 않는다.
- Docling·Unstructured 처럼 모델을 쓰는 도구와는 아직 비교하지 않았다.
