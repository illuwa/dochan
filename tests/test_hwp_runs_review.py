"""리뷰에서 지적한 자원 예산 경로의 합성 회귀 입력."""
import pytest

from dochan.hwpx import parser as hwpx
from dochan.hwp.section import _HWPStructureError
from dochan.model.document import TextRun
from test_hwpx_run_budget import _package, _paragraph, _runs
from test_hwp_run_budget import _parser, _paragraph as hwp_paragraph, _record


@pytest.mark.parametrize('nested', [
    '<hp:ctrl><hp:footNote><hp:subList>%s</hp:subList></hp:footNote></hp:ctrl>',
    '<hp:rect><hp:drawText><hp:subList>%s</hp:subList></hp:drawText></hp:rect>',
])
def test_hwpx_nested_budget_follows_document_order(monkeypatch, nested):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_TEXT_RUNS', 1)
    body = '<hp:p><hp:run charPrIDRef="0"><hp:t>앞</hp:t>'
    body += nested % _paragraph('안') + '<hp:t>뒤</hp:t></hp:run></hp:p>'
    doc = hwpx.HWPXParser().parse(_package(body))
    paragraphs = doc.find_all('paragraph')
    assert paragraphs[0].runs[0] == TextRun('앞', bold=True)
    assert [r for p in paragraphs for r in p.runs if r.text == '안'] == [TextRun('안')]


@pytest.mark.parametrize('body,expected', [
    ('<hp:p>' + _runs('앞') + '<hp:ctrl><hp:btn caption="값"/></hp:ctrl>' + _runs('뒤') + '</hp:p>', '앞값뒤'),
    ('<hp:p><hp:run><hp:t>앞</hp:t><hp:btn caption="값"/><hp:t>뒤</hp:t></hp:run></hp:p>', '앞값뒤'),
    ('<hp:p><hp:run><hp:t>앞</hp:t><hp:ctrl><hp:bookmark name="표"/></hp:ctrl><hp:t>뒤</hp:t></hp:run></hp:p>', '앞[bookmark: 표] 뒤'),
    ('<hp:p><hp:run><hp:t>앞</hp:t><hp:ctrl><hp:btn caption="값"/></hp:ctrl><hp:t>뒤</hp:t></hp:run></hp:p>', '앞값뒤'),
])
def test_hwpx_all_auxiliary_runs_share_zero_budget(monkeypatch, body, expected):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_TEXT_RUNS', 0)
    doc = hwpx.HWPXParser().parse(_package(body))
    assert doc.find_all('paragraph')[0].runs == [TextRun(expected)]


def test_plain_paragraphs_do_not_warn_about_lost_formatting(monkeypatch):
    parser = _parser(monkeypatch, limit=0)
    section = parser.parse_stream(hwp_paragraph('본문', []), False)
    assert section.elements[0].runs == [TextRun('본문')]
    assert not parser.errors
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_TEXT_RUNS', 0)
    doc = hwpx.HWPXParser().parse(_package('<hp:p><hp:run><hp:t>본문</hp:t></hp:run></hp:p>' * 5))
    assert len(doc.find_all('paragraph')) == 5
    assert not doc.errors


def test_budget_warning_discloses_hyperlink_loss(monkeypatch):
    parser = _parser(monkeypatch, limit=0)
    parser.parse_stream(hwp_paragraph('본문', [(0, 0)]), False)
    assert 'hyperlink' in parser.errors[0]
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_TEXT_RUNS', 0)
    doc = hwpx.HWPXParser().parse(_package(_paragraph('본문')))
    assert 'hyperlink' in doc.errors[0]


@pytest.mark.parametrize('failure', ['exception', 'serial'])
def test_hwp_failed_control_refunds_run_budget(monkeypatch, failure):
    parser = _parser(monkeypatch, limit=3)
    original = parser._parse_control

    def failing(node):
        original(node)
        if failure == 'exception':
            raise _HWPStructureError('test', 'ERR: synthetic rejected control')
        parser._table_failure_serial += 1
        return None

    monkeypatch.setattr(parser, '_parse_control', failing)
    data = (hwp_paragraph('a', [(0, 0)]) + _record(71, 1, b'  nf')
            + _record(72, 2, bytes(8)) + hwp_paragraph('bc', [(0, 0), (1, 1)], level=3))
    parser.parse_stream(data, False)
    para = parser.parse_stream(hwp_paragraph('de', [(0, 0), (1, 1)]), False).elements[0]
    assert para.runs == [TextRun('d', bold=True, font_size_pt=0.0), TextRun('e', italic=True, font_size_pt=0.0)]


def test_hwpx_document_body_budget_flattens_across_sections(monkeypatch):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_BODY_NODES', 2, raising=False)
    doc = hwpx.HWPXParser().parse(_package(_paragraph('가') + _paragraph('나'),
                                          _paragraph('다') + _paragraph('라'), _paragraph('마')))
    assert [p.text for p in doc.find_all('paragraph')] == ['가', '나', '다라마']
    assert doc.find_all('paragraph')[-1].runs == [TextRun('다라마')]
    assert len(doc.errors) == 1
    assert 'paragraph/note budget' in doc.errors[0]


