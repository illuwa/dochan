"""작은 XLS 가 같은 SST 문자열을 반복 참조해 출력이 폭증하는 경로를 막는다."""
import dochan.office_binary.xls as xls
from test_xls_reader import _bof, _boundsheet, _eof, _labelsst, _sst


def _workbook(globals_part, sheet_part):
    offset = len(globals_part) + len(_boundsheet(0, "Sheet1"))
    return globals_part + _boundsheet(offset, "Sheet1") + sheet_part


def _texts(doc):
    table = next(e for e in doc.sections[0].elements if hasattr(e, "rows"))
    return [cell.text for row in table.rows for cell in row]


def test_repeated_sst_string_output_is_bounded_with_warning(monkeypatch):
    monkeypatch.setattr(xls, "MIN_CELL_TEXT_CHARS", 20_000)
    sheet = _bof() + b"".join(_labelsst(row, 0, 0) for row in range(100)) + _labelsst(100, 0, 1) + _eof()
    data = _workbook(_bof() + _sst(["x" * 6_000, "tail"]), sheet)
    doc = xls.parse_biff_workbook(data)
    texts = _texts(doc)
    assert texts[0] == "x" * 6_000
    assert sum(map(len, texts)) <= max(20_000, 4 * len(data))
    assert "tail" not in texts
    warnings = [e for e in doc.errors if "cell text" in e]
    assert len(warnings) == 1 and warnings[0].startswith("WARN: XLS")


def test_xls_cell_text_budget_keeps_proportional_output(monkeypatch):
    monkeypatch.setattr(xls, "MIN_CELL_TEXT_CHARS", 1_000)
    strings = ["y%03d" % index * 40 for index in range(50)]
    sheet = _bof() + b"".join(_labelsst(row, 0, row) for row in range(50)) + _eof()
    doc = xls.parse_biff_workbook(_workbook(_bof() + _sst(strings), sheet))
    assert _texts(doc) == strings
    assert not any("cell text" in e for e in doc.errors)
