import unicodedata

import pytest

from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.header_footer import HeaderFooter
from dochan.model.table import Cell, Table
from scripts.compare_pdf_pairs import (
    cell_hit_rate,
    normalize_text,
    structure_matches,
    summarize,
    table_signature,
    table_stats,
    token_ratio,
)


def _table(rows, cols, merged=()):
    grid = [[Cell(row=r, col=c) for c in range(cols)] for r in range(rows)]
    for (r, c, rs, cs) in merged:
        grid[r][c].row_span, grid[r][c].col_span = rs, cs
        for rr in range(r, r + rs):
            for cc in range(c, c + cs):
                if (rr, cc) != (r, c):
                    grid[rr][cc].row_span = grid[rr][cc].col_span = 0
    return Table(rows=grid)


def test_normalize_and_token_ratio_ignore_whitespace_and_unicode_form():
    assert normalize_text("  가나 다  \n라 ") == "가나 다 라"
    assert token_ratio("제1조 목적", "제1조\n목적") == 1.0
    assert 0 < token_ratio("제1조 목적 이 규칙", "제1조 구성") < 1
    assert token_ratio("제1조 목적", "제2조 구성") == 0.0


def test_table_signature_and_stats_count_only_visible_cells():
    table = _table(2, 3, merged=[(0, 0, 1, 3)])
    table.rows[0][0].paragraphs = [Paragraph(runs=[TextRun(text="머리")])]
    table.rows[1][1].paragraphs = [Paragraph(runs=[TextRun(text=" 값 ")])]
    assert table_signature(table) == (2, 3, ((1, 3),))
    doc = Document()
    doc.sections.append(Section(elements=[table]))
    signatures, cells = table_stats(doc)
    assert signatures == [(2, 3, ((1, 3),))]
    assert cells == ["머리", "값"]
    assert cell_hit_rate(["머리", "값", "없음"], cells) == 2 / 3
    assert cell_hit_rate([], cells) is None


def test_structure_matches_separates_dims_from_merge_agreement():
    answer = [(2, 3, ((1, 3),)), (2, 2, ()), (3, 3, ((2, 1),))]
    candidate = [(2, 3, ((1, 3),)), (2, 2, ()), (3, 3, ())]
    exact, merged_total, merged_dims, merged_exact = structure_matches(answer, candidate)
    assert (exact, merged_total, merged_dims, merged_exact) == (2, 2, 2, 1)


def test_summarize_reports_rates_and_handles_errors():
    rows = {
        "a": {"tok_ratio": 0.9, "hwpx_tables": 2, "pdf_tables": 2, "cell_hit": 0.5,
              "signature_exact": 1, "merged_tables": 1, "merged_dims_matched": 1, "merged_exact": 1},
        "b": {"tok_ratio": 0.7, "hwpx_tables": 2, "pdf_tables": 1, "cell_hit": None,
              "signature_exact": 1, "merged_tables": 1, "merged_dims_matched": 0, "merged_exact": 0},
        "c": {"error": "boom"},
    }
    summary = summarize(rows)
    assert summary["pairs"] == 3
    assert summary["mean_tok_ratio"] == 0.8 and summary["min_tok_ratio"] == 0.7
    assert summary["mean_cell_hit"] == 0.5
    assert summary["signature_match"] == 0.5
    assert summary["merge_match"] == 1.0
    assert summarize({})["mean_tok_ratio"] is None
    assert summary["mean_hf_hit"] is None and summary["docs_with_hf"] == 0


def test_header_footer_metric_normalizes_and_ignores_page_numbers():
    from scripts.compare_pdf_pairs import header_footer_texts

    doc = Document(sections=[Section(elements=[
        HeaderFooter(type="header", paragraphs=[Paragraph(runs=[TextRun(text="  가나  다 ")])]),
        HeaderFooter(type="footer", paragraphs=[Paragraph(runs=[TextRun(text="Page 3")])]),
    ])])
    assert header_footer_texts(doc) == {"가나 다"}
    assert summarize({"a": {"hf_hit": 1.0}, "b": {"hf_hit": 0.5},
                      "c": {"hf_hit": None}})["mean_hf_hit"] == 0.75
    assert summarize({"a": {"hf_hit": 1.0}, "b": {"hf_hit": None}})["docs_with_hf"] == 1


def test_header_footer_metric_matches_multiline_content_by_line():
    from scripts.compare_pdf_pairs import header_footer_texts

    hwpx = Document(sections=[Section(elements=[HeaderFooter(type="header", paragraphs=[
        Paragraph(runs=[TextRun(text="ACME")]),
        Paragraph(runs=[TextRun(text="Confidential")]),
    ])])])
    pdf = Document(sections=[Section(elements=[HeaderFooter(type="header", paragraphs=[
        Paragraph(runs=[TextRun(text="ACME\nConfidential")]),
    ])])])
    expected = header_footer_texts(hwpx)
    actual = header_footer_texts(pdf)
    assert expected == actual == {"ACME", "Confidential"}
    hf_hit = round(len(expected & actual) / len(expected), 4)
    assert hf_hit == 1.0


def test_join_accuracy_labels_only_unambiguous_normalized_contexts():
    from scripts.compare_pdf_pairs import join_accuracy

    answer = unicodedata.normalize("NFD", "이사회의\n운영에 국가안보 같은문장 같은 문장")
    joins = [("사회의", "운영에", True), ("국가안", "보", False),
             ("사회의", "운영에", False), ("같은", "문장", True),
             ("없는", "문장", False)]
    accuracy, labeled = join_accuracy(answer, joins)
    assert labeled == 3
    assert accuracy == pytest.approx(2 / 3)
    assert join_accuracy(answer, []) == (None, 0)
    assert join_accuracy(answer, [("같은", "문장", False)]) == (None, 0)


