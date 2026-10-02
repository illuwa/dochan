"""Core 14 AFM metrics and PDF encoding contracts; fixtures are synthetic."""
import pytest

from dochan.pdf.objects import PDFName
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile
from dochan.pdf.content import ContentTextExtractor
from dochan.pdf.widths import WidthMap
from test_pdf_structure import _build_pdf, _minimal_objects


def font_info(base="Times-Roman", encoding=None, **extra):
    font = {"Subtype": PDFName("Type1"), "BaseFont": PDFName(base)}
    if encoding is not None:
        font["Encoding"] = encoding
    font.update(extra)
    pdf = PDFFile(_build_pdf(_minimal_objects()))
    return PDFReader()._build_font_info(pdf, "F", font)


@pytest.mark.parametrize("base,width", [("Times-Roman", 944), ("Helvetica", 944),
    ("Courier", 600), ("ArialMT", 944), ("TimesNewRomanPSMT", 944),
    ("TimesNewRomanPS-BoldMT", 1000), ("Arial-BoldItalicMT", 944)])
def test_core14_widths_without_widths_array(base, width):
    info = font_info(base)
    assert info.widths.advance(87) == width
    assert info.widths.explicit(87)
    assert info.link_metrics_reliable


@pytest.mark.parametrize("base,encoding,raw,text,width", [
    ("Times-Roman", None, b"\x27", "’", 333),
    ("Times-Roman", PDFName("StandardEncoding"), b"\xae", "ﬁ", 556),
    ("Helvetica", PDFName("WinAnsiEncoding"), b"\xe9", "é", 556),
    ("Helvetica", PDFName("MacRomanEncoding"), b"\x8e", "é", 556),
    ("Symbol", None, b"A", "Α", 722),
    ("ZapfDingbats", None, b"!", "✁", 974),
    ("Times-Roman", {"BaseEncoding": PDFName("WinAnsiEncoding"),
                     "Differences": [65, PDFName("W")]}, b"A", "W", 944),
])
def test_core14_encoding_maps_code_to_glyph(base, encoding, raw, text, width):
    info = font_info(base, encoding)
    assert info.decode(raw) == text
    assert info.widths.advance(raw[0]) == width
    assert info.widths.explicit(raw[0])
    assert info.link_metrics_reliable


def test_core14_explicit_widths_override_afm():
    info = font_info("Helvetica", FirstChar=65, Widths=[123])
    assert info.widths.advance(65) == 123
    assert not info.widths.explicit(66)


def test_custom_and_embedded_fonts_do_not_borrow_core14_metrics():
    assert not font_info("CustomFont").widths.explicit(65)
    assert not font_info("ABCDEF+Helvetica").widths.explicit(65)
    assert not font_info("Helvetica", FontDescriptor={"FontFile": b"embedded"}).widths.explicit(65)


def test_unknown_difference_defers_link_geometry():
    info = font_info("Helvetica", {"Differences": [65, PDFName("unknownGlyph")]})
    frags = ContentTextExtractor.from_fonts({"F": info}, track_char_positions=True).extract_fragments(
        b"BT /F 12 Tf 10 20 Td (A) Tj ET")
    assert not frags[0].link_geometry_reliable


def test_cid_dw_is_authoritative_even_without_w_entries():
    info = font_info("CID", PDFName("Identity-H"), Subtype=PDFName("Type0"),
                     DescendantFonts=[{"DW": 880}])
    assert info.widths.advance(42) == 880
    assert info.widths.explicit(42)
    assert WidthMap.cid([]).explicit(65535)
    assert not WidthMap.cid([]).explicit(65536)


def test_cid_widths_bound_nonfinite_and_out_of_range():
    widths = WidthMap.cid([-10, 3, 123, 65535, [800, 900], 5, [float("nan")]])
    assert widths.advance(65535) == 800
    assert not widths.explicit(-1)
    assert not widths.explicit(65536)
    assert widths.advance(5) == 1000


def test_duplicate_annotations_do_not_exhaust_link_geometry_budget():
    from dochan.pdf.annotations import LinkRegion, attach_links
    from dochan.pdf.content import Fragment
    fragment = Fragment(0, 10, 3000, 10, "A" * 3000, 1,
                        char_offsets=tuple(range(3001)))
    regions = [LinkRegion("https://example.com/", [[(0, 9), (1, 9), (1, 22), (0, 22)]])
               for _ in range(256)]
    warnings = []
    attach_links([fragment], regions, warnings)
    assert fragment.link_spans == [(0, 1, "https://example.com/")]
    assert all(region.matched for region in regions)
    assert not warnings


def test_cid_repeated_large_ranges_are_bounded_and_warn():
    widths = WidthMap.cid([0, 65535, 400, 0, 65535, 500])
    assert widths.warnings
    assert widths.advance(42) == 400


def test_sparse_annotations_skip_geometrically_disjoint_fragments():
    from dochan.pdf.annotations import LinkRegion, attach_links
    from dochan.pdf.content import Fragment
    fragments = [Fragment(0, 10 + 20 * i, 1, 10, "A", 1, char_offsets=(0, 1))
                 for i in range(6000)]
    regions = [LinkRegion("https://example.com/", [[(i * 2, 9), (i * 2 + 1, 9),
                                                    (i * 2 + 1, 22), (i * 2, 22)]])
               for i in range(128)]
    warnings = []
    attach_links(fragments, regions, warnings)
    assert fragments[0].link_spans == [(0, 1, "https://example.com/")]
    assert not any(f.link_spans for f in fragments[1:])
    assert not warnings


def test_core14_afm_widths_attach_body_text_without_widths_array(tmp_path):
    objects = _minimal_objects(b"BT /F1 12 Tf 72 720 Td (WW) Tj 40 0 Td (Other) Tj ET")
    objects[4] = "<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>"
    objects[3] = objects[3][:-2] + " /Annots [6 0 R] >>"
    objects[6] = ("<< /Subtype /Link /Rect [72 716 94.656 733] "
                  "/A << /S /URI /URI (https://example.com/) >> >>")
    path = tmp_path / "core14-link.pdf"
    path.write_bytes(_build_pdf(objects))
    doc = PDFReader().read(str(path))
    linked = [run for p in doc.find_all("paragraph") for run in p.runs if run.link]
    assert len(linked) == 1
    assert linked[0].text == "WW"
    assert linked[0].provenance.path != "annots"


def test_oversized_differences_warns_and_does_not_trust_partial_encoding():
    pdf = PDFFile(_build_pdf(_minimal_objects()))
    info = PDFReader()._build_font_info(pdf, "F", {
        "Subtype": PDFName("Type1"), "BaseFont": PDFName("Helvetica"),
        "Encoding": {"Differences": [65, PDFName("A")] * 2049}})
    assert pdf.warnings
    assert not info.widths.explicit(65)


def test_invalid_cid_default_cannot_authorize_link_geometry():
    widths = WidthMap.cid([1, [800]], default_width=float("inf"))
    assert widths.advance(2) == 1000
    assert widths.warnings
    assert not widths.explicit(1)


def test_pdf_macroman_currency_and_undefined_codes_differ_from_python_codec():
    info = font_info("Helvetica", PDFName("MacRomanEncoding"))
    assert info.decode(b"\xdb") == "¤"
    for code in (173, 176, 178, 179, 182, 183, 184, 185, 186, 195, 197, 198, 215, 240):
        assert not info.widths.explicit(code)
        assert info.decode(bytes([code])) == "\ufffd"
