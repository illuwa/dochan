"""Text revision projections; gold comes from revision-spec.md, not the parser."""

import hashlib
import inspect
import json
from pathlib import Path
import re
import zipfile

import pytest
from lxml import etree

from dochan import Dochan, HWPReader
from dochan.hwpx.parser import HWPXParser
from dochan.hwpx.revisions import RevisionProjector


ROOT = Path(__file__).resolve().parents[1]
NS = (
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
    'xmlns:foreign="urn:foreign"'
)
CHANGES = '<hh:trackChange id="1" type="Insert"/><hh:trackChange id="2" type="Delete"/>'


def package(tmp_path, body, changes=CHANGES, sections=None):
    path = tmp_path / "revisions.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/header.xml", (
            f'<hh:head {NS}><hh:refList><hh:trackChanges>{changes}'
            '</hh:trackChanges></hh:refList></hh:head>'
        ))
        for i, content in enumerate(sections or [body]):
            archive.writestr(f"Contents/section{i}.xml", f'<hs:sec {NS}>{content}</hs:sec>')
    return path


def paragraph(text):
    return f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>'


def marker(kind, end=False, identity=None, tc=None, paraend="0"):
    identity = identity or ("range-I" if kind == "insert" else "range-D")
    tc = tc or ("1" if kind == "insert" else "2")
    attr = f' paraend="{paraend}"' if end else ""
    return f'<hp:{kind}{"End" if end else "Begin"} Id="{identity}" TcId="{tc}"{attr}/>'


def texts(document):
    return [p.text for p in document.find_all("paragraph")]


@pytest.fixture(params=["reader", "parser"])
def read_document(request):
    if request.param == "reader":
        return lambda path, **kwargs: Dochan(path, **kwargs).doc
    return HWPXParser().parse


@pytest.mark.parametrize("mode, expected", [
    ("preserve", "변경 추적 \t인간은"),
    ("final", "변경 \t인간은"),
    ("original", "변경 추적 \t"),
])
def test_marker_tails_tabs_and_independent_range_ids(tmp_path, read_document, mode, expected):
    path = package(tmp_path, paragraph(
        "변경" + marker("delete") + " 추적" + marker("delete", True)
        + ' <hp:tab/>' + marker("insert") + "인간은" + marker("insert", True)
    ))
    document = read_document(path, revision_mode=mode)
    assert document.errors == []
    assert texts(document) == [expected]
    if mode == "preserve":
        assert read_document(path) == document


@pytest.mark.parametrize("mode", ["preserve", "final", "original"])
def test_unchanged_document_is_identical(tmp_path, read_document, mode):
    path = package(tmp_path, paragraph('A<hp:tab/>B<hp:lineBreak/>C<hp:nbSpace/>D'), changes="")
    assert read_document(path, revision_mode=mode) == read_document(path)


@pytest.mark.parametrize("kind, mode", [("delete", "final"), ("insert", "original")])
def test_ranges_cross_runs_and_paragraphs_without_leaking(tmp_path, kind, mode):
    body = (
        '<hp:p><hp:run><hp:t>before' + marker(kind) + 'gone-1</hp:t></hp:run>'
        '<hp:run><hp:t>gone-2</hp:t><hp:tab/><hp:lineBreak/>'
        '<hp:compose composeText="gone-compose"/></hp:run></hp:p>'
        '<hp:p><hp:run><hp:t>gone-3' + marker(kind, True) + 'after</hp:t></hp:run></hp:p>'
        + paragraph("untouched")
    )
    document = Dochan(package(tmp_path, body), revision_mode=mode).doc
    assert document.errors == []
    assert texts(document) == ["before", "after", "untouched"]


@pytest.mark.parametrize("scope", ["run", "paragraph", "section"])
def test_marker_siblings_at_parser_boundaries(tmp_path, scope):
    begin, end = marker("delete"), marker("delete", True)
    if scope == "run":
        body = f'<hp:p><hp:run>{begin}<hp:t>gone</hp:t>{end}<hp:t>kept</hp:t></hp:run></hp:p>'
    elif scope == "paragraph":
        body = f'<hp:p>{begin}<hp:run><hp:t>gone</hp:t></hp:run>{end}<hp:run><hp:t>kept</hp:t></hp:run></hp:p>'
    else:
        body = begin + paragraph("gone") + end + paragraph("kept")
    document = Dochan(package(tmp_path, body), revision_mode="final").doc
    assert document.errors == []
    assert texts(document) == ["kept"]


