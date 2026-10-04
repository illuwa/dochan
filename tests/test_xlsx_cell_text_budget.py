"""작은 XLSX 가 같은 공유 문자열을 반복 참조해 출력이 폭증하는 경로를 막는다."""
import pytest

import dochan.ooxml.xlsx as xlsx_module
from dochan.ooxml.xlsx import XLSXReader
from test_xlsx_reader import _write_xlsx

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
WORKBOOK = (f'<workbook xmlns="{NS}" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>')


def _amplifying_xlsx(path, text_chars, cells):
    shared = f'<sst xmlns="{NS}"><si><t>{"x" * text_chars}</t></si><si><t>tail</t></si></sst>'
    rows = "".join(f'<row r="{row}"><c r="A{row}" t="s"><v>0</v></c></row>' for row in range(1, cells + 1))
    rows += f'<row r="{cells + 1}"><c r="A{cells + 1}" t="s"><v>1</v></c></row>'
    sheet = f'<worksheet xmlns="{NS}"><sheetData>{rows}</sheetData></worksheet>'
    _write_xlsx(path, WORKBOOK, {"xl/worksheets/sheet1.xml": sheet}, shared_strings_xml=shared)


def _cell_texts(doc):
    return [row[0].text for table in doc.find_all("table") for row in table.rows]


@pytest.mark.parametrize("streaming", [False, True])
def test_repeated_shared_string_output_is_bounded_with_warning(tmp_path, monkeypatch, streaming):
    monkeypatch.setattr(xlsx_module, "MIN_CELL_TEXT_CHARS", 30_000)
    if streaming:
        monkeypatch.setattr(xlsx_module, "MAX_XML_PART_SIZE", 1)
    path = tmp_path / "amplify.xlsx"
    _amplifying_xlsx(path, 10_000, 50)  # 500,000 characters from ~12 KB of XML
    doc = XLSXReader().read(str(path))
    texts = _cell_texts(doc)
    assert sum(map(len, texts)) <= max(30_000, 4 * 15_000)
    assert texts[0] == "x" * 10_000
    assert "tail" not in texts  # cells after the budget are empty (and trailing empty rows trimmed)
    warnings = [e for e in doc.errors if "cell text" in e]
    assert len(warnings) == 1 and warnings[0].startswith("WARN: XLSX")


def test_cell_text_budget_scales_with_input_size(tmp_path, monkeypatch):
    monkeypatch.setattr(xlsx_module, "MIN_CELL_TEXT_CHARS", 1_000)
    path = tmp_path / "plain.xlsx"
    # Distinct inline strings: output is proportional to input, so nothing is cut.
    rows = "".join(f'<row r="{row}"><c r="A{row}" t="inlineStr"><is><t>{"y" * 200}</t></is></c></row>'
                   for row in range(1, 101))
    _write_xlsx(path, WORKBOOK, {"xl/worksheets/sheet1.xml":
                                 f'<worksheet xmlns="{NS}"><sheetData>{rows}</sheetData></worksheet>'})
    doc = XLSXReader().read(str(path))
    assert sum(map(len, _cell_texts(doc))) == 20_000
    assert not any("cell text" in e for e in doc.errors)
