"""구형 expat에서도 본 파싱 전에 선언을 차단한다."""
from io import BytesIO
import time

import pytest

from dochan.utils import safe_xml as xml


@pytest.mark.parametrize("declaration", [
    '<!DOCTYPE r SYSTEM "https://example.invalid/external.dtd">',
    '<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>',
    '<!DOCTYPE r [<!ENTITY % x SYSTEM "https://example.invalid/x">%x;]>',
    '<!DOCTYPE r [<!ENTITY x "' + 'x' * 100000 + '">]>',
    '<!DOCTYPE r [<!ENTITY a "lol">' + ''.join(
        '<!ENTITY e%d "%s">' % (i, ('&a;' if i == 0 else '&e%d;' % (i - 1)) * 10)
        for i in range(10)) + ']>',
])
@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-16-be", "utf-16-le"])
def test_reject_declarations_before_tree_parser(declaration, encoding, monkeypatch):
    source = (declaration + '<r>&x;</r>').encode(encoding)
    called = []
    monkeypatch.setattr(xml, "_parse_tree", lambda *a, **k: called.append(True))
    started = time.monotonic()
    with pytest.raises(xml.ForbiddenDTD):
        xml.fromstring(source)
    assert not called
    assert time.monotonic() - started < 2


def test_depth_and_size_limits():
    with pytest.raises(ValueError, match="depth"):
        xml.fromstring(b'<r>' * 10000 + b'</r>' * 10000)
    with pytest.raises(ValueError, match="size"):
        xml.fromstring(b'<r>oversized</r>', max_bytes=5)


@pytest.mark.parametrize("encoding", ["euc-kr", "cp949", "shift_jis"])
def test_multibyte_encoding(encoding):
    value = "한글" if encoding != "shift_jis" else "日本語"
    source = ('<?xml version="1.0" encoding="%s"?><r>%s</r>' % (encoding, value)).encode(encoding)
    assert xml.fromstring(source).text == value


def test_comments_pi_tail_and_parent_map():
    root = xml.fromstring(b'<r>a<!--c-->b<?pi v?>c<t>d</t>e</r>')
    assert root[0].text == 'c'
    assert root[1].text == 'pi v'
    assert ''.join(xml.itertext(root)) == 'abcde'
    assert xml.parent_map(root)[root[2]] is root


def test_namespace_scope_rebinding():
    root = xml.fromstring(b'<r xmlns:q="urn:one"><a xmlns:q="urn:two"><q:x/></a><q:y/></r>', namespaces=True)
    assert xml.namespace_map(root)['q'] == 'urn:one'
    assert xml.namespace_map(root[0][0])['q'] == 'urn:two'
    assert xml.namespace_map(root[1])['q'] == 'urn:one'


def test_large_token_stream_and_dtd_guard():
    source = b'<r><row value="' + b'x' * (24 * 1024 * 1024) + b'"/></r>'
    started = time.monotonic()
    with pytest.raises(ValueError, match='start tag byte limit'):
        list(xml.iterparse(BytesIO(source), events=('end',), tag='row'))
    assert time.monotonic() - started < 4
    with pytest.raises(xml.ForbiddenDTD):
        list(xml.iterparse(BytesIO(b'<!DOCTYPE r [<!ENTITY x "boom">]><r>&x;</r>')))


def test_recovery_still_rejects_dtd():
    with pytest.raises(xml.ForbiddenDTD):
        xml.fromstring(b'<!DOCTYPE r><r><br>', recover=True)
    assert xml.fromstring(b'<r><t>ok</t>', recover=True).findtext('t') == 'ok'


def test_vml_recovery_preserves_images_after_unclosed_br():
    source = b'<xml xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"><v:shape><div><br>text</div><v:imagedata o:relid="r1" o:title="image"/></v:shape></xml>'
    root = xml.vml_fromstring(source)
    image = root.find('.//{urn:schemas-microsoft-com:vml}imagedata')
    assert image.get('{urn:schemas-microsoft-com:office:office}relid') == 'r1'
    assert image.get('{urn:schemas-microsoft-com:office:office}title') == 'image'
    with pytest.raises(xml.ForbiddenDTD):
        xml.vml_fromstring(b'<!DOCTYPE xml>' + source)


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-16-be', 'utf-16-le'])
def test_compatibility_sanitization_preserves_safe_text(encoding):
    data = ('<!DOCTYPE r [<!ENTITY x "expanded">]><r>a&x;b&amp;</r>').encode(encoding)
    assert xml.fromstring(xml.sanitize_dtd(data)).text == 'ab&'


def test_non_xml_part_diagnostic_is_stable():
    with pytest.raises(xml.XMLSyntaxError, match="Start tag expected, '<' not found, line 1, column 1"):
        xml.fromstring(b'opaque\x00binary\xff')


def test_namespace_scope_allocation_is_bounded():
    source = b'<r xmlns:a="urn:a" xmlns:b="urn:b"><s xmlns:c="urn:c"/></r>'
    with pytest.raises(ValueError, match='namespace limit'):
        xml.fromstring(source, namespaces=True, max_namespaces=4)


def test_stream_decodes_multibyte_declaration():
    source = '<?xml version="1.0" encoding="EUC-KR"?><r><row>한글</row></r>'.encode('euc-kr')
    assert list(xml.iterparse(BytesIO(source), tag='row'))[0][1].text == '한글'


def test_long_declaration_multibyte_encoding_across_chunks():
    source = ('<?xml version="1.0"' + ' ' * (xml.CHUNK_SIZE + 16) +
              'encoding="EUC-KR"?><r><row>한글</row></r>').encode('euc-kr')
    assert xml.fromstring(source)[0].text == '한글'
    assert list(xml.iterparse(BytesIO(source), tag='row'))[0][1].text == '한글'


def test_vml_namespace_work_is_bounded(monkeypatch):
    monkeypatch.setattr(xml, 'MAX_NAMESPACE_WORK', 5)
    source = b'<xml xmlns:a="urn:a" xmlns:b="urn:b"><br><s xmlns:c="urn:c"><t xmlns:d="urn:d"/></s></xml>'
    with pytest.raises(ValueError, match='namespace limit'):
        xml.vml_fromstring(source)
