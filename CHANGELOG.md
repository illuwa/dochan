# Changelog

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
