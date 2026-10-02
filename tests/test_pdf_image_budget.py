"""Image decoding shares predictor work, never the body byte budget (no Pillow)."""
import zlib

from dochan.pdf import filters, reader, structure
from dochan.pdf.objects import PDFStream
from test_pdf_structure import _build_pdf, _minimal_objects


def _image(data, parms=None):
    dictionary = {"Subtype": "Image", "Filter": "FlateDecode"}
    if parms is not None:
        dictionary["DecodeParms"] = parms
    return PDFStream(dictionary, zlib.compress(data))


def test_image_callback_preserves_body_budget_and_cache_without_pillow(monkeypatch):
    monkeypatch.setattr(structure, "MAX_TOTAL_DECODED", 8)
    pdf = structure.PDFFile(_build_pdf(_minimal_objects()))
    decoded = []

    def extract(stream, warnings, decode):
        decoded.append(decode(stream))
        return b"", ""

    monkeypatch.setattr(reader, "extract_image_bytes", extract)
    image = _image(b"pixels" * 10)
    reader.PDFReader()._page_images(pdf, {"XObject": {"I": image}}, 1)
    assert decoded == [b"pixels" * 10]
    assert pdf._decode_budget == 8
    assert id(image) not in pdf._decoded_cache
    assert pdf.decode_stream_bytes(PDFStream({}, b"Body end")) == b"Body end"
    assert not any("총량" in warning for warning in pdf.warnings)


def test_image_callback_shares_packed_predictor_work_without_pillow(monkeypatch):
    monkeypatch.setattr(filters, "MAX_PACKED_PREDICTOR_SAMPLES", 4)
    pdf = structure.PDFFile(_build_pdf(_minimal_objects()))
    parms = {"Predictor": 2, "Columns": 4, "BitsPerComponent": 1}
    decoded = []

    def extract(stream, warnings, decode):
        decoded.append(decode(stream))
        return b"", ""

    monkeypatch.setattr(reader, "extract_image_bytes", extract)
    image = _image(b"\x80", parms)
    budget = pdf._decode_budget
    reader.PDFReader()._page_images(pdf, {"XObject": {"I": image}}, 1)
    assert decoded == [b"\xf0"]
    assert pdf._decode_budget == budget
    assert pdf.decode_stream_bytes(_image(b"\x80", parms)) == b""
    assert any("연산 한도" in warning for warning in pdf.warnings)


def test_image_callback_cache_is_bounded_separately_from_body(monkeypatch):
    monkeypatch.setattr(structure, "MAX_IMAGE_DECODED_CACHE", 8, raising=False)
    pdf = structure.PDFFile(_build_pdf(_minimal_objects()))
    first, second = _image(b"123456"), _image(b"abcdef")
    assert pdf.decode_image_bytes(first) == b"123456"
    assert pdf.decode_image_bytes(second) == b"abcdef"
    assert sum(len(value[1]) for value in pdf._image_decoded_cache.values()) <= 8
    assert not pdf._decoded_cache
    assert pdf.decode_image_bytes(_image(b"x" * 9)) == b"x" * 9
    assert sum(len(value[1]) for value in pdf._image_decoded_cache.values()) <= 8


def test_image_callback_keeps_per_stream_decode_limit(monkeypatch):
    monkeypatch.setattr(filters, "MAX_DECODED_SIZE", 8)
    pdf = structure.PDFFile(_build_pdf(_minimal_objects()))
    assert pdf.decode_image_bytes(_image(b"x" * 20)) == b"x" * 8
    assert any("한도" in warning for warning in pdf.warnings)


def test_image_cache_bounds_entry_count_and_keeps_recent_image(monkeypatch):
    monkeypatch.setattr(structure, "MAX_IMAGE_CACHE_ENTRIES", 2)
    pdf = structure.PDFFile(_build_pdf(_minimal_objects()))
    first, second, third = _image(b"a"), _image(b"b"), _image(b"c")
    pdf._decode_budget = 0
    assert pdf.decode_image_bytes(first) == b"a"
    assert pdf.decode_image_bytes(second) == b"b"
    assert pdf.decode_image_bytes(first) == b"a"
    assert pdf.decode_image_bytes(third) == b"c"
    assert set(pdf._image_decoded_cache) == {id(first), id(third)}
    assert pdf._image_cached_bytes == 2
    assert pdf._decode_budget == 0
