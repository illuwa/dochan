# legacy Office 이미지 OCR 실물 검증 (DOC·PPT·XLS)

2026년 10월 2일 통합 브랜치(`illuwa/patch-2026-09-06`)에서 측정했다. 세 형식의 리더 작업은 Python 3.9 에서 OCR 이
꺼져 있어(`dochan/utils/ocr.py` 의 3.10 이상 조건) 실제 엔진 결과를 확인하지 못했고, 이 문서가 그 빈칸을 채운다.

## 환경

Python 3.11 가상환경(저장소 밖, `pytesseract`·`Pillow` 설치)에서 레포 소스를 그대로 불러 `Dochan(path, ocr=True)` 로 읽었다.
Tesseract 5.5.3, 언어 `kor+eng`(기본값). 표본은 Apache POI test-data 와 LibreOffice 테스트 문서(공개 자료)다.

## 판정 기준

OCR 칸은 "문서 안 그림의 바이트를 정확히 꺼내 기존 OCR 경로로 넘기고, 인식 결과가 출력에 들어가는가"를 본다. 인식 품질은 엔진
몫이라 형식과 무관하다. 그래서 두 가지로 확인했다. 같은 문서의 OOXML 판이 있으면 바이트가 같은 그림의 OCR 결과가 OOXML 리더와
같은지 비교했다(OOXML 의 OCR 칸은 이미 ✅). 짝이 없으면 꺼낸 그림을 사람이 직접 보고 OCR 결과가 그림 속 글자와 맞는지 대조했다.

## 결과

| 형식 | 표본 | 방법 | 결과 |
|---|---|---|---|
| PPT | POI `alterman_security.ppt`, `customGeo.ppt` (각 `.pptx` 짝) | 바이트가 같은 그림의 OCR 결과 비교 | 공통 그림 8개 중 8개 동일, 8개 모두 비어 있지 않음(예: "Ohio Assessment Timeline", "Department of Education") |
| XLS | POI `ConditionalFormattingSamples.xls` (`.xlsx` 짝) | 바이트가 같은 그림의 OCR 결과 비교 | 그림 16개 바이트 동일, OCR 결과 16/16 동일(예: "Identify specific numbers, dates, and text in a list of products") |
| DOC | POI `53446.doc`, `64132.doc` | 꺼낸 그림을 직접 보고 대조 | `64132.doc` 그림 1 의 OCR "Cidades / Centro Integrado de Desenvolvimento / Administrativo, Estatistico e Social" 이 그림 속 글자와 일치(악센트 하나 차이는 엔진 품질), `53446.doc` 그림 2 의 "Enron Capital & Trade" 일치 |

단위 테스트는 각 리더 작업이 이미 두었다: `test_doc_image_bytes_reach_existing_ocr_path`,
`test_image_pib_delayed_blip_description_asset_and_ocr`(PPT), `test_xls_picture_bstore_pib_anchor_asset_and_ocr`(XLS).

## 한계

EMF·WMF 같은 벡터 그림은 OCR 엔진이 읽지 못해 결과가 비어 있다(다른 형식도 같다). XLS 의 다른 표본(`49423.xls` 등 러시아어
스캔 그림)은 짝이 없고 언어가 `kor+eng` 밖이라 품질 판정에서 뺐다.
