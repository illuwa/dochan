from pathlib import Path

import pytest

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


def _png_bytes(color):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (300, 80), color).save(buf, format="PNG")
    return buf.getvalue()


def test_ocr_image_reuses_result_for_identical_bytes(monkeypatch):
    pytesseract = pytest.importorskip("pytesseract")
    calls = []

    def fake_image_to_string(img, lang, config):
        calls.append(lang)
        return "회사 로고\nlogo text"

    monkeypatch.setattr(ocr, "is_ocr_available", lambda: True)
    monkeypatch.setattr(pytesseract, "image_to_string", fake_image_to_string)
    ocr.clear_ocr_cache()

    same = _png_bytes("white")
    first = ocr.ocr_image(same)
    second = ocr.ocr_image(bytes(same))
    other = ocr.ocr_image(_png_bytes("black"))

    assert first == second == other == "회사 로고\nlogo text"
    assert len(calls) == 2  # 동일 바이트는 1회만 실행, 다른 이미지는 별도 실행


def test_ocr_image_cache_is_keyed_by_language(monkeypatch):
    pytesseract = pytest.importorskip("pytesseract")
    calls = []
    monkeypatch.setattr(ocr, "is_ocr_available", lambda: True)
    monkeypatch.setattr(pytesseract, "image_to_string",
                        lambda img, lang, config: calls.append(lang) or "text ok")
    ocr.clear_ocr_cache()

    data = _png_bytes("white")
    ocr.ocr_image(data, lang="kor")
    ocr.ocr_image(data, lang="eng")

    assert calls == ["kor", "eng"]
