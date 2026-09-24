import unicodedata

from dochan.model.document import Document, Paragraph, Section, TextRun
from scripts.compare_hwp_pairs import (
    find_pairs,
    format_match_stats,
    formatting_signature,
    summarize,
)


def _paragraph(*runs):
    return Paragraph(runs=[TextRun(text=text, bold=bold, italic=italic)
                           for text, bold, italic in runs])


def test_find_pairs_matches_nfc_and_nfd_and_multiple_directories(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    nfc = "가나다"
    nfd = unicodedata.normalize("NFD", nfc)
    (first / (nfc + ".hwpx")).touch()
    (first / (nfd + ".hwp")).touch()
    (first / "unpaired.hwpx").touch()
    (second / "other.hwpx").touch()
    (second / "other.hwp").touch()

    pairs = find_pairs([str(first), str(second)])

    assert [(name, hwpx.rsplit("/", 1)[-1], hwp.rsplit("/", 1)[-1])
            for name, hwpx, hwp in pairs] == [
        (nfc, nfc + ".hwpx", nfd + ".hwp"),
        ("other", "other.hwpx", "other.hwp"),
    ]


def test_formatting_signature_merges_runs_and_normalizes_text():
    para = _paragraph(
        ("  가", True, False), (" 나  ", True, False),
        ("", False, True), ("다", False, True),
    )
    assert formatting_signature(para) == (("가 나", True, False), ("다", False, True))


def test_format_match_counts_duplicate_body_text_as_multiset():
    answer = Document(sections=[Section(elements=[
        _paragraph(("  가 나 ", True, False)),
        _paragraph(("가 나", False, False)),
        _paragraph(("서로", False, True)),
    ])])
    candidate = Document(sections=[Section(elements=[
        _paragraph((unicodedata.normalize("NFD", "가 나"), True, False)),
        _paragraph(("가 나", True, False)),
        _paragraph(("없는", False, False)),
    ])])

    assert format_match_stats(answer, candidate) == (1, 2, 3, 3)
    assert format_match_stats(Document(), Document()) == (0, 0, 0, 0)


def test_summarize_all_keys_and_null_denominators():
    rows = {
        "a": {"tok_ratio": 0.8, "hwpx_tables": 2, "hwp_tables": 1,
              "signature_exact": 1, "cell_hit": 0.5, "hwpx_nested": 1,
              "hwp_nested": 1, "nested_exact": 1, "format_match": 0.5,
              "hwp_errors": ["ERR: broken"], "hwp_warnings": 2},
        "b": {"tok_ratio": 1.0, "hwpx_tables": 1, "hwp_tables": 1,
              "signature_exact": 1, "cell_hit": None, "hwpx_nested": 1,
              "hwp_nested": 0, "nested_exact": 0, "format_match": None,
              "hwp_errors": [], "hwp_warnings": 0},
        "c": {"error": "failed"},
    }

    assert summarize(rows) == {
        "pairs": 3, "mean_tok_ratio": 0.9, "min_tok_ratio": 0.8,
        "hwpx_tables": 3, "hwp_tables": 2, "signature_match": 0.6667,
        "mean_cell_hit": 0.5, "hwpx_nested": 2, "hwp_nested": 1,
        "nested_match": 0.5, "mean_format_match": 0.5,
        "pairs_with_errors": 2,
    }
    empty = summarize({})
    assert empty["pairs"] == empty["pairs_with_errors"] == 0
    for key in ("mean_tok_ratio", "min_tok_ratio", "signature_match",
                "mean_cell_hit", "nested_match", "mean_format_match"):
        assert empty[key] is None


def test_find_pairs_ignores_extension_case(tmp_path):
    (tmp_path / "문서.HWPX").write_bytes(b"")
    (tmp_path / "문서.HWP").write_bytes(b"")
    pairs = find_pairs([str(tmp_path)])
    assert [stem for stem, _, _ in pairs] == ["문서"]
    assert pairs[0][1].endswith("문서.HWPX") and pairs[0][2].endswith("문서.HWP")
