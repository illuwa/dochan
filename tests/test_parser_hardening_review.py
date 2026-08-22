import sys
import struct
import tracemalloc
import zipfile
import zlib

import pytest

from dochan import Dochan
from dochan.constants import (
    HWPTAG_CTRL_HEADER,
    HWPTAG_LIST_HEADER,
    HWPTAG_PARA_HEADER,
    HWPTAG_TABLE,
)
from dochan.hwp.doc_info import DocInfoParser
from dochan.hwp.section import RawRecord, SectionParser
from dochan.hwpx.parser import HWPXParser
from dochan.model.table import Table
from dochan.office_binary.xls import parse_biff_workbook
from dochan.ooxml.docx import DOCXReader
from dochan.ooxml.package import OOXMLPackage
from dochan.ooxml.pptx import PPTXReader
from dochan.ooxml.xlsx import XLSXReader
from dochan.utils.safe_decompress import safe_zlib_decompress


def _raw_deflate(data):
    compressor = zlib.compressobj(wbits=-15)
    return compressor.compress(data) + compressor.flush()


def _write_zip(path, entries, compression=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


def test_safe_decompress_rejects_oversize_before_allocating_full_output():
    compressed = _raw_deflate(b"A" * (32 * 1024 * 1024))

    tracemalloc.start()
    try:
        with pytest.raises(ValueError, match="exceeds limit"):
            safe_zlib_decompress(compressed, max_size=1024 * 1024)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < 8 * 1024 * 1024


@pytest.mark.parametrize("trim", [1, 2, 5, 10])
def test_safe_decompress_rejects_truncated_stream(trim):
    compressed = _raw_deflate((b"bounded-stream-" * 4096))

    with pytest.raises(ValueError, match="truncated"):
        safe_zlib_decompress(compressed[:-trim])


def test_safe_decompress_allows_output_exactly_at_limit():
    raw = b"exact" * 1024

    assert safe_zlib_decompress(_raw_deflate(raw), max_size=len(raw)) == raw


def test_safe_decompress_rejects_trailing_stream_data():
    compressed = _raw_deflate(b"first") + _raw_deflate(b"second")

    with pytest.raises(ValueError, match="trailing"):
        safe_zlib_decompress(compressed)


def test_safe_decompress_accepts_valid_hwp_crc_and_size_trailer():
    raw = b"hwp-stream" * 4096
    trailer = struct.pack("<II", zlib.crc32(raw), len(raw))

    assert safe_zlib_decompress(_raw_deflate(raw) + trailer) == raw


@pytest.mark.parametrize("field", ["checksum", "size"])
def test_safe_decompress_rejects_corrupt_hwp_trailer(field):
    raw = b"hwp-stream" * 128
    checksum = zlib.crc32(raw) + (1 if field == "checksum" else 0)
    size = len(raw) + (1 if field == "size" else 0)

    with pytest.raises(ValueError, match="mismatch"):
        safe_zlib_decompress(_raw_deflate(raw) + struct.pack("<II", checksum, size))


def test_section_parser_rejects_truncated_declared_payload():
    header = (100 << 20) | 66
    parser = SectionParser()

    records = parser._read_all_records(struct.pack("<I", header) + b"xx")

    assert records == []
    assert any("truncated" in error.lower() for error in parser.errors)


def test_section_parser_stops_before_record_object_count_exceeds_limit(monkeypatch):
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_RECORDS", 2)
    parser = SectionParser()

    records = parser._read_all_records(struct.pack("<I", 66) * 3)

    assert len(records) == 2
    assert parser.errors == [
        "ERR: HWP section record count exceeds limit: more than 2"
    ]


def test_doc_info_parser_stops_before_record_object_count_exceeds_limit(monkeypatch):
    monkeypatch.setattr("dochan.hwp.doc_info.MAX_HWP_RECORDS", 2)
    parser = DocInfoParser()

    records = parser._read_all_records(struct.pack("<I", 16) * 3)

    assert len(records) == 2
    assert parser.errors == [
        "ERR: HWP DocInfo record count exceeds limit: more than 2"
    ]


def test_doc_info_parser_rejects_truncated_extended_payload():
    header = (0xFFF << 20) | 16
    parser = DocInfoParser()

    records = parser._read_all_records(struct.pack("<II", header, 100) + b"xx")

    assert records == []
    assert any("truncated" in error.lower() for error in parser.errors)


def test_section_parser_rejects_truncated_extended_payload():
    header = (0xFFF << 20) | 66
    parser = SectionParser()

    records = parser._read_all_records(struct.pack("<II", header, 100) + b"xx")

    assert records == []
    assert any("truncated" in error.lower() for error in parser.errors)


def _hwp_table_node(row_count, col_count, cells_info):
    table_data = b"\x00" * 4 + struct.pack("<HH", row_count, col_count)
    children = [
        {
            "record": RawRecord(
                tag_id=HWPTAG_TABLE,
                level=1,
                size=len(table_data),
                data=table_data,
            ),
            "children": [],
        }
    ]
    children.extend(
        {
            "record": RawRecord(
                tag_id=HWPTAG_LIST_HEADER,
                level=1,
                size=0,
                data=b"",
            ),
            "children": [],
            "cell_info": cell_info,
        }
        for cell_info in cells_info
    )
    return {"children": children}


def test_hwp_table_fallback_rejects_padded_cell_count_before_allocation(monkeypatch):
    import dochan.hwp.section as section_module

    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_TABLE_CELLS", 5)
    monkeypatch.setattr(parser, "_parse_cell_info", lambda node: node["cell_info"])

    def unexpected_cell_allocation(*args, **kwargs):
        raise AssertionError("fallback cells must not be allocated over the budget")

    monkeypatch.setattr(section_module, "Cell", unexpected_cell_allocation)
    table = parser._parse_table(
        _hwp_table_node(
            row_count=0,
            col_count=3,
            cells_info=[{"paragraphs": []} for _ in range(4)],
        )
    )

    assert table.rows == []
    assert parser.errors == [
        "ERR: HWP table cell allocation exceeds limit: 6 > 5"
    ]


@pytest.mark.parametrize("cell_limit", [6, 7])
def test_hwp_table_fallback_keeps_exact_limit_and_normal_inputs(
    monkeypatch, cell_limit
):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_TABLE_CELLS", cell_limit)
    monkeypatch.setattr(parser, "_parse_cell_info", lambda node: node["cell_info"])
    cells_info = [{"paragraphs": [index]} for index in range(4)]

    table = parser._parse_table(_hwp_table_node(0, 3, cells_info))

    assert [[cell.paragraphs for cell in row] for row in table.rows] == [
        [[0], [1], [2]],
        [[3], [], []],
    ]
    assert parser.errors == []


def test_hwp_table_fallback_rejects_max_column_count_with_multiple_cells(monkeypatch):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_TABLE_CELLS", 65_534)
    monkeypatch.setattr(parser, "_parse_cell_info", lambda node: node["cell_info"])

    table = parser._parse_table(
        _hwp_table_node(
            row_count=0,
            col_count=65_535,
            cells_info=[{"paragraphs": []}, {"paragraphs": []}],
        )
    )

    assert table.rows == []
    assert parser.errors == [
        "ERR: HWP table cell allocation exceeds limit: 65535 > 65534"
    ]


def test_hwp_table_fallback_bounds_cells_when_column_count_is_missing(monkeypatch):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_TABLE_CELLS", 3)
    monkeypatch.setattr(parser, "_parse_cell_info", lambda node: node["cell_info"])

    table = parser._parse_table(
        _hwp_table_node(
            row_count=2,
            col_count=0,
            cells_info=[{"paragraphs": []} for _ in range(4)],
        )
    )

    assert table.rows == []
    assert parser.errors == [
        "ERR: HWP table cell allocation exceeds limit: 4 > 3"
    ]


@pytest.mark.parametrize("cell_limit", [3, 4])
def test_hwp_table_declared_dimensions_keep_existing_budget_contract(
    monkeypatch, cell_limit
):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_TABLE_CELLS", cell_limit)
    monkeypatch.setattr(parser, "_parse_cell_info", lambda node: node["cell_info"])

    table = parser._parse_table(
        _hwp_table_node(
            row_count=2,
            col_count=2,
            cells_info=[{"row": 0, "col": 0, "paragraphs": []}],
        )
    )

    if cell_limit == 3:
        assert table.rows == []
        assert parser.errors == [
            "ERR: HWP table cell allocation exceeds limit: 4 > 3"
        ]
    else:
        assert table.row_count == 2
        assert table.col_count == 2
        assert parser.errors == []


def _hwp_table_control_node(row_count, col_count, cells_info, *, level=1):
    node = _hwp_table_node(row_count, col_count, cells_info)
    node["record"] = RawRecord(
        tag_id=HWPTAG_CTRL_HEADER,
        level=level,
        size=4,
        data=b" lbt",
    )
    return node


def _hwp_paragraph_with_control(control_node, *, level=0):
    return {
        "record": RawRecord(
            tag_id=HWPTAG_PARA_HEADER,
            level=level,
            size=0,
            data=b"",
        ),
        "children": [control_node],
    }


def _hwp_cell_with_paragraph(paragraph, *, row=0, col=0, row_span=1, col_span=1):
    return {
        "record": RawRecord(
            tag_id=HWPTAG_LIST_HEADER,
            level=1,
            size=16,
            data=(
                b"\x00" * 8
                + struct.pack("<HHHH", col, row, col_span, row_span)
            ),
        ),
        "children": [paragraph],
    }


def test_hwp_section_cell_budget_exact_limit_preserves_safe_tables(monkeypatch):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_SECTION_CELLS", 4, raising=False)
    tree = [
        _hwp_paragraph_with_control(_hwp_table_control_node(1, 2, [])),
        _hwp_paragraph_with_control(_hwp_table_control_node(1, 2, [])),
    ]

    section = parser._tree_to_section(tree)

    assert [table.col_count for table in section.elements] == [2, 2]
    assert parser.errors == []


def test_hwp_section_cell_budget_first_excess_is_fatal_once_and_keeps_safe_sibling(
    monkeypatch,
):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_SECTION_CELLS", 3, raising=False)
    tree = [
        _hwp_paragraph_with_control(_hwp_table_control_node(1, 2, [])),
        _hwp_paragraph_with_control(_hwp_table_control_node(1, 2, [])),
        _hwp_paragraph_with_control(_hwp_table_control_node(1, 1, [])),
    ]

    section = parser._tree_to_section(tree)

    assert [table.col_count for table in section.elements] == [2, 1]
    assert parser.errors == [
        "ERR: HWP section cell allocation exceeds limit: 2 + 2 > 3"
    ]


def test_hwp_document_cell_budget_spans_sections_and_preserves_safe_sibling(
    monkeypatch,
):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_DOCUMENT_CELLS", 3, raising=False)
    first = parser._tree_to_section(
        [_hwp_paragraph_with_control(_hwp_table_control_node(1, 2, []))]
    )
    second = parser._tree_to_section(
        [
            _hwp_paragraph_with_control(_hwp_table_control_node(1, 2, [])),
            _hwp_paragraph_with_control(_hwp_table_control_node(1, 1, [])),
        ]
    )

    assert [table.col_count for table in first.elements] == [2]
    assert [table.col_count for table in second.elements] == [1]
    assert parser.errors == [
        "ERR: HWP document cell allocation exceeds limit: 2 + 2 > 3"
    ]


def test_hwp_nested_table_cell_budget_cannot_be_bypassed(monkeypatch):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_SECTION_CELLS", 2, raising=False)
    nested = _hwp_table_control_node(1, 2, [])
    parent_cell = _hwp_cell_with_paragraph(_hwp_paragraph_with_control(nested))
    outer = _hwp_table_control_node(1, 1, [])
    outer["children"].append(parent_cell)

    table = parser._parse_table(outer)

    assert table.rows == []
    assert parser.errors == [
        "ERR: HWP section cell allocation exceeds limit: 1 + 2 > 2"
    ]


def test_hwp_failed_nested_table_rolls_back_budget_for_safe_sibling(monkeypatch):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_SECTION_CELLS", 2, raising=False)
    nested = _hwp_table_control_node(1, 2, [])
    parent_cell = _hwp_cell_with_paragraph(_hwp_paragraph_with_control(nested))
    unsafe_outer = _hwp_table_control_node(1, 1, [])
    unsafe_outer["children"].append(parent_cell)
    safe_sibling = _hwp_table_control_node(1, 2, [])

    section = parser._tree_to_section(
        [
            _hwp_paragraph_with_control(unsafe_outer),
            _hwp_paragraph_with_control(safe_sibling),
        ]
    )

    assert [table.col_count for table in section.elements] == [2]
    assert parser.errors == [
        "ERR: HWP section cell allocation exceeds limit: 1 + 2 > 2"
    ]


def test_hwp_table_depth_exact_limit_accepts_nested_content(monkeypatch):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_TABLE_DEPTH", 2, raising=False)
    nested = _hwp_table_control_node(1, 1, [])
    parent_cell = _hwp_cell_with_paragraph(_hwp_paragraph_with_control(nested))
    outer = _hwp_table_control_node(1, 1, [])
    outer["children"].append(parent_cell)

    table = parser._parse_table(outer)

    assert table.row_count == 1
    assert parser.errors == []


def test_hwp_table_depth_first_excess_is_fatal_once(monkeypatch):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_TABLE_DEPTH", 1, raising=False)
    nested = _hwp_table_control_node(1, 1, [])
    parent_cell = _hwp_cell_with_paragraph(_hwp_paragraph_with_control(nested))
    outer = _hwp_table_control_node(1, 1, [])
    outer["children"].append(parent_cell)

    table = parser._parse_table(outer)

    assert table.rows == []
    assert parser.errors == ["ERR: HWP table nesting exceeds depth limit: 2 > 1"]


def test_hwp_control_recursion_error_is_normalized_and_safe_sibling_survives(
    monkeypatch,
):
    parser = SectionParser()
    safe = _hwp_paragraph_with_control(_hwp_table_control_node(1, 1, []))
    crashing = _hwp_paragraph_with_control(_hwp_table_control_node(1, 1, []))
    original = parser._parse_table
    calls = 0

    def recurse_once(node):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RecursionError("synthetic parser recursion")
        return original(node)

    monkeypatch.setattr(parser, "_parse_table", recurse_once)

    section = parser._tree_to_section([crashing, safe])

    assert [table.col_count for table in section.elements] == [1]
    assert parser.errors == ["ERR: HWP structure recursion limit exceeded"]


@pytest.mark.parametrize(
    ("row", "col", "row_span", "col_span", "message"),
    [
        (0, 0, 0, 1, "invalid cell span"),
        (0, 0, 1, 0, "invalid cell span"),
        (1, 0, 1, 1, "cell position out of bounds"),
        (0, 1, 1, 1, "cell position out of bounds"),
        (0, 0, 2, 1, "cell span out of bounds"),
        (0, 0, 1, 2, "cell span out of bounds"),
    ],
)
def test_hwp_table_rejects_invalid_position_and_span_before_allocation(
    monkeypatch,
    row,
    col,
    row_span,
    col_span,
    message,
):
    import dochan.hwp.section as section_module

    parser = SectionParser()
    info = {
        "row": row,
        "col": col,
        "row_span": row_span,
        "col_span": col_span,
        "paragraphs": [],
    }
    monkeypatch.setattr(parser, "_parse_cell_info", lambda node, **kwargs: info)

    def unexpected_cell_allocation(*args, **kwargs):
        raise AssertionError("invalid table must fail before Cell allocation")

    monkeypatch.setattr(section_module, "Cell", unexpected_cell_allocation)

    table = parser._parse_table(_hwp_table_node(1, 1, [info]))

    assert table.rows == []
    assert parser.errors == [f"ERR: HWP table {message}"]


def test_hwp_table_span_exactly_at_declared_boundary_is_accepted():
    parser = SectionParser()
    info = {
        "row": 0,
        "col": 0,
        "row_span": 1,
        "col_span": 2,
        "paragraphs": [],
    }

    table = parser._parse_table(_hwp_table_node(1, 2, [info]))

    assert table.rows[0][0].col_span == 2
    assert parser.errors == []


def test_hwp_structure_depth_cap_handles_tree_deeper_than_python_recursion(
    monkeypatch,
):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_STRUCTURE_DEPTH", 8, raising=False)
    root = []
    nodes = root
    for depth in range(sys.getrecursionlimit() + 10):
        node = {
            "record": RawRecord(
                tag_id=HWPTAG_LIST_HEADER,
                level=depth,
                size=0,
                data=b"",
            ),
            "children": [],
        }
        nodes.append(node)
        nodes = node["children"]

    parser._fix_empty_list_headers(root)

    assert parser.errors == ["ERR: HWP structure depth exceeds limit: 9 > 8"]


def test_hwp_structure_depth_exact_limit_is_accepted(monkeypatch):
    parser = SectionParser()
    monkeypatch.setattr(parser, "MAX_STRUCTURE_DEPTH", 3, raising=False)
    root = []
    nodes = root
    for depth in range(4):
        node = {
            "record": RawRecord(
                tag_id=HWPTAG_LIST_HEADER,
                level=depth,
                size=0,
                data=b"",
            ),
            "children": [],
        }
        nodes.append(node)
        nodes = node["children"]

    parser._fix_empty_list_headers(root)

    assert parser.errors == []


def test_hwp_fallback_table_span_is_validated_before_allocation(monkeypatch):
    import dochan.hwp.section as section_module

    parser = SectionParser()
    info = {
        "row": 0,
        "col": 0,
        "row_span": 1,
        "col_span": 2,
        "paragraphs": [],
    }

    def unexpected_cell_allocation(*args, **kwargs):
        raise AssertionError("invalid fallback span must fail before allocation")

    monkeypatch.setattr(section_module, "Cell", unexpected_cell_allocation)

    table = parser._parse_table(_hwp_table_node(0, 0, [info]))

    assert table.rows == []
    assert parser.errors == ["ERR: HWP table cell span out of bounds"]


def test_doc_info_parser_rejects_truncated_standard_payload():
    header = (100 << 20) | 16
    parser = DocInfoParser()

    records = parser._read_all_records(struct.pack("<I", header) + b"xx")

    assert records == []
    assert any("truncated" in error.lower() for error in parser.errors)


@pytest.mark.parametrize(
    "reader",
    [DOCXReader, PPTXReader, XLSXReader],
)
def test_ooxml_readers_report_corrupt_archives_instead_of_raising(tmp_path, reader):
    path = tmp_path / "corrupt.bin"
    path.write_bytes(b"PK\x03\x04 truncated")

    document = reader().read(str(path))

    assert document.errors
    assert document.source_format == reader.format_name


def test_hwpx_rejects_unrelated_zip_instead_of_empty_success(tmp_path):
    path = tmp_path / "unrelated.hwpx"
    _write_zip(path, {"data/file.txt": "hello"})

    document = HWPXParser().parse(str(path))

    assert document.source_format == "hwpx"
    assert document.errors
    assert document.sections == []


def test_hwpx_metadata_part_obeys_size_limit(tmp_path, monkeypatch):
    import dochan.hwpx.parser as hwpx_module

    path = tmp_path / "oversized-metadata.hwpx"
    _write_zip(
        path,
        {
            "mimetype": "application/hwp+zip",
            "Contents/header.xml": "<header>" + ("x" * 1000) + "</header>",
            "Contents/section0.xml": "<section/>",
        },
    )
    monkeypatch.setattr(hwpx_module, "MAX_META_FILE_SIZE", 64)

    document = HWPXParser().parse(str(path))

    assert any(
        "header.xml" in error and "size" in error.lower() for error in document.errors
    )


def test_hwpx_requires_the_standard_mimetype_marker(tmp_path):
    path = tmp_path / "missing-marker.hwpx"
    _write_zip(path, {"Contents/section0.xml": "<section/>"})

    document = HWPXParser().parse(str(path))

    assert any("mimetype" in error.lower() for error in document.errors)
    assert document.sections == []


def test_hwpx_handles_xml_comments_in_valid_section(tmp_path):
    path = tmp_path / "comments.hwpx"
    _write_zip(
        path,
        {
            "mimetype": "application/hwp+zip",
            "Contents/section0.xml": "<section><!-- comment --><p/></section>",
        },
    )

    document = HWPXParser().parse(str(path))

    assert not [error for error in document.errors if error.startswith("ERR:")]
    assert len(document.sections) == 1


def test_hwpx_deduplicates_normalized_manifest_section_references(tmp_path):
    path = tmp_path / "duplicate-section-references.hwpx"
    _write_zip(
        path,
        {
            "mimetype": "application/hwp+zip",
            "Contents/content.hpf": """
                <package>
                  <item href="section0.xml"/>
                  <item href="./section0.xml"/>
                  <item href="Contents/section0.xml"/>
                </package>
            """,
            "Contents/section0.xml": "<section><p><run><t>once</t></run></p></section>",
        },
    )

    document = HWPXParser().parse(str(path))

    assert not [error for error in document.errors if error.startswith("ERR:")]
    assert len(document.sections) == 1
    assert document.sections[0].elements[0].text == "once"


def test_hwpx_stops_before_parsing_sections_over_document_budget(tmp_path, monkeypatch):
    import dochan.hwpx.parser as hwpx_module

    path = tmp_path / "too-many-sections.hwpx"
    _write_zip(
        path,
        {
            "mimetype": "application/hwp+zip",
            "Contents/content.hpf": """
                <package>
                  <item href="section0.xml"/>
                  <item href="section1.xml"/>
                </package>
            """,
            "Contents/section0.xml": "<section/>",
            "Contents/section1.xml": "<section/>",
        },
    )
    monkeypatch.setattr(hwpx_module, "MAX_SECTION_COUNT", 1, raising=False)

    document = HWPXParser().parse(str(path))

    assert document.sections == []
    assert any("section count exceeds limit" in error.lower() for error in document.errors)


def _hwpx_cell(text, attributes="", extra=""):
    return (
        f"<tc {attributes}>"
        f"{extra}<p><run><t>{text}</t></run></p>"
        "</tc>"
    )


def _write_hwpx_section(path, section_xml):
    _write_zip(
        path,
        {
            "mimetype": "application/hwp+zip",
            "Contents/section0.xml": section_xml,
        },
    )


def test_hwpx_table_cell_budget_omits_only_cells_beyond_limit(tmp_path, monkeypatch):
    import dochan.hwpx.parser as hwpx_module

    path = tmp_path / "table-cell-budget.hwpx"
    cells = "".join(_hwpx_cell(text) for text in ("A", "B", "C"))
    _write_hwpx_section(
        path,
        f"<section><p><run><tbl><tr>{cells}</tr></tbl></run></p></section>",
    )
    monkeypatch.setattr(hwpx_module, "MAX_TABLE_CELLS", 2)

    document = HWPXParser().parse(str(path))
    table = document.sections[0].elements[0]

    assert [cell.text for cell in table.rows[0]] == ["A", "B"]
    assert document.errors == [
        "ERR: HWPX table cell limit exceeded: more than 2 cells"
    ]


def test_hwpx_table_cell_budget_exact_limit_has_no_false_positive(
    tmp_path,
    monkeypatch,
):
    import dochan.hwpx.parser as hwpx_module

    path = tmp_path / "table-cell-budget-exact.hwpx"
    cells = "".join(_hwpx_cell(text) for text in ("A", "B"))
    _write_hwpx_section(
        path,
        f"<section><p><run><tbl><tr>{cells}</tr></tbl></run></p></section>",
    )
    monkeypatch.setattr(hwpx_module, "MAX_TABLE_CELLS", 2)

    document = HWPXParser().parse(str(path))

    assert [cell.text for cell in document.sections[0].elements[0].rows[0]] == [
        "A",
        "B",
    ]
    assert not [error for error in document.errors if error.startswith("ERR:")]


def test_hwpx_flat_and_nested_tables_share_one_document_cell_budget(
    tmp_path,
    monkeypatch,
):
    import dochan.hwpx.parser as hwpx_module

    path = tmp_path / "nested-table-cell-budget.hwpx"
    nested_cells = "".join(_hwpx_cell(text) for text in ("C", "D"))
    nested_table = f"<p><run><tbl><tr>{nested_cells}</tr></tbl></run></p>"
    first_table = f"<tbl><tr>{_hwpx_cell('A')}</tr></tbl>"
    second_table = (
        "<tbl><tr>"
        f"{_hwpx_cell('B', extra=nested_table)}"
        f"{_hwpx_cell('E')}"
        "</tr></tbl>"
    )
    _write_hwpx_section(
        path,
        (
            "<section>"
            f"<p><run>{first_table}</run></p>"
            f"<p><run>{second_table}</run></p>"
            "</section>"
        ),
    )
    monkeypatch.setattr(hwpx_module, "MAX_TABLE_CELLS", 3)

    document = HWPXParser().parse(str(path))
    first, second = document.sections[0].elements
    outer_cell = second.rows[0][0]
    nested = next(item for item in outer_cell.paragraphs if isinstance(item, Table))

    assert first.rows[0][0].text == "A"
    assert len(second.rows[0]) == 1
    assert [cell.text for cell in nested.rows[0]] == ["C"]
    assert "D" not in second.text
    assert "E" not in second.text
    assert document.errors == [
        "ERR: HWPX table cell limit exceeded: more than 3 cells"
    ]


def test_hwpx_table_cell_budget_is_shared_across_sections(tmp_path, monkeypatch):
    import dochan.hwpx.parser as hwpx_module

    path = tmp_path / "cross-section-table-cell-budget.hwpx"
    _write_zip(
        path,
        {
            "mimetype": "application/hwp+zip",
            "Contents/section0.xml": (
                "<section><p><run><tbl><tr>"
                f"{_hwpx_cell('A')}"
                "</tr></tbl></run></p></section>"
            ),
            "Contents/section1.xml": (
                "<section><p><run><tbl><tr>"
                f"{_hwpx_cell('B')}{_hwpx_cell('C')}"
                "</tr></tbl></run></p></section>"
            ),
        },
    )
    monkeypatch.setattr(hwpx_module, "MAX_TABLE_CELLS", 2)

    document = HWPXParser().parse(str(path))

    assert document.sections[0].elements[0].rows[0][0].text == "A"
    assert [
        cell.text for cell in document.sections[1].elements[0].rows[0]
    ] == ["B"]
    assert document.errors == [
        "ERR: HWPX table cell limit exceeded: more than 2 cells"
    ]


def test_hwpx_rejects_nonpositive_and_oversized_table_spans(tmp_path, monkeypatch):
    import dochan.hwpx.parser as hwpx_module

    path = tmp_path / "invalid-table-spans.hwpx"
    cells = "".join(
        (
            _hwpx_cell("zero", 'colSpan="0" rowSpan="-1"'),
            _hwpx_cell("huge", 'colSpan="999999999999999999999999"'),
            _hwpx_cell(
                "child",
                extra='<cellSpan colSpan="2" rowSpan="100"/>',
            ),
            _hwpx_cell("valid", 'colSpan="2" rowSpan="3"'),
        )
    )
    _write_hwpx_section(
        path,
        f"<section><p><run><tbl><tr>{cells}</tr></tbl></run></p></section>",
    )
    monkeypatch.setattr(hwpx_module, "MAX_TABLE_SPAN", 10, raising=False)

    document = HWPXParser().parse(str(path))
    row = document.sections[0].elements[0].rows[0]

    assert [(cell.col_span, cell.row_span) for cell in row] == [
        (1, 1),
        (1, 1),
        (2, 1),
        (2, 3),
    ]
    assert document.errors == ["ERR: HWPX invalid table span value"]


def test_hwpx_resolves_image_reference_by_exact_index_not_substring(tmp_path):
    path = tmp_path / "exact-image-reference.hwpx"
    _write_zip(
        path,
        {
            "mimetype": "application/hwp+zip",
            "Contents/section0.xml": """
                <section><p><run><pic><img binaryItemIDRef="image1"/></pic></run></p></section>
            """,
            "BinData/image10.png": b"wrong-image",
            "BinData/image1.png": b"right-image",
        },
    )

    document = HWPXParser().parse(str(path))

    images = document.find_all("image")
    assert len(images) == 1
    assert images[0].filename == "image1.png"
    assert images[0].image_data == b"right-image"


def test_hwpx_resolves_explicit_binary_item_id_from_header(tmp_path):
    path = tmp_path / "explicit-image-reference.hwpx"
    _write_zip(
        path,
        {
            "mimetype": "application/hwp+zip",
            "Contents/header.xml": """
                <header><binItem id="asset-7" href="BinData/photo.png"/></header>
            """,
            "Contents/section0.xml": """
                <section><p><run><pic><img binaryItemIDRef="asset-7"/></pic></run></p></section>
            """,
            "BinData/photo.png": b"photo-data",
        },
    )

    document = HWPXParser().parse(str(path))

    images = document.find_all("image")
    assert len(images) == 1
    assert images[0].filename == "photo.png"
    assert images[0].image_data == b"photo-data"


def test_hwpx_does_not_guess_when_inferred_image_reference_is_ambiguous(tmp_path):
    path = tmp_path / "ambiguous-image-reference.hwpx"
    _write_zip(
        path,
        {
            "mimetype": "application/hwp+zip",
            "Contents/section0.xml": """
                <section><p><run><pic><img binaryItemIDRef="photo"/></pic></run></p></section>
            """,
            "BinData/photo.png": b"png-data",
            "BinData/photo.jpg": b"jpg-data",
        },
    )

    document = HWPXParser().parse(str(path))

    images = document.find_all("image")
    assert len(images) == 1
    assert images[0].image_data == b""
    assert any("image reference is ambiguous" in error for error in document.errors)


def test_dochan_hwpx_metadata_preserves_source_format(tmp_path):
    path = tmp_path / "valid.hwpx"
    _write_zip(
        path,
        {
            "mimetype": "application/hwp+zip",
            "Contents/section0.xml": "<section/>",
        },
    )

    reader = Dochan(str(path))

    assert reader.doc.source_format == "hwpx"
    assert reader.metadata["source_format"] == "hwpx"


def test_dochan_invalid_hwp_still_preserves_source_format(tmp_path):
    path = tmp_path / "invalid.hwp"
    path.write_bytes(b"not an OLE document")

    reader = Dochan(str(path))

    assert reader.doc.source_format == "hwp"
    assert reader.metadata["source_format"] == "hwp"
    assert reader.errors


def test_hwp_section_discovery_includes_declared_gaps():
    class FakeOle:
        @staticmethod
        def listdir(streams=True, storages=False):
            return [["BodyText", "Section0"], ["BodyText", "Section2"]]

    assert Dochan._hwp_section_indices(FakeOle(), "BodyText", 3, 1000) == [0, 1, 2]


def test_hwp_section_discovery_reports_indices_outside_limit():
    class FakeOle:
        @staticmethod
        def listdir(streams=True, storages=False):
            return [["BodyText", "Section1000"]]

    errors = []
    assert Dochan._hwp_section_indices(
        FakeOle(), "BodyText", 0, 1000, errors
    ) == []
    assert errors == ["ERR: HWP section index exceeds limit: maximum 999"]


def test_hwp_declared_section_count_reports_limit_overflow():
    class FakeOle:
        @staticmethod
        def listdir(streams=True, storages=False):
            return []

        @staticmethod
        def exists(name):
            return False

    errors = []
    assert len(
        Dochan._hwp_section_indices(FakeOle(), "BodyText", 1001, 1000, errors)
    ) == 1000
    assert errors == ["ERR: HWP section index exceeds limit: maximum 999"]


def test_ooxml_package_rejects_archive_total_size_budget(tmp_path, monkeypatch):
    import dochan.ooxml.package as package_module

    path = tmp_path / "many-parts.docx"
    _write_zip(path, {"word/document.xml": "x" * 80, "word/styles.xml": "y" * 80})
    monkeypatch.setattr(package_module, "MAX_ARCHIVE_UNCOMPRESSED_SIZE", 100)

    with pytest.raises(ValueError, match="total uncompressed size"):
        with OOXMLPackage(str(path)):
            pass


def test_ooxml_package_rejects_archive_entry_count_budget(tmp_path, monkeypatch):
    import dochan.ooxml.package as package_module

    path = tmp_path / "many-entries.docx"
    _write_zip(path, {"word/document.xml": "<root/>", "word/styles.xml": "<root/>"})
    monkeypatch.setattr(package_module, "MAX_ARCHIVE_ENTRIES", 1)

    with pytest.raises(ValueError, match="too many entries"):
        with OOXMLPackage(str(path)):
            pass


def test_ooxml_package_rejects_duplicate_normalized_part_names(tmp_path):
    path = tmp_path / "duplicates.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<root/>")
        archive.writestr("word\\document.xml", "<other/>")

    with pytest.raises(ValueError, match="duplicate package part"):
        with OOXMLPackage(str(path)):
            pass


