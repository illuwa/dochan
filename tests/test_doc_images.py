"""Synthetic [MS-DOC] PICF/OfficeArt picture extraction cases."""
import struct
from types import SimpleNamespace

from dochan.model.document import Document
from dochan.office_binary.doc_images import DocImages


def record(kind, data=b'', version=0, instance=0):
    return struct.pack('<HHI', version | instance << 4, kind, len(data)) + data


def shape(spid=1025, pib=1, alt=''):
    props = [(0x4104, pib)]
    complex_data = b''
    if alt:
        complex_data = (alt + '\0').encode('utf-16le')
        props.append((0x8381, len(complex_data)))
    opt = b''.join(struct.pack('<HI', key, value) for key, value in props) + complex_data
    return record(0xf004, record(0xf00a, struct.pack('<II', spid, 0), instance=75)
                  + record(0xf00b, opt, version=3, instance=len(props)), version=15)


def fbse(payload=b'\x89PNG\r\n\x1a\nexample', delay=None):
    blip = record(0xf01e, b'\0' * 16 + b'\xff' + payload, instance=0x6e0)
    header = struct.pack('<BB16sHIIIBBBB', 6, 6, b'\0' * 16, 0xff, len(blip), 1,
                         0xffffffff if delay is None else delay, 0, 0, 0, 0)
    return record(0xf007, header + (blip if delay is None else b''), version=2), blip


def picf(alt='', payload=b'\x89PNG\r\n\x1a\nexample'):
    body = shape(alt=alt) + fbse(payload)[0]
    return struct.pack('<IHH', 68 + len(body), 68, 100) + b'\0' * 60 + body


def binary(text='\x01', data=b'', blobs=None, word=b'', ranges=None):
    return SimpleNamespace(text=text, data=data, word=word, blob=lambda index: (blobs or {}).get(index, b''),
                           ranges=ranges or {}, char_props=lambda cp: {'pic_location': 0, 'special': True})


def test_doc_inline_picture_bytes_alt_and_asset():
    doc = Document()
    pictures = DocImages(binary(data=picf('Example diagram')), doc)
    image = pictures.image_at(0)
    assert image.image_format == 'png'
    assert image.image_data == b'\x89PNG\r\n\x1a\nexample'
    assert image.alt_text == 'Example diagram'
    assert image.provenance.source_format == 'doc'
    assert len(doc.assets) == 1
    assert doc.assets[0].content_type == 'image/png'
    assert doc.assets[0].metadata['source_format'] == 'doc'


def test_doc_reused_picture_has_two_placements_one_asset():
    doc = Document()
    pictures = DocImages(binary(text='\x01\x01', data=picf()), doc)
    first, second = pictures.image_at(0), pictures.image_at(1)
    assert first is not second
    assert first.filename == second.filename
    assert len(doc.assets) == 1


def test_doc_picture_ignores_ordinary_character_and_non_special_marker():
    doc = Document()
    pictures = DocImages(binary(text='a\x01', data=picf()), doc)
    assert pictures.image_at(0) is None
    assert pictures.image_at(1, {'pic_location': 0, 'special': False}) is None
    assert not doc.assets


def test_doc_floating_picture_uses_spa_shape_id_and_delayed_bstore():
    entry, blip = fbse(delay=12)
    dgg = record(0xf000, record(0xf001, entry, version=15), version=15)
    drawing = record(0xf002, shape(spid=2050, alt='Floating diagram'), version=15)
    spa = struct.pack('<II', 2, 3) + struct.pack('<I', 2050) + b'\0' * 22
    doc = Document()
    pictures = DocImages(binary(text='ab\x08', blobs={50: dgg + b'\0' + drawing, 40: spa},
                                word=b'\0' * 12 + blip), doc)
    assert pictures.image_at(0) is None
    image = pictures.image_at(2)
    assert image.alt_text == 'Floating diagram'
    assert image.image_data == b'\x89PNG\r\n\x1a\nexample'


def test_doc_truncated_picf_is_warning_not_exception():
    doc = Document()
    pictures = DocImages(binary(data=struct.pack('<IHH', 1000, 68, 100)), doc)
    assert pictures.image_at(0) is None
    assert any('PICF' in error for error in doc.errors)


def test_doc_picture_location_bounds():
    doc = Document()
    pictures = DocImages(binary(data=picf()), doc)
    for location in [-1, 10**20, None]:
        assert pictures.image_at(0, {'special': True, 'pic_location': location}) is None
    assert not doc.assets


def test_doc_malformed_drawing_and_spa_are_warnings():
    doc = Document()
    pictures = DocImages(binary(text='\x08', blobs={50: b'\xff' * 9, 40: b'\0' * 7}), doc)
    assert pictures.image_at(0) is None
    assert doc.errors


def test_doc_image_bytes_reach_existing_ocr_path(monkeypatch):
    calls = []
    monkeypatch.setattr('dochan.utils.ocr.ocr_image', lambda data: calls.append(data) or 'recognized')
    image = DocImages(binary(data=picf()), Document()).image_at(0)
    assert image.run_ocr() == 'recognized'
    assert calls == [image.image_data]


def test_doc_header_picture_anchor_uses_header_story_cp():
    entry, _ = fbse()
    dgg = record(0xf000, record(0xf001, entry, version=15), version=15)
    drawing = record(0xf002, shape(spid=2050), version=15)
    spa = struct.pack('<II', 2, 3) + struct.pack('<I', 2050) + b'\0' * 22
    b = binary(text='body\rxx\x08', blobs={50: dgg + b'\x01' + drawing, 41: spa})
    b.stories = {'header': (5, 8)}
    pictures = DocImages(b, Document())
    assert pictures.image_at(7).has_data
    assert pictures.image_at(2) is None


def test_doc_inline_picture_total_decoded_budget_is_bounded():
    from dochan.office_binary.officeart import Limits
    first = picf(payload=b'1234')
    b = binary(text='\x01\x01', data=first + picf(payload=b'5678'))
    doc = Document()
    pictures = DocImages(b, doc)
    pictures.limits = Limits(max_image_bytes=4, max_total_image_bytes=4)
    assert pictures.image_at(0).image_data == b'1234'
    assert pictures.image_at(1, {'special': True, 'pic_location': len(first)}) is None
    assert pictures._inline[len(first)] is None
    assert doc.errors


def test_doc_textbox_shape_maps_anchor_to_zero_based_story_index():
    text_props = record(0xf00b, struct.pack('<HI', 0x80, 2 << 16), version=3, instance=1)
    text_shape = record(0xf004, record(0xf00a, struct.pack('<II', 2050, 0)) + text_props, version=15)
    drawing = record(0xf002, text_shape, version=15)
    spa = struct.pack('<II', 2, 3) + struct.pack('<I', 2050) + b'\0' * 22
    pictures = DocImages(binary(text='ab\x08', blobs={50: record(0xf000, version=15) + b'\0' + drawing,
                                                   40: spa}), Document())
    assert pictures.textbox_at(2) == 1
    assert pictures.textbox_at(0) is None
    assert pictures.image_at(2) is None
