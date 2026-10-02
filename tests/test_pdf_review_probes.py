import zlib

import pytest

from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile
from scripts import probe_pdf_annotations, probe_pdf_vertical
from test_pdf_structure import _build_pdf, _minimal_objects


def _stream(data, compressed=False):
    data = zlib.compress(data) if compressed else data
    return (b"<< /Length %d" % len(data) +
            (b" /Filter /FlateDecode" if compressed else b"") +
            b" >>\nstream\n" + data + b"\nendstream")


@pytest.mark.parametrize("compressed", [False, True])
def test_rc_stream_comment_and_independent_probe(tmp_path, compressed):
    objects = _minimal_objects()
    objects[3] = objects[3][:-2] + " /Annots [6 0 R] >>"
    objects[6] = "<< /Subtype /FreeText /RC 7 0 R /T (Author) >>"
    objects[7] = _stream(b"<body><p>Review &amp; revise</p></body>", compressed)
    path = tmp_path / "rc-stream.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader().read(str(path))
    assert [(c.text, c.author) for c in doc.find_all("comment")] == [("Review & revise", "Author")]
    result = probe_pdf_annotations.probe(tmp_path)
    assert result["comment_expected"] == result["comment_actual"] == 1
    assert result["comment_mismatches"] == result["failures"] == []
    assert result["rich_text_fallbacks"] == 1


@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("payload,warning", [
    (b"<body>" + b"a" * 65536 + b"</body>", "한도"),
    (b"<!DOCTYPE body [<!ENTITY x 'bad'>]><body>&x;</body>", "DTD"),
])
def test_rc_stream_rejects_oversized_and_entity_payloads(tmp_path, payload, warning, compressed):
    objects = _minimal_objects()
    objects[3] = objects[3][:-2] + " /Annots [6 0 R] >>"
    objects[6] = "<< /Subtype /FreeText /RC 7 0 R >>"
    objects[7] = _stream(payload, compressed)
    path = tmp_path / "unsafe-rc.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader().read(str(path))
    assert not doc.find_all("comment")
    assert any("RC" in error and warning in error for error in doc.errors)


def _inherited_font_pdf(vertical):
    objects = _minimal_objects(b"BT /F1 12 Tf 72 720 Td <0001> Tj ET")
    objects[2] = "<< /Type /Pages /Kids [3 0 R] /Count 1 /Resources << /Font << /F1 4 0 R >> >> >>"
    objects[3] = "<< /Type /Page /Parent 2 0 R /Contents 5 0 R /Annots [8 0 R] >>"
    objects[4] = ("<< /Type /Font /Subtype /Type0 /Encoding /Identity-%s "
                  "/DescendantFonts [6 0 R] /ToUnicode 7 0 R >>") % ("V" if vertical else "H")
    objects[6] = "<< /Type /Font /Subtype /CIDFontType2 /DW 1000 /W [1 [1000]] >>"
    objects[7] = _stream(b"1 beginbfchar <0001> <0041> endbfchar")
    objects[8] = "<< /Subtype /Link /Rect [72 720 84 734] /A << /S /URI /URI (https://example.org) >> >>"
    return _build_pdf(objects)


def test_vertical_probe_uses_effective_inherited_resources(tmp_path):
    data = _inherited_font_pdf(True)
    (tmp_path / "inherited-vertical.pdf").write_bytes(data)
    pages = probe_pdf_vertical._extract(PDFFile(data))
    assert pages[0]["fragments"][0]["text"] == "A"
    assert pages[0]["fragments"][0]["direction"] == "down"
    result = probe_pdf_vertical.probe(tmp_path)
    assert result["negative_documents"] == 0
    assert len(result["vertical_documents"]) == 1


def test_annotation_probe_uses_effective_inherited_resources(tmp_path):
    (tmp_path / "inherited-horizontal.pdf").write_bytes(_inherited_font_pdf(False))
    result = probe_pdf_annotations.probe(tmp_path)
    assert result["failures"] == []
    sample = result["geometry"]["first_examples"][0]
    assert sample["matches"][0]["text"] == "A"
    assert sample["matches"][0]["width"] == 12


def test_vertical_probe_timeout_survives_parser_exception_downgrade(tmp_path, monkeypatch):
    (tmp_path / "timeout.pdf").write_bytes(_build_pdf(_minimal_objects()))
    previous_handler = object()
    state = {"handler": previous_handler, "alarms": [], "swallowed": False}

    def set_handler(signum, handler):
        assert signum == probe_pdf_vertical.signal.SIGALRM
        previous = state["handler"]
        state["handler"] = handler
        return previous

    class ParserWithExceptionDowngrade:
        def __init__(self, data):
            try:
                state["handler"](probe_pdf_vertical.signal.SIGALRM, None)
            except Exception:
                state["swallowed"] = True

        def pages(self):
            return []

    monkeypatch.setattr(probe_pdf_vertical.signal, "signal", set_handler)
    monkeypatch.setattr(probe_pdf_vertical.signal, "alarm", state["alarms"].append)
    monkeypatch.setattr(probe_pdf_vertical, "PDFFile", ParserWithExceptionDowngrade)
    result = probe_pdf_vertical.probe(tmp_path)
    assert result["failures"] == [{"file": "timeout.pdf", "error": "ProbeDeadline"}]
    assert result["uninspectable_documents"] == result["negative_documents"] == 0
    assert result["vertical_documents"] == []
    assert not state["swallowed"]
    assert state["alarms"] == [5, 0]
    assert state["handler"] is previous_handler