def test_ooxml_xml_element_budget_is_enforced_before_parsing(tmp_path, monkeypatch):
    import dochan.ooxml.package as package_module

    path = tmp_path / "many-elements.docx"
    _write_zip(path, {"word/document.xml": "<root><x/><x/><x/></root>"})
    monkeypatch.setattr(package_module, "MAX_XML_ELEMENTS", 2)

    with OOXMLPackage(str(path)) as package:
        with pytest.raises(ValueError, match="element limit"):
            package.read_xml_part("word/document.xml")


def test_hwpx_rejects_archive_total_size_budget(tmp_path, monkeypatch):
    import dochan.hwpx.parser as hwpx_module

    path = tmp_path / "total-size.hwpx"
    _write_zip(
        path,
        {
            "mimetype": "application/hwp+zip",
            "Contents/section0.xml": "<section>" + ("x" * 100) + "</section>",
        },
    )
    monkeypatch.setattr(hwpx_module, "MAX_ARCHIVE_UNCOMPRESSED_SIZE", 64)

    document = HWPXParser().parse(str(path))

    assert any("total uncompressed size" in error.lower() for error in document.errors)


def test_hwpx_rejects_duplicate_part_names(tmp_path):
    path = tmp_path / "duplicates.hwpx"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/hwp+zip")
            archive.writestr("Contents/section0.xml", "<section/>")
            archive.writestr("Contents/section0.xml", "<other/>")

    document = HWPXParser().parse(str(path))

    assert any("duplicate" in error.lower() for error in document.errors)
    assert document.sections == []


