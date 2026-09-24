"""괘선 없는 PDF 표의 텍스트 정렬 탐지."""
from dochan.pdf.content import Fragment, assemble_lines
from dochan.pdf.text_tables import detect_text_tables


def _lines(rows):
    fragments = []
    for row, values in enumerate(rows):
        for col, value in enumerate(values):
            if value:
                fragments.append(Fragment(20 + 80 * col, 700 - 14 * row,
                                          20, 10, value, 5, order=len(fragments)))
    return assemble_lines(fragments)


def test_three_aligned_rows_become_three_column_table():
    lines = _lines([("Name", "Age", "City"), ("Ada", "30", "Seoul"),
                    ("Bob", "41", "Busan")])
    table, consumed = detect_text_tables(lines, page_number=4)[0]
    assert consumed == {0, 1, 2}
    assert [[cell.text for cell in row] for row in table.rows] == [
        ["Name", "Age", "City"], ["Ada", "30", "Seoul"], ["Bob", "41", "Busan"]]
    assert table.rows[0][0].provenance.page == 4
    assert table.rows[0][0].paragraphs[0].provenance.page == 4


def test_two_rows_do_not_form_table():
    assert detect_text_tables(_lines([("A", "B"), ("C", "D")])) == []


def test_single_segment_interrupts_run():
    lines = _lines([("A", "B"), ("C", "D"), ("Body", ""),
                    ("E", "F"), ("G", "H"), ("I", "J")])
    table, consumed = detect_text_tables(lines)[0]
    assert consumed == {3, 4, 5}
    assert lines[2].text == "Body"


def test_misaligned_candidate_ends_an_existing_table():
    fragments = [Fragment(x, 700 - 14 * row, 20, 10, text, 5,
                          order=row * 3 + col)
                 for row, values in enumerate((("A", "B", "C"),
                                               ("D", "E", "F"),
                                               ("G", "H", "I"),
                                               ("J", "K", "L")))
                 for col, (x, text) in enumerate(zip(
                     (20, 100, 180) if row < 3 else (20, 300, 380), values))]
    lines = assemble_lines(fragments)
    table, consumed = detect_text_tables(lines)[0]
    assert table.row_count == 3
    assert consumed == {0, 1, 2}
    assert lines[3].text == "J K L"


def test_repeated_bullets_do_not_form_table():
    lines = _lines([("•", "First"), ("•", "Second"), ("•", "Third")])
    assert detect_text_tables(lines) == []


def test_each_row_must_hit_two_distinct_columns():
    fragments = [Fragment(x, y, 0.5, 10, text, 5, order=index)
                 for index, (x, y, text) in enumerate((
                     (20, 700, "A"), (21, 700, "B"), (80, 700, "one"),
                     (20, 686, "C"), (100, 686, "two"),
                     (20, 672, "D"), (100, 672, "three")))]
    assert detect_text_tables(assemble_lines(fragments)) == []


def test_21_segments_are_skipped():
    fragments = [Fragment(i * 30, 700, 2, 10, str(i), 5, order=i)
                 for i in range(21)]
    lines = assemble_lines(fragments)
    assert detect_text_tables(lines * 3) == []


def test_row_and_group_caps():
    lines = _lines([(str(i), str(i + 1)) for i in range(501)])
    detected = detect_text_tables(lines)
    assert detected and all(table.row_count <= 500 for table, _ in detected)
    assert detect_text_tables(lines * 10) == []
