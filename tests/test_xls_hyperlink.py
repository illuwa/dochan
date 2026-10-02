"""Synthetic MS-XLS HLink / MS-OSHARED Hyperlink structure tests."""
import struct

import pytest

from dochan.office_binary.xls_hyperlink import parse_hlink


_HLINK_GUID = bytes.fromhex('d0c9ea79f9bace118c8200aa004ba90b')


def _string(value):
    raw = (value + '\0').encode('utf-16le')
    return struct.pack('<I', len(raw) // 2) + raw


def _hlink(location, display='', frame=''):
    flags = 8 | (0x14 if display else 0) | (0x80 if frame else 0)
    return (struct.pack('<4H', 0, 0, 0, 0) + _HLINK_GUID
            + struct.pack('<II', 2, flags)
            + (_string(display) if display else b'')
            + (_string(frame) if frame else b'') + _string(location))


@pytest.mark.parametrize('location', ['Data!A1', "'Sales 2026'!$B$4", 'RevenueBookmark', '자료!A1'])
def test_hlink_internal_location_uses_xlsx_fragment_contract(location):
    link = parse_hlink(_hlink(location, 'Jump to Data'))
    assert link.target == '#' + location
    assert link.display == 'Jump to Data'


def test_hlink_internal_skips_optional_target_frame():
    link = parse_hlink(_hlink('Data!A1', '이동 😀', '_self'))
    assert (link.target, link.display) == ('#Data!A1', '이동 😀')


def test_hlink_internal_without_display():
    link = parse_hlink(_hlink('Bookmark'))
    assert (link.target, link.display) == ('#Bookmark', '')


@pytest.mark.parametrize('malformation', ['truncated', 'oversized', 'missing_terminator', 'invalid_unicode'])
def test_hlink_malformed_string_warns_without_raising(malformation):
    data = _hlink('Data!A1')
    if malformation == 'truncated':
        data = data[:-1]
    elif malformation == 'oversized':
        data = data[:32] + struct.pack('<I', 0xffffffff) + data[36:]
    elif malformation == 'missing_terminator':
        data = data[:-2] + b'XX'
    else:
        data = data[:36] + b'\0\xd8' + data[38:]
    errors = []
    assert parse_hlink(data, errors) is None
    assert len(errors) == 1 and errors[0].startswith('WARN: XLS hyperlink')


def test_hlink_unrecognized_legacy_payload_allows_existing_url_fallback():
    assert parse_hlink(b'\0' * 8 + 'https://example.com'.encode('utf-16le')) is None


def test_hlink_external_moniker_is_not_misread_as_internal_link():
    data = struct.pack('<4H', 0, 0, 0, 0) + _HLINK_GUID + struct.pack('<II', 2, 0x19)
    assert parse_hlink(data) is None


def _link_document(cell_record, location='Data!A1', display='Jump to Data'):
    from dochan.office_binary.xls import parse_biff_workbook
    def record(kind, data=b''):
        return struct.pack('<HH', kind, len(data)) + data
    bof = record(0x809, struct.pack('<HH', 0x600, 0x10))
    name = b'Links'
    boundsheet = record(0x85, struct.pack('<IBBBB', len(bof) + 12 + len(name), 0, 0, len(name), 0) + name)
    return parse_biff_workbook(bof + boundsheet + bof + cell_record + record(0x1b8, _hlink(location, display)) + record(10))


def test_xls_internal_hyperlink_populates_existing_blank_with_display():
    blank = struct.pack('<HHHHH', 0x201, 6, 0, 0, 0)
    doc = _link_document(blank)
    assert doc.sections[0].elements[0].rows[0][0].text == 'Jump to Data <#Data!A1>'


def test_xls_internal_hyperlink_preserves_existing_cell_text():
    text = b'Cell text'
    payload = struct.pack('<4HB', 0, 0, 0, len(text), 0) + text
    label = struct.pack('<HH', 0x204, len(payload)) + payload
    doc = _link_document(label)
    assert doc.sections[0].elements[0].rows[0][0].text == 'Cell text <#Data!A1>'
