"""Synthetic regression inputs for the independent PPT reviews."""
import io
import struct

import pytest

from dochan.conversion import Provenance
from dochan.model.document import Document
from dochan.office_binary.ppt import PPTReader, parse_ppt_document_stream
from dochan.office_binary.ppt_render import _Renderer
from test_ppt_structure import record, presentation, sheet, shape, slide_list
from test_ppt_text import block, interaction


def test_review_latest_slide_comments_match_pptx_contract():
    comment = record(12000, record(4026, 'Author'.encode('utf-16le')) +
                     record(4026, 'Review text'.encode('utf-16le'), instance=1), container=True)
    tags = record(5000, record(5002, record(4026, '___PPT10'.encode('utf-16le')) +
                              record(5003, comment), container=True), container=True)
    current_slide = record(1006, tags, container=True)
    data, cu = presentation([(2, record(1006, container=True))],
                            [slide_list([(2, 256, b'')])], previous=(2, current_slide))
    doc = parse_ppt_document_stream(data, current_user=cu)
    paragraphs = doc.find_all('paragraph')
    assert [p.text for p in paragraphs] == ['[comment: Author: Review text]']
    assert paragraphs[0].provenance.path == 'PowerPoint Document#slide1#comments'


def test_review_multiline_comment_is_one_pptx_compatible_paragraph():
    comment = record(12000, record(4026, 'Author'.encode('utf-16le')) +
                     record(4026, 'First\r\nSecond'.encode('utf-16le'), instance=1), container=True)
    tags = record(5000, record(5002, record(4026, '___PPT10'.encode('utf-16le')) +
                              record(5003, comment), container=True), container=True)
    data, cu = presentation([(2, record(1006, tags, container=True))], [slide_list([(2, 256, b'')])])
    doc = parse_ppt_document_stream(data, current_user=cu)
    assert [p.text for p in doc.find_all('paragraph')] == ['[comment: Author: First\nSecond]']


def test_review_repeated_commentless_sheet_scanned_once(monkeypatch):
    import dochan.office_binary.ppt_render as rendering
    original = rendering.walk_records
    visited = []
    def counted(records):
        for rec in original(records):
            visited.append(rec)
            yield rec
    data, cu = presentation([(2, sheet(shapes=record(0xF003, container=True) * 100))],
                            [slide_list([(2, 256 + i, b'') for i in range(100)])])
    monkeypatch.setattr(rendering, 'walk_records', counted)
    doc = parse_ppt_document_stream(data, current_user=cu)
    assert len(doc.sections) == 100
    assert len(visited) < 1000


@pytest.mark.parametrize('kind', [4087, 4088, 4089, 4090, 4117])
def test_review_unresolved_field_metacharacter_is_not_literal_text(kind):
    doc = Document(source_format='ppt')
    renderer = _Renderer(doc, [], {}, 'PowerPoint Document')
    field = record(kind, struct.pack('<II', 0, 0))
    paragraphs = renderer.text(block('* saved', tail=field), Provenance(source_format='ppt', slide=1))
    assert [p.text for p in paragraphs] == ['saved']
    assert any('field' in e for e in doc.errors)


def test_review_slide_number_remaps_links_and_paragraph_bullets():
    doc = Document(source_format='ppt')
    renderer = _Renderer(doc, [], {7: 'https://example.com'}, 'PowerPoint Document')
    b = block('*\rLink', tail=record(4056, struct.pack('<I', 0)) + interaction(7) +
              record(4063, struct.pack('<II', 2, 6)))
    b.paragraph_bullets = [(0, 2, ''), (2, 7, '•')]
    result = renderer.text(b, Provenance(source_format='ppt', slide=10))
    assert [p.text for p in result] == ['10', '• Link <https://example.com>']
    # No mutation of a cached block when another slide uses the same object.
    assert b.text == '*\rLink'
    assert b.paragraph_bullets == [(0, 2, ''), (2, 7, '•')]


def test_review_wordart_unicode_shape_property():
    value = 'בדיקה'.encode('utf-16le') + b'\0\0'
    wordart = record(0xF004, record(0xF00A, struct.pack('<II', 1025, 0xA00)) +
                     record(0xF00B, struct.pack('<HI', 0x80C0, len(value)) + value, instance=1), container=True)
    data, cu = presentation([(2, sheet(shapes=wordart))], [slide_list([(2, 256, b'')])])
    doc = parse_ppt_document_stream(data, current_user=cu)
    assert [p.text for p in doc.find_all('paragraph')] == ['בדיקה']