@pytest.mark.parametrize("body, code", [
    (marker("delete") + "kept", "missing-end"),
    ("kept" + marker("delete", True), "missing-begin"),
    (marker("delete") + "kept" + marker("delete", True, tc="1"), "reference-mismatch"),
    ('<hp:deleteBegin TcId="2"/>kept' + marker("delete", True), "missing-id"),
    (marker("delete", tc="99") + "kept" + marker("delete", True, tc="99"), "header-reference"),
    (marker("delete", tc="1") + "kept" + marker("delete", True, tc="1"), "header-reference"),
    (marker("delete") + "kept" + marker("delete", True, paraend="1"), "paraend"),
    (marker("delete") + "kept" + marker("delete", True, paraend="bad"), "paraend"),
    (marker("delete") + "kept" + '<hp:deleteEnd Id="range-D" TcId="2"/>', "paraend"),
    (marker("delete") + "ke" + marker("insert") + "p" + marker("delete", True)
     + "t" + marker("insert", True), "overlap"),
    (marker("delete") + "ke" + marker("insert") + "p" + marker("insert", True)
     + "t" + marker("delete", True), "overlap"),
    ('<foreign:deleteBegin Id="range-D" TcId="2"/>kept'
     '<foreign:deleteEnd Id="range-D" TcId="2" paraend="0"/>', "namespace"),
])
@pytest.mark.parametrize("mode", ["preserve", "final", "original"])
def test_unresolved_ranges_are_preserved_and_diagnosed(tmp_path, body, code, mode):
    document = Dochan(package(tmp_path, paragraph(body)), revision_mode=mode).doc
    assert texts(document) == ["kept"]
    assert any("revision" in e and code in e for e in document.errors), document.errors


def test_section_end_resets_unclosed_range(tmp_path):
    path = package(tmp_path, "", sections=[
        paragraph(marker("delete") + "first"),
        paragraph("second" + marker("delete", True)),
    ])
    document = Dochan(path, revision_mode="final").doc
    assert texts(document) == ["first", "second"]
    assert any("missing-end" in e and "section0.xml" in e for e in document.errors)
    assert any("missing-begin" in e and "section1.xml" in e for e in document.errors)


def test_nested_table_story_does_not_close_outer_range(tmp_path):
    cell = '<hp:tbl><hp:tr><hp:tc><hp:subList>' + paragraph(
        'cell' + marker("delete", True)
    ) + '</hp:subList></hp:tc></hp:tr></hp:tbl>'
    body = '<hp:p><hp:run><hp:t>' + marker("delete") + 'outer</hp:t>' + cell + '</hp:run></hp:p>'
    document = Dochan(package(tmp_path, body), revision_mode="final").doc
    assert texts(document) == ["outer", "cell"]
    assert any("missing-end" in e for e in document.errors)
    assert any("missing-begin" in e for e in document.errors)


@pytest.mark.parametrize("kind, mode", [("delete", "final"), ("insert", "original")])
def test_sublist_marker_cannot_delete_following_body(tmp_path, read_document, kind, mode):
    cell = ('<hp:tbl><hp:tr><hp:tc><hp:subList>'
            + marker(kind, identity="d") + paragraph("CELL")
            + '</hp:subList></hp:tc></hp:tr></hp:tbl>')
    body = ('<hp:p><hp:run>' + cell + '</hp:run></hp:p>'
            + paragraph("BODY" + marker(kind, True, identity="d") + "KEEP"))
    document = read_document(package(tmp_path, body), revision_mode=mode)
    assert texts(document) == ["CELL", "BODYKEEP"]
    assert any("marker-position" in e for e in document.errors)
    assert any("missing-begin" in e for e in document.errors)


@pytest.mark.parametrize("container", [
    "subList", "tc", "footNote", "endNote", "header", "footer", "caption",
    "drawText", "memo", "unknownContainer",
])
@pytest.mark.parametrize("mode, kind", [("preserve", "delete"), ("final", "delete"),
                                       ("original", "insert")])
