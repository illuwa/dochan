from pathlib import Path

from dochan.model.document import Document
from dochan.reader import Dochan
from dochan.utils import ocr


def test_ocr_is_unavailable_below_supported_python(monkeypatch):
    monkeypatch.setattr(ocr, "_python_supports_ocr", lambda: False)
    monkeypatch.setattr(ocr, "_ocr_available", True)

    assert ocr.is_ocr_available() is False


def test_reader_reports_python_requirement_when_ocr_is_unsupported(monkeypatch):
    reader = Dochan.__new__(Dochan)
    reader.doc = Document()
    monkeypatch.setattr(ocr, "_python_supports_ocr", lambda: False)
    monkeypatch.setattr(ocr, "_ocr_available", None)

    reader._run_ocr()

    assert reader.doc.errors == ["WARN: OCR은 Python 3.10 이상 필요 — OCR 건너뜀"]


def test_ocr_dependency_markers_exclude_python_39():
    project = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"pytesseract>=0.3; python_version >= \'3.10\'"' in project
    assert '"Pillow>=12.3; python_version >= \'3.10\'"' in project
