"""Regression inputs for the stdlib XML migration review."""
from io import BytesIO
from time import perf_counter

import pytest

from dochan.utils import safe_xml as xml
from dochan.ooxml.xlsx import _sheet_rows
from dochan.ooxml.xlsx import XLSXReader
from dochan.hwpx.parser import HWPXParser
from dochan.ooxml.docx import DOCXReader, W_NS


def test_vml_incomplete_tags_do_not_use_html_parser():
    assert not hasattr(xml, 'HTMLParser')
    source = (b'<xml xmlns:v="urn:schemas-microsoft-com:vml">' + b'<a ' * 2000 +
              b'<v:imagedata id="ok"/>')
    root = xml.vml_fromstring(source)
    assert root.find('.//{urn:schemas-microsoft-com:vml}imagedata').get('id') == 'ok'


def test_streaming_discards_unselected_siblings(monkeypatch):
    source = b'<r>' + b'<x/><row/>' * 1000 + b'</r>'
    roots = []
    original = xml._ET.XMLPullParser.read_events
    def watched(self):
        for event, node in original(self):
            if event == 'start' and node.tag == 'r' and not roots:
                roots.append(node)
            yield event, node
    monkeypatch.setattr(xml._ET.XMLPullParser, 'read_events', watched)
    sizes = []
    for _, row in xml.iterparse(BytesIO(source), tag='row', clear=True):
        sizes.append(len(row))
    assert len(sizes) == 1000
    assert len(roots[0]) == 0


def test_sanitize_dtd_long_unclosed_subset_is_linear(monkeypatch):
    # Count regex use instead of asserting a machine-dependent time.
    original = xml.re.sub

    def counted(pattern, *args, **kwargs):
        if isinstance(pattern, bytes) and pattern.startswith(b'<!DOCTYPE'):
            raise AssertionError('DTD must use a bounded scanner')
        return original(pattern, *args, **kwargs)

    monkeypatch.setattr(xml.re, 'sub', counted)
    data = b'<r/>\n<!DOCTYPE ' * 2000
    xml.sanitize_dtd(data)


def test_hwpx_section_dtd_is_reported():
    with pytest.raises(xml.ForbiddenDTD):
        HWPXParser()._parse_section_xml(b'<!DOCTYPE r><r/>')


def test_hwpx_budget_removes_siblings_in_one_batch(monkeypatch):
    root = xml.fromstring(b'<r>' + b'<p/>' * 1000 + b'</r>')
    parser = HWPXParser()
    parser._body_nodes_remaining = 1
    class Parent:
        def __init__(self, node):
            self.node = node
        def remove(self, child):
            raise AssertionError('linear child search used per removed node')
        def __iter__(self):
            return iter(self.node)
        def __setitem__(self, key, value):
            self.node[key] = value
    parent = Parent(root)
    monkeypatch.setattr(parser, '_xml_parents', lambda: {child: parent for child in root})
    parser._limit_body_nodes(root)
    assert len(root) == 1


def test_depth_is_limited_during_tree_build(monkeypatch):
    original = xml._ET.TreeBuilder
    allocated = []
    def watched(*args, **kwargs):
        def create(tag, attrs):
            allocated.append(tag)
            return xml._ET.Element(tag, attrs)
        return original(*args, element_factory=create, **kwargs)
    monkeypatch.setattr(xml._ET, 'TreeBuilder', watched)
    with pytest.raises(ValueError, match='depth'):
        xml.fromstring(b'<r>' + b'<a>' * 1000 + b'</a>' * 1000 + b'</r>', max_depth=2)
    assert len(allocated) <= 2


def test_cdata_closing_text_cannot_reduce_depth_bound():
    source = b'<r><![CDATA[' + b'</x>' * 200 + b']]>' + b'<a>' * 100 + b'</a>' * 100 + b'</r>'
    with pytest.raises(ValueError, match='depth'):
        xml.fromstring(source, max_depth=2)