def test_docx_rejects_unbounded_grid_before_without_allocating_cells(tmp_path):
    path = tmp_path / "grid-before.docx"
    document_xml = """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:tbl><w:tr>
        <w:trPr><w:gridBefore w:val="1000000000"/></w:trPr>
        <w:tc><w:p><w:r><w:t>cell</w:t></w:r></w:p></w:tc>
      </w:tr></w:tbl></w:body>
    </w:document>
    """
    _write_zip(path, {"word/document.xml": document_xml})

    document = DOCXReader().read(str(path))

    assert any("cell limit" in error.lower() for error in document.errors)
    table = document.find_all("table")[0]
    assert table.row_count <= 1
    assert table.col_count <= 1


@pytest.mark.parametrize(
    ("property_xml", "diagnostic"),
    [
        ('<w:trPr><w:gridBefore w:val="-1"/></w:trPr>', "gridBefore"),
        ('<w:trPr><w:gridBefore w:val="invalid"/></w:trPr>', "gridBefore"),
        ('<w:tcPr><w:gridSpan w:val="-1"/></w:tcPr>', "gridSpan"),
        ('<w:tcPr><w:gridSpan w:val="invalid"/></w:tcPr>', "gridSpan"),
    ],
)
def test_docx_diagnoses_invalid_table_expansion_values(
    tmp_path, property_xml, diagnostic
):
    path = tmp_path / f"invalid-{diagnostic}.docx"
    if "trPr" in property_xml:
        row_properties, cell_properties = property_xml, ""
    else:
        row_properties, cell_properties = "", property_xml
    _write_zip(
        path,
        {
            "word/document.xml": f"""
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body><w:tbl><w:tr>{row_properties}<w:tc>{cell_properties}<w:p/></w:tc></w:tr></w:tbl></w:body>
            </w:document>
            """,
        },
    )

    document = DOCXReader().read(str(path))

    assert any(
        diagnostic in error and "invalid" in error.lower() for error in document.errors
    )


