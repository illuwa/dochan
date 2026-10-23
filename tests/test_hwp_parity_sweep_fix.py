"""합성 앵커로 4차 감수의 순서·조각·예산 결함을 재현한다."""

import json
import struct
from types import SimpleNamespace

import pytest

from dochan.constants import (
    HWPTAG_CTRL_DATA, HWPTAG_CTRL_HEADER, HWPTAG_EQEDIT, HWPTAG_LIST_HEADER,
    HWPTAG_PARA_CHAR_SHAPE, HWPTAG_PARA_HEADER, HWPTAG_PARA_TEXT, HWPTAG_TABLE,
    HWPTAG_SHAPE_COMPONENT, HWPTAG_SHAPE_COMP_PICTURE,
)
from dochan.hwp.records.char_shape import CharShape
from dochan.hwp.section import SectionParser
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.header_footer import Footnote, HeaderFooter
from dochan.model.image import Image
from dochan.model.table import Table


def rec(tag, level, data):
    if len(data) >= 4095:
        return struct.pack('<II', 4095 << 20 | level << 10 | tag, len(data)) + data
    return struct.pack('<I', len(data) << 20 | level << 10 | tag) + data


def u(text):
    return text.encode('utf-16-le')


def anchor(cid, code=11):
    return struct.pack('<H', code) + cid + bytes(8) + struct.pack('<H', code)


def table(text='셀', as_char=True, level=1, body=None):
    return (rec(HWPTAG_CTRL_HEADER, level, b' lbt' + struct.pack('<I', int(as_char)) + bytes(4)) +
            rec(HWPTAG_TABLE, level + 1, bytes(4) + struct.pack('<HH', 1, 1)) +
            rec(HWPTAG_LIST_HEADER, level + 1, bytes(8) + struct.pack('<HHHH', 0, 0, 1, 1)) +
            (body if body is not None else
             rec(HWPTAG_PARA_HEADER, level + 1, bytes(22)) +
             rec(HWPTAG_PARA_TEXT, level + 2, u(text + '\r'))))


def container(cid=b'daeh', text='정의'):
    return (rec(HWPTAG_CTRL_HEADER, 1, cid + bytes(8)) +
            rec(HWPTAG_LIST_HEADER, 2, bytes(8)) +
            rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
            rec(HWPTAG_PARA_TEXT, 3, u(text + '\r')))


