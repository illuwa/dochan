"""Synthetic BIFF / OfficeArt image links, independent of the POI corpus."""
import struct

from dochan.model.image import Image
from dochan.office_binary.xls_drawing import XlsDrawingReader


def biff(kind, data=b''):
    return struct.pack('<HH', kind, len(data)) + data


def art(kind, data=b'', version=0, instance=0):
    return struct.pack('<HHI', instance << 4 | version, kind, len(data)) + data


def store(image=b'png pixels'):
    blip = art(0xF01E, bytes(16) + b'\xff' + image, instance=0x6E0)
    fbse = struct.pack('<BB16sHIIIBBBB', 6, 6, bytes(16), 0xff, len(blip), 1, 0xffffffff, 0, 0, 0, 0)
    return art(0xF000, art(0xF001, art(0xF007, fbse + blip, version=2), version=15), version=15)


def shape(pib=1, row=4, col=2):
    return art(0xF004,
        art(0xF00A, struct.pack('<II', 1025, 0xa00), version=2, instance=75) +
        art(0xF00B, struct.pack('<HI', 0x4104, pib), version=3, instance=1) +
        art(0xF010, struct.pack('<9H', 0, col, 0, row, 0, col + 1, 0, row + 1, 0)) +
        art(0xF011), version=15)


def test_xls_picture_bstore_pib_anchor_asset_and_ocr(monkeypatch):
    reader = XlsDrawingReader(biff(0xeb, store()) + biff(0xa))
    elements = reader.read_sheet(biff(0xec, shape()) + biff(0x5d, b'object') + biff(0xa), 'Pictures')
    image = next(e for e in elements if isinstance(e, Image))
    assert image.image_data == b'png pixels'
    assert image.image_format == 'png'
    assert image.provenance.cell == 'C5'
    assert image.provenance.sheet == 'Pictures'
    assert elements[0].text == '![image](xls/media/image1.png)'
    assert reader.assets[0].source_path == 'xls/media/image1.png'
    assert reader.assets[0].metadata['kind'] == 'image'
    monkeypatch.setattr('dochan.utils.ocr.ocr_image', lambda data: 'visible text' if data == b'png pixels' else '')
    assert image.run_ocr() == 'visible text'


def test_xls_drawing_continues_and_multiple_placements():
    group = store()
    drawing = shape(row=9) + shape(row=1)
    reader = XlsDrawingReader(biff(0xeb, group[:25]) + biff(0x3c, group[25:]) + biff(0xa))
    elements = reader.read_sheet(biff(0xec, drawing[:20]) + biff(0x3c, drawing[20:]) + biff(0xa), 'S')
    images = [e for e in elements if isinstance(e, Image)]
    assert [i.provenance.cell for i in images] == ['C2', 'C10']
    assert len(reader.assets) == 1


def test_xls_bad_image_index_warns_without_losing_valid_picture():
    errors = []
    reader = XlsDrawingReader(biff(0xeb, store()) + biff(0xa), errors=errors)
    elements = reader.read_sheet(biff(0xec, shape(pib=900) + shape()) + biff(0xa), 'S')
    assert len([e for e in elements if isinstance(e, Image)]) == 1
    assert any('pib' in e and e.startswith('WARN:') for e in errors)


def test_xls_drawing_does_not_consume_txo_continue_as_art():
    reader = XlsDrawingReader(biff(0xeb, store()) + biff(0xa))
    errors = reader.errors
    sheet = biff(0xec, shape()) + biff(0x1b6, b'text object') + biff(0x3c, b'text content') + biff(0xa)
    assert len([e for e in reader.read_sheet(sheet, 'S') if isinstance(e, Image)]) == 1
    assert errors == []


def test_xls_truncated_drawing_and_stream_limit_are_warnings():
    from dochan.office_binary.officeart import Limits
    errors = []
    reader = XlsDrawingReader(biff(0xeb, store()) + biff(0xa), errors=errors, limits=Limits(max_stream_bytes=10))
    assert reader.read_sheet(biff(0xec, shape()) + biff(0xa), 'S') == []
    assert any('limit' in e for e in errors)
    errors = []
    reader = XlsDrawingReader(biff(0xeb, store()) + biff(0xa), errors=errors)
    assert reader.read_sheet(biff(0xec, shape()[:-3]) + biff(0xa), 'S') == []
    assert any('truncated' in e for e in errors)


def test_xls_drawing_continues_after_obj_and_empty_txo():
    drawing = shape() + shape(row=6)
    reader = XlsDrawingReader(biff(0xeb, store()) + biff(0xa))
    sheet = (biff(0xec, drawing[:30]) + biff(0x5d, b'object') +
             biff(0x3c, drawing[30:60]) + biff(0x1b6, bytes(18)) +
             biff(0x3c, drawing[60:]) + biff(0xa))
    assert len([e for e in reader.read_sheet(sheet, 'S') if isinstance(e, Image)]) == 2
    assert reader.errors == []


def test_xls_drawing_resumes_after_txo_text_and_runs():
    drawing = shape() + shape(row=6)
    txo = bytes(10) + struct.pack('<HHI', 4, 8, 0)
    reader = XlsDrawingReader(biff(0xeb, store()) + biff(0xa))
    sheet = (biff(0xec, drawing[:30]) + biff(0x1b6, txo) +
             biff(0x3c, b'\0text') + biff(0x3c, bytes(8)) +
             biff(0x3c, drawing[30:]) + biff(0xa))
    assert len([e for e in reader.read_sheet(sheet, 'S') if isinstance(e, Image)]) == 2
    assert reader.errors == []


def test_xls_reused_pib_exports_bytes_once_across_sheets(tmp_path, monkeypatch):
    from dochan.model.document import Document, Section
    from dochan.utils import image_export

    pixels = b'\x89PNG\r\n\x1a\n' + b'x' * 4096
    reader = XlsDrawingReader(biff(0xeb, store(pixels)) + biff(0xa))
    sections = [Section(elements=reader.read_sheet(
        biff(0xec, shape(row=9) + shape(row=1)) + biff(0xa), name))
        for name in ('First', 'Second')]
    document = Document(sections=sections)
    images = document.find_all('image')
    assert [(image.provenance.sheet, image.provenance.cell) for image in images] == [
        ('First', 'C2'), ('First', 'C10'), ('Second', 'C2'), ('Second', 'C10')]
    assert len(reader.assets) == 1
    assert all(image.filename == 'image1.png' for image in images)
    hashes = []
    original_sha256 = image_export.hashlib.sha256

    def counted_sha256(data):
        hashes.append(len(data))
        return original_sha256(data)

    monkeypatch.setattr(image_export.hashlib, 'sha256', counted_sha256)
    paths = image_export.export_images(document, str(tmp_path), 'pictures')
    assert len(paths) == 1
    assert (tmp_path / 'pictures-image-001.png').read_bytes() == pixels
    assert hashes == [len(pixels)]
    assert sum(image.has_data for image in images) == 1