def test_xlsx_sparse_max_coordinate_is_bounded_and_diagnosed(tmp_path):
    path = tmp_path / "sparse.xlsx"
    _write_zip(
        path,
        {
            "xl/workbook.xml": """
              <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
              </workbook>
            """,
            "xl/_rels/workbook.xml.rels": """
              <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
              </Relationships>
            """,
            "xl/worksheets/sheet1.xml": """
              <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                <sheetData><row r="1048576"><c r="A1048576" t="inlineStr"><is><t>far</t></is></c></row></sheetData>
              </worksheet>
            """,
        },
    )

    document = XLSXReader().read(str(path))

    assert any("dense cell limit" in error.lower() for error in document.errors)
    assert not document.find_all("table")


def test_xlsx_full_sheet_merge_and_hyperlink_ranges_are_bounded(tmp_path):
    path = tmp_path / "ranges.xlsx"
    _write_zip(
        path,
        {
            "xl/workbook.xml": """
              <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
              </workbook>
            """,
            "xl/_rels/workbook.xml.rels": """
              <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
              </Relationships>
            """,
            "xl/worksheets/sheet1.xml": """
              <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                <sheetData/>
                <mergeCells><mergeCell ref="A1:XFD1048576"/></mergeCells>
                <hyperlinks><hyperlink ref="A1:XFD1048576" location="Sheet2!A1"/></hyperlinks>
              </worksheet>
            """,
        },
    )

    document = XLSXReader().read(str(path))

    assert (
        len([error for error in document.errors if "range limit" in error.lower()]) >= 2
    )
    assert not document.find_all("table")