@pytest.mark.parametrize("end_inside", [False, True])
def test_misplaced_markers_preserve_xml_and_diagnose(container, mode, kind, end_inside):
    begin, end = marker(kind), marker(kind, True)
    body = (f'<hp:p><hp:run><hp:{container}>' + begin + paragraph("INNER")
            + (end if end_inside else "") + f'</hp:{container}></hp:run></hp:p>'
            + paragraph("BODY" + ("" if end_inside else end) + "KEEP"))
    root = etree.fromstring(f'<hs:sec {NS}>{body}</hs:sec>')
    before = etree.tostring(root)
    errors = []
    projector = RevisionProjector(errors, mode)
    projector.read_header(etree.fromstring(f'<hh:head {NS}>{CHANGES}</hh:head>'))
    projector.project_section(root)
    assert etree.tostring(root) == before
    assert any("marker-position" in e for e in errors), errors
    prefix = "WARN:" if mode == "preserve" else "ERR:"
    assert all(e.startswith(prefix) for e in errors), errors


@pytest.mark.parametrize("kind, mode", [("delete", "final"), ("insert", "original")])
@pytest.mark.parametrize("container", ["subList", "tc", "footNote", "caption"])
def test_sibling_flows_cannot_pair_markers(container, kind, mode):
    body = (f'<hp:{container}>' + paragraph(marker(kind) + "FIRST")
            + f'</hp:{container}><hp:{container}>'
            + paragraph("SECOND" + marker(kind, True)) + f'</hp:{container}>')
    root = etree.fromstring(f'<hs:sec {NS}>{body}</hs:sec>')
    before = etree.tostring(root)
    errors = []
    projector = RevisionProjector(errors, mode)
    projector.read_header(etree.fromstring(f'<hh:head {NS}>{CHANGES}</hh:head>'))
    projector.project_section(root)
    assert etree.tostring(root) == before
    assert any("missing-end" in e for e in errors)
    assert any("missing-begin" in e for e in errors)


@pytest.mark.parametrize("kind, mode", [("delete", "final"), ("insert", "original")])
def test_valid_ranges_in_cell_and_note_stay_independent(tmp_path, kind, mode):
    inner = (paragraph(marker(kind) + "gone-1")
             + paragraph("gone-2" + marker(kind, True) + "INNER"))
    cell = '<hp:tbl><hp:tr><hp:tc><hp:subList>' + inner + '</hp:subList></hp:tc></hp:tr></hp:tbl>'
    note = '<hp:ctrl><hp:footNote><hp:subList>' + inner + '</hp:subList></hp:footNote></hp:ctrl>'
    body = ('<hp:p><hp:run>' + cell + note + '</hp:run></hp:p>'
            + paragraph(marker(kind) + "gone-body" + marker(kind, True) + "BODY"))
    document = Dochan(package(tmp_path, body), revision_mode=mode).doc
    assert document.errors == []
    assert document.find_all("table")[0].rows[0][0].text == "INNER"
    assert document.find_all("note")[0].text == "INNER"
    assert texts(document)[-1] == "BODY"


@pytest.mark.parametrize("kind, mode", [("delete", "final"), ("insert", "original")])
def test_switch_branches_keep_unestablished_revision_semantics(kind, mode):
    branch = paragraph(marker(kind) + "KEEP" + marker(kind, True))
    root = etree.fromstring(
        f'<hs:sec {NS}><hp:switch><hp:case>{branch}</hp:case>'
        f'<hp:default>{branch}</hp:default></hp:switch></hs:sec>'
    )
    before = etree.tostring(root)
    errors = []
    projector = RevisionProjector(errors, mode)
    projector.read_header(etree.fromstring(f'<hh:head {NS}>{CHANGES}</hh:head>'))
    projector.project_section(root)
    assert etree.tostring(root) == before
    assert any("switch" in e for e in errors)


@pytest.mark.parametrize("mode", ["preserve", "final", "original"])
def test_formatting_revision_is_explicitly_partial(tmp_path, mode):
    changes = CHANGES + '<hh:trackChange id="3" type="ParaShape" parashapeID="13"/>'
    body = '<hp:p paraTcId="3"><hp:run charTcId="4"><hp:t>kept</hp:t></hp:run></hp:p>'
    document = Dochan(package(tmp_path, body, changes), revision_mode=mode).doc
    assert texts(document) == ["kept"]
    assert any("formatting" in e for e in document.errors)
    assert any("header-reference" in e for e in document.errors)
    prefix = "WARN:" if mode == "preserve" else "ERR:"
    assert all(e.startswith(prefix) for e in document.errors)


@pytest.mark.parametrize("mode", [None, "accepted", "FINAL", "", [], 1])
def test_invalid_mode_raises_before_parse(tmp_path, read_document, mode):
    with pytest.raises(ValueError, match="revision_mode"):
        read_document(tmp_path / "missing.hwpx", revision_mode=mode)


