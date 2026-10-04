"""합성 입력으로 메모 독립 정답지의 연결·순서·안전 경계를 검사한다."""
import builtins
import struct
import zipfile

import pytest

from scripts.comment_probe_common import compare, xml
from scripts.probe_presentation_comments import ppt_oracle_stream, pptx_oracle
from scripts.probe_xls_comment_cells import xls_oracle_stream
from test_ppt_structure import presentation, record, slide_list
from test_xls_notes import _note, _obj, _record, _txo, _workbook


def comment(author, body, index=1):
    atom = record(12001, struct.pack('<I8Hii', index, 2026, 10, 0, 4, 12, 0, 0, 0, 20, 30))
    cm = record(12000, record(4026, author.encode('utf-16le')) +
                record(4026, body.encode('utf-16le'), instance=1) +
                record(4026, b'A\0', instance=2) + atom, container=True)
    return record(5000, record(5002, record(4026, '___PPT10'.encode('utf-16le')) +
                              record(5003, cm), container=True), container=True)


def test_ppt_comment_oracle_latest_save_and_slide_order_without_product(monkeypatch):
    slides = [(2, record(1006, comment('Old', 'obsolete'), container=True)),
              (3, record(1006, comment('Second', 'two'), container=True))]
    data, current = presentation(slides, [slide_list([(3, 257, b''), (2, 256, b'')])],
                                 previous=(2, record(1006, comment('New', 'one\r\nline'), container=True)))
    original = builtins.__import__

    def reject_product(name, *args, **kwargs):
        if name == 'dochan' or name.startswith('dochan.'):
            raise AssertionError('product imported by oracle')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', reject_product)
    rows = ppt_oracle_stream(data, current)
    assert rows['historical_count'] == 3
    assert [(c['slide'], c['author'], c['body']) for c in rows['comments']] == [
        (1, 'Second', 'two'), (2, 'New', 'one\nline')]
    assert rows['comments'][1]['position'] == [20, 30]
    assert rows['comments'][1]['system_time'] == [2026, 10, 0, 4, 12, 0, 0, 0]
    assert rows['comments'][1]['initials'] == 'A'


def test_ppt_comment_oracle_skips_roundtrip_zip_payload():
    opaque = record(1064, b'PK\x03\x04' + b'opaque ZIP bytes', container=True)
    slide = record(1006, comment('A', 'body'), container=True)
    data, current = presentation([(2, slide)], [opaque, slide_list([(2, 256, b'')])])
    assert ppt_oracle_stream(data, current)['comments'][0]['body'] == 'body'


def pptx_parts():
    p = 'http://schemas.openxmlformats.org/presentationml/2006/main'
    r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    rel = 'http://schemas.openxmlformats.org/package/2006/relationships'
    return {
        'ppt/presentation.xml': '<p:presentation xmlns:p="%s" xmlns:r="%s"><p:sldIdLst><p:sldId r:id="second"/><p:sldId r:id="first"/></p:sldIdLst></p:presentation>' % (p, r),
        'ppt/_rels/presentation.xml.rels': '<Relationships xmlns="%s"><Relationship Id="first" Type="%s/slide" Target="slides/slide1.xml"/><Relationship Id="second" Type="%s/slide" Target="slides/slide2.xml"/></Relationships>' % (rel, r, r),
        'ppt/slides/slide1.xml': '<p:sld xmlns:p="%s"><p:cSld><p:spTree/></p:cSld></p:sld>' % p,
        'ppt/slides/slide2.xml': '<p:sld xmlns:p="%s"><p:cSld><p:spTree/></p:cSld></p:sld>' % p,
        'ppt/slides/_rels/slide1.xml.rels': '<Relationships xmlns="%s"><Relationship Id="c" Type="%s/comments" Target="../comments/b.xml"/></Relationships>' % (rel, r),
        'ppt/slides/_rels/slide2.xml.rels': '<Relationships xmlns="%s"><Relationship Id="c" Type="%s/comments" Target="../comments/a.xml"/></Relationships>' % (rel, r),
        'ppt/commentAuthors.xml': '<p:cmAuthorLst xmlns:p="%s"><p:cmAuthor id="7" name="First author"/><p:cmAuthor id="42" name="Second author"/></p:cmAuthorLst>' % p,
        'ppt/comments/a.xml': '<p:cmLst xmlns:p="%s"><p:cm authorId="42" idx="2"><p:pos x="5" y="6"/><p:text>two&#10;lines</p:text></p:cm><p:cm authorId="7" idx="1"><p:text>third ] text</p:text></p:cm></p:cmLst>' % p,
        'ppt/comments/b.xml': '<p:cmLst xmlns:p="%s"><p:cm authorId="7" idx="5"><p:text>last</p:text></p:cm></p:cmLst>' % p,
    }


def write_pptx(path, parts):
    with zipfile.ZipFile(path, 'w') as package:
        for name, body in parts.items():
            package.writestr(name, body)


def test_pptx_comment_oracle_and_product_keep_slide_and_comment_order(tmp_path):
    from dochan.ooxml.pptx import PPTXReader
    path = tmp_path / 'synthetic.pptx'
    write_pptx(path, pptx_parts())
    expected = pptx_oracle(path)['comments']
    doc = PPTXReader().read(str(path))
    actual = [{'slide': p.provenance.slide, 'annotation': p.text}
              for p in doc.find_all('paragraph')]
    assert [(c['slide'], c['author'], c['body']) for c in expected] == [
        (1, 'Second author', 'two\nlines'), (1, 'First author', 'third ] text'),
        (2, 'First author', 'last')]
    assert compare(expected, actual, ('slide', 'annotation'))['exact']


def test_xls_oracle_joins_ids_and_orders_cells_with_split_surrogates():
    emoji = '😀'.encode('utf-16le')
    sheet = (_record(0x0809, struct.pack('<HH', 0x0600, 0x0010)) +
             _obj(2) + _txo(4, b'\0late') + _obj(1) +
             _txo(2, b'\1' + emoji[:2], b'\1' + emoji[2:]) +
             _note(4, 2, 2, 'B') + _note(1, 0, 1, 'A', hidden=True) + _record(0x000A))
    rows = xls_oracle_stream(_workbook(sheet))['comments']
    assert [(c['cell'], c['record_order'], c['body']) for c in rows] == [('A2', 2, '😀'), ('C5', 1, 'late')]
    assert rows[0]['hidden']


@pytest.mark.parametrize('field,value', [('slide', 2), ('annotation', '[comment: wrong]')])
def test_comment_comparison_detects_position_and_text_mutation(field, value):
    expected = [{'slide': 1, 'annotation': '[comment: A: text]'}]
    actual = [dict(expected[0], **{field: value})]
    assert not compare(expected, actual, ('slide', 'annotation'))['exact']


@pytest.mark.parametrize('payload', [b'<!DOCTYPE a><a/>', b'<!ENTITY x "text"><a/>',
                                     '<!DOCTYPE a><a/>'.encode('utf-16'),
                                     b'<a>' * 129 + b'</a>' * 129])
def test_comment_oracle_rejects_dtd_entities_and_excess_depth(payload):
    with pytest.raises(ValueError):
        xml(payload)
