import json

from scripts.summarize_competitive_index import render_markdown_summary


def test_render_markdown_summary_lists_competitive_rows_and_candidates():
    index = {
        "corpus": "/tmp/corpus",
        "competitors": [
            {
                "competitor": "markitdown",
                "ok": True,
                "output": "/tmp/out/markitdown.json",
                "report_summary": {
                    "file_count": 3,
                    "format_summary": [
                        {
                            "converter": "dochan",
                            "format": "docx",
                            "median_json_asset_count": 1,
                            "median_json_run_provenance_count": 59,
                        }
                    ],
                    "competitive_summary": [
                        {
                            "format": "docx",
                            "competitor": "markitdown",
                            "speedup_vs_competitor": 2.5,
                            "accuracy_delta": 0.25,
                            "success_rate_delta": 0.0,
                            "median_json_asset_count_delta": 1,
                            "median_json_run_provenance_count_delta": 12,
                        }
                    ],
                    "improvement_candidates": [],
                },
            },
            {
                "competitor": "docling",
                "ok": True,
                "output": "/tmp/out/docling.json",
                "report_summary": {
                    "file_count": 3,
                    "competitive_summary": [],
                    "improvement_candidates": [
                        {
                            "format": "xlsx",
                            "competitor": "docling",
                            "worst_gap_score": 0.7,
                            "reasons": ["dochan_accuracy_trails_by=0.650"],
                        }
                    ],
                    "file_improvement_candidates": [
                        {
                            "file": "/tmp/corpus/xlsx/book.xlsx",
                            "format": "xlsx",
                            "competitor": "docling",
                            "worst_gap_score": 0.1,
                            "reasons": ["dochan_table_rows_trail_by=2"],
                            "dochan_output_path": "/tmp/out/dochan/book.xlsx.run1.md",
                            "competitor_output_path": "/tmp/out/docling/book.xlsx.run1.md",
                        }
                    ],
                },
            },
        ],
    }

    markdown = render_markdown_summary(index)

    assert "# dochan Competitive Index Summary" in markdown
    assert "| Competitor | Format | Speedup | Accuracy Delta | Success Delta | JSON Assets Delta | JSON Run Provenance Delta |" in markdown
    assert "| markitdown | docx | 2.50x | +0.250 | +0.000 | +1.000 | +12.000 |" in markdown
    assert "## dochan JSON Profile" in markdown
    assert "| markitdown | docx | 1.000 | 59.000 |" in markdown
    assert "| docling | xlsx | 0.700 | dochan_accuracy_trails_by=0.650 |" in markdown
    assert "| Competitor | Format | File | Gap Score | Reasons | dochan Output | Competitor Output |" in markdown
    assert "| docling | xlsx | /tmp/corpus/xlsx/book.xlsx | 0.100 | dochan_table_rows_trail_by=2 | /tmp/out/dochan/book.xlsx.run1.md | /tmp/out/docling/book.xlsx.run1.md |" in markdown


def test_render_markdown_summary_reports_failed_competitor():
    index = {
        "corpus": "/tmp/corpus",
        "competitors": [
            {
                "competitor": "docling",
                "ok": False,
                "error": "CalledProcessError(...)",
                "output": "/tmp/out/docling.json",
                "report_summary": {},
            }
        ],
    }

    markdown = render_markdown_summary(index)

    assert "| docling | false | CalledProcessError(...) |" in markdown


def test_render_markdown_summary_accepts_json_roundtrip():
    index = json.loads(json.dumps({"corpus": "/tmp/corpus", "competitors": []}))

    markdown = render_markdown_summary(index)

    assert "Corpus: `/tmp/corpus`" in markdown