def test_xlsx_out_of_bounds_row_is_rejected_before_dense_expansion(tmp_path):
    path = tmp_path / "row-bounds.xlsx"
    _write_zip(
        path,
        {
            "xl/workbook.xml": """
              <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
              </workbook>
            """,
            "xl/_rels/workbook.xml.rels": """
              <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
              </Relationships>
            """,
            "xl/worksheets/sheet1.xml": """
              <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                <sheetData><row r="1048577"><c r="A1048577"><v>1</v></c></row></sheetData>
              </worksheet>
            """,
        },
    )

    document = XLSXReader().read(str(path))

    assert any(
        "row reference out of bounds" in error.lower() for error in document.errors
    )
    assert not document.find_all("table")


def test_biff_dimension_uint32_max_is_diagnosed_without_expansion():
    dimension = struct.pack("<IIHHH", 0, 0xFFFFFFFF, 0, 1, 0)

    document = parse_biff_workbook(
        struct.pack("<HH", 0x0200, len(dimension)) + dimension
    )

    assert any(
        "dimension" in error.lower() and "bounds" in error.lower()
        for error in document.errors
    )
    assert not document.find_all("table")


def test_biff_full_sheet_merge_is_rejected_before_range_expansion():
    merged = struct.pack("<H", 1) + struct.pack("<HHHH", 0, 65535, 0, 255)

    document = parse_biff_workbook(struct.pack("<HH", 0x00E5, len(merged)) + merged)

    assert any("range limit" in error.lower() for error in document.errors)
    assert not document.find_all("table")


