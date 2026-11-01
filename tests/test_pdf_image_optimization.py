"""Evidence gates for preserving eager PDF image extraction semantics."""
import builtins

import pytest

from dochan.reader import Dochan
from dochan.pdf.images import extract_image_bytes
from dochan.pdf.objects import PDFStream
from test_pdf_structure import _build_pdf, _minimal_objects


def _image_pdf(tmp_path):
    objects = _minimal_objects(b"")
    objects[3] = ("<< /Type /Page /Parent 2 0 R /Resources "
                  "<< /XObject << /I 6 0 R >> >> /Contents 5 0 R >>")
    objects[6] = (b"<< /Subtype /Image /Width 1 /Height 1 /BitsPerComponent 8 "
                  b"/ColorSpace /DeviceRGB /Length 3 >>\nstream\n"
                  b"\xff\x00\x00\nendstream")
    path = tmp_path / "image.pdf"
    path.write_bytes(_build_pdf(objects))
    return path


def test_png_encode_failure_changes_all_output_and_scan_diagnostic(tmp_path, monkeypatch):
    pil = pytest.importorskip("PIL.Image")
    path = _image_pdf(tmp_path)
    good = Dochan(str(path))
    assert good.doc.find_all("image")
    assert good.to_dict()["assets"][0]["content_type"] == "image/png"

    def fail(*args, **kwargs):
        raise OSError("encoder unavailable")

    monkeypatch.setattr(pil.Image, "save", fail)
    bad = Dochan(str(path))
    assert bad.doc.find_all("image") == []
    assert bad.to_dict()["assets"] == []
    for method in ("to_markdown", "to_json", "to_plain_text", "to_dict"):
        assert getattr(good, method)() != getattr(bad, method)()
    assert any("이미지 기반" in warning for warning in good.doc.errors)
    assert any("이미지 추출 불가" in warning for warning in bad.doc.errors)
    assert good.doc.errors != bad.doc.errors


def test_no_pillow_skips_raw_decode_but_keeps_jpeg(monkeypatch):
    original_import = builtins.__import__

    def no_pillow(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError("Pillow unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pillow)
    called = []
    raw = PDFStream({"Width": 1, "Height": 1, "ColorSpace": "DeviceRGB"}, b"rgb")
    assert extract_image_bytes(raw, [], lambda stream: called.append(stream)) == (b"", "")
    assert called == []
    jpeg = PDFStream({"Filter": "DCTDecode"}, b"jpeg")
    assert extract_image_bytes(jpeg, []) == (b"jpeg", "jpg")
