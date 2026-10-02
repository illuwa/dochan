"""Packed TIFF predictor work is bounded across a complete PDF document."""
import zlib

import pytest

from dochan.pdf.objects import PDFStream
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile
from test_pdf_structure import _build_pdf, _minimal_objects


def _packed_stream(bits, rows=1):
    # Four pixels: encoded [1, 0, 0, 0], reconstructed [1, 1, 1, 1].
    width = (4 * bits + 7) // 8
    raw = (1 << (width * 8 - bits)).to_bytes(width, "big") * rows
    return PDFStream({"Filter": "FlateDecode", "DecodeParms": {
        "Predictor": 2, "Columns": 4, "BitsPerComponent": bits}}, zlib.compress(raw))


@pytest.mark.parametrize("bits", [1, 2, 4])
def test_packed_tiff_document_budget_shared_between_streams(bits, monkeypatch):
    import dochan.pdf.filters as filters
    monkeypatch.setattr(filters, "MAX_PACKED_PREDICTOR_SAMPLES", 9)
    pdf = PDFFile(_build_pdf(_minimal_objects()))
    first = pdf.decode_stream_bytes(_packed_stream(bits))
    second = pdf.decode_stream_bytes(_packed_stream(bits, rows=2))
    assert first
    assert second == first  # Only one complete row fits the remaining budget.
    assert pdf.decode_stream_bytes(_packed_stream(bits)) == b""
    assert any("연산 한도" in warning for warning in pdf.warnings)


def test_packed_tiff_cached_result_does_not_spend_budget_again(monkeypatch):
    import dochan.pdf.filters as filters
    monkeypatch.setattr(filters, "MAX_PACKED_PREDICTOR_SAMPLES", 8)
    pdf = PDFFile(_build_pdf(_minimal_objects()))
    stream = _packed_stream(1)
    assert pdf.decode_stream_bytes(stream) == b"\xf0"
    assert pdf.decode_stream_bytes(stream) == b"\xf0"
    assert pdf.decode_stream_bytes(_packed_stream(1)) == b"\xf0"
    assert pdf.decode_stream_bytes(_packed_stream(1)) == b""
    assert pdf.decode_stream_bytes(stream) == b"\xf0"


def test_packed_tiff_budget_is_not_shared_between_documents(monkeypatch):
    import dochan.pdf.filters as filters
    monkeypatch.setattr(filters, "MAX_PACKED_PREDICTOR_SAMPLES", 4)
    data = _build_pdf(_minimal_objects())
    first, second = PDFFile(data), PDFFile(data)
    assert first.decode_stream_bytes(_packed_stream(1)) == b"\xf0"
    assert first.decode_stream_bytes(_packed_stream(1)) == b""
    assert second.decode_stream_bytes(_packed_stream(1)) == b"\xf0"


def test_packed_tiff_document_budget_warning_reaches_reader(tmp_path, monkeypatch):
    import dochan.pdf.filters as filters
    monkeypatch.setattr(filters, "MAX_PACKED_PREDICTOR_SAMPLES", 4)
    objects = _minimal_objects()
    objects[3] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                  "/Contents [5 0 R 6 0 R] >>")
    raw = zlib.compress(b"\x00")
    for number in (5, 6):
        objects[number] = (b"<< /Length %d /Filter /FlateDecode /DecodeParms "
                           b"<< /Predictor 2 /Columns 4 /BitsPerComponent 1 >> >>\n"
                           b"stream\n%s\nendstream") % (len(raw), raw)
    path = tmp_path / "packed-tiff.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader().read(str(path))
    assert any("연산 한도" in warning for warning in doc.errors)
    assert doc.sections


def test_packed_tiff_images_share_content_stream_budget(monkeypatch):
    pytest.importorskip("PIL")
    import dochan.pdf.filters as filters
    monkeypatch.setattr(filters, "MAX_PACKED_PREDICTOR_SAMPLES", 8)
    pdf = PDFFile(_build_pdf(_minimal_objects()))
    assert pdf.decode_stream_bytes(_packed_stream(1)) == b"\xf0"
    image = _packed_stream(1)
    image.dictionary.update({"Subtype": "Image", "Width": 1, "Height": 1,
                             "BitsPerComponent": 8, "ColorSpace": "DeviceGray"})
    other_image = PDFStream(dict(image.dictionary), image.raw)
    reader = PDFReader()
    assert len(reader._page_images(pdf, {"XObject": {"I1": image}}, 1)) == 1
    assert reader._page_images(pdf, {"XObject": {"I2": other_image}}, 2) == []
    # A repeated image uses cached decoded bytes even after exhaustion.
    assert len(reader._page_images(pdf, {"XObject": {"I1": image}}, 3)) == 1
