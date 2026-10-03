"""표 서명 진단기의 합성 문서 분류 검증."""
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.table import Cell, Table
from scripts.probe_pdf_table_mismatch import classify_documents


def _table(rows, page=None):
    from dochan.conversion import Provenance

    cells = []
    for r, row in enumerate(rows):
        cells.append([Cell(row=r, col=c, paragraphs=[Paragraph(runs=[TextRun(text=value)])],
                           provenance=Provenance(source_format="pdf", page=page))
                      for c, value in enumerate(row)])
    return Table(rows=cells)


def test_classifies_split_row_change_and_unmatched_without_exposing_text():
    answer = Document(sections=[Section(elements=[
        _table([["north one", "north two", "north three"],
                ["south one", "south two", "south three"],
                ["west one", "west two", "west three"],
                ["east one", "east two", "east three"]]),
        _table([["apple red", "berry blue"], ["cherry green", "date gold"]]),
        _table([["unique missing", "another missing"]]),
    ])])
    candidate = Document(sections=[Section(elements=[
        _table([["north one", "north two", "north three"],
                ["south one", "south two", "south three"]], page=1),
        _table([["west one", "west two", "west three"],
                ["east one", "east two", "east three"]], page=2),
        _table([["apple red", "berry blue"], ["cherry green", "date gold"],
                ["", ""]], page=2),
    ])])
    result = classify_documents(answer, candidate)
    assert result["baseline_exact"] == 0
    assert result["categories"] == {
        "page_split": 1, "row_count": 1, "not_found": 1,
    }
    assert result["pdf_only"] == 0
    assert "north one" not in str(result)
