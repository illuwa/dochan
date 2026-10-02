import json
import unicodedata

from dochan.conversion import AssetRef, Provenance
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.header_footer import Comment, Footnote, HeaderFooter
from dochan.model.image import Image
from dochan.model.table import Cell, Table
from scripts.compare_office_pairs import (
    compare_documents, find_pairs, main, summarize,
)


def para(text, bold=False, italic=False, path="", link=""):
    return Paragraph(runs=[TextRun(text=text, bold=bold, italic=italic, link=link)],
                     provenance=Provenance(path=path))


def test_find_pairs_all_formats_normalization_extensions_dedup_and_collision(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for directory in (first, second):
        for ext in ("DOC", "docx", "ppt", "PPTX", "xls", "xlsx"):
            stem = unicodedata.normalize("NFD" if ext in ("DOC", "ppt", "xls") else "NFC", "한글")
            (directory / (stem + "." + ext)).touch()
    (first / "lonely.doc").touch()
    pairs = find_pairs([str(first), str(second), str(first)])
    assert len(pairs) == 6
    assert len({key for key, _, _ in pairs}) == 6
    assert {p.rsplit(".", 1)[1].lower() for _, p, _ in pairs} == {"docx", "pptx", "xlsx"}


def test_all_metrics_recurse_and_do_not_double_count_image_assets():
    table = Table(rows=[[Cell(paragraphs=[para("cell", bold=True)], col_span=2),
                         Cell(row_span=0, col_span=0)]], caption=[para("chart", path="xl/charts/chart1.xml")])
    answer = Document(source_format="xlsx", sections=[Section(elements=[
        table, Image(filename="picture.png", image_data=b"png", alt_text="label"),
        Footnote(paragraphs=[para("foot text")]),
        Footnote(type="endnote", paragraphs=[para("end text")]),
        Comment(paragraphs=[para("comment text")]),
        HeaderFooter(paragraphs=[para("head")]),
        HeaderFooter(type="footer", paragraphs=[para("foot")]),
        para("[bookmark: here] label <https://example.test>"),
        para("speaker text", path="ppt/notesSlides/notesSlide1.xml"),
        para("[comment: inline]"),
    ], provenance=Provenance(sheet="one", slide=1))],
        assets=[AssetRef(source_path="xl/media/picture.png", metadata={"kind": "image"})])
    row = compare_documents(answer, answer)
    for metric in row["metrics"].values():
        if metric["answer"]:
            assert metric["ratio"] == 1
        else:
            assert metric["ratio"] is None
    assert row["metrics"]["images"]["answer"] == 1
    assert row["metrics"]["image_bytes"]["answer"] == 1
    assert row["metrics"]["cells"]["answer"] == 1
    assert row["metrics"]["merged_cells"]["answer"] == 1
    assert row["metrics"]["comments"]["answer"] == 2
    assert row["metrics"]["charts"]["answer"] == 1
    assert row["metrics"]["slides"]["answer"] == row["metrics"]["sheets"]["answer"] == 1
    assert row["metrics"]["hyperlinks"]["set_equal"] is True
    assert row["texts"]["speaker_notes"]["answer"] == ["speaker text"]


def test_null_denominators_missing_features_extra_urls_and_duplicate_runs():
    empty = compare_documents(Document(), Document())
    assert empty["tok_ratio"] is None
    assert all(m["ratio"] is None for m in empty["metrics"].values())
    answer = Document(sections=[Section(elements=[para("same", True), para("same", True)])])
    candidate = Document(sections=[Section(elements=[para("same", True), para("same"),
                                                      para("extra", link="https://extra.test")])])
    row = compare_documents(answer, candidate)
    assert row["metrics"]["format_runs"]["ratio"] == 0.5
    assert row["metrics"]["hyperlinks"]["ratio"] is None
    assert row["metrics"]["hyperlinks"]["set_equal"] is False
    assert row["metrics"]["hyperlinks"]["candidate"] == 1


def test_run_partition_does_not_change_score_and_reference_without_bytes_counts():
    answer = Document(sections=[Section(elements=[Paragraph(runs=[TextRun("a", bold=True), TextRun("b", bold=True)])])],
                      assets=[AssetRef(source_path="media/missing.png", metadata={"kind": "image", "missing": True})])
    candidate = Document(sections=[Section(elements=[para("ab", True)])])
    row = compare_documents(answer, candidate)
    assert row["metrics"]["format_runs"]["ratio"] == 1
    assert row["metrics"]["images"]["answer"] == 1
    assert row["metrics"]["image_bytes"]["ratio"] is None


def test_threshold_and_parser_errors_are_visible_and_excluded_from_summary():
    good = compare_documents(Document(sections=[Section(elements=[para("a b c")])]),
                             Document(sections=[Section(elements=[para("a b c")])]))
    bad = compare_documents(Document(sections=[Section(elements=[para("a b c")])]),
                            Document(sections=[Section(elements=[para("x y z")])]))
    broken = compare_documents(Document(errors=["ERR: encrypted"]), Document())
    summary = summarize({"good": good, "bad": bad, "broken": broken}, min_token_ratio=0.8)
    assert (summary["pairs"], summary["eligible_pairs"], summary["below_threshold"], summary["parse_failures"]) == (3, 1, 1, 1)
    assert summary["mean_tok_ratio"] == 1
    assert summarize({})["mean_tok_ratio"] is None


def test_main_json_and_human_summary_keep_failed_pairs(tmp_path, monkeypatch, capsys):
    (tmp_path / "sample.doc").touch()
    (tmp_path / "sample.docx").touch()
    monkeypatch.setattr("scripts.compare_office_pairs.compare_pair", lambda *args: {"error": "failed"})
    output = tmp_path / "result.json"
    assert main([str(tmp_path), "--output", str(output)]) == 0
    data = json.loads(output.read_text())
    assert data["summary"]["parse_failures"] == 1
    assert len(data["pairs"]) == 1
    assert "1" in capsys.readouterr().out


def test_cycle_and_nested_tables_have_finite_metrics():
    table = Table(rows=[[Cell(paragraphs=[])]])
    table.rows[0][0].paragraphs.append(table)
    doc = Document(sections=[Section(elements=[table])])
    row = compare_documents(doc, doc)
    assert row["metrics"]["tables"]["answer"] == 1


def test_styles_in_missing_text_stay_in_answer_denominator():
    answer = Document(sections=[Section(elements=[para("kept", True), para("lost", True)])])
    candidate = Document(sections=[Section(elements=[para("kept", True)])])
    assert compare_documents(answer, candidate)["metrics"]["format_runs"]["ratio"] == 0.5


def test_multiline_comments_repeated_image_placements_and_legacy_ppt_comments():
    answer = Document(sections=[Section(elements=[
        para("[comment: Author:\nactual text]"),
        Image(filename="same.png", image_data=b"a"),
        Image(filename="same.png", image_data=b"a"),
    ])], assets=[AssetRef(source_path="media/same.png", metadata={"kind": "image"})])
    candidate = Document(sections=[Section(elements=[
        para("Comments", path="PowerPoint Document#slide1#comments"),
        para("Author: actual text", path="PowerPoint Document#slide1#comments"),
    ])])
    candidate.sections[0].elements[0].heading_level = 2
    row = compare_documents(answer, candidate)
    assert row["metrics"]["comments"]["ratio"] == 1
    assert row["metrics"]["images"]["answer"] == 2
    assert row["metrics"]["image_references"]["answer"] == 1
    assert row["metrics"]["image_bytes"]["answer"] == 2


def test_verified_name_only_pair_exclusion_preserves_raw_rows():
    row = compare_documents(Document(sections=[Section(elements=[para("a")])]),
                            Document(sections=[Section(elements=[para("b")])]))
    rows = {"different.doc": row, "parser-gap.xls": row}
    summary = summarize(rows, exclude_pairs=["different.doc"])
    assert summary["pairs"] == 2 and summary["eligible_pairs"] == 1
    assert summary["excluded_pairs"] == 1
    assert summary["excluded_pair_keys"] == ["different.doc"]
    assert len(rows) == 2 and "different.doc" in rows