def test_namespace_limit_precedes_tree_build(monkeypatch):
    original = xml._ET.TreeBuilder
    allocated = []
    def watched(*args, **kwargs):
        def create(tag, attrs):
            allocated.append(tag)
            return xml._ET.Element(tag, attrs)
        return original(*args, element_factory=create, **kwargs)
    monkeypatch.setattr(xml._ET, 'TreeBuilder', watched)
    with pytest.raises(ValueError, match='namespace limit'):
        xml.fromstring(b'<r xmlns:a="urn:a" xmlns:b="urn:b"/>', max_namespaces=1)
    assert not allocated


def test_stream_element_limit():
    with pytest.raises(ValueError, match='element limit'):
        list(xml.iterparse(BytesIO(b'<r><x/><x/><x/></r>'), max_elements=3))


def test_namespace_uri_with_brace_is_rejected():
    with pytest.raises((ValueError, xml.XMLSyntaxError)):
        xml.fromstring(b'<r xmlns:a="urn:x}evil"><a:b/></r>')


def test_namespace_undeclaration_is_allowed():
    root = xml.fromstring(b'<r xmlns="urn:a"><child xmlns=""/></r>')
    assert root[0].tag == 'child'


def test_missing_recovered_root_has_no_declared_namespaces():
    assert xml.namespace_uris(None) == ()


def test_choice_scopes_are_recorded_without_every_element():
    source = (b'<r xmlns:q="urn:one" xmlns:mc="urn:mc"><ordinary/>'
              b'<choice xmlns:q="urn:two"><mc:Choice><ordinary/></mc:Choice></choice></r>')
    root = xml.fromstring(source, namespaces='choices')
    assert xml.namespace_map(root)['q'] == 'urn:one'
    assert xml.namespace_map(root[1][0])['q'] == 'urn:two'
    assert xml.namespace_map(root[0]) == {}


def test_utf8_alias_and_unknown_encoding():
    assert xml.fromstring(b'<?xml version="1.0" encoding="utf8"?><r>\xc3\xa9</r>').text == '\u00e9'
    with pytest.raises(xml.XMLSyntaxError):
        xml.fromstring(b'<?xml version="1.0" encoding="ISO-10646-UCS-2"?><r/>')
    with pytest.raises(xml.XMLSyntaxError):
        xml.fromstring('<?xml version="1.0" encoding="ISO-10646-UCS-2"?><r/>'.encode('utf-16'))


def test_caption_neighbor_uses_registered_position():
    root = xml.fromstring(('<body xmlns:w="%s">' % W_NS).encode() +
                          b'<w:p/><w:tbl/><w:p/></body>')
    reader = DOCXReader()
    reader._register_tree(root)
    assert reader._sibling_positions[root[1]] == 1
    assert reader._caption_neighbor(root[0], 1) is root[1]
    assert reader._caption_neighbor(root[2], -1) is root[1]


def test_sheet_stops_after_broken_sibling_without_reparsing():
    source = (b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              b'<sheetData><row r="1"/><bad & broken/><row r="2"/></sheetData></worksheet>')
    rows = []
    with pytest.raises(xml.XMLSyntaxError):
        for _, row in _sheet_rows(BytesIO(source)):
            rows.append(row.get('r'))
    assert rows == ['1']


def test_sheet_recovery_without_error_position_keeps_syntax_error():
    with pytest.raises(xml.XMLSyntaxError):
        list(_sheet_rows(BytesIO(b'<?xml version="1.0" encoding="ISO-10646-UCS-2"?><r/>')))


@pytest.mark.parametrize('tail', [
    b'', b'<bad & broken/><row r="3"/></sheetData></worksheet>',
    '<bad>한글</oops></sheetData></worksheet>'.encode('utf-8'),
])
def test_sheet_keeps_completed_rows_before_damage(tail):
    source = (b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              b'<sheetData><row r="1"/><row r="2"/>' + tail)
    rows = []
    with pytest.raises(xml.XMLSyntaxError):
        for _, row in _sheet_rows(BytesIO(source)):
            rows.append(row.get('r'))
    assert rows == ['1', '2']


