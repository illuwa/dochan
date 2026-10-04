"""한컴의 반올림 배율과 인접 구분자 진행 상자 겹침을 재현한다."""
import pytest

from dochan.pdf.annotations import LinkRegion, attach_comments, attach_links
from dochan.pdf.content import Fragment
from scripts.probe_pdf_press_links import normalize
from test_pdf_link_review import URL, _document


def _body(document):
    return [run.text for paragraph in document.find_all("paragraph")
            for run in paragraph.runs if run.link == URL and run.provenance.path != "annots"]


@pytest.mark.parametrize("scale", ["1.00055", "0.99945"])
def test_hancom_rounded_scale_attaches_body_link(tmp_path, scale):
    content = ("BT /F1 10 Tf %s 0 0 1 72 720 Tm (AB) Tj ET" % scale).encode()
    document = _document(tmp_path, content, "71 716 83 734")
    assert _body(document) == ["AB"]


@pytest.mark.parametrize("cut", [0.02, 0.3])
def test_hancom_opening_parenthesis_shallow_intrusion_attaches(tmp_path, cut):
    start = 77 - cut
    content = ("BT /F1 10 Tf 1 0 0 1 72 720 Tm (\\() Tj "
               "1 0 0 1 %.4f 720 Tm (AB) Tj ET" % start).encode()
    document = _document(tmp_path, content, "%.4f 716 %.4f 734" % (start, start + 10))
    assert _body(document) == ["AB"]


@pytest.mark.parametrize("neighbor,cut,expected", [
    ("(", 0.02, True), ("(", 0.3, True), ("(", 0.6, False),
    ("X", 0.02, False), ("/", 0.02, False), ("-", 0.02, False),
])
def test_shallow_overlap_does_not_split_a_word(neighbor, cut, expected):
    fragments = [Fragment(0, 10, 5, 10, neighbor, 2.5, char_offsets=(0, 5)),
                 Fragment(5 - cut, 10, 10, 10, "AB", 2.5, order=1, char_offsets=(0, 5, 10))]
    region = LinkRegion(URL, [[(5 - cut, 9), (15 - cut, 9), (15 - cut, 22), (5 - cut, 22)]])
    attach_links(fragments, [region], [], allow_clipped_edges=True)
    assert region.matched == expected
    assert fragments[0].link_spans == []
    assert fragments[1].link_spans == ([(0, 2, URL)] if expected else [])


def test_closing_parenthesis_shallow_intrusion_attaches():
    fragment = Fragment(0, 10, 15, 10, "AB)", 2.5, char_offsets=(0, 5, 10, 15))
    region = LinkRegion(URL, [[(0, 9), (10.02, 9), (10.02, 22), (0, 22)]])
    attach_links([fragment], [region], [], allow_clipped_edges=True)
    assert fragment.link_spans == [(0, 2, URL)]


@pytest.mark.parametrize("cut,matched", [(0.02, True), (0.6, False)])
def test_selected_closing_parenthesis_shallow_cut_before_quote(cut, matched):
    fragment = Fragment(0, 10, 20, 10, "AB)\u2019", 2.5, char_offsets=(0, 5, 10, 15, 20))
    region = LinkRegion(URL, [[(0, 9), (15 - cut, 9), (15 - cut, 22), (0, 22)]])
    attach_links([fragment], [region], [], allow_clipped_edges=True)
    assert fragment.link_spans == ([(0, 3, URL)] if matched else [])


def test_shallow_overlap_keeps_comment_boundary_conservative():
    fragment = Fragment(0, 10, 15, 10, "(AB", 2.5, char_offsets=(0, 5, 10, 15))
    region = LinkRegion("1", [[(4.98, 9), (15, 9), (15, 22), (4.98, 22)]])
    attach_comments([fragment], [region], [])
    assert fragment.comment_spans == []


@pytest.mark.parametrize("matrix", ["1.005 0 0 1", "1 0 0.001 1", "1 0 0 -1"])
def test_material_scale_or_shear_keeps_fallback(tmp_path, matrix):
    document = _document(tmp_path, ("BT /F1 10 Tf %s 72 720 Tm (AB) Tj ET" % matrix).encode(),
                         "71 716 83 734")
    assert _body(document) == []


def test_deep_cut_keeps_synthetic_pdf_fallback(tmp_path):
    document = _document(tmp_path, b"BT /F1 10 Tf 72 720 Td (ABCD) Tj ET", "76 716 83 734")
    assert _body(document) == []
    assert any(run.link == URL for p in document.find_all("paragraph") for run in p.runs)


def test_press_probe_normalization_preserves_internal_punctuation():
    assert normalize(" （ a b ） ") == "ab"
    assert normalize("(a(b)c)") == "a(b)c"
    assert normalize("[ab]") != normalize("ab")
    assert normalize("a.b") != normalize("ab")


def test_press_probe_keeps_distinct_hwpx_occurrences(tmp_path):
    from scripts.probe_pdf_press_links import hwpx_links
    from test_hwpx_reader import (_HYPERLINK_END, _hyperlink_begin, _para,
                                  _run, _section, _write_hwpx)
    path = tmp_path / "paired.hwpx"
    body = "".join(_para(_run(_hyperlink_begin(URL) + "<hp:t>%s</hp:t>" % text +
                             _HYPERLINK_END)) for text in ["one", "two"])
    _write_hwpx(path, _section(body))
    links, errors = hwpx_links(path)
    assert links == {URL: ["one", "two"]}
    assert errors == []


def test_press_probe_measures_depth_independently():
    from scripts.probe_pdf_press_links import _diagnostics
    fragment = Fragment(0, 10, 5, 10, "(", 2.5, char_offsets=(0, 5))
    diagnostic = _diagnostics([fragment], [[(4.98, 9), (15, 9), (15, 22), (4.98, 22)]])
    assert diagnostic["native_center_text"] == ""
    assert diagnostic["cuts"][0]["depth_pt"] == pytest.approx(0.02)
    assert diagnostic["cuts"][0]["depth_ratio"] == pytest.approx(0.004)


def test_press_probe_checks_final_output_and_hwpx_pair(tmp_path):
    pytest.importorskip("pypdfium2")  # 독립 검증 도구이며 CI 필수 의존성이 아니다.
    from scripts.probe_pdf_press_links import summarize, verify
    from test_hwpx_reader import (_HYPERLINK_END, _hyperlink_begin, _para,
                                  _run, _section, _write_hwpx)
    _document(tmp_path, b"BT /F1 10 Tf 72 720 Td (AB) Tj ET", "71 716 83 734")
    _write_hwpx(tmp_path / "links.hwpx", _section(_para(_run(
        _hyperlink_begin(URL) + "<hp:t> ( A B ) </hp:t>" + _HYPERLINK_END))))
    result = verify(tmp_path / "links.pdf")
    row = result["records"][0]
    assert row["attached_text"] == "AB"
    assert row["native_center_status"] == "match"
    assert row["hwpx_status"] == "match"
    assert row["target_preserved"]
    summary = summarize({"links.pdf": result})
    assert summary["annotations"] == summary["resolved_annotations"] == summary["attached"] == 1
    assert summary["native_center_mismatch"] == summary["hwpx_mismatch"] == summary["target_loss"] == 0
