"""Delayed encrypted-PPT BLIPs may have a zero FBSE size hint."""
import struct

import pytest

from dochan.office_binary.officeart import Limits, parse_records, read_bstore


def _record(kind, body, options=0):
    return struct.pack('<HHI', options, kind, len(body)) + body


def _store(delay=0):
    fbse = struct.pack('<BB16sHIIIBBBB', 6, 6, b'u' * 16, 255,
                       0, 1, delay, 0, 0, 0, 0)
    return parse_records(_record(0xF001, _record(0xF007, fbse, 0x62), 15))


def test_bstore_zero_size_delayed_blip_uses_record_length():
    image = _record(0xF01E, b'u' * 16 + b'\xffpixels', 0x6E00)
    errors = []
    entries = read_bstore(_store(4), delayed_stream=b'pad!' + image, errors=errors)
    assert len(entries) == 1
    assert entries[0].size == 0
    assert entries[0].image == ('png', b'pixels')
    assert errors == []


@pytest.mark.parametrize('stream,limit', [
    (b'short', 100),
    (struct.pack('<HHI', 0x6E00, 0xF01E, 1000), 100),
    (_record(0xF01E, b'u' * 16 + b'\xffpixels', 0x6E00), 10),
])
def test_bstore_zero_size_delayed_blip_retains_bounds(stream, limit):
    errors = []
    entries = read_bstore(_store(), delayed_stream=stream,
                          limits=Limits(max_record_bytes=limit), errors=errors)
    assert entries[0].image is None
    assert errors