def test_start_tag_byte_and_attribute_limits_precede_expat(monkeypatch):
    source = b'<r ' + b' '.join(b'a%d="x"' % index for index in range(8000)) + b'/>'
    calls = []
    original = xml._prolog_parser

    def watched():
        calls.append(True)
        return original()

    monkeypatch.setattr(xml, '_prolog_parser', watched)
    with pytest.raises(ValueError, match='start tag'):
        xml.fromstring(source)
    with pytest.raises(ValueError, match='start tag'):
        list(xml.iterparse(BytesIO(source)))
    assert not calls


def test_start_tag_attribute_count_is_bounded_independently(monkeypatch):
    monkeypatch.setattr(xml, 'MAX_START_TAG_ATTRIBUTES', 8)
    source = b'<r ' + b' '.join(b'a%d="x"' % index for index in range(9)) + b'/>'
    with pytest.raises(ValueError, match='attribute limit'):
        xml.fromstring(source)
    with pytest.raises(ValueError, match='attribute limit'):
        list(xml.iterparse(BytesIO(source)))
    assert xml.fromstring(b'<r a="' + b'=' * 20 + b'"/>').get('a') == '=' * 20


def test_start_tag_limit_crossing_stream_chunks(monkeypatch):
    monkeypatch.setattr(xml, 'CHUNK_SIZE', 32)
    monkeypatch.setattr(xml, 'MAX_START_TAG_BYTES', 48)
    source = b'<r><a x="' + b'a' * 60 + b'"/></r>'
    with pytest.raises(ValueError, match='start tag byte limit'):
        list(xml.iterparse(BytesIO(source)))


def test_dtd_comment_brackets_do_not_consume_root():
    assert xml.sanitize_dtd(b'<!DOCTYPE r [<!-- [ -->]><r/>') == b'<r/>'


def test_dtd_long_plain_span_uses_one_delimiter_search(monkeypatch):
    original = xml._dtd_delimiter
    calls = []

    class Counted:
        def search(self, data, position):
            calls.append(position)
            return original.search(data, position)

    monkeypatch.setattr(xml, '_dtd_delimiter', Counted())
    assert xml.sanitize_dtd(b'<!DOCTYPE r [' + b'a' * (1024 * 1024)) == b''
    assert len(calls) == 2


@pytest.mark.parametrize('hidden', [
    b'<!-- <v:imagedata id="fake"/> -->',
    b'<![CDATA[ <v:imagedata id="fake"/> ]]>',
    b'<?pi <v:imagedata id="fake"/> ?>',
])
def test_vml_skips_markup_containers(hidden):
    source = (b'<xml xmlns:v="urn:schemas-microsoft-com:vml">' + hidden +
              b'<br><v:imagedata id="real"/></xml>')
    root = xml.vml_fromstring(source)
    assert [node.get('id') for node in root.findall('.//{urn:schemas-microsoft-com:vml}imagedata')] == ['real']


def test_vml_unmatched_closes_remain_bounded():
    source = (b'<xml xmlns:v="urn:schemas-microsoft-com:vml">' + b'<a>' * 250 +
              b'</missing>' * 100_000 + b'<v:imagedata id="real"/></xml>')
    started = perf_counter()
    root = xml.vml_fromstring(source)
    assert root.find('.//{urn:schemas-microsoft-com:vml}imagedata').get('id') == 'real'
    assert perf_counter() - started < 3


def test_xlsx_vml_part_error_does_not_discard_sheet(monkeypatch):
    reader = XLSXReader()
    reader._errors = []
    monkeypatch.setattr(reader, '_read_sheet_relationships', lambda *args, **kwargs: {'rId1': 'xl/drawings/bad.vml'})
    monkeypatch.setattr(reader, '_read_vml_drawing_part', lambda *args: (_ for _ in ()).throw(ValueError('depth limit')))
    monkeypatch.setattr(reader, '_record_sheet_embedded_assets', lambda *args: None)

    class Package:
        def exists(self, path):
            return True

    root = xml.fromstring(
        b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        b'<legacyDrawing r:id="rId1"/></worksheet>')
    assert reader._read_sheet_drawings(Package(), root, 'xl/worksheets/sheet1.xml', 'Sheet1') == []
    assert reader._errors == ['ERR: XLSX VML XML parse failed: xl/drawings/bad.vml: depth limit']
