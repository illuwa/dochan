"""HWPX ID references and table fallback regressions."""

from io import BytesIO
from pathlib import Path
import zipfile

import pytest

import dochan.hwpx.parser as hwpx_module
from dochan.hwpx.parser import HWPXParser
from dochan.model.table import Cell, Table


_NS = (
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"'
)


def _hwpx(body, header=None) -> BytesIO:
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", f"<hs:sec {_NS}>{body}</hs:sec>")
        if header is not None:
            zf.writestr("Contents/header.xml", f"<hh:head {_NS}>{header}</hh:head>")
    archive.seek(0)
    return archive


def _para(body, char_pr="0"):
    return f'<hp:p><hp:run charPrIDRef="{char_pr}">{body}</hp:run></hp:p>'


def test_parse_accepts_paths_and_binary_streams(tmp_path: Path):
    archive = _hwpx(_para("<hp:t>content</hp:t>"))
    path = tmp_path / "document.hwpx"
    path.write_bytes(archive.getvalue())

    with path.open("rb") as stream:
        for source in (str(path), path, archive, stream):
            document = HWPXParser().parse(source)
            assert document.errors == []
            assert document.sections[0].elements[0].text == "content"
        assert not stream.closed
    assert not archive.closed


def test_build_grid_returns_cells_and_preserves_anchors():
    merged = Cell(row_span=2, col_span=2)
    later = Cell()
    anchors = [
        (0, 0, 2, 2, merged),
        (1, 1, 1, 1, later),
        (0, 0, 1, 1, Cell()),  # Duplicate anchor.
        (2, 0, 1, 1, Cell()),  # Outside the declared grid.
    ]
    rows, dropped = hwpx_module._build_grid(anchors, 2, 3)
    table = Table(rows=rows)

    assert dropped == 2
    assert (table.row_count, table.col_count) == (2, 3)
    assert rows[0][0] is merged
    assert rows[1][1] is later
    assert rows[0][1].is_merged_away
    assert rows[1][0].is_merged_away
    assert not rows[0][2].is_merged_away
    assert not rows[1][2].is_merged_away
    assert len({id(cell) for row in rows for cell in row}) == 6
    assert all(isinstance(cell, Cell) and (cell.row, cell.col) == (r, c)
               for r, row in enumerate(rows) for c, cell in enumerate(row))


@pytest.mark.parametrize(
    "first_id, second_id",
    [(1, 0), (41, 7), (10**12, 7)],
    ids=["reversed", "sparse", "large-sparse"],
)
def test_char_pr_references_use_ids_and_preserve_document_list(first_id, second_id):
    header = (
        f'<hh:charPr id="{first_id}" height="2600"><hh:bold/></hh:charPr>'
        f'<hh:charPr id="{second_id}" height="2400">'
        '<hh:italic/><hh:underline type="BOTTOM"/>'
        '<hh:strikeout shape="SOLID"/></hh:charPr>'
    )
    document = HWPXParser().parse(_hwpx(
        _para("<hp:t>second</hp:t>", second_id)
        + _para("<hp:t>first</hp:t>", first_id),
        header,
    ))

    assert document.errors == []
    second, first = [paragraph.runs[0] for paragraph in document.sections[0].elements]
    assert (second.font_size_pt, second.bold, second.italic,
            second.underline, second.strikeout) == (24.0, False, True, True, True)
    assert (first.font_size_pt, first.bold, first.italic,
            first.underline, first.strikeout) == (26.0, True, False, False, False)
    # Public metadata stays a compact list in XML order, even for sparse IDs.
    assert isinstance(document.char_shapes, list)
    assert document.metadata["char_shapes"] == 2
    assert [entry.size_pt for entry in document.char_shapes] == [26.0, 24.0]
    assert [entry.underline_type for entry in document.char_shapes] == [0, 1]


@pytest.mark.parametrize("reference", ["0", "1", "999", "-1", "invalid", ""])
def test_unknown_char_pr_reference_keeps_default_formatting(reference):
    document = HWPXParser().parse(_hwpx(
        _para("<hp:t>default</hp:t>", reference),
        '<hh:charPr id="41" height="2600"><hh:bold/></hh:charPr>'
        '<hh:charPr id="7" height="2400"><hh:italic/></hh:charPr>',
    ))

    assert document.errors == []
    run = document.sections[0].elements[0].runs[0]
    assert (run.font_size_pt, run.bold, run.italic,
            run.underline, run.strikeout) == (10.0, False, False, False, False)


def test_char_pr_lookup_resets_between_documents():
    parser = HWPXParser()
    first = parser.parse(_hwpx(
        _para("<hp:t>styled</hp:t>", "41"),
        '<hh:charPr id="41" height="2400"><hh:bold/></hh:charPr>',
    ))
    second = parser.parse(_hwpx(_para("<hp:t>default</hp:t>", "41")))

    assert first.errors == second.errors == []
    assert first.sections[0].elements[0].runs[0].bold is True
    run = second.sections[0].elements[0].runs[0]
    assert (run.font_size_pt, run.bold) == (10.0, False)
    assert second.char_shapes == []


def _note(text, tag="footNote"):
    return (
        f'<hp:ctrl><hp:{tag}><hp:subList>'
        + _para(f"<hp:t>{text}</hp:t>")
        + f'</hp:subList></hp:{tag}></hp:ctrl>'
    )


def _cell(body, address=""):
    return f"<hp:tc>{address}<hp:subList>{_para(body)}</hp:subList></hp:tc>"


