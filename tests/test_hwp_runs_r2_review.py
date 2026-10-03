"""두 번째 리뷰의 누적 복사와 문단 중간 링크 경고를 재현한다."""
import struct
import sys

from dochan.utils import safe_xml as etree
import pytest

from dochan.hwpx import parser as hwpx
from dochan.model.document import TextRun
from test_hwp_run_budget import _parser, _record
from test_hwp_section_controls import field_start_block, field_end_block, hlk_ctrl_payload
from test_hwpx_run_budget import NS


@pytest.mark.parametrize('control', ['<hp:rect/>', '<hp:ctrl><hp:unknown/></hp:ctrl>'])
@pytest.mark.parametrize('count', [32, 256])
@pytest.mark.parametrize('budget', [0, 1])
def test_empty_hwpx_controls_have_linear_visits_and_copies(monkeypatch, control, count, budget):
    # 실행 시간 대신 노드 방문·리스트 복사 원소·join 입력 바이트를 계수한다.
    metrics = dict(visits=0, copied_parts=0, joined_parts=0, joined_bytes=0)
    selected = hwpx._selected_children

    def counted_children(element):
        for child in selected(element):
            metrics['visits'] += 1
            yield child

    class CountedList(list):
        def __init__(self, source=()):
            super().__init__(source)
            metrics['copied_parts'] += len(self)

    def profile(frame, event, arg):
        if (event == 'c_call' and getattr(arg, '__name__', '') == 'join'
                and frame.f_code.co_filename == hwpx.__file__
                and 'text_parts' in frame.f_locals):
            parts = frame.f_locals['text_parts']
            metrics['joined_parts'] += len(parts)
            metrics['joined_bytes'] += sum(len(part.encode('utf-8')) for part in parts)

    monkeypatch.setattr(hwpx, '_selected_children', counted_children)
    monkeypatch.setattr(hwpx, 'list', CountedList, raising=False)
    parser = hwpx.HWPXParser()
    parser._text_runs_remaining = budget
    body = '<hp:run %s>' % NS + ('<hp:t>' + 'x' * 1000 + '</hp:t>' + control) * count + '</hp:run>'
    root = etree.fromstring(body.encode(), etree.XMLParser(
        resolve_entities=False, load_dtd=False, no_network=True))
    previous = sys.getprofile()
    try:
        sys.setprofile(profile)
        result = parser._parse_run_with_objects(root)
    finally:
        sys.setprofile(previous)
    assert result == ([TextRun('x' * (1000 * count))] if budget else ['x' * (1000 * count)])
    assert not parser.errors
    assert metrics['visits'] <= count * 4
    assert metrics['copied_parts'] <= count, metrics
    assert metrics['joined_parts'] == count, metrics
    assert metrics['joined_bytes'] == count * 1000, metrics


@pytest.mark.parametrize('linked_part', ['prefix', 'tail', 'both'])
def test_hwp_mid_paragraph_budget_warns_only_for_lost_links(monkeypatch, linked_part):
    parser = _parser(monkeypatch, limit=1)
    for shape in parser.doc_info.char_shapes:
        shape.base_size = 1000
        shape.italic = False
    start, end = field_start_block(b'klh%'), field_end_block()
    a, b = 'a'.encode('utf-16-le'), 'b'.encode('utf-16-le')
    if linked_part == 'prefix':
        payload, tail_position = start + a + end + b, 17
    elif linked_part == 'tail':
        payload, tail_position = a + start + b + end, 9
    else:
        payload, tail_position = start + a + b + end, 9
    data = (_record(66, 0, bytes(22)) + _record(67, 1, payload + b'\r\x00')
            + _record(68, 1, struct.pack('<IIII', 0, 0, tail_position, 1))
            + _record(71, 1, hlk_ctrl_payload('https://example.org;1;0;0;')))
    paragraph = parser.parse_stream(data, False).elements[0]
    assert paragraph.text == 'ab'
    assert paragraph.runs[0] == TextRun('a', bold=True, link=(
        'https://example.org' if linked_part != 'tail' else ''))
    assert paragraph.runs[1] == TextRun('b')
    assert len(parser.errors) == (0 if linked_part == 'prefix' else 1)
    if linked_part != 'prefix':
        assert 'without formatting or hyperlinks' in parser.errors[0]