def test_review_reader_connects_current_user_and_delayed_pictures(monkeypatch, tmp_path):
    png = b'\x89PNG\r\n\x1a\nsynthetic'
    blip = record(0xF01E, b'u' * 16 + b'\xff' + png, 0x6E0)
    bse = record(0xF007, struct.pack('<BB16sHIIIBBBB', 6, 6, b'u' * 16, 255, len(blip), 1, 0, 0, 0, 0, 0))
    drawing = record(1035, record(0xF000, record(0xF001, bse, 1, True), container=True), container=True)
    data, cu = presentation([(2, sheet(shapes=shape(b'Old', pib=1)))],
                            [drawing, slide_list([(2, 256, b'')])],
                            previous=(2, sheet(shapes=shape(b'Latest', pib=1))))
    streams = {'PowerPoint Document': data, 'Current User': cu, 'Pictures': blip}
    opened = []

    class FakeOle:
        def __init__(self, path):
            pass
        def exists(self, name):
            return name in streams
        def openstream(self, name):
            opened.append(name)
            return io.BytesIO(streams[name])
        def close(self):
            pass

    monkeypatch.setattr('dochan.office_binary.ppt.olefile.OleFileIO', FakeOle)
    path = tmp_path / 'synthetic.ppt'
    path.write_bytes(b'fake')
    doc = PPTReader().read(str(path))
    assert {'Current User', 'Pictures'} <= set(opened)
    assert doc.find_all('image')[0].image_data == png
    assert 'Latest' in [p.text for p in doc.find_all('paragraph')]
    assert 'Old' not in [p.text for p in doc.find_all('paragraph')]


def test_review_inherited_footer_placeholder_matches_pptx(tmp_path):
    from test_pptx_reader import _write_pptx
    from dochan.ooxml.pptx import PPTXReader
    ns = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    footer = '<p:sp><p:nvSpPr><p:cNvPr id="1" name="Footer"/><p:cNvSpPr/><p:nvPr><p:ph type="ftr"/></p:nvPr></p:nvSpPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Inherited footer</a:t></a:r></a:p></p:txBody></p:sp>'
    path = tmp_path / 'footer.pptx'
    _write_pptx(path,
                '<p:presentation %s xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>' % ns,
                {'ppt/slides/slide1.xml': '<p:sld %s><p:cSld><p:spTree/></p:cSld></p:sld>' % ns},
                extra_parts={
                    'ppt/slides/_rels/slide1.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="layout" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>',
                    'ppt/slideLayouts/slideLayout1.xml': '<p:sldLayout %s><p:cSld><p:spTree>%s</p:spTree></p:cSld></p:sldLayout>' % (ns, footer),
                })
    reference = PPTXReader().read(str(path))
    data, cu = presentation([(2, sheet(master=900)),
                            (3, sheet(1016, shape(b'Inherited footer', placeholder=9)))],
                           [slide_list([(2, 256, b'')]), slide_list([(3, 900, b'')], 1)])
    actual = parse_ppt_document_stream(data, current_user=cu)
    assert [p.text for p in reference.find_all('paragraph')] == []
    assert [p.text for p in actual.find_all('paragraph')] == []


def test_review_saved_local_footer_field_and_literal_asterisk():
    textbox = record(3999, struct.pack('<I', 4)) + record(4008, b'* literal *') + record(4090, struct.pack('<I', 0))
    sp = record(0xF004, record(0xF00A, struct.pack('<II', 1, 0xA00)) + record(0xF00D, textbox), container=True)
    hf = record(4057, record(4058, struct.pack('<HH', 0, 0x20)) +
                record(4026, 'saved footer'.encode('utf-16le'), instance=2), container=True)
    obj = record(1006, hf + record(1036, record(0xF002, sp, container=True), container=True), container=True)
    data, cu = presentation([(2, obj)], [slide_list([(2, 256, b'')])])
    doc = parse_ppt_document_stream(data, current_user=cu)
    assert [p.text for p in doc.find_all('paragraph')] == ['saved footer literal *']
