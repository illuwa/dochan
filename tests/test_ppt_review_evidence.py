"""PPT 검증 지표가 런 경계와 직접 XML 서식을 보존하는지 확인한다."""

from lxml import etree

from scripts.pptx_style_reference import A, lvl_props, rpr_props
from scripts.probe_ppt_review_evidence import changes


def test_review_evidence_counts_characters_not_runs():
    def row(runs):
        return {"public.ppt": {"paras": [["#slide1", runs]], "md": "unchanged"}}

    before = row([["abc", False, False, False, 10, False, False]])
    after = row(
        [
            ["a", True, False, False, 10, False, False],
            ["bc", True, False, False, 10, False, False],
        ]
    )
    actual = changes(before, after)
    assert actual["changed_characters"] == {"bold": 3}
    assert actual["changed_files"] == {"bold": 1, "any": 1}
    assert actual["text_mismatch"] == []


def test_reference_xml_preserves_explicit_false_and_point_units():
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    element = etree.fromstring(
        (
            '<a:rPr xmlns:a="%s" b="0" i="true" u="none" '
            'sz="2250" baseline="-25000"/>' % A[1:-1]
        ).encode(),
        parser,
    )
    assert rpr_props(element) == {
        "b": False,
        "i": True,
        "u": False,
        "sz": 22.5,
        "base": -25000,
    }


def test_reference_xml_keeps_paragraph_levels_separate():
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    element = etree.fromstring(
        (
            '<a:lstStyle xmlns:a="%s"><a:lvl1pPr><a:defRPr b="1"/></a:lvl1pPr>'
            '<a:lvl2pPr><a:defRPr b="0" sz="1800"/></a:lvl2pPr></a:lstStyle>' % A[1:-1]
        ).encode(),
        parser,
    )
    assert lvl_props(element, 0) == {"b": True}
    assert lvl_props(element, 1) == {"b": False, "sz": 18.0}
    assert lvl_props(element, 2) == {}
