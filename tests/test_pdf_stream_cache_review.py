"""임시 xref 스트림의 수명과 해제 캐시 식별자 충돌 회귀를 검증한다."""
import gc
import weakref
import zlib

from dochan.pdf import structure
from dochan.pdf.objects import PDFStream


def test_stream_cache_identity_collision_does_not_reuse_other_stream(monkeypatch):
    pdf = structure.PDFFile(b"%PDF-1.7\n%%EOF")
    pdf._decode_budget = 100
    # A released temporary stream's id can be reused by a different stream.
    # Force this case independently of CPython allocator timing.
    monkeypatch.setattr(structure, "id", lambda obj: 42, raising=False)
    first = PDFStream({"Filter": "FlateDecode"}, zlib.compress(b"xref"))
    second = PDFStream({"Filter": "FlateDecode"}, zlib.compress(b"page content"))
    assert pdf.decode_stream_bytes(first) == b"xref"
    assert pdf.decode_stream_bytes(second) == b"page content"
    assert pdf._decode_budget == 84
    assert pdf.decode_stream_bytes(second) == b"page content"
    assert pdf._decode_budget == 84


def test_temporary_xref_stream_remains_alive_while_decoded_result_is_cached(monkeypatch):
    pdf = structure.PDFFile(b"%PDF-1.7\n%%EOF")
    pdf.data = (b"1 0 obj\n<< /Type /XRef /Size 1 /W [1 1 1] /Length 3 >>\n"
                b"stream\n\x01\x00\x00\nendstream\nendobj")
    original = structure.parse_indirect_object
    refs = []

    def record_stream(*args, **kwargs):
        result = original(*args, **kwargs)
        refs.append(weakref.ref(result[2]))
        return result

    monkeypatch.setattr(structure, "parse_indirect_object", record_stream)
    assert pdf._parse_xref_stream_at(0)["Type"] == "XRef"
    gc.collect()
    assert refs[0]() is not None
    stream = refs[0]()
    budget = pdf._decode_budget
    assert pdf.decode_stream_bytes(stream) == b"\x01\x00\x00"
    assert pdf._decode_budget == budget
