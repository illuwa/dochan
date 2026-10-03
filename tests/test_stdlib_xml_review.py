"""Regression inputs for the stdlib XML migration review."""
from io import BytesIO
from time import perf_counter
import tracemalloc

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


def test_many_attributes_are_bounded_by_part_size_and_parse_consistently():
    source = b'<r ' + b' '.join(b'a%d="x"' % index for index in range(1500)) + b'/>'
    assert len(xml.fromstring(source).attrib) == 1500
    assert len(list(xml.iterparse(BytesIO(source), events=('start',)))[0][1].attrib) == 1500
    with pytest.raises(ValueError, match='size'):
        xml.fromstring(source, max_bytes=100)
    with pytest.raises(ValueError, match='size'):
        list(xml.iterparse(BytesIO(source), max_bytes=100))


def test_quote_mixture_does_not_bypass_xml_parser():
    source = b'<r x="\'" y=\'"\' z="\'>" a="ok"/>'
    assert xml.fromstring(source).get('a') == 'ok'
    assert list(xml.iterparse(BytesIO(source), events=('start',)))[0][1].get('a') == 'ok'


def test_large_start_tag_crossing_stream_chunks(monkeypatch):
    monkeypatch.setattr(xml, 'CHUNK_SIZE', 32)
    source = b'<r><a x="' + b'a' * 60 + b'"/></r>'
    assert list(xml.iterparse(BytesIO(source), tag='a'))[0][1].get('x') == 'a' * 60


def test_dtd_comment_brackets_do_not_consume_root():
    assert xml.sanitize_dtd(b'<!DOCTYPE r [<!-- [ -->]><r/>') == b'<r/>'


def test_dtd_subset_size_is_bounded():
    assert xml.sanitize_dtd(b'<!DOCTYPE r [<!-- [ -->]><r/>') == b'<r/>'
    for suffix in (b'a' * (64 * 1024 + 1),
                   b'<!--' + b'a' * (64 * 1024 + 1),
                   b'"' + b'a' * (64 * 1024 + 1)):
        with pytest.raises(ValueError, match='DTD internal subset limit'):
            xml.sanitize_dtd(b'<!DOCTYPE r [' + suffix)


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


def test_vml_unclosed_comment_does_not_create_fake_image():
    source = (b'<xml xmlns:v="urn:schemas-microsoft-com:vml"><br>'
              b'<!-- <v:imagedata id="fake"/></xml>')
    root = xml.vml_fromstring(source)
    assert root.find('.//{urn:schemas-microsoft-com:vml}imagedata') is None


def test_vml_ignores_non_image_attributes_before_parsing(monkeypatch):
    original = xml._vml_attributes
    calls = []

    class Counted:
        def finditer(self, token):
            calls.append(token)
            return original.finditer(token)

    monkeypatch.setattr(xml, '_vml_attributes', Counted())
    attrs = b' '.join(b'a%d="x"' % index for index in range(1000))
    source = (b'<xml xmlns:v="urn:schemas-microsoft-com:vml"><br '
              + attrs + b'><v:imagedata id="real"/></xml>')
    root = xml.vml_fromstring(source)
    assert root.find('.//{urn:schemas-microsoft-com:vml}imagedata').get('id') == 'real'
    assert calls == ['id="real"']


def test_vml_unmatched_closes_remain_bounded():
    source = (b'<xml xmlns:v="urn:schemas-microsoft-com:vml">' + b'<a>' * 250 +
              b'</missing>' * 100_000 + b'<v:imagedata id="real"/></xml>')
    started = perf_counter()
    root = xml.vml_fromstring(source)
    assert root.find('.//{urn:schemas-microsoft-com:vml}imagedata').get('id') == 'real'
    assert perf_counter() - started < 3


def test_vml_fallback_rejects_oversized_part(monkeypatch):
    monkeypatch.setattr(xml, 'MAX_VML_FALLBACK_BYTES', 64)
    source = b'<xml><br>' + b'x' * 100 + b'</xml>'
    with pytest.raises(ValueError, match='XML size limit'):
        xml.vml_fromstring(source)


def test_vml_unterminated_eight_mib_tag_uses_input_sized_memory(monkeypatch):
    assert xml.MAX_VML_FALLBACK_BYTES == 1024 * 1024
    monkeypatch.setattr(xml, 'MAX_VML_FALLBACK_BYTES', 8 * 1024 * 1024)
    source = b'<xml><' + b'a' * (8 * 1024 * 1024 - 6)
    tracemalloc.start()
    try:
        root = xml.vml_fromstring(source)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert root.tag == 'xml'
    assert peak < 48 * 1024 * 1024


def test_vml_namespace_text_inside_attribute_is_not_a_declaration():
    source = (b'<xml note="x xmlns:v=\'urn:schemas-microsoft-com:vml\'">'
              b'<br><v:imagedata id="forged"/></xml>')
    root = xml.vml_fromstring(source)
    assert root.find('.//{urn:schemas-microsoft-com:vml}imagedata') is None


@pytest.mark.parametrize('encoding', ['utf-16-le', 'utf-16-be'])
def test_vml_fallback_recognizes_bomless_utf16(encoding):
    source = ('<xml xmlns:v="urn:schemas-microsoft-com:vml"><br>'
              '<v:imagedata id="real"/></xml>').encode(encoding)
    root = xml.vml_fromstring(source)
    assert root.find('.//{urn:schemas-microsoft-com:vml}imagedata').get('id') == 'real'


def test_iterparse_short_reads_keep_multibyte_declaration():
    class ShortRead(BytesIO):
        def read(self, size=-1):
            return super().read(1 if size < 0 else min(size, 1))

    source = '<?xml version="1.0" encoding="EUC-KR"?><r><row>한글</row></r>'.encode('euc-kr')
    assert list(xml.iterparse(ShortRead(source), tag='row'))[0][1].text == '한글'


def test_streaming_does_not_keep_comment_or_pi_nodes():
    source = b'<r><!-- comment --><?pi data?><row>ok</row></r>'
    events = list(xml.iterparse(BytesIO(source), events=('end',)))
    root = events[-1][1]
    assert [child.tag for child in root] == ['row']


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
