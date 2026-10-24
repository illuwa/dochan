"""A restored ZIP must preserve content-based format detection."""
from io import BytesIO
import zipfile
import struct
import zlib

from dochan import Dochan
from dochan.utils.zip_salvage import ZipSalvageError, open_document_zip
import pytest


def test_truncated_docx_with_hwp_extension_restores_text(tmp_path):
    stream = BytesIO()
    entries = {
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>',
        'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>Recovered text</w:t></w:r></w:p></w:body></w:document>',
        'word/_rels/document.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
    }
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        cutoff = archive.fp.tell()
    path = tmp_path / 'mislabelled.hwp'
    path.write_bytes(stream.getvalue()[:cutoff])
    reader = Dochan(str(path))
    assert reader.to_markdown() == 'Recovered text'
    assert reader.doc.source_format == 'docx'
    assert not any(error.startswith('ERR:') for error in reader.errors)
    assert any(error.startswith('WARN: ZIP 중앙 디렉터리') for error in reader.errors)


def test_hwpx_missing_referenced_chart_is_fatal():
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('mimetype', 'application/hwp+zip')
        archive.writestr('Contents/header.xml', '<head secCnt="1"/>')
        archive.writestr('Contents/section0.xml', '<sec><chart chartIDRef="Chart/chart1.xml"/></sec>')
        cutoff = archive.fp.tell()
    with pytest.raises(ZipSalvageError, match='Chart/chart1.xml'):
        open_document_zip(BytesIO(stream.getvalue()[:cutoff]), [], kind='hwpx')


def test_hwpx_declared_content_manifest_is_required():
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('mimetype', 'application/hwp+zip')
        archive.writestr('META-INF/container.xml', '<container><rootfile full-path="Contents/content.hpf"/></container>')
        archive.writestr('Contents/header.xml', '<head secCnt="1"/>')
        archive.writestr('Contents/section0.xml', '<sec/>')
        cutoff = archive.fp.tell()
    with pytest.raises(ZipSalvageError, match='Contents/content.hpf'):
        open_document_zip(BytesIO(stream.getvalue()[:cutoff]), [], kind='hwpx')


def test_xlsx_vml_relationship_part_is_required():
    from test_zip_salvage import _xlsx_parts, _rels, _zip, _without_directory

    parts = _xlsx_parts()
    parts['xl/worksheets/_rels/sheet1.xml.rels'] = _rels([('vmlDrawing', '../drawings/vml1.vml', False)])
    parts['xl/drawings/vml1.vml'] = '<xml xmlns:o="urn:schemas-microsoft-com:office:office"><image o:relid="rImage"/></xml>'
    with pytest.raises(ZipSalvageError, match='vml1.vml.rels'):
        open_document_zip(BytesIO(_without_directory(_zip(parts))), [], kind='ooxml')


def test_required_deflate_stream_must_reach_eof_not_just_declared_size():
    from test_zip_salvage import _docx_parts, _local

    parts = _docx_parts()
    records = []
    for name, text in parts.items():
        payload = text.encode()
        if name != 'word/document.xml':
            records.append(_local(name, payload))
            continue
        compressor = zlib.compressobj(wbits=-15)
        encoded = (compressor.compress(payload) + compressor.flush())[:-1]
        name_bytes = name.encode()
        records.append(struct.pack('<4s5H3I2H', b'PK\x03\x04', 20, 0, 8, 0, 0,
                                   zlib.crc32(payload), len(encoded), len(payload), len(name_bytes), 0)
                       + name_bytes + encoded)
    with pytest.raises(ZipSalvageError, match='deflate'):
        open_document_zip(BytesIO(b''.join(records)), [], kind='ooxml')


def test_required_deflate_may_not_hide_bytes_after_declared_length():
    from test_zip_salvage import _docx_parts, _local

    records = []
    for name, text in _docx_parts().items():
        payload = text.encode()
        records.append(_local(name, payload + b' ' * 1000, method=8,
                              declared_size=len(payload), crc=zlib.crc32(payload))
                       if name == 'word/document.xml' else _local(name, payload))
    with pytest.raises(ZipSalvageError, match='deflate decoded size mismatch'):
        open_document_zip(BytesIO(b''.join(records)), [], kind='ooxml')


@pytest.mark.parametrize('signature', [False, True])
def test_stored_descriptor_with_known_size_is_verified(signature):
    from test_zip_salvage import _local
    from dochan.utils.zip_salvage import salvage_zip

    payload = b'stored descriptor body'
    data = _local('part.xml', payload, flags=8)
    data += (b'PK\x07\x08' if signature else b'')
    data += struct.pack('<III', zlib.crc32(payload), len(payload), len(payload))
    with zipfile.ZipFile(BytesIO(salvage_zip(data))) as archive:
        assert archive.read('part.xml') == payload


def test_missing_ooxml_tag_properties_are_optional():
    from test_zip_salvage import _pptx_parts, _rels, _zip, _without_directory

    parts = _pptx_parts()
    parts['ppt/_rels/presentation.xml.rels'] = _rels([
        ('slide', 'slides/slide1.xml', False), ('tags', 'tags/tag1.xml', False),
        ('presProps', 'presProps.xml', False), ('viewProps', 'viewProps.xml', False),
    ])
    with open_document_zip(BytesIO(_without_directory(_zip(parts))), [], kind='ooxml') as archive:
        assert archive.read('ppt/slides/slide1.xml')


def test_unrecognized_relationship_uri_cannot_claim_optional_image_type():
    from test_zip_salvage import _docx_parts, _zip, _without_directory

    parts = _docx_parts([('image', 'required.xml', False)])
    rels = 'word/_rels/document.xml.rels'
    parts[rels] = parts[rels].replace(
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image',
        'urn:untrusted/image')
    with pytest.raises(ZipSalvageError, match='required.xml'):
        open_document_zip(BytesIO(_without_directory(_zip(parts))), [], kind='ooxml')


@pytest.mark.parametrize('prefix,spacing', [('관계', ' '), ('r', ' ' * 66000)],
                         ids=['unicode-prefix', 'long-space'])
def test_leaf_relationship_detection_handles_unicode_prefix_and_long_whitespace(prefix, spacing):
    from test_zip_salvage import _pptx_parts, _zip, _without_directory

    parts = _pptx_parts()
    parts['ppt/slides/slide1.xml'] = (
        '<slide xmlns:%s="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<image %s:embed%s="rImage"/></slide>' % (prefix, prefix, spacing))
    with pytest.raises(ZipSalvageError, match='slide1.xml.rels'):
        open_document_zip(BytesIO(_without_directory(_zip(parts))), [], kind='ooxml')
