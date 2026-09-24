import zlib

from dochan.pdf.reader import PDFReader
from test_pdf_structure import _build_pdf, _minimal_objects


def _write(tmp_path, name, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_reads_single_page_text(tmp_path):
    content = b"BT /F1 12 Tf 72 720 Td (Hello PDF) Tj ET"
    path = _write(tmp_path, "one.pdf", _build_pdf(_minimal_objects(content)))

    doc = PDFReader().read(path)

    assert doc.source_format == "pdf"
    assert len(doc.sections) == 1
    para = doc.sections[0].elements[0]
    assert para.text == "Hello PDF"
    assert para.provenance.source_format == "pdf"
    assert para.provenance.page == 1
    assert doc.sections[0].provenance.page == 1


def test_ruleless_table_is_opt_in_and_keeps_stream_order(tmp_path):
    from dochan import Dochan
    from dochan.model.table import Table

    content = b"BT /F1 10 Tf 20 760 Td (Before) Tj ET "
    for row, labels in enumerate(((b"A", b"One"), (b"B", b"Two"),
                                  (b"C", b"Three"))):
        for col, label in enumerate(labels):
            content += b"BT /F1 10 Tf %d %d Td (%s) Tj ET " % (
                20 + col * 100, 730 - row * 20, label)
    content += b"BT /F1 10 Tf 20 650 Td (After) Tj ET"
    path = _write(tmp_path, "ruleless.pdf", _build_pdf(_minimal_objects(content)))

    plain = PDFReader().read(path)
    assert plain.find_all("table") == []
    flagged = PDFReader(text_tables=True).read(path)
    before, table, after = flagged.sections[0].elements
    assert isinstance(table, Table)
    assert (before.text, after.text) == ("Before", "After")
    assert [[cell.text for cell in row] for row in table.rows] == [
        ["A", "One"], ["B", "Two"], ["C", "Three"]]
    assert len(Dochan(path, pdf_text_tables=True).find_all("table")) == 1


def test_reads_multiple_pages_in_order(tmp_path):
    c1 = b"BT (Page one) Tj ET"
    c2 = b"BT (Page two) Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R >>",
        4: "<< /Type /Page /Parent 2 0 R /Contents 6 0 R >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c1), c1),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c2), c2),
    }
    path = _write(tmp_path, "two.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    assert len(doc.sections) == 2
    assert doc.sections[0].elements[0].text == "Page one"
    assert doc.sections[1].elements[0].text == "Page two"
    assert doc.sections[1].elements[0].provenance.page == 2


def _running_pages(tmp_path, headers):
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [%s] /Count %d /MediaBox [0 0 600 800] "
           "/Resources << /Font << /F1 20 0 R >> >> >>" % (
               " ".join("%d 0 R" % (3 + i) for i in range(len(headers))), len(headers)),
        20: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, header in enumerate(headers):
        content = (b"BT /F1 10 Tf 30 730 Td (%s) Tj ET " % header.encode("ascii") +
                   b"BT /F1 10 Tf 30 400 Td (Body%d) Tj ET " % (index + 1) +
                   b"BT /F1 10 Tf 30 40 Td (%d) Tj ET" % (index + 1))
        objects[3 + index] = "<< /Type /Page /Parent 2 0 R /Contents %d 0 R >>" % (10 + index)
        objects[10 + index] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content)
    return PDFReader().read(_write(tmp_path, "running.pdf", _build_pdf(objects)))


def test_running_header_and_page_number_become_section_elements(tmp_path):
    from dochan.output.markdown import to_markdown

    doc = _running_pages(tmp_path, ["Running", "Running", "Running"])
    assert [(hf.type, hf.text) for hf in doc.find_all("header_footer")] == [
        ("header", "Running"), ("footer", "1")]
    assert [elem.text for elem in doc.sections[0].elements] == ["Running", "1", "Body1"]
    assert [[elem.text for elem in section.elements] for section in doc.sections[1:]] == [
        ["Body2"], ["Body3"]]
    assert to_markdown(doc).count("<!-- header: Running -->") == 1