def test_keyword_only_and_compatibility_alias():
    for api in (Dochan, HWPReader, HWPXParser.parse):
        parameter = inspect.signature(api).parameters["revision_mode"]
        assert parameter.kind == inspect.Parameter.KEYWORD_ONLY
        assert parameter.default == "preserve"


@pytest.mark.parametrize("mode", ["final", "original"])
@pytest.mark.parametrize("suffix, data", [
    (".hwp", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    (".pdf", b"%PDF-1.7\n"), (".hwpx", b"%PDF-1.7\n"), (".txt", b"plain"),
])
def test_other_formats_reject_nondefault_option(tmp_path, mode, suffix, data):
    path = tmp_path / ("other" + suffix)
    path.write_bytes(data)
    with pytest.raises(ValueError, match="revision_mode.*HWPX"):
        Dochan(path, revision_mode=mode)


def test_default_mode_is_allowed_on_other_formats(tmp_path):
    path = tmp_path / "other.txt"
    path.write_text("plain")
    assert Dochan(path, revision_mode="preserve").doc == Dochan(path).doc


@pytest.mark.parametrize("mode", ["final", "original"])
def test_ambiguous_package_rejects_nondefault_option(tmp_path, mode):
    path = package(tmp_path, paragraph("text"))
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="urn:word"/>')
    with pytest.raises(ValueError, match="revision_mode.*HWPX"):
        Dochan(path, revision_mode=mode)


def test_option_uses_package_identity_and_composes_with_assets(tmp_path):
    path = package(tmp_path, paragraph(marker("delete") + "gone" + marker("delete", True) + "kept"))
    renamed = path.with_suffix(".pdf")
    path.rename(renamed)
    document = Dochan(renamed, False, include_assets=False, revision_mode="final").doc
    assert document.errors == []
    assert texts(document) == ["kept"]


def test_parser_reuse_resets_mode_header_and_diagnostics(tmp_path):
    parser = HWPXParser()
    path = package(tmp_path, paragraph(marker("delete") + "gone" + marker("delete", True) + "kept"))
    assert texts(parser.parse(path, revision_mode="final")) == ["kept"]
    assert texts(parser.parse(path)) == ["gonekept"]
    broken = package(tmp_path, paragraph(marker("delete") + "kept"), changes="")
    assert parser.parse(broken, revision_mode="final").errors
    unchanged = package(tmp_path, paragraph("unchanged"), changes="")
    document = parser.parse(unchanged)
    assert document.errors == []
    assert texts(document) == ["unchanged"]


def spec_gold():
    spec = (ROOT / "docs/benchmarks/hwpx/revision-spec.md").read_text()
    return [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", spec, re.S)]


def real_sample(gold):
    path = ROOT / "corpus/hwp-public/hwpx" / gold["sample"]
    if not path.exists():
        pytest.skip("Optional real corpus fixture is not installed")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == gold["sha256"]
    return path


@pytest.mark.parametrize("mode, gold_key", [("preserve", "all"), ("final", "accepted"), ("original", "rejected")])
def test_real_changetrack_spec_gold_through_api(read_document, mode, gold_key):
    gold = spec_gold()[0]
    document = read_document(real_sample(gold), revision_mode=mode)
    assert document.errors == []
    assert texts(document) == [gold["text"][gold_key]]


@pytest.mark.parametrize("mode", ["preserve", "final", "original"])
def test_real_complex_document_is_partial(mode):
    document = Dochan(real_sample(spec_gold()[1]), revision_mode=mode).doc
    assert document.sections
    assert texts(document)
    assert any("revision" in e and "formatting" in e for e in document.errors)
    assert any("revision" in e and "paraend" in e for e in document.errors)
    assert any("revision" in e and "missing-begin" in e for e in document.errors)


def test_real_complex_preserve_leaves_source_xml_unchanged():
    errors = []
    projector = RevisionProjector(errors)
    with zipfile.ZipFile(real_sample(spec_gold()[1])) as archive:
        header = etree.fromstring(archive.read("Contents/header.xml"))
        before = etree.tostring(header)
        projector.read_header(header)
        assert etree.tostring(header) == before
        sections = [name for name in archive.namelist()
                    if name.startswith("Contents/section") and name.endswith(".xml")]
        assert sections
        for name in sections:
            root = etree.fromstring(archive.read(name))
            before = etree.tostring(root)
            projector.project_section(root, name)
            assert etree.tostring(root) == before, name
    assert errors
    assert all(e.startswith("WARN:") for e in errors)
