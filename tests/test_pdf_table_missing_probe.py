"""PDF 원시 괘선과 글자 위치의 익명 진단 테스트."""
from dochan.pdf import reader
from dochan.pdf.reader import PDFReader
from scripts.probe_pdf_table_missing import _geometry
from test_pdf_structure import _build_pdf, _minimal_objects


def _probe(tmp_path, rules):
    content = (rules + b' BT /F1 10 Tf 10 40 Td (a) Tj 50 0 Td (b) Tj '
               b'-50 -30 Td (c) Tj 50 0 Td (d) Tj ET')
    path = tmp_path / 'probe.pdf'
    path.write_bytes(_build_pdf(_minimal_objects(content)))
    captured = []
    original = reader.build_tables

    def capture(segments, fragments, **kwargs):
        captured.append((segments, fragments))
        return original(segments, fragments, **kwargs)

    reader.build_tables = capture
    try:
        PDFReader().read(str(path))
    finally:
        reader.build_tables = original
    assert len(captured) == 1
    return _geometry(*captured[0], (2, 2))


def test_closed_pdf_grid_is_distinguished_from_partial_rules(tmp_path):
    full = (b'0 0 100 60 re S 50 0 m 50 60 l S '
            b'0 30 m 100 30 l S')
    horizontal = (b'0 0 m 100 0 l S 0 30 m 100 30 l S '
                  b'0 60 m 100 60 l S')
    assert _probe(tmp_path, full)[0] == 'a'
    assert _probe(tmp_path, horizontal)[0] == 'c'
    assert _probe(tmp_path, b'')[0] == 'b'


def test_thin_filled_rectangle_is_single_row_rule(tmp_path):
    rules = (b'0 0 100 60 re S 50 0 m 50 60 l S '
             b'0 29.8 100 0.4 re f')
    assert _probe(tmp_path, rules)[0] == 'a'


def test_hwpx_cell_border_references_are_counted(tmp_path):
    import zipfile

    from scripts.probe_pdf_table_missing import _border_styles

    path = tmp_path / 'synthetic.hwpx'
    header = (b'<root><borderFill id="1">'
              b'<leftBorder type="NONE" width="0.1 mm"/>'
              b'<rightBorder type="NONE" width="0.1 mm"/>'
              b'<topBorder type="SOLID" width="0.4 mm"/>'
              b'<bottomBorder type="DASH" width="0.12 mm"/>'
              b'</borderFill></root>')
    section = (b'<root><tbl rowCnt="1" colCnt="1"><tr>'
               b'<tc borderFillIDRef="1"/></tr></tbl></root>')
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Contents/header.xml', header)
        archive.writestr('Contents/section0.xml', section)
    border, = _border_styles(path)
    assert border['visible_sides'] == 2
    assert border['horizontal_sides'] == 2
    assert border['vertical_sides'] == 0


def test_probe_does_not_infer_grid_from_twenty_thousand_rules():
    from dochan.pdf.content import Fragment
    from dochan.pdf.paths import Segment

    segments = [Segment(0, 30, 100, 30) for _ in range(20000)]
    segments.extend([Segment(0, 0, 0, 60), Segment(100, 0, 100, 60)])
    anchor = Fragment(10, 20, 10, 10, 'a', 5)
    assert _geometry(segments, [anchor], (2, 2))[0] == 'other'


def test_repeated_text_cannot_fix_table_page():
    from collections import Counter

    from dochan.pdf.content import Fragment, assemble_lines
    from scripts.probe_pdf_table_missing import _anchors

    first = Fragment(10, 20, 20, 10, 'repeat', 5)
    second = Fragment(10, 20, 20, 10, 'repeat', 5)
    pages = {1: ([], [first], assemble_lines([first])),
             2: ([], [second], assemble_lines([second]))}
    page, anchors, reason, locations = _anchors(Counter({'repeat': 1}), pages)
    assert page is None and anchors == []
    assert reason == 'repeated_or_ambiguous'
    assert len(locations) == 2
