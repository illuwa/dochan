"""
tests/test_hwpx_invalid_xml_char.py — XML 1.0 무효 제어문자 내결함성 테스트

docs/benchmarks/2026-07-27-hwp-corpus-collection-and-quality-scan.md finding #4:
corpus/hwp-public/hwpx/일반기안문_서식.hwpx 의 header.xml 안에 XML 1.0에서
허용하지 않는 제어문자(0x01)가 하나 섞여 있어 lxml이 전체 파싱을 중단시킨다
("PCDATA invalid Char value 1"). 문자 하나 때문에 섹션 전체를 못 읽는 대신,
그 문자만 제거하고 한 번 더 시도해야 한다.
"""
from dochan.utils import safe_xml as etree

from dochan.hwpx.parser import _parse_xml_tolerant


def test_parse_xml_tolerant_recovers_from_single_invalid_control_char():
    xml = b'<root><child>\x01broken</child></root>'

    root = _parse_xml_tolerant(xml)

    assert root.find('child').text == 'broken'


def test_parse_xml_tolerant_still_raises_on_genuinely_malformed_xml():
    xml = b'<root><unclosed></root>'

    try:
        _parse_xml_tolerant(xml)
        assert False, "should have raised"
    except etree.XMLSyntaxError:
        pass


def test_parse_xml_tolerant_parses_clean_xml_unchanged():
    xml = '<root><child>정상 텍스트</child></root>'.encode('utf-8')

    root = _parse_xml_tolerant(xml)

    assert root.find('child').text == '정상 텍스트'


def test_tolerant_xml_neutralizes_entities_and_keeps_surrounding_text():
    from dochan.hwpx.parser import _text_of_t

    source = '<!DOCTYPE t [<!ENTITY secret "DO_NOT_EXPAND">]><t>앞&secret;<span>중<!--ignore--><?pi ignore?>간</span>뒤</t>'
    for encoding in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
        root = _parse_xml_tolerant(source.encode(encoding))
        assert _text_of_t(root) == "앞중간뒤"


def test_tolerant_xml_keeps_predefined_entities_and_rejects_depth_bomb():
    root = _parse_xml_tolerant(b"<!DOCTYPE t><t>&amp;&lt;&gt;&apos;&quot;</t>")
    assert root.text == "&<>\'\""
    try:
        _parse_xml_tolerant(b"<t>" * 300 + b"</t>" * 300)
        assert False, "depth limit must reject the whole tree"
    except ValueError:
        pass