def _table(rows, attributes=""):
    return f"<hp:tbl {attributes}>{rows}</hp:tbl>"


@pytest.mark.parametrize(
    "fallback",
    ["missing-coordinates", "invalid-coordinate", "missing-dimensions",
     "grid-limit", "document-limit"],
)
def test_fallback_parses_each_cell_once_and_preserves_rows(fallback, monkeypatch):
    addresses = [
        '<hp:cellAddr rowAddr="0" colAddr="0"/>',
        '<hp:cellAddr rowAddr="0" colAddr="1"/>',
        '<hp:cellAddr rowAddr="2" colAddr="0"/>',
    ]
    attributes = 'rowCnt="3" colCnt="2"'
    if fallback == "missing-coordinates":
        addresses = ["", "", ""]
    elif fallback == "invalid-coordinate":
        addresses[1] = '<hp:cellAddr rowAddr="0" colAddr="-1"/>'
    elif fallback == "missing-dimensions":
        attributes = ""
    elif fallback == "grid-limit":
        monkeypatch.setattr(hwpx_module, "MAX_TABLE_CELLS", 3)
    elif fallback == "document-limit":
        monkeypatch.setattr(hwpx_module, "MAX_DOCUMENT_CELLS", 5)

    parser = HWPXParser()
    parsed_cells = []
    parse_cell = parser._parse_table_cell

    def track_cell(elem):
        parsed_cells.append(elem)
        return parse_cell(elem)

    monkeypatch.setattr(parser, "_parse_table_cell", track_cell)
    cells = [_cell(f"<hp:t>{text}</hp:t>", address)
             for text, address in zip("ABC", addresses)]
    caption = '<hp:caption side="TOP"><hp:subList>' + _para(
        "<hp:t>caption</hp:t>"
    ) + '</hp:subList></hp:caption>'
    document = parser.parse(_hwpx(_para(_table(
        caption + f"<hp:tr>{cells[0]}{cells[1]}</hp:tr>"
        f"<hp:tr/><hp:tr>{cells[2]}</hp:tr>",
        attributes,
    ))))

    assert len(parsed_cells) == 3
    table = document.sections[0].elements[0]
    assert [[cell.text for cell in row] for row in table.rows] == [["A", "B"], [], ["C"]]
    assert (table.caption_text, table.caption_side) == ("caption", "TOP")
    assert parser._table_cells_remaining == hwpx_module.MAX_TABLE_CELLS - 3
    if fallback == "grid-limit":
        assert document.errors == ["표 크기 초과: 3x2"]
    elif fallback == "document-limit":
        assert document.errors == ["문서 셀 예산 초과 — 표 3x2 를 좌표 배치하지 않음"]
    else:
        assert document.errors == []


def test_coordinate_free_table_notes_are_numbered_once():
    table = _table(
        "<hp:tr>" + _cell("<hp:t>A</hp:t>" + _note("first")) + "</hp:tr>"
        "<hp:tr>" + _cell("<hp:t>B</hp:t>" + _note("second", "endNote")) + "</hp:tr>"
    )
    document = HWPXParser().parse(_hwpx(
        _para(table) + _para("<hp:t>C</hp:t>" + _note("third"))
    ))

    assert document.errors == []
    assert [(note.number, note.text) for note in document.find_all("note")] == [
        (1, "first"), (2, "second"), (3, "third"),
    ]
    assert [run.note_ref for paragraph in document.find_all("paragraph")
            for run in paragraph.runs if run.note_ref] == [1, 2, 3]


def test_fallback_does_not_parse_notes_in_cells_over_budget(monkeypatch):
    monkeypatch.setattr(hwpx_module, "MAX_TABLE_CELLS", 1)
    table = _table("<hp:tr>"
                   + _cell("<hp:t>kept</hp:t>" + _note("first"))
                   + _cell("<hp:t>dropped</hp:t>" + _note("discarded"))
                   + "</hp:tr>")
    document = HWPXParser().parse(_hwpx(_para(table) + _para(_note("second"))))

    assert [(note.number, note.text) for note in document.find_all("note")] == [
        (1, "first"), (2, "second"),
    ]
    assert len(document.sections[0].elements[0].rows[0]) == 1
    assert document.errors == ["ERR: HWPX table cell limit exceeded: more than 1 cells"]


def test_fallback_nested_table_consumes_cell_budgets_once(monkeypatch):
    monkeypatch.setattr(hwpx_module, "MAX_TABLE_CELLS", 2)
    monkeypatch.setattr(hwpx_module, "MAX_DOCUMENT_CELLS", 1)
    nested = _table(
        "<hp:tr>" + _cell(
            "<hp:t>nested</hp:t>" + _note("detail"),
            '<hp:cellAddr rowAddr="0" colAddr="0"/>',
        ) + "</hp:tr>",
        'rowCnt="1" colCnt="1"',
    )
    outer = _table("<hp:tr>" + _cell(nested) + "</hp:tr>")
    parser = HWPXParser()
    document = parser.parse(_hwpx(_para(outer)))

    assert document.errors == []
    table = document.sections[0].elements[0]
    inner = next(block for block in table.rows[0][0].paragraphs if isinstance(block, Table))
    assert inner.rows[0][0].text == "nested[1]"
    assert [(note.number, note.text) for note in document.find_all("note")] == [(1, "detail")]
    assert parser._cell_budget == parser._table_cells_remaining == 0
