import unicodedata

import pytest

from dochan.model.document import Document, Paragraph, Section, TextRun
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
        assert recorded == [("사회의", "운영에", True)]
    assert layout.JOIN_OBSERVER is previous_hook