@pytest.mark.parametrize('wrapper', [
    '<hp:ctrl><hp:footNote><hp:subList>%s</hp:subList></hp:footNote></hp:ctrl>',
    '<hp:rect><hp:drawText><hp:subList>%s</hp:subList></hp:drawText></hp:rect>',
    '<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc><hp:subList>%s</hp:subList></hp:tc></hp:tr></hp:tbl>',
])
def test_hwpx_body_budget_includes_nested_text(monkeypatch, wrapper):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_BODY_NODES', 1, raising=False)
    body = '<hp:p><hp:run><hp:t>앞</hp:t>' + wrapper % _paragraph('안')
    body += '<hp:t>뒤</hp:t></hp:run></hp:p>'
    doc = hwpx.HWPXParser().parse(_package(body, _paragraph('끝')))
    assert ''.join(p.text for p in doc.find_all('paragraph')) == '앞안뒤끝'
    assert len(doc.find_all('paragraph')) <= 2
    assert len(doc.errors) == 1


def test_hwpx_empty_note_fanout_is_bounded_and_parser_resets(monkeypatch):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_BODY_NODES', 6, raising=False)
    parser = hwpx.HWPXParser()
    body = '<hp:p><hp:run>' + '<hp:ctrl><hp:footNote/></hp:ctrl>' * 100 + '<hp:t>끝</hp:t></hp:run></hp:p>'
    doc = parser.parse(_package(body))
    assert len(doc.find_all('paragraph')) + len(doc.find_all('note')) <= 7
    assert doc.find_all('paragraph')[-1].text == '끝'
    assert len(doc.errors) == 1
    assert not parser.parse(_package(_paragraph('정상'))).errors


def test_hwp_plain_text_with_discarded_link_still_warns(monkeypatch):
    parser = _parser(monkeypatch, limit=0)
    monkeypatch.setattr(parser, '_hyperlink_ranges', lambda *args: [(0, 2, 'https://example.org')])
    section = parser.parse_stream(hwp_paragraph('본문', []), False)
    assert section.elements[0].runs == [TextRun('본문')]
    assert len(parser.errors) == 1
    assert 'hyperlink' in parser.errors[0]


def test_hwp_inline_note_codes_do_not_allocate_note_models(monkeypatch):
    parser = _parser(monkeypatch)
    # 각주 제어문자만 반복해도 CTRL_HEADER 레코드 없이는 각주 모델을 만들지 않는다.
    marker = b'\x11\x00' + bytes(14)
    data = _record(66, 0, bytes(22)) + _record(67, 1, marker * 10000 + '끝\r'.encode('utf-16-le'))
    section = parser.parse_stream(data, False)
    assert len(section.elements) == 1
    assert section.elements[0].text == '끝'


def test_hwpx_body_tail_preserves_selected_display_text_and_masks_passwords(monkeypatch):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_BODY_NODES', 0)
    body = '<hp:p><hp:run><hp:t>앞</hp:t><hp:compose composeText="겹"/>'
    body += '<hp:edit><hp:text>값</hp:text></hp:edit><hp:edit passwordChar="*"><hp:text>secret</hp:text></hp:edit>'
    body += '<hp:switch><hp:case required-namespace="unsupported"><hp:t>버림</hp:t></hp:case><hp:default><hp:t>선택</hp:t></hp:default></hp:switch>'
    body += '<hp:equation><hp:script>x+y</hp:script></hp:equation><hp:t>뒤</hp:t></hp:run></hp:p>'
    doc = hwpx.HWPXParser().parse(_package(body))
    text = doc.find_all('paragraph')[0].text
    assert text == '앞겹값선택x+y뒤'
    assert len(doc.errors) == 1


def test_hwpx_empty_objects_do_not_split_runs(monkeypatch):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_TEXT_RUNS', 1)
    body = '<hp:p><hp:run charPrIDRef="0"><hp:t>앞</hp:t><hp:rect/><hp:ctrl><hp:unknown/></hp:ctrl><hp:t>뒤</hp:t></hp:run></hp:p>'
    doc = hwpx.HWPXParser().parse(_package(body))
    assert doc.find_all('paragraph')[0].runs == [TextRun('앞뒤', bold=True)]
    assert not doc.errors


def test_hwp_default_shape_at_zero_budget_has_no_false_warning(monkeypatch):
    parser = _parser(monkeypatch, limit=0)
    for shape in parser.doc_info.char_shapes:
        shape.bold = shape.italic = False
        shape.base_size = 1000
    section = parser.parse_stream(hwp_paragraph('본문', [(0, 0)]), False)
    assert section.elements[0].runs == [TextRun('본문')]
    assert not parser.errors


def test_hwp_rejected_table_caption_refunds_runs(monkeypatch):
    import struct
    parser = _parser(monkeypatch, limit=2)
    data = (_record(66, 0, bytes(22)) + _record(71, 1, b' lbt')
            + _record(72, 2, bytes(12)) + hwp_paragraph('캡션', [(0, 0), (1, 1)], level=3)
            + _record(77, 2, bytes(4) + struct.pack('<HH', 65535, 65535))
            + hwp_paragraph('정상', [(0, 0), (1, 1)]))
    section = parser.parse_stream(data, False)
    assert len(section.elements) == 1
    assert [r.bold for r in section.elements[0].runs] == [True, False]
    assert [r.italic for r in section.elements[0].runs] == [False, True]
    assert len(parser.errors) == 1
    assert 'cell allocation' in parser.errors[0]