def test_pptx_deep_group_tree_reports_limit_instead_of_recursion_error(tmp_path):
    path = tmp_path / "deep-groups.pptx"
    depth = 1100
    nested = "<p:grpSp>" * depth + "<p:sp/>" + "</p:grpSp>" * depth
    _write_zip(
        path,
        {
            "ppt/presentation.xml": """
              <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
              </p:presentation>
            """,
            "ppt/_rels/presentation.xml.rels": """
              <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                <Relationship Id="rId1" Target="slides/slide1.xml"/>
              </Relationships>
            """,
            "ppt/slides/slide1.xml": f"""
              <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
                <p:cSld><p:spTree>{nested}</p:spTree></p:cSld>
              </p:sld>
            """,
        },
        compression=zipfile.ZIP_STORED,
    )

    document = PPTXReader().read(str(path))

    assert any("group depth limit" in error.lower() for error in document.errors)


def test_xlsx_streaming_preview_enforces_dense_cell_budget(tmp_path, monkeypatch):
    import dochan.ooxml.xlsx as xlsx_module

    path = tmp_path / "streaming-wide.xlsx"
    rows = "".join(
        f'<row r="{row}"><c r="U{row}"><v>{row}</v></c></row>' for row in range(1, 4)
    )
    _write_zip(
        path,
        {
            "xl/workbook.xml": """
              <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
              </workbook>
            """,
            "xl/_rels/workbook.xml.rels": """
              <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
              </Relationships>
            """,
            "xl/worksheets/sheet1.xml": f"""
              <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                <sheetData>{rows}</sheetData>
              </worksheet>
            """,
        },
    )
    monkeypatch.setattr(xlsx_module, "MAX_XML_PART_SIZE", 1)
    monkeypatch.setattr(xlsx_module, "MAX_DENSE_TABLE_CELLS", 50)

    document = XLSXReader().read(str(path))

    assert any("dense cell limit" in error.lower() for error in document.errors)
    assert not document.find_all("table")