def equation(script):
    data = u(script)
    return (rec(HWPTAG_CTRL_HEADER, 1, b'deqe' + struct.pack('<I', 1) + bytes(36)) +
            rec(HWPTAG_EQEDIT, 2, bytes(4) + struct.pack('<H', len(data) // 2) + data))


def drawing(shape=False):
    body = (rec(HWPTAG_LIST_HEADER, 3, bytes(8)) +
            rec(HWPTAG_PARA_HEADER, 3, bytes(22)) +
            rec(HWPTAG_PARA_TEXT, 4, u('도형\r'))) if shape else (
                rec(HWPTAG_SHAPE_COMP_PICTURE, 3, bytes(71) + struct.pack('<H', 3)))
    return (rec(HWPTAG_CTRL_HEADER, 1, b' osg' + bytes(40)) +
            rec(HWPTAG_SHAPE_COMPONENT, 2, bytes(4)) + body)


def parse(text, controls, parser=None):
    parser = parser or SectionParser()
    return parser.parse_stream(
        rec(HWPTAG_PARA_HEADER, 0, bytes(22)) +
        rec(HWPTAG_PARA_TEXT, 1, text + u('\r')) +
        rec(HWPTAG_PARA_CHAR_SHAPE, 1, struct.pack('<II', 0, 0)) + controls, False).elements


@pytest.mark.parametrize('cid', [b'daeh', b'toof'])
def test_header_footer_middle_keeps_sentence_intact(cid):
    elements = parse(u('제목 앞 ') + anchor(cid, 16) + u('뒤'), container(cid))
    assert [type(e) for e in elements] == [Paragraph, HeaderFooter]
    assert elements[0].text == '제목 앞 뒤'


def test_floating_table_middle_keeps_sentence_intact():
    elements = parse(u('앞 ') + anchor(b' lbt') + u('뒤'), table(as_char=False))
    assert [type(e) for e in elements] == [Paragraph, Table]
    assert elements[0].text == '앞 뒤'


def test_floating_table_leading_precedes_text():
    elements = parse(anchor(b' lbt') + u('뒤'), table(as_char=False))
    assert [type(e) for e in elements] == [Table, Paragraph]


@pytest.mark.parametrize('cid', [b'daeh', b'toof'])
def test_header_footer_leading_precedes_text(cid):
    elements = parse(anchor(cid, 16) + u('뒤'), container(cid))
    assert [type(e) for e in elements] == [HeaderFooter, Paragraph]


@pytest.mark.parametrize('before', [True, False])
@pytest.mark.parametrize('prefix', ['앞', ''])
def test_empty_inline_equation_survives_table_boundary(before, prefix):
    markers = [anchor(b'deqe'), anchor(b' lbt')]
    if not before:
        markers.reverse()
    elements = parse(u(prefix) + b''.join(markers) + u('뒤'), equation('') + table())
    runs = [r for e in elements if isinstance(e, Paragraph) for r in e.runs if r.equation is not None]
    assert len(runs) == 1
    assert runs[0].text == ''
    owner = next(i for i, e in enumerate(elements) if isinstance(e, Paragraph) and runs[0] in e.runs)
    index = next(i for i, e in enumerate(elements) if isinstance(e, Table))
    assert (owner < index) == before


@pytest.mark.parametrize('note_first', [True, False])
def test_record_order_mismatch_never_cuts_equation_or_note(note_first):
    left, right = (b'  nf', b'deqe') if note_first else (b'deqe', b'  nf')
    controls = equation('a over b') + container(b'  nf') if note_first else container(b'  nf') + equation('a over b')
    elements = parse(anchor(left, 17 if note_first else 11) + anchor(b' lbt') +
                     anchor(right, 11 if note_first else 17) + u('뒤'), controls + table())
    paragraphs = [e for e in elements if isinstance(e, Paragraph)]
    eq_runs = [r for p in paragraphs for r in p.runs if r.equation is not None]
    note_runs = [r for p in paragraphs for r in p.runs if r.note_ref]
    assert [r.text for r in eq_runs] == [r'\frac{a}{b}']
    assert [r.text for r in note_runs] == ['[1]']
    assert paragraphs[0].text == ('[1]' if note_first else r'\frac{a}{b}')


def test_note_definition_before_table_follows_raw_anchor_order():
    elements = parse(anchor(b'  nf', 17) + anchor(b' lbt') + u('뒤'),
                     table() + container(b'  nf'))
    assert next(i for i, e in enumerate(elements) if isinstance(e, Footnote)) < next(
        i for i, e in enumerate(elements) if isinstance(e, Table))


@pytest.mark.parametrize('shape', [False, True])
def test_picture_and_shape_before_table_stay_before_moved_table(shape):
    controls = table() + drawing(shape)
    elements = parse(anchor(b' osg') + u('앞') + anchor(b' lbt') + u('뒤'), controls)
    obj = (next(e for e in elements if isinstance(e, Paragraph) and e.text == '도형')
           if shape else next(e for e in elements if isinstance(e, Image)))
    assert elements.index(obj) < next(i for i, e in enumerate(elements) if isinstance(e, Table))


def test_picture_only_paragraph_keeps_anchored_objects():
    elements = parse(anchor(b' osg'), drawing())
    assert [type(e) for e in elements] == [Image]
    assert elements[0].bin_id == 3


def test_bookmark_leading_table_attaches_to_body_without_marker_fragment():
    name = u('위치')
    bm = (rec(HWPTAG_CTRL_HEADER, 1, b'mkob' + bytes(8)) +
          rec(HWPTAG_CTRL_DATA, 2, bytes(10) + struct.pack('<H', len(name) // 2) + name))
    elements = parse(anchor(b' lbt') + u('제목'), bm + table())
    assert [type(e) for e in elements] == [Table, Paragraph]
    assert elements[1].text == '[bookmark: 위치] 제목'


def test_marker_only_bookmark_is_never_heading():
    info = SimpleNamespace(styles=[SimpleNamespace(name='개요 1', para_shape_id=-1)],
                           para_shapes=[], char_shapes=[])
    parser = SectionParser(doc_info=info)
    assert parser._detect_heading_level(Paragraph(runs=[TextRun('[bookmark: 위치] ')], style_id=0)) == 0


def test_whitespace_only_fragment_is_discarded():
    elements = parse(u('앞') + anchor(b' lbt') + u(' \n ') + anchor(b' lbt') + u('뒤'),
                     table('1') + table('2'))
    assert [e.text for e in elements if isinstance(e, Paragraph)] == ['앞', '뒤']


def test_fragment_heading_registration_uses_only_reachable_fragments():
    info = SimpleNamespace(styles=[], para_shapes=[], char_shapes=[CharShape(base_size=2000)])
    parser = SectionParser(doc_info=info)
    elements = parse(u('제목') + anchor(b' lbt') + u('뒷글'), table(), parser)
    fragments = [e for e in elements if isinstance(e, Paragraph)]
    assert fragments[0].heading_level == 1
    assert fragments[1].heading_level == 0
    assert len(parser._font_heading_paragraphs) == 1
    assert parser._font_heading_paragraphs[0] is fragments[0]


def test_fragment_never_promotes_part_of_nonheading_source():
    info = SimpleNamespace(styles=[], para_shapes=[], char_shapes=[CharShape(base_size=2000)])
    parser = SectionParser(doc_info=info)
    elements = parse(u('앞글') + anchor(b' lbt') + u('뒷글' * 70), table(), parser)
    assert all(e.heading_level == 0 for e in elements if isinstance(e, Paragraph))


def test_fragment_finalization_uses_source_text_and_restores_fragment_runs():
    info = SimpleNamespace(styles=[], para_shapes=[], char_shapes=[CharShape(base_size=2000)])
    parser = SectionParser(doc_info=info)
    elements = parse(u('앞글') + anchor(b' lbt') + u('뒷글' * 70), table(), parser)
    first = elements[0]
    info.char_shapes[0] = CharShape(base_size=1000)
    for _ in range(3):
        elements.extend(parse(u('본문 문장입니다. ' * 10), b'', parser))
    doc = Document(sections=[Section(elements=elements)])
    assert parser.finalize_font_headings(doc) == 10
    assert first.text == '앞글'
    assert first.heading_level == 0
    assert not hasattr(first, '_hwp_heading_source_runs')


def test_private_use_bullet_fragment_cannot_inherit_heading():
    info = SimpleNamespace(styles=[SimpleNamespace(name='개요 1', para_shape_id=-1)],
                           para_shapes=[], char_shapes=[])
    elements = parse(u('\ue000') + anchor(b' lbt') + u('제목'), table(), SectionParser(doc_info=info))
    paragraphs = [e for e in elements if isinstance(e, Paragraph)]
    assert [e.heading_level for e in paragraphs] == [0, 1]


def test_split_inside_table_cell_keeps_cell_context_and_nested_blocks():
    info = SimpleNamespace(styles=[], para_shapes=[], char_shapes=[CharShape(base_size=2000)])
    body = (rec(HWPTAG_PARA_HEADER, 2, bytes(22)) +
            rec(HWPTAG_PARA_TEXT, 3, u('앞') + anchor(b' lbt') + u('뒤\r')) +
            rec(HWPTAG_PARA_CHAR_SHAPE, 3, struct.pack('<II', 0, 0)) + table(level=3))
    elements = parse(anchor(b' lbt') + u('본문'), table(body=body), SectionParser(doc_info=info))
    cell = elements[0].rows[0][0]
    assert [type(e) for e in cell.paragraphs] == [Paragraph, Table, Paragraph]
    assert all(e.heading_level == 0 for e in cell.paragraphs if isinstance(e, Paragraph))


def test_split_runs_spend_document_run_budget():
    parser = SectionParser()
    parse(u('앞') + anchor(b' lbt') + u('뒤'), table(), parser)
    # 두 본문 조각과 표 셀의 런 하나.
    assert parser._document_text_runs == 3


def test_split_run_budget_exhaustion_preserves_text_and_warns(monkeypatch):
    parser = SectionParser()
    monkeypatch.setattr(parser, 'MAX_DOCUMENT_TEXT_RUNS', 1)
    elements = parse(u('앞') + anchor(b' lbt') + u('뒤'), table(), parser)
    assert ''.join(e.text for e in elements if isinstance(e, Paragraph)) == '앞뒤'
    assert parser._document_text_runs <= 1
    assert any('text run budget' in e for e in parser.errors)


def test_inline_equation_latex_conversion_occurs_once(monkeypatch):
    import dochan.model.equation as module
    calls = []
    original = module._hwp_to_latex

    def convert(script):
        calls.append(script)
        return original(script)

    monkeypatch.setattr(module, '_hwp_to_latex', convert)
    parse(u('앞') + anchor(b'deqe') + u('뒤'), equation('a over b'))
    assert calls == ['a over b']


def test_probe_diff_detects_regression_hidden_by_equal_totals(tmp_path, capsys):
    from scripts.probe_hwp_parity_sweep_fix import diff
    before = {'files': {}, 'press': {}, 'private': {}, 'pairs': {
        'a': {'same_document': True, 'asset_neutral_markdown_equal': True},
        'b': {'same_document': True, 'asset_neutral_markdown_equal': False}}}
    after = {'files': {}, 'press': {}, 'private': {}, 'pairs': {
        'a': {'same_document': True, 'asset_neutral_markdown_equal': False},
        'b': {'same_document': True, 'asset_neutral_markdown_equal': True}}}
    a, b, out = [tmp_path / name for name in ('before.json', 'after.json', 'diff.json')]
    a.write_text(json.dumps(before))
    b.write_text(json.dumps(after))
    diff(SimpleNamespace(before=a, after=b, output=out, pair_reference=None))
    result = json.loads(out.read_text())
    assert result['pairs']['metrics']['asset_neutral_markdown_equal'] == {
        'before': 1, 'after': 1, 'plus': 1, 'minus': 1}
    capsys.readouterr()