def test_nonrepeating_top_lines_remain_body(tmp_path):
    doc = _running_pages(tmp_path, ["First", "Second"])
    assert doc.find_all("header") == []
    assert [[elem.text for elem in section.elements if elem.__class__.__name__ == "Paragraph"]
            for section in doc.sections] == [["First", "Body1"], ["Second", "Body2"]]


def test_running_detection_limit_keeps_all_page_text(tmp_path, monkeypatch):
    from dochan.pdf import reader

    monkeypatch.setattr(reader, "MAX_RUNNING_TEXT_PAGES", 1)
    doc = _running_pages(tmp_path, ["Running", "Running"])
    assert doc.find_all("header_footer") == []
    assert [[elem.text for elem in section.elements] for section in doc.sections] == [
        ["Running", "Body1", "1"], ["Running", "Body2", "2"]]


def test_flate_compressed_content(tmp_path):
    body = zlib.compress(b"BT (Compressed) Tj ET")
    objects = _minimal_objects()
    objects[5] = b"<< /Length %d /Filter /FlateDecode >>\nstream\n%s\nendstream" % (len(body), body)
    path = _write(tmp_path, "flate.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    assert doc.sections[0].elements[0].text == "Compressed"


def test_contents_array_concatenated(tmp_path):
    c1 = b"BT (First) Tj ET"
    c2 = b"BT (Second) Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents [5 0 R 6 0 R] >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c1), c1),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c2), c2),
    }
    path = _write(tmp_path, "arr.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    texts = [p.text for p in doc.sections[0].elements]
    assert texts == ["First", "Second"]


def test_tounicode_font_decodes_korean(tmp_path):
    cmap = (
        b"1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        b"2 beginbfchar\n<0001> <AC00>\n<0002> <B098>\nendbfchar\n"
    )
    content = b"BT /F1 12 Tf <00010002> Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
           "/Contents 5 0 R >>",
        4: "<< /Type /Font /Subtype /Type0 /ToUnicode 6 0 R >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(cmap), cmap),
    }
    path = _write(tmp_path, "kr.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    assert doc.sections[0].elements[0].text == "가나"  # 가나


def test_encrypted_pdf_stops_with_warning(tmp_path):
    data = _build_pdf(_minimal_objects(), trailer_extra="/Encrypt 4 0 R")
    path = _write(tmp_path, "enc.pdf", data)

    doc = PDFReader().read(path)

    assert doc.sections == []
    assert any("암호화" in e for e in doc.errors)


def test_scanned_only_page_warns(tmp_path):
    image = b"\xff\xd8fakejpeg"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /XObject << /Im1 5 0 R >> >> "
           "/Contents 6 0 R >>",
        5: b"<< /Length %d /Subtype /Image /Filter /DCTDecode >>\nstream\n%s\nendstream"
           % (len(image), image),
        6: b"<< /Length 10 >>\nstream\nq /Im1 Do Q\nendstream",
    }
    path = _write(tmp_path, "scan.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    # 텍스트 없는 이미지 페이지 — 추출 가능하면 OCR 안내, 아니면 스캔 경고
    assert any("이미지" in e or "스캔" in e for e in doc.errors)


def test_non_pdf_file_reports_error(tmp_path):
    path = _write(tmp_path, "junk.pdf", b"this is not a pdf at all")

    doc = PDFReader().read(path)

    assert any("%PDF-" in e for e in doc.errors)
    assert doc.sections == []


def test_dochan_routes_pdf_extension(tmp_path):
    from dochan import Dochan

    content = b"BT (Routed) Tj ET"
    path = _write(tmp_path, "route.pdf", _build_pdf(_minimal_objects(content)))

    doc = Dochan(path)

    assert doc.metadata["source_format"] == "pdf"
    assert doc.to_markdown() == "Routed"


def test_dochan_routes_pdf_magic_without_extension(tmp_path):
    from dochan import Dochan

    content = b"BT (MagicRouted) Tj ET"
    path = _write(tmp_path, "mystery.bin", _build_pdf(_minimal_objects(content)))

    doc = Dochan(path)

    assert doc.metadata["source_format"] == "pdf"
    assert doc.to_markdown() == "MagicRouted"


def test_batch_convert_includes_pdf_by_default(tmp_path):
    from dochan.batch import batch_convert

    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    content = b"BT (Batch PDF) Tj ET"
    (input_dir / "doc.pdf").write_bytes(_build_pdf(_minimal_objects(content)))

    summary = batch_convert(str(input_dir), str(output_dir),
                            output_format="markdown", max_workers=1)

    assert summary.total == 1
    assert summary.success == 1
    assert (output_dir / "doc.md").read_text(encoding="utf-8") == "Batch PDF"


def test_outline_bookmarks_extracted_with_page_numbers(tmp_path):
    c1 = b"BT (Chapter one body) Tj ET"
    c2 = b"BT (Chapter two body) Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R /Outlines 7 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R >>",
        4: "<< /Type /Page /Parent 2 0 R /Contents 6 0 R >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c1), c1),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c2), c2),
        7: "<< /Type /Outlines /First 8 0 R /Last 9 0 R /Count 2 >>",
        8: "<< /Title (First chapter) /Parent 7 0 R /Next 9 0 R "
           "/Dest [3 0 R /XYZ 0 792 0] /First 10 0 R /Last 10 0 R >>",
        9: "<< /Title (Second chapter) /Parent 7 0 R /Dest [4 0 R /Fit] >>",
        10: "<< /Title (Nested section) /Parent 8 0 R /Dest [3 0 R /Fit] >>",
    }
    path = _write(tmp_path, "outline.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)
    markdown = __import__("dochan.output.markdown", fromlist=["to_markdown"]).to_markdown(doc)

    assert "First chapter" in markdown
    assert "Second chapter" in markdown
    assert "Nested section" in markdown
    # 페이지 번호 매핑
    assert "(p.1)" in markdown and "(p.2)" in markdown
    # 본문은 그대로
    assert "Chapter one body" in markdown


def test_circular_outline_terminates(tmp_path):
    objects = _minimal_objects()
    objects[1] = "<< /Type /Catalog /Pages 2 0 R /Outlines 7 0 R >>"
    objects[7] = "<< /Type /Outlines /First 8 0 R >>"
    objects[8] = "<< /Title (Loop) /Next 8 0 R /First 8 0 R >>"  # 자기 참조
    path = _write(tmp_path, "loop-outline.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)  # 무한 루프 없이 반환

    assert doc.source_format == "pdf"


def test_link_annotation_urls_extracted(tmp_path):
    content = b"BT (Visit our site) Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R /Annots [6 0 R 7 0 R] >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        6: "<< /Type /Annot /Subtype /Link /Rect [0 0 100 20] "
           "/A << /S /URI /URI (https://example.com/docs) >> >>",
        7: "<< /Type /Annot /Subtype /Link /Rect [0 30 100 50] "
           "/A << /S /URI /URI (mailto:hello@example.com) >> >>",
    }
    path = _write(tmp_path, "links.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)
    markdown = __import__("dochan.output.markdown", fromlist=["to_markdown"]).to_markdown(doc)

    assert "<https://example.com/docs>" in markdown
    assert "<mailto:hello@example.com>" in markdown
    assert "Visit our site" in markdown
    link_paras = [p for p in doc.sections[0].elements
                  if "example.com/docs" in getattr(p, "text", "")]
    assert link_paras and link_paras[0].provenance.page == 1


def test_font_size_based_heading_detection(tmp_path):
    content = (
        b"BT /F1 24 Tf 72 720 Td (Document Title) Tj "
        b"/F1 10 Tf 0 -30 Td (First body line) Tj "
        b"0 -14 Td (Second body line) Tj "
        b"0 -14 Td (Third body line) Tj ET"
    )
    path = _write(tmp_path, "headed.pdf", _build_pdf(_minimal_objects(content)))

    doc = PDFReader().read(path)
    paras = doc.sections[0].elements

    assert paras[0].text == "Document Title"
    assert paras[0].heading_level >= 1
    assert all(p.heading_level == 0 for p in paras[1:])


def test_uniform_font_size_produces_no_headings(tmp_path):
    content = (
        b"BT /F1 12 Tf 72 720 Td (Line A) Tj "
        b"0 -14 Td (Line B) Tj 0 -14 Td (Line C) Tj ET"
    )
    path = _write(tmp_path, "flat.pdf", _build_pdf(_minimal_objects(content)))

    doc = PDFReader().read(path)

    assert all(p.heading_level == 0 for p in doc.sections[0].elements)


def test_nested_table_round_trips_reader_markdown_and_json(tmp_path):
    from dochan.model.table import Table
    from dochan.output.json_out import to_dict
    from dochan.output.markdown import to_markdown

    content = (
        b'0 0 100 60 re S 50 0 m 50 60 l S 0 30 m 100 30 l S '
        b'55 35 40 20 re S 75 35 m 75 55 l S 55 45 m 95 45 l S '
        b'BT /F1 8 Tf 57 47 Td (A) Tj ET '
        b'BT /F1 8 Tf 78 47 Td (B) Tj ET '
        b'BT /F1 8 Tf 57 37 Td (C) Tj ET '
        b'BT /F1 8 Tf 78 37 Td (D) Tj ET '
    )
    path = _write(tmp_path, 'nested.pdf', _build_pdf(_minimal_objects(content)))
    doc = PDFReader().read(path)

    outer, inner = doc.find_all('table')
    assert doc.sections[0].elements == [outer]
    assert isinstance(outer.rows[0][1].paragraphs[0], Table)
    assert outer.rows[0][1].paragraphs[0] is inner
    assert [[cell.text for cell in row] for row in inner.rows] == [['A', 'B'], ['C', 'D']]
    assert 'A / B ; C / D' in to_markdown(doc)
    nested = to_dict(doc)['sections'][0]['elements'][0]['rows'][0][1]['paragraphs'][0]
    assert nested['type'] == 'table' and nested['row_count'] == nested['col_count'] == 2


def _table_page(top_row, bottom_row, *, first=False, body_below=False,
                low_tail=False, low_head=False, body_above=False, cols=2):
    """200pt 페이지의 위/아래 표와 주변 본문을 그린다."""
    bottom, top = ((20, 70) if low_tail else (80, 140)) if first else (
        (40, 120) if low_head else (80, 160))
    content = b""
    if first:
        content += b"BT /F1 10 Tf 10 180 Td (Before) Tj ET "
    if body_above:
        content += b"BT /F1 10 Tf 10 130 Td (Above) Tj ET "
    content += b"0 %d 100 %d re S " % (bottom, top - bottom)
    for col in range(1, cols):
        x = round(100 * col / cols)
        content += b"%d %d m %d %d l S " % (x, bottom, x, top)
    middle = (bottom + top) // 2
    content += b"0 %d m 100 %d l S " % (middle, middle)
    for row, y in ((top_row, (middle + top) // 2),
                   (bottom_row, (bottom + middle) // 2)):
        for col, label in enumerate(row):
            x = round(100 * col / cols) + 5
            content += b"BT /F1 10 Tf %d %d Td (%s) Tj ET " % (
                x, y, label.encode("ascii"))
    if body_below:
        content += b"BT /F1 10 Tf 10 70 Td (Between) Tj ET "
    if not first:
        content += b"BT /F1 10 Tf 10 40 Td (After) Tj ET "
    return content


def _read_table_pages(tmp_path, contents):
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [%s] /Count %d /MediaBox [0 0 200 200] "
           "/Resources << /Font << /F1 20 0 R >> >> >>" % (
               " ".join("%d 0 R" % (3 + i) for i in range(len(contents))), len(contents)),
        20: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, content in enumerate(contents):
        objects[3 + index] = "<< /Type /Page /Parent 2 0 R /Contents %d 0 R >>" % (10 + index)
        objects[10 + index] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content)
    return PDFReader().read(_write(tmp_path, "pages.pdf", _build_pdf(objects)))


def test_continued_table_merges_rows_and_preserves_body_order(tmp_path):
    from dochan.output.markdown import to_markdown

    doc = _read_table_pages(tmp_path, [
        _table_page(("A", "B"), ("C", "D"), first=True),
        _table_page(("E", "F"), ("G", "H")),
    ])
    table, = doc.find_all("table")
    assert [[c.text for c in row] for row in table.rows] == [
        ["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]]
    assert all(c.provenance.page == 2 for row in table.rows[2:] for c in row)
    assert [type(elem).__name__ for elem in doc.sections[0].elements] == ["Paragraph", "Table"]
    assert [elem.text for elem in doc.sections[1].elements] == ["After"]
    assert to_markdown(doc).count("| A | B |") == 1
    assert to_markdown(doc).count("| E | F |") == 1


def test_body_below_first_table_prevents_merge(tmp_path):
    doc = _read_table_pages(tmp_path, [
        _table_page(("A", "B"), ("C", "D"), first=True, body_below=True),
        _table_page(("E", "F"), ("G", "H")),
    ])
    assert len(doc.find_all("table")) == 2


def test_body_above_second_table_prevents_merge(tmp_path):
    doc = _read_table_pages(tmp_path, [
        _table_page(("A", "B"), ("C", "D"), first=True),
        _table_page(("E", "F"), ("G", "H"), low_head=True, body_above=True),
    ])
    assert len(doc.find_all("table")) == 2


def test_different_column_grid_prevents_merge(tmp_path):
    doc = _read_table_pages(tmp_path, [
        _table_page(("A", "B"), ("C", "D"), first=True),
        _table_page(("E", "F", "G"), ("H", "I", "J"), cols=3),
    ])
    assert len(doc.find_all("table")) == 2


def test_repeated_header_is_dropped_when_tables_merge(tmp_path):
    doc = _read_table_pages(tmp_path, [
        _table_page(("A", "B"), ("C", "D"), first=True),
        _table_page(("A", "B"), ("E", "F")),
    ])
    table, = doc.find_all("table")
    assert [[c.text for c in row] for row in table.rows] == [
        ["A", "B"], ["C", "D"], ["E", "F"]]


def test_empty_middle_page_resets_continuation(tmp_path):
    doc = _read_table_pages(tmp_path, [
        _table_page(("A", "B"), ("C", "D"), first=True),
        b"BT /F1 10 Tf 10 100 Td (Middle) Tj ET",
        _table_page(("E", "F"), ("G", "H")),
    ])
    assert len(doc.find_all("table")) == 2


def test_mixed_horizontal_and_vertical_text_keeps_stream_order(tmp_path):
    content = (
        b"BT /F1 10 Tf 70 100 Td (Before) Tj ET "
        b"q 0 -1 1 0 90 700 cm BT /F1 10 Tf (Vertical) Tj ET Q "
        b"BT /F1 10 Tf 70 86 Td (After) Tj ET"
    )
    path = _write(tmp_path, "mixed.pdf", _build_pdf(_minimal_objects(content)))
    doc = PDFReader().read(path)
    assert [element.text for element in doc.sections[0].elements] == [
        "Before", "Vertical", "After"]
    assert not doc.errors


def _ruled(bottom, top, top_row, bottom_row, cols=2):
    """200pt 페이지용: (bottom, top) 사이의 2행 표와 셀 텍스트를 그린다."""
    content = b"0 %d 100 %d re S " % (bottom, top - bottom)
    for col in range(1, cols):
        x = round(100 * col / cols)
        content += b"%d %d m %d %d l S " % (x, bottom, x, top)
    middle = (bottom + top) // 2
    content += b"0 %d m 100 %d l S " % (middle, middle)
    for row, y in ((top_row, (middle + top) // 2), (bottom_row, (bottom + middle) // 2)):
        for col, label in enumerate(row):
            content += b"BT /F1 10 Tf %d %d Td (%s) Tj ET " % (
                round(100 * col / cols) + 5, y, label.encode("ascii"))
    return content


def _read_pages_with(tmp_path, contents, page_extra=""):
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [%s] /Count %d /MediaBox [0 0 200 200] "
           "/Resources << /Font << /F1 20 0 R >> >> >>" % (
               " ".join("%d 0 R" % (3 + i) for i in range(len(contents))), len(contents)),
        20: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, content in enumerate(contents):
        objects[3 + index] = "<< /Type /Page /Parent 2 0 R %s /Contents %d 0 R >>" % (page_extra, 10 + index)
        objects[10 + index] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content)
    return PDFReader().read(_write(tmp_path, "pages2.pdf", _build_pdf(objects)))


def test_tail_far_above_the_page_bottom_is_not_merged(tmp_path):
    # 표 아래 60pt 가 비어 있어도(본문 하단 60 → 표 하단 120) 다음 행이 들어갈 공간이 남았으면 연속이 아니다
    doc = _read_pages_with(tmp_path, [
        _ruled(120, 180, ("A", "B"), ("C", "D")),
        _ruled(80, 140, ("E", "F"), ("G", "H")) + b"BT /F1 10 Tf 10 40 Td (After) Tj ET ",
    ])
    assert len(doc.find_all("table")) == 2


def test_head_far_below_the_page_top_is_not_merged(tmp_path):
    doc = _read_pages_with(tmp_path, [
        _ruled(60, 120, ("A", "B"), ("C", "D")),
        _ruled(40, 100, ("E", "F"), ("G", "H")),
    ])
    assert len(doc.find_all("table")) == 2


def test_tail_is_the_lowest_table_not_the_last_drawn(tmp_path):
    # 1쪽: 아래쪽 3열 표를 먼저 그리고 위쪽 2열 표를 나중에 그린다 → 꼬리 후보는 위치상 아래 표(3열)
    lower = _ruled(60, 95, ("a", "b", "c"), ("d", "e", "f"), cols=3)
    upper = _ruled(100, 135, ("A", "B"), ("C", "D"))
    doc = _read_pages_with(tmp_path, [
        lower + upper,
        _ruled(80, 140, ("E", "F"), ("G", "H")) + b"BT /F1 10 Tf 10 40 Td (After) Tj ET ",
    ])
    assert len(doc.find_all("table")) == 3


def test_rotated_page_never_merges(tmp_path):
    doc = _read_pages_with(tmp_path, [
        _ruled(60, 120, ("A", "B"), ("C", "D")),
        _ruled(80, 140, ("E", "F"), ("G", "H")),
    ], page_extra="/Rotate 90")
    assert len(doc.find_all("table")) == 2


def test_huge_mediabox_integer_falls_back_without_losing_the_page(tmp_path):
    objects = _minimal_objects(b"BT /F1 12 Tf 72 720 Td (Hello) Tj ET")
    objects[3] = "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 1%s] /Contents 5 0 R >>" % ("0" * 400)
    doc = PDFReader().read(_write(tmp_path, "huge.pdf", _build_pdf(objects)))
    assert doc.sections[0].elements[0].text == "Hello"


def test_table_wholly_inside_the_header_zone_is_not_a_continuation_head(tmp_path):
    # 2쪽 표가 머리말 영역(상단 60pt) 안에만 있으면 본문 상단 거리가 음수라도 머리 후보가 아니다
    doc = _read_pages_with(tmp_path, [
        _ruled(60, 120, ("A", "B"), ("C", "D")),
        _ruled(160, 190, ("E", "F"), ("G", "H")),
    ])
    assert len(doc.find_all("table")) == 2


def test_table_wholly_inside_the_footer_zone_is_not_a_continuation_tail(tmp_path):
    doc = _read_pages_with(tmp_path, [
        _ruled(10, 50, ("A", "B"), ("C", "D")),
        _ruled(80, 140, ("E", "F"), ("G", "H")),
    ])
    assert len(doc.find_all("table")) == 2


def test_rotated_180_page_never_merges(tmp_path):
    doc = _read_pages_with(tmp_path, [
        _ruled(60, 120, ("A", "B"), ("C", "D")),
        _ruled(80, 140, ("E", "F"), ("G", "H")),
    ], page_extra="/Rotate 180")
    assert len(doc.find_all("table")) == 2