def test_xlsx_merge_and_hyperlink_expansions_share_a_sheet_budget(
    tmp_path, monkeypatch
):
    import dochan.ooxml.xlsx as xlsx_module

    path = tmp_path / "cumulative-sheet-ranges.xlsx"
    _write_zip(
        path,
        {
            "xl/workbook.xml": """
              <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
              </workbook>
            """,
            "xl/_rels/workbook.xml.rels": """
              <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
              </Relationships>
            """,
            "xl/worksheets/sheet1.xml": """
              <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                <sheetData><row r="1">
                  <c r="A1"><v>1</v></c><c r="C1"><v>2</v></c><c r="D1"><v>3</v></c>
                </row></sheetData>
                <mergeCells><mergeCell ref="A1:B1"/></mergeCells>
                <hyperlinks><hyperlink ref="C1:D1" location="Data!A1"/></hyperlinks>
              </worksheet>
            """,
        },
    )
    monkeypatch.setattr(xlsx_module, "MAX_RANGE_CELLS", 3)

    document = XLSXReader().read(str(path))

    assert any(
        "cumulative sheet range limit" in error.lower() for error in document.errors
    )
    table = document.find_all("table")[0]
    assert table.rows[0][0].col_span == 2
    assert all(
        "#Data!A1" not in run.text
        for cell in table.rows[0]
        for paragraph in cell.paragraphs
        for run in paragraph.runs
    )


def test_xlsx_range_expansions_share_a_document_budget(tmp_path, monkeypatch):
    import dochan.ooxml.xlsx as xlsx_module

    path = tmp_path / "cumulative-document-ranges.xlsx"
    sheet_xml = """
      <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
        <sheetData><row r="1"><c r="A1"><v>1</v></c></row></sheetData>
        <mergeCells><mergeCell ref="A1:B1"/></mergeCells>
      </worksheet>
    """
    _write_zip(
        path,
        {
            "xl/workbook.xml": """
              <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                <sheets>
                  <sheet name="One" sheetId="1" r:id="rId1"/>
                  <sheet name="Two" sheetId="2" r:id="rId2"/>
                </sheets>
              </workbook>
            """,
            "xl/_rels/workbook.xml.rels": """
              <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
                <Relationship Id="rId2" Target="worksheets/sheet2.xml"/>
              </Relationships>
            """,
            "xl/worksheets/sheet1.xml": sheet_xml,
            "xl/worksheets/sheet2.xml": sheet_xml,
        },
    )
    monkeypatch.setattr(xlsx_module, "MAX_RANGE_CELLS", 3)

    document = XLSXReader().read(str(path))

    assert any(
        "cumulative document range limit" in error.lower() for error in document.errors
    )
    tables = document.find_all("table")
    assert tables[0].rows[0][0].col_span == 2
    assert tables[1].rows[0][0].col_span == 1