def test_summarize_weights_accuracy_by_labeled_joins():
    summary = summarize({"a": {"join_accuracy": 1.0, "labeled_joins": 1},
                         "b": {"join_accuracy": 0.5, "labeled_joins": 3},
                         "c": {"join_accuracy": None, "labeled_joins": 0},
                         "d": {"error": "failed"}})
    assert summary["join_accuracy"] == 0.625
    assert summary["labeled_joins"] == 4
    assert summarize({})["join_accuracy"] is None
    assert summarize({})["labeled_joins"] == 0


@pytest.mark.parametrize("fail", [False, True])
def test_compare_pair_observes_hangul_and_restores_previous_hook(monkeypatch, fail):
    import dochan
    from dochan.pdf import layout
    from scripts import compare_pdf_pairs

    def previous_hook(*args):
        pass

    monkeypatch.setattr(layout, "JOIN_OBSERVER", previous_hook)

    class TinyDocument:
        doc = Document()
        errors = []

        def __init__(self, path):
            if path == "candidate.pdf":
                layout.JOIN_OBSERVER("이사회의", "운영에 관한", True)
                layout.JOIN_OBSERVER("abc", "def", True)
                if fail:
                    raise ValueError("broken PDF")

        def to_plain_text(self):
            return "이사회의 운영에 관한"

    recorded = []
    label_joins = compare_pdf_pairs.join_accuracy

    def measure(answer, joins):
        recorded.extend(joins)
        return label_joins(answer, joins)

    monkeypatch.setattr(dochan, "Dochan", TinyDocument)
    monkeypatch.setattr(compare_pdf_pairs, "join_accuracy", measure)
    if fail:
        with pytest.raises(ValueError, match="broken PDF"):
            compare_pdf_pairs.compare_pair("answer.hwpx", "candidate.pdf")
    else:
        row = compare_pdf_pairs.compare_pair("answer.hwpx", "candidate.pdf")
        assert row["join_accuracy"] == 1.0 and row["labeled_joins"] == 1
        assert row["hwpx_hf"] == row["pdf_hf"] == []
        assert row["hf_hit"] is None
        assert recorded == [("사회의", "운영에", True)]
    assert layout.JOIN_OBSERVER is previous_hook


def test_nested_signatures_report_only_tables_inside_cells():
    from scripts.compare_pdf_pairs import nested_signatures

    inner = _table(1, 2)
    outer = _table(2, 2)
    outer.rows[0][0].paragraphs = [Paragraph(runs=[TextRun(text="머리")]), inner]
    doc = Document()
    doc.sections.append(Section(elements=[outer, _table(3, 3)]))
    assert nested_signatures(doc) == [(1, 2, ())]
    # 깊이 2 도 센다
    innermost = _table(1, 1)
    inner.rows[0][1].paragraphs = [innermost]
    assert sorted(nested_signatures(doc)) == [(1, 1, ()), (1, 2, ())]


def test_summarize_reports_nested_match_and_counts():
    rows = {
        "a": {"tok_ratio": 0.9, "hwpx_tables": 2, "pdf_tables": 2, "cell_hit": 0.5,
              "signature_exact": 1, "merged_tables": 0, "merged_dims_matched": 0, "merged_exact": 0,
              "hwpx_nested": 3, "pdf_nested": 4, "nested_exact": 2},
        "b": {"tok_ratio": 0.8, "hwpx_tables": 1, "pdf_tables": 1, "cell_hit": None,
              "signature_exact": 1, "merged_tables": 0, "merged_dims_matched": 0, "merged_exact": 0,
              "hwpx_nested": 1, "pdf_nested": 0, "nested_exact": 0},
    }
    summary = summarize(rows)
    assert summary["hwpx_nested"] == 4 and summary["pdf_nested"] == 4
    assert summary["nested_match"] == 0.5
    assert summarize({})["nested_match"] is None


def test_compare_pair_passes_text_table_option_only_when_enabled(monkeypatch):
    import dochan
    from scripts import compare_pdf_pairs

    calls = []

    class TinyDocument:
        doc = Document()
        errors = []

        def __init__(self, path, **kwargs):
            calls.append((path, kwargs))

        def to_plain_text(self):
            return "text"

    monkeypatch.setattr(dochan, "Dochan", TinyDocument)
    compare_pdf_pairs.compare_pair("answer.hwpx", "candidate.pdf", pdf_text_tables=True)
    assert calls == [("answer.hwpx", {}),
                     ("candidate.pdf", {"pdf_text_tables": True})]


def test_main_forwards_pdf_text_tables_flag(monkeypatch, capsys):
    from scripts import compare_pdf_pairs

    calls = []
    monkeypatch.setattr(compare_pdf_pairs, "find_pairs",
                        lambda _directory: [("sample", "answer.hwpx", "candidate.pdf")])

    def fake_compare(_hwpx, _pdf, pdf_text_tables=False):
        calls.append(pdf_text_tables)
        return {"pdf_tables": 1}

    monkeypatch.setattr(compare_pdf_pairs, "compare_pair", fake_compare)
    assert compare_pdf_pairs.main(["pairs", "--pdf-text-tables"]) == 0
    assert calls == [True]
    capsys.readouterr()
