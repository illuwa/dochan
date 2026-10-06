"""scripts/probe_markdown_run_merge.py — 기준 규칙 재현과 대조 집계."""
import pytest

from dochan.conversion import Provenance
from dochan.model.document import TextRun
from scripts.probe_markdown_run_merge import baseline_runs, compare_renderings, stripped_words, summarize


def test_baseline_merges_only_ppt_and_pdf_runs():
    plain = [TextRun(text="가", bold=True), TextRun(text="나", bold=True)]
    assert [run.text for run in baseline_runs(plain)] == ["가", "나"]
    source = Provenance(source_format="pdf", page=1)
    pdf = [TextRun(text="가", bold=True, provenance=source), TextRun(text="나", bold=True, provenance=source)]
    assert [run.text for run in baseline_runs(pdf)] == ["가나"]


def test_stripped_words_ignore_markers_and_escape_backslashes():
    assert stripped_words("**가****나** <u>다</u>~~라~~ \\* 마") == stripped_words("**가나** <u>다</u>~~라~~ * 마")
    assert stripped_words("**가** 나") != stripped_words("**가** 다")


def test_compare_renderings_counts_adjacency_and_literal_stars():
    markdown_it = pytest.importorskip("markdown_it")
    parser = markdown_it.MarkdownIt("commonmark")
    record = compare_renderings("**제1조(목적)****이 규칙은**", "**제1조(목적)이 규칙은**", parser)
    assert record["changed"] and record["text_equal"]
    assert (record["adjacent_before"], record["adjacent_after"]) == (1, 0)
    # 구두점 뒤 글자 앞의 **** 는 닫지 못해 별표가 글자로 남는다
    assert record["literal_before"] > 0 and record["literal_after"] == 0
    assert compare_renderings("같음", "같음", parser) == {"changed": False}


def test_summarize_flags_text_changes_and_more_literal_stars():
    records = {
        "a.hwpx": {"changed": True, "text_equal": True, "adjacent_before": 2, "adjacent_after": 0,
                   "literal_before": 4, "literal_after": 0},
        "b.hwpx": {"changed": True, "text_equal": False, "adjacent_before": 1, "adjacent_after": 0},
        "c.docx": {"changed": True, "text_equal": True, "adjacent_before": 0, "adjacent_after": 0,
                   "literal_before": 0, "literal_after": 2},
        "d.docx": {"changed": False},
        "e.pdf": {"failure": "timeout"},
    }
    summary, flagged = summarize(records)
    assert summary["hwpx"]["changed"] == 2 and summary["hwpx"]["literal_fewer"] == 1
    assert summary["docx"]["files"] == 2 and summary["docx"]["literal_more"] == 1
    assert summary["pdf"]["failures"] == 1
    assert flagged == ["b.hwpx", "c.docx"]
