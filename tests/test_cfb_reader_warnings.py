"""Container loss diagnostics reach document outputs, including lazy asset reads."""
import os
import struct
import zlib
from pathlib import Path

import pytest

from dochan import Dochan
from dochan.office_binary.doc import DOCReader
from dochan.office_binary.ppt import PPTReader
from dochan.office_binary.xls import XLSReader
from dochan.office_binary.ole_objects import decompress_ppt_storage
from test_cfb import END, FREE, change, compound, entry
from test_reader_magic_byte_fallback import _file_header_bytes, _para_section_bytes

PREFIX = 'WARN: OLE/CFB 컨테이너 손상 복구: '


def hwp_container(damage=None):
    """Version 4 CFB with two sections and two tiny image streams."""
    raw, _ = compound(4)
    raw = bytearray(raw)
    mini = bytearray(4096)
    links = [FREE] * 1024
    offset = 0

    def stream(name, payload, **kwargs):
        nonlocal offset
        count = (len(payload) + 63) // 64
        start = offset // 64 if count else END
        mini[offset:offset + len(payload)] = payload
        for sid in range(start, start + count) if count else ():
            links[sid] = sid + 1 if sid < start + count - 1 else END
        offset += count * 64
        return entry(name, 2, start, len(payload), **kwargs)

    records = [entry('Root Entry', 5, 3, 0, child=1),
               stream('FileHeader', _file_header_bytes(), right=2),
               stream('DocInfo', b'', right=3),
               entry('BodyText', 1, child=4, right=6),
               stream('Section0', _para_section_bytes('FIRST'), right=5),
               stream('Section1', _para_section_bytes('SECOND')),
               entry('BinData', 1, child=7),
               stream('BIN0001.png', b'image one', right=8),
               stream('BIN0002.png', b'image two')]
    struct.pack_into('<Q', records[0], 120, offset)
    if damage == 'section_name':
        struct.pack_into('<H', records[5], 64, 0)
    if damage == 'image_cycle':
        sid = struct.unpack_from('<I', records[7], 116)[0]
        links[sid] = sid
    if damage == 'image_crosslink':
        records[8][116:120] = records[7][116:120]
    raw[4096:8192] = b''.join(records).ljust(4096, b'\0')
    raw[12288:16384] = struct.pack('<1024I', *links)
    raw[16384:20480] = mini
    return bytes(raw)


def test_hwp_omitted_section_is_visible_in_document_errors(tmp_path):
    path = tmp_path / 'sections.hwp'
    path.write_bytes(hwp_container())
    intact = Dochan(str(path))
    assert 'FIRST' in intact.to_plain_text() and 'SECOND' in intact.to_plain_text()
    assert intact.errors == []
    path.write_bytes(hwp_container('section_name'))
    damaged = Dochan(str(path))
    assert 'FIRST' in damaged.to_plain_text() and 'SECOND' not in damaged.to_plain_text()
    assert any(error.startswith(PREFIX) for error in damaged.errors)
    assert any('invalid directory entry omitted' in error for error in damaged.errors)


@pytest.mark.parametrize('damage', ['image_cycle', 'image_crosslink'])
def test_hwp_bindata_loss_is_visible_in_document_errors(tmp_path, damage):
    path = tmp_path / 'assets.hwp'
    path.write_bytes(hwp_container(damage))
    reader = Dochan(str(path))
    assert 'FIRST' in reader.to_plain_text() and 'SECOND' in reader.to_plain_text()
    assert any(error.startswith(PREFIX) and 'BinData/' in error for error in reader.errors)


@pytest.mark.parametrize('reader,name', [(DOCReader, 'WordDocument'),
                                        (PPTReader, 'PowerPoint Document'),
                                        (XLSReader, 'Workbook')])
@pytest.mark.parametrize('damage', ['directory', 'payload', 'missing_required'])
def test_legacy_reader_recovery_warnings_survive_document_replacement(tmp_path, reader, name, damage):
    raw, _ = compound()
    raw = bytearray(raw)
    raw[512 + 3 * 128:1024] = entry(name, 2, 4, 4096)
    if damage in ('directory', 'missing_required'):
        index = 2 if damage == 'directory' else 3
        struct.pack_into('<H', raw, 512 + index * 128 + 64, 0)
    else:
        raw = raw[:-20]
    path = tmp_path / ('synthetic.' + reader.format_name)
    path.write_bytes(raw)
    doc = reader().read(str(path))
    warnings = [error for error in doc.errors if error.startswith(PREFIX)]
    assert warnings
    assert len(warnings) == len(set(warnings))


def test_format_detection_retains_recovery_when_required_stream_is_omitted(tmp_path):
    raw, _ = compound()
    path = tmp_path / 'unrecognized.doc'
    path.write_bytes(change(raw, 512 + 2 * 128 + 64, 0, '<H'))
    doc = Dochan(str(path))
    assert any(error.startswith(PREFIX) for error in doc.errors)


def test_ppt_incomplete_zlib_allows_metadata_only_cfb_deviation():
    raw, _ = compound()
    # A FAT sector's non-addressing self marker is FREESECT instead of FATSECT.
    raw = change(raw, 1024 + 4, FREE)
    errors = []
    compressed = struct.pack('<I', len(raw)) + zlib.compress(raw)[:-4]
    assert decompress_ppt_storage(compressed, 1, errors) == raw
    assert any('compression framing anomaly' in error for error in errors)


@pytest.mark.parametrize('name,percent', [('tdf168786.ppt', 97), ('41071.ppt', 90),
                                         ('tdf168736-1.ppt', 90), ('tdf105150.ppt', 60)])
def test_real_truncated_ppt_retains_container_loss_warning(tmp_path, name, percent):
    root = os.environ.get('DOCHAN_CORPUS_ROOT')
    if root is None:
        pytest.skip('DOCHAN_CORPUS_ROOT is required for optional public corpus regression')
    subdir = ('poi-src/test-data/slideshow' if name == '41071.ppt' else
              'lo-src/sd/qa/unit/data/ppt')
    source = Path(root) / subdir / name
    if not source.is_file():
        pytest.skip('optional public Office sample is not present')
    raw = source.read_bytes()
    path = tmp_path / name
    path.write_bytes(raw[:len(raw) * percent // 100])
    doc = Dochan(str(path))
    assert any(error.startswith(PREFIX) for error in doc.errors)


def test_ppt_incomplete_zlib_rejects_truncated_cfb_payload():
    raw, _ = compound()
    raw = raw[:-20]
    compressed = struct.pack('<I', len(raw)) + zlib.compress(raw)[:-4]
    with pytest.raises(ValueError, match='incomplete compression'):
        decompress_ppt_storage(compressed, 1)
