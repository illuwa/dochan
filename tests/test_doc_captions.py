"""DOC 캡션 계약을 STSH/PAPX/필드 합성 바이트로 검증한다."""
import struct

import pytest

from dochan.model.document import Document, Paragraph, Section
from dochan.model.image import Image
from dochan.model.table import Table
from dochan.office_binary.doc_binary import DocBinary
from dochan.office_binary.doc_stories import Stories
from dochan.office_binary.doc_structure import StructureRenderer
from dochan.output.markdown import to_markdown
from test_doc_binary import make_binary, style_record


def binary_fixture(records, styles=()):
    # Each record is (text, istd, table depth, row end).
    text = ''.join(r[0] for r in records)
    encoded = text.encode('utf-16-le')
    stshi = struct.pack('<HH', len(styles), 10) + bytes(14)
    stsh = struct.pack('<H', len(stshi)) + stshi
    for name, base, sti in styles:
        raw = bytearray(style_record(name, base))
        struct.pack_into('<H', raw, 2, sti)
        stsh += raw
    original = make_binary('x' * (len(encoded) // 2), styles=stsh)
    word, table = bytearray(original.word), bytearray(original.table)
    word.extend(bytes(4608 - len(word)))
    word[1024:1024 + len(encoded)] = encoded
    struct.pack_into('<I', table, 15, 1024)  # Uncompressed Unicode PCD.
    page = bytearray(512)
    fc, pos = 1024, 260
    for i, (content, style, depth, row_end) in enumerate(records):
        struct.pack_into('<I', page, i * 4, fc)
        fc += len(content.encode('utf-16-le'))
        pap = struct.pack('<H', style)
        if depth:
            pap += struct.pack('<HBHI', 0x2416, 1, 0x6649, depth)
        if row_end:
            pap += struct.pack('<HB', 0x2417 if depth == 1 else 0x244c, 1)
        if len(pap) % 2 == 0:
            pap += b'\0'
        page[(len(records) + 1) * 4 + i * 13] = pos // 2
        page[pos] = (len(pap) + 1) // 2
        page[pos + 1:pos + 1 + len(pap)] = pap
        pos += len(pap) + 1
    struct.pack_into('<I', page, len(records) * 4, fc)
    page[511] = len(records)
    word[4096:4608] = page
    plc = struct.pack('<III', 1024, fc, 8)
    struct.pack_into('<II', word, 154 + 13 * 8, len(table), len(plc))
    table.extend(plc)
    return DocBinary(bytes(word), bytes(table))


def p(text, style=0, depth=0):
    return (text + '\r', style, depth, False)


def table_records(depth=1):
    return [('cell\x07', 0, depth, False), ('\x07', 0, depth, True)]


class Pictures:
    def image_at(self, cp, props):
        return Image(filename='synthetic.png', image_data=b'PNG')


def read_records(records, styles=(), configure=None):
    binary = binary_fixture(records, styles)
    doc = Document(source_format='doc')
    stories, pictures = Stories(binary, doc), Pictures()
    renderer = StructureRenderer(binary, doc, stories, pictures)
    if configure:
        configure(binary, stories, pictures, renderer)
    doc.sections = [Section(elements=renderer.render(*binary.stories['main']))]
    return doc


@pytest.mark.parametrize('name,sti', [('Caption', 4094), ('caption', 4094),
    ('캡션', 34), ('Beschriftung', 34), ('任意の名前', 34)])
@pytest.mark.parametrize('above', [True, False])
def test_doc_caption_stsh_name_or_builtin_id_attaches_table(name, sti, above):
    cap = [p('Table one', 1)]
    records = cap + table_records() if above else table_records() + cap
    doc = read_records(records, [('Normal', 4095, 0), (name, 0, sti)])
    assert len(doc.sections[0].elements) == 1
    target = doc.sections[0].elements[0]
    assert isinstance(target, Table)
    assert (target.caption_text, target.caption_side) == ('Table one', 'TOP' if above else 'BOTTOM')
    assert to_markdown(doc).count('Table one') == 1
    assert target.caption[0].provenance.path.startswith('WordDocument#cp')


@pytest.mark.parametrize('label,target', [('Table', Table), ('표', Table),
    ('Figure', Image), ('그림', Image), ('"Tableau"', Table)])
@pytest.mark.parametrize('above', [True, False])
def test_doc_caption_seq_cached_result_and_target_type(label, target, above):
    caption = [p('Label \x13 SEQ ' + label + ' \\* ARABIC \x141\x15 caption')]
    body = table_records() if target is Table else [p('\x01')]
    doc = read_records(caption + body if above else body + caption)
    elements = doc.sections[0].elements
    assert len(elements) == 1 and isinstance(elements[0], target)
    assert elements[0].caption_text == 'Label 1 caption'
    assert elements[0].caption_side == ('TOP' if above else 'BOTTOM')
    assert to_markdown(doc).count('Label 1 caption') == 1


def test_doc_caption_inherited_style_and_sequential_target_exclusion():
    styles = [('Normal', 4095, 0), ('Caption', 0, 34), ('Custom', 1, 4094)]
    doc = read_records([p('first', 2)] + table_records() + [p('second', 2)] + table_records(), styles)
    assert [t.caption_text for t in doc.find_all('table')] == ['first', 'second']


@pytest.mark.parametrize('gap', ['', 'ordinary'])
def test_doc_caption_never_crosses_empty_or_text_paragraph(gap):
    doc = read_records([p('caption', 1), p(gap)] + table_records(),
                       [('Normal', 4095, 0), ('Caption', 0, 34)])
    assert not doc.find_all('table')[0].caption
    assert doc.sections[0].elements[0].text == 'caption'


def test_doc_caption_ambiguous_between_tables_stays_paragraph():
    doc = read_records(table_records() + [p('\x13SEQ Table\x141\x15')] + table_records())
    assert [type(e) for e in doc.sections[0].elements] == [Table, Paragraph, Table]
    assert not any(t.caption for t in doc.find_all('table'))


@pytest.mark.parametrize('label', ['Figure', 'Equation', '수식'])
def test_doc_caption_wrong_target_and_equation_stay_paragraph(label):
    doc = read_records([p('\x13SEQ ' + label + '\x141\x15', 1)] + table_records(),
                       [('Normal', 4095, 0), ('Caption', 0, 34)])
    assert not doc.find_all('table')[0].caption
    assert doc.sections[0].elements[0].text == '1'


def test_doc_caption_cell_and_nested_table_are_not_attached():
    doc = read_records([p('inner caption', 1, 1)] + table_records(2) + table_records(),
                       [('Normal', 4095, 0), ('Caption', 0, 34)])
    assert not any(t.caption for t in doc.find_all('table'))
    assert doc.find_all('table')[0].rows[0][0].paragraphs[0].text == 'inner caption'


def test_doc_caption_textbox_story_never_attaches():
    def configure(binary, stories, pictures, renderer):
        end = len(binary.text)
        binary.stories = {'main': (0, 2), 'textbox': (2, end)}
        pictures.image_at = lambda cp, props: None if cp == 0 else Image(filename='box.png')
        pictures.textbox_at = lambda cp: 0 if cp == 0 else None
        stories.textbox = lambda index, render, header=False: render(2, end)
    doc = read_records([p('\x08'), p('\x01'), p('\x13SEQ Figure\x141\x15')], configure=configure)
    assert not doc.find_all('image')[0].caption
    assert doc.sections[0].elements[-1].text == '1'


def test_doc_caption_style_cycle_is_bounded_and_not_a_caption():
    doc = read_records([p('ordinary', 1)] + table_records(),
                       [('Normal', 4095, 0), ('Custom', 2, 4094), ('Other', 1, 4094)])
    assert not doc.find_all('table')[0].caption


def test_doc_caption_does_not_guess_from_visible_label():
    doc = read_records([p('Figure 1 visible label'), p('\x01')])
    assert not doc.find_all('image')[0].caption


def test_doc_caption_image_text_remains_discoverable_once():
    doc = read_records([p('\x01'), p('Figure \x13SEQ Figure\x141\x15 Spacewalk')])
    assert [p.text for p in doc.find_all('paragraph')] == ['Figure 1 Spacewalk']


def test_doc_caption_existing_image_caption_is_not_overwritten():
    from dochan.model.document import TextRun
    def configure(binary, stories, pictures, renderer):
        pictures.image_at = lambda cp, props: Image(caption=[Paragraph([TextRun('existing')])])
    doc = read_records([p('Figure \x13SEQ Figure\x141\x15'), p('\x01')], configure=configure)
    assert doc.find_all('image')[0].caption_text == 'existing'
    assert doc.sections[0].elements[0].text == 'Figure 1'


def test_doc_caption_seq_disambiguates_table_and_image():
    doc = read_records(table_records() + [p('Figure \x13SEQ Figure\x141\x15'), p('\x01')])
    assert not doc.find_all('table')[0].caption
    assert doc.find_all('image')[0].caption_text == 'Figure 1'


def test_doc_caption_multiple_images_are_ambiguous():
    doc = read_records([p('Figure \x13SEQ Figure\x141\x15'), p('\x01\x01')])
    assert not any(i.caption for i in doc.find_all('image'))
    assert doc.sections[0].elements[0].text == 'Figure 1'


def test_doc_caption_same_source_paragraph_is_not_its_own_caption():
    doc = read_records([p('\x01Figure \x13SEQ Figure\x141\x15')])
    assert not doc.find_all('image')[0].caption
    assert doc.find_all('paragraph')[0].text == 'Figure 1'


def test_doc_caption_textbox_cannot_supply_neighbor_target():
    def configure(binary, stories, pictures, renderer):
        end = len(binary.text)
        box_start = end - 2
        binary.stories = {'main': (0, box_start), 'textbox': (box_start, end)}
        pictures.image_at = lambda cp, props: None if binary.text[cp] == '\x08' else Image()
        pictures.textbox_at = lambda cp: 0 if binary.text[cp] == '\x08' else None
        stories.textbox = lambda index, render, header=False: render(box_start, end)
    doc = read_records([p('Figure \x13SEQ Figure\x141\x15'), p('\x08'), p('\x01')], configure=configure)
    assert not doc.find_all('image')[0].caption
    assert doc.sections[0].elements[0].text == 'Figure 1'


@pytest.mark.parametrize('malformed', [b'\x01', struct.pack('<HHH', 4, 4097, 10),
    struct.pack('<HHHH', 4, 1, 10, 65535)])
def test_doc_caption_bad_stsh_warns_and_preserves_visible_text(malformed):
    def configure(binary, stories, pictures, renderer):
        original = binary.blob
        binary.blob = lambda index: malformed if index == 1 else original(index)
    doc = read_records([p('ordinary')] + table_records(), configure=configure)
    assert doc.sections[0].elements[0].text == 'ordinary'
    assert any('WARN: DOC caption styles:' in error for error in doc.errors)


def test_doc_caption_reader_integration_keeps_json_contract(monkeypatch, tmp_path):
    from dochan.output.json_out import to_dict
    from test_doc_structure import _fake_reader
    binary = binary_fixture([p('Table \x13SEQ Table\x141\x15')] + table_records())
    doc = _fake_reader(monkeypatch, tmp_path, {'WordDocument': binary.word, '0Table': binary.table})
    assert doc.errors == []
    caption = to_dict(doc)['sections'][0]['elements'][0]['caption']
    assert caption['text'] == 'Table 1'
    assert caption['side'] == 'TOP'


def test_doc_caption_field_instruction_of_outer_field_is_not_evidence():
    doc = read_records([p('\x13 IF \x13SEQ Figure\x141\x15 = 1 \x14ordinary\x15'), p('\x01')])
    assert not doc.find_all('image')[0].caption
    assert doc.sections[0].elements[0].text == 'ordinary'


def test_doc_caption_preserves_runs_and_uses_shared_markdown_format():
    def configure(binary, stories, pictures, renderer):
        original = binary.char_props
        binary.char_props = lambda cp: dict(original(cp), bold=True)
    doc = read_records([p('\x01'), p('Figure \x13SEQ Figure\x141\x15  Spacewalk')], configure=configure)
    caption = doc.find_all('image')[0].caption[0]
    assert caption.text == 'Figure 1  Spacewalk'
    assert all(run.bold for run in caption.runs)
    assert '*Figure 1 Spacewalk*' in to_markdown(doc)


@pytest.mark.parametrize('above', [True, False])
@pytest.mark.parametrize('equation_first', [True, False])
def test_doc_caption_never_crosses_equation_in_adjacent_source_paragraph(above, equation_first):
    from types import SimpleNamespace
    from dochan.model.equation import Equation
    def configure(binary, stories, pictures, renderer):
        cp = binary.text.index('\x01') + (0 if equation_first else 1)
        renderer.objects = SimpleNamespace(at=lambda position, props, provenance:
            [Equation(latex_override='x')] if position == cp else [], labels={})
    caption, body = [p('Figure \x13SEQ Figure\x141\x15')], [p('\x01\x01')]
    doc = read_records(caption + body if above else body + caption, configure=configure)
    image = doc.find_all('image')[0]
    assert bool(image.caption) == (above != equation_first)
    assert to_markdown(doc).count('Figure 1') == 1
