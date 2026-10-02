"""Regression cases for tolerant PPT storage and targeted OLE fallback."""
import struct
import zlib

import pytest

from dochan.office_binary.ole_objects import decompress_ppt_storage
from dochan.office_binary.officeart import parse_records
from dochan.office_binary.ppt import parse_ppt_document_stream
from test_ole_objects import compound
from test_ppt_structure import record, presentation, slide_list, shape, sheet


def object_document(progid, storage, instance=0, preview=b''):
    base = parse_records(shape(preview))[0]
    ref = record(0xF004, bytes(base.data) + record(0xF011, record(3009, struct.pack('<I', 77))), container=True)
    embed = record(4035, struct.pack('<6I', 1, 0, 77, 0, 3, 0))
    embed += record(4026, progid.encode('utf-16le'), instance=2)
    data, current = presentation([(2, sheet(shapes=ref)), (3, record(4113, storage, instance=instance))],
                                 [slide_list([(2, 256, b'')]), record(1033, embed, container=True)])
    return parse_ppt_document_stream(data, current_user=current)


@pytest.mark.parametrize('suffix', ['missing_checksum', 'trailing_byte'])
def test_complete_cfb_with_zlib_anomaly_is_accepted_with_warning(suffix):
    raw = compound('Package', b'content')
    compressed = zlib.compress(raw)
    compressed = compressed[:-1] if suffix == 'missing_checksum' else compressed + b'\0'
    assert decompress_ppt_storage(struct.pack('<I', len(raw)) + compressed, 1) == raw
    errors = []
    assert decompress_ppt_storage(struct.pack('<I', len(raw)) + compressed, 1, errors) == raw
    assert errors and 'compression' in errors[0]


def test_zlib_anomaly_does_not_accept_non_cfb_payload():
    raw = b'not compound'
    with pytest.raises(ValueError):
        decompress_ppt_storage(struct.pack('<I', len(raw)) + zlib.compress(raw)[:-1], 1, [])


@pytest.mark.parametrize('progid', ['Package', 'MS_ClipArt_Gallery.5', 'Word.Document.12'])
def test_unrelated_object_does_not_add_warning_or_placeholder(progid):
    doc = object_document(progid, b'corrupt storage')
    assert not doc.errors
    assert not doc.find_all('paragraph')


def test_supported_object_failure_preserves_existing_preview():
    doc = object_document('Equation.3', b'corrupt storage', preview=b'Equation preview')
    assert [p.text for p in doc.find_all('paragraph')] == ['Equation preview']
    assert doc.errors and all(e.startswith('WARN:') for e in doc.errors)


def test_supported_object_without_preview_has_fallback_marker():
    doc = object_document('Equation.3', b'corrupt storage')
    assert [p.text for p in doc.find_all('paragraph')] == ['[내장 개체]']
    assert doc.errors
