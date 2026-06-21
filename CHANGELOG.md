# Changelog

## [1.0.1] - 2026-06-21

- Python 3.9 호환성 회귀 수정: `int | None` 타입 힌트를 `Optional[int]`로 교체
- 태그 릴리스 파이프라인이 Python 3.9 테스트를 통과하도록 정리

## [1.0.0] - 2026-06-21

- Stable PyPI packaging baseline for dochan.
- Marked package as production/stable (PEP 621 metadata and classifiers).
- Added PyPI publishing workflow with tag-driven release and tag build gate.
- Excluded internal test package from wheel/sdist distribution.
- Added project changelog and synchronized package version with `dochan.__version__`.

### Supported for this release

- HWP/HWPX: native parsing + markdown/json/plain outputs.
- Office documents: DOC/DOCX, PPT/PPTX, XLS/XLSX.
- CLI conversion + directory batch conversion.
- OCR optional dependency (Tesseract via `dochan[ocr]`).
