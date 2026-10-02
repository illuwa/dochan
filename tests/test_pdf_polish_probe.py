"""PDF polish 프로브가 회귀를 분모에서 누락하지 않는지 검사한다."""
from scripts.probe_pdf_polish import compare_encryption, compare_tables, missing_characters


def test_polish_probe_counts_repeated_characters_and_ignores_order_whitespace():
    assert missing_characters("aba 12", "2a1\nba") == {}
    assert missing_characters("aba 12", "ab 12") == {"a": 1}


def test_polish_probe_detects_decryption_and_empty_output_regressions():
    baseline = {"encrypted": True, "decrypt_ok": True, "text": "Issue 7665"}
    head = {"encrypted": True, "decrypt_ok": False, "text": ""}
    assert compare_encryption(baseline, head)["regressions"] == ["decrypt_failed", "text_became_empty"]
    head["decrypt_ok"] = True
    assert compare_encryption(baseline, head)["regressions"] == ["text_became_empty"]


def test_polish_probe_keeps_parser_failures_as_unverified():
    result = compare_encryption({"encrypted": True, "decrypt_ok": True, "text": "a"}, {"error": "timeout"})
    assert result["status"] == "unverified"
    assert result["regressions"] == ["candidate_unreadable"]
    assert compare_encryption({"error": "parse"}, {"encrypted": False})["status"] == "unverified"


def test_polish_probe_checks_tables_against_both_baseline_and_mode_off():
    result = compare_tables({"text": "aba"}, {"text": "ab"}, {"text": "abc"})
    assert result["baseline_missing"] == {"a": 1}
    assert result["mode_off_missing"] == {"c": 1}
    assert result["status"] == "regression"
    assert compare_tables({"text": "abc"}, {"error": "timeout"}, {"text": "abc"})["status"] == "unverified"


def test_polish_probe_missing_sample_is_unverified(tmp_path):
    from pathlib import Path
    from scripts.probe_pdf_polish import run_one
    repo = Path(__file__).resolve().parents[1]
    result = run_one(repo, tmp_path / "absent.pdf", "tables", 5)
    assert result["error"].startswith("ERR:")
    assert compare_tables(result, result, result)["status"] == "unverified"


def test_polish_probe_rejects_empty_denominators(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    manifest = tmp_path / "manifest.txt"
    manifest.write_text("sample.pdf\n")
    command = [sys.executable, str(repo / "scripts/probe_pdf_polish.py"), str(tmp_path),
               "--baseline-repo", str(repo), "--table-manifest", str(manifest),
               "--output", str(tmp_path / "out.json")]
    empty_corpus = subprocess.run(command, capture_output=True, text=True)  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
    assert empty_corpus.returncode == 2
    assert "corpus contains no PDF" in empty_corpus.stderr
    (tmp_path / "sample.pdf").write_bytes(b"%PDF-1.4\n")
    manifest.write_text("")
    empty_manifest = subprocess.run(command, capture_output=True, text=True)  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
    assert empty_manifest.returncode == 2
    assert "manifest contains no PDF" in empty_manifest.stderr


def test_polish_probe_body_text_excludes_annotation_metadata():
    from dochan.model.document import Document, Paragraph, Section, TextRun
    from dochan.model.header_footer import Comment
    from dochan.conversion import Provenance
    from scripts.probe_pdf_polish import _model_text
    doc = Document(sections=[Section(elements=[
        Paragraph(runs=[TextRun(text="body", link="https://example.test")]),
        Paragraph(runs=[TextRun(text="<https://example.test>")],
                  provenance=Provenance(source_format="pdf", path="annots")),
        Comment(paragraphs=[Paragraph(runs=[TextRun(text="review")])]),
    ])])
    assert _model_text(doc) == ("body", 0)