def test_biff_mulblank_rejects_extreme_declared_span_without_allocating_entries():
    import dochan.office_binary.xls as xls_module

    payload = struct.pack("<HHHH", 0, 0, 0, 65535)
    sheet = xls_module._SheetInfo(name="Sheet1", offset=0)

    tracemalloc.start()
    try:
        xls_module._parse_sheet_records(
            struct.pack("<HH", 0x00BE, len(payload)) + payload,
            sheet,
            [],
            {},
            [],
            [],
            [],
            [],
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert not sheet.cells
    assert any("mulblank" in error.lower() for error in sheet.errors)
    assert peak < 2 * 1024 * 1024


def test_biff_mulblank_validates_column_bounds_and_xf_count():
    import dochan.office_binary.xls as xls_module

    out_of_bounds = struct.pack("<HHHHH", 0, 255, 0, 0, 256)
    count_mismatch = struct.pack("<HHHH", 0, 0, 0, 2)

    for payload, diagnostic in (
        (out_of_bounds, "range out of bounds"),
        (count_mismatch, "xf count mismatch"),
    ):
        sheet = xls_module._SheetInfo(name="Sheet1", offset=0)
        xls_module._parse_sheet_records(
            struct.pack("<HH", 0x00BE, len(payload)) + payload,
            sheet,
            [],
            {},
            [],
            [],
            [],
            [],
        )

        assert not sheet.cells
        assert any(diagnostic in error.lower() for error in sheet.errors)


def test_biff_mulblank_enforces_global_cell_budget(monkeypatch):
    import dochan.office_binary.xls as xls_module

    payload = struct.pack("<HHHHHH", 0, 0, 0, 0, 0, 2)
    sheet = xls_module._SheetInfo(name="Sheet1", offset=0)
    monkeypatch.setattr(xls_module, "MAX_BIFF_DENSE_CELLS", 2)

    xls_module._parse_sheet_records(
        struct.pack("<HH", 0x00BE, len(payload)) + payload,
        sheet,
        [],
        {},
        [],
        [],
        [],
        [],
    )

    assert not sheet.cells
    assert any("cell limit" in error.lower() for error in sheet.errors)


def test_biff_cell_budget_caps_separate_blank_records_and_deduplicates_error(
    monkeypatch,
):
    import dochan.office_binary.xls as xls_module

    records = b"".join(struct.pack("<HHHHH", 0x0201, 6, 0, col, 0) for col in range(4))
    sheet = xls_module._SheetInfo(name="Sheet1", offset=0)
    monkeypatch.setattr(xls_module, "MAX_BIFF_DENSE_CELLS", 2)

    xls_module._parse_sheet_records(records, sheet, [], {}, [], [], [], [])

    assert len(sheet.cells) == 2
    assert set(sheet.cells) == {(0, 0), (0, 1)}
    assert len([error for error in sheet.errors if "cell limit" in error.lower()]) == 1


def test_biff_cell_budget_accumulates_across_record_types(monkeypatch):
    import dochan.office_binary.xls as xls_module

    label = (
        struct.pack("<HH", 0x0204, 9) + struct.pack("<HHH", 0, 0, 0) + b"\x00\x00\x00"
    )
    number_payload = struct.pack("<HHHd", 0, 1, 0, 2.0)
    number = struct.pack("<HH", 0x0203, len(number_payload)) + number_payload
    integer_payload = struct.pack("<HHHH", 0, 2, 0, 3)
    integer = struct.pack("<HH", 0x0002, len(integer_payload)) + integer_payload
    sheet = xls_module._SheetInfo(name="Sheet1", offset=0)
    monkeypatch.setattr(xls_module, "MAX_BIFF_DENSE_CELLS", 2)

    xls_module._parse_sheet_records(
        label + number + integer, sheet, [], {}, [], [], [], []
    )

    assert set(sheet.cells) == {(0, 0), (0, 1)}
    assert len([error for error in sheet.errors if "cell limit" in error.lower()]) == 1


def test_biff_cell_budget_allows_duplicate_coordinate_update(monkeypatch):
    import dochan.office_binary.xls as xls_module

    blank = struct.pack("<HHHHH", 0x0201, 6, 0, 0, 0)
    number_payload = struct.pack("<HHHd", 0, 0, 0, 7.0)
    number = struct.pack("<HH", 0x0203, len(number_payload)) + number_payload
    overflow = struct.pack("<HHHHH", 0x0201, 6, 0, 1, 0)
    sheet = xls_module._SheetInfo(name="Sheet1", offset=0)
    monkeypatch.setattr(xls_module, "MAX_BIFF_DENSE_CELLS", 1)

    xls_module._parse_sheet_records(
        blank + number + overflow, sheet, [], {}, [], [], [], []
    )

    assert sheet.cells == {(0, 0): "7"}
    assert len([error for error in sheet.errors if "cell limit" in error.lower()]) == 1


@pytest.mark.parametrize(
    ("record_type", "payload", "shared_strings"),
    [
        (0x00FD, struct.pack("<HHHI", 0, 0, 0, 0), ["shared"]),
        (0x0204, struct.pack("<HHH", 0, 0, 0) + b"\x00\x00", []),
        (0x0004, struct.pack("<HHH", 0, 0, 0) + b"\x00", []),
        (0x00D6, struct.pack("<HHH", 0, 0, 0) + b"\x00\x00\x00", []),
        (0x0201, struct.pack("<HHH", 0, 0, 0), []),
        (0x0203, struct.pack("<HHHd", 0, 0, 0, 1.0), []),
        (0x0002, struct.pack("<HHHH", 0, 0, 0, 1), []),
        (0x027E, struct.pack("<HHHI", 0, 0, 0, 4), []),
        (0x0205, struct.pack("<HHHBB", 0, 0, 0, 1, 0), []),
        (0x0006, struct.pack("<HHHd", 0, 0, 0, 1.0), []),
    ],
)
def test_biff_single_cell_record_types_share_preallocation_gate(
    monkeypatch, record_type, payload, shared_strings
):
    import dochan.office_binary.xls as xls_module

    sheet = xls_module._SheetInfo(name="Sheet1", offset=0)
    monkeypatch.setattr(xls_module, "MAX_BIFF_DENSE_CELLS", 0)

    xls_module._parse_sheet_records(
        struct.pack("<HH", record_type, len(payload)) + payload,
        sheet,
        shared_strings,
        {},
        [],
        [],
        [],
        [],
    )

    assert not sheet.cells
    assert len([error for error in sheet.errors if "cell limit" in error.lower()]) == 1


def test_biff_mulrk_hyperlink_and_note_share_preallocation_gate(monkeypatch):
    import dochan.office_binary.xls as xls_module

    mulrk_payload = struct.pack("<HHHIHIH", 0, 0, 0, 4, 0, 8, 1)
    mulrk = struct.pack("<HH", 0x00BD, len(mulrk_payload)) + mulrk_payload
    hyperlink_payload = (
        struct.pack("<HHHH", 1, 1, 0, 0)
        + b"\x00" * 24
        + "https://example.com".encode("utf-16-le")
        + b"\x00\x00"
    )
    hyperlink = struct.pack("<HH", 0x01B8, len(hyperlink_payload)) + hyperlink_payload
    note_payload = struct.pack("<HHHHHB", 2, 0, 0, 1, 1, 0) + b"A"
    note = struct.pack("<HH", 0x001C, len(note_payload)) + note_payload
    sheet = xls_module._SheetInfo(name="Sheet1", offset=0)
    monkeypatch.setattr(xls_module, "MAX_BIFF_DENSE_CELLS", 2)

    xls_module._parse_sheet_records(
        mulrk + hyperlink + note, sheet, [], {}, [], [], [], []
    )

    assert set(sheet.cells) == {(0, 0), (0, 1)}
    assert not sheet.hyperlinks
    assert not sheet.comments
    assert len([error for error in sheet.errors if "cell limit" in error.lower()]) == 1
