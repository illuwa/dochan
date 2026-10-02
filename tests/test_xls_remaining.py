"""BIFF regression fixtures built from record bytes, without a corpus dependency."""
import struct

import pytest

from dochan.office_binary.xls import _decode_rk, parse_biff_workbook


def record(kind, data=b""):
    return struct.pack("<HH", kind, len(data)) + data


def font(bold=False, italic=False):
    return record(0x31, struct.pack("<HHHHHBBBB", 200, 2 if italic else 0,
                                  0, 700 if bold else 400, 0, 0, 0, 0, 0))


def workbook(globals_, sheet):
    bof = record(0x809, struct.pack("<HH", 0x600, 5))
    bounds = record(0x85, struct.pack("<IBBBB", 0, 0, 0, 1, 0) + b"S")
    offset = len(bof + globals_ + bounds + record(0xA))
    bounds = record(0x85, struct.pack("<IBBBB", offset, 0, 0, 1, 0) + b"S")
    return bof + globals_ + bounds + record(0xA) + record(0x809, struct.pack("<HH", 0x600, 0x10)) + sheet + record(0xA)


@pytest.mark.parametrize("raw, expected", [(0x3FF00000, 1.0), (0xC0040000, -2.5),
    (0x40590001, 1.0), ((-123 & 0x3FFFFFFF) << 2 | 3, -1.23)])
def test_rk_high_ieee_word_and_signed_scaled_integer(raw, expected):
    assert _decode_rk(raw) == expected


def test_colinfo_256_is_end_sentinel_not_a_cell():
    doc = parse_biff_workbook(workbook(b"", record(0x208, b"\0\0") + record(0x7D, struct.pack("<HH", 0, 256))))
    assert not doc.errors
    assert not doc.sections[0].elements  # Formatting alone is not a used range.


@pytest.mark.parametrize("kind", ["sst", "rstring"])
def test_rich_runs_use_font_indices_and_default_prefix(kind):
    globals_ = font() + font(bold=True) + font(italic=True)
    text = b"plainBoldItalic"
    runs = struct.pack("<HHHH", 5, 1, 9, 2)
    if kind == "sst":
        rich = struct.pack("<HBH", len(text), 8, 2) + text + runs
        globals_ += record(0xFC, struct.pack("<II", 1, 1) + rich)
        cell = record(0xFD, struct.pack("<HHHI", 0, 0, 0, 0))
    else:
        cell = record(0xD6, struct.pack("<HHHHB", 0, 0, 0, len(text), 0)
                      + text + struct.pack("<H", 2) + runs)
    doc = parse_biff_workbook(workbook(globals_, cell))
    actual = doc.sections[0].elements[0].rows[0][0].paragraphs[0].runs
    assert [(r.text, r.bold, r.italic) for r in actual] == [
        ("plain", False, False), ("Bold", True, False), ("Italic", False, True)]


def test_sst_rich_runs_continue_and_utf16_indices():
    # Character offsets count UTF-16 code units, not Python code points.
    text = "😀Bold"
    encoded = text.encode("utf-16le")
    rich = struct.pack("<HBH", len(encoded) // 2, 9, 1) + encoded
    globals_ = font() + font(bold=True)
    globals_ += record(0xFC, struct.pack("<II", 1, 1) + rich)
    globals_ += record(0x3C, struct.pack("<HH", 2, 1))
    doc = parse_biff_workbook(workbook(globals_, record(0xFD, struct.pack("<HHHI", 0, 0, 0, 0))))
    runs = doc.sections[0].elements[0].rows[0][0].paragraphs[0].runs
    assert [(r.text, r.bold) for r in runs] == [("😀", False), ("Bold", True)]


def test_rich_invalid_run_warns_and_keeps_text():
    globals_ = font() + record(0xFC, struct.pack("<IIHBH", 1, 1, 3, 8, 1)
                              + b"abc" + struct.pack("<HH", 20, 9))
    doc = parse_biff_workbook(workbook(globals_, record(0xFD, struct.pack("<HHHI", 0, 0, 0, 0))))
    assert doc.sections[0].elements[0].rows[0][0].text == "abc"
    assert any("rich text" in e for e in doc.errors)


def test_chart_cache_does_not_overwrite_worksheet_cell():
    def number(value):
        return record(0x203, struct.pack("<HHHd", 0, 0, 0, value))
    chart = record(0x809, struct.pack("<HH", 0x600, 0x20)) + number(999) + record(0xA)
    doc = parse_biff_workbook(workbook(b"", number(42) + chart))
    assert doc.sections[0].elements[0].rows[0][0].text == "42"


def test_colinfo_end_sentinel_does_not_spend_cell_budget(monkeypatch):
    import dochan.office_binary.xls as xls
    monkeypatch.setattr(xls, 'MAX_WORKBOOK_CELLS', 30)
    sheet = record(0x7D, struct.pack('<HH', 1, 256))
    sheet += b''.join(record(0x203, struct.pack('<HHHd', row, 0, 0, row + 1))
                      for row in range(6))
    doc = parse_biff_workbook(workbook(b'', sheet))
    table = doc.sections[0].elements[0]
    assert len(table.rows) == 6
    assert table.rows[5][0].text == '6'
    assert not doc.errors
