import sys
from types import SimpleNamespace

from dochan.conversion import AssetRef
from dochan.model.document import Document, Section
from dochan.quality.batch_validate import _report_to_dict, _score_summary
from dochan.quality.comparator import compare_with_gt
from dochan.quality.cross_validator import (
    CrossValidationReport,
    CrossValidator,
    PairComparison,
    SourceResult,
)


class _FakePage:
    def __init__(self, text, fail_tables=False, tables=None):
        self._text = text
        self._fail_tables = fail_tables
        self._tables = [] if tables is None else tables
        self.images = []

    def extract_text(self):
        return self._text

    def extract_tables(self):
        if self._fail_tables:
            raise RuntimeError("table extraction failed")
        return self._tables


class _FakePDF:
    def __init__(self, pages):
        self.pages = pages
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.closed = True


def _install_pdfplumber(monkeypatch, page_texts, fail_page=None, page_tables=None):
    page_tables = page_tables or {}
    pdf = _FakePDF(
        [
            _FakePage(
                text,
                fail_tables=index == fail_page,
                tables=page_tables.get(index),
            )
            for index, text in enumerate(page_texts)
        ]
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=lambda path: pdf))
    monkeypatch.setattr(
        "dochan.quality.cross_validator.os.path.getsize",
        lambda path: 1,
    )
    return pdf


def test_pdf_extraction_preserves_unique_first_and_last_lines_on_three_pages(monkeypatch):
    pdf = _install_pdfplumber(
        monkeypatch,
        [
            "Unique first one\nBody one\nUnique last one",
            "Unique first two\nBody two\nUnique last two",
            "Unique first three\nBody three\nUnique last three",
        ],
    )

    result = CrossValidator()._extract_pdfplumber("sample.pdf")

    assert result.error == ""
    assert pdf.closed is True
    for suffix in ("one", "two", "three"):
        assert f"Unique first {suffix}" in result.raw_text
        assert f"Unique last {suffix}" in result.raw_text


def test_pdf_extraction_uses_ceil_threshold_and_removes_only_repeated_edges(monkeypatch):
    page_texts = []
    for index in range(7):
        header = "Two-use header" if index < 2 else f"Unique header {index}"
        footer = "Three-use footer" if index < 3 else f"Unique footer {index}"
        page_texts.append(f"{header}\nBody {index}\n{footer}")
    _install_pdfplumber(monkeypatch, page_texts)

    result = CrossValidator()._extract_pdfplumber("sample.pdf")

    assert result.raw_text.count("Two-use header") == 2
    assert "Three-use footer" not in result.raw_text
    assert "Unique header 3" in result.raw_text
    assert "Unique footer 3" in result.raw_text


def test_pdf_extraction_closes_document_when_page_processing_fails(monkeypatch):
    pdf = _install_pdfplumber(
        monkeypatch,
        ["Header\nBody\nFooter"],
        fail_page=0,
    )

    result = CrossValidator()._extract_pdfplumber("sample.pdf")

    assert result.error == "table extraction failed"
    assert pdf.closed is True


def test_pdf_extraction_rejects_input_above_byte_limit_before_open(monkeypatch):
    pdf = _install_pdfplumber(monkeypatch, ["unused"])
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_PDF_BYTES",
        16,
    )
    monkeypatch.setattr(
        "dochan.quality.cross_validator.os.path.getsize",
        lambda path: 17,
    )

    result = CrossValidator()._extract_pdfplumber("oversized.pdf")

    assert result.error == "PDF input exceeds the 16-byte limit"
    assert result.raw_text == ""
    assert result.clean_text == ""
    assert result.table_count == 0
    assert result.image_count == 0
    assert pdf.closed is False


def test_pdf_extraction_rejects_page_count_above_limit(monkeypatch):
    pdf = _install_pdfplumber(monkeypatch, ["one", "two", "three"])
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_PDF_PAGES",
        2,
    )

    result = CrossValidator()._extract_pdfplumber("too-many-pages.pdf")

    assert result.error == "PDF page count exceeds the 2-page limit"
    assert result.raw_text == ""
    assert result.clean_text == ""
    assert pdf.closed is True


def test_pdf_extraction_rejects_cumulative_text_above_byte_limit(monkeypatch):
    _install_pdfplumber(monkeypatch, ["1234", "5678"])
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_PDF_TEXT_BYTES",
        9,
    )

    result = CrossValidator()._extract_pdfplumber("too-much-text.pdf")

    assert result.error == "PDF extracted text exceeds the 9-byte limit"
    assert result.raw_text == ""
    assert result.clean_text == ""
    assert result.char_count == 0


def test_pdf_extraction_accepts_text_at_exact_byte_limit(monkeypatch):
    _install_pdfplumber(monkeypatch, ["1234", "5678"])
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_PDF_TEXT_BYTES",
        10,
    )

    result = CrossValidator()._extract_pdfplumber("bounded-text.pdf")

    assert result.error == ""
    assert result.raw_text == "1234\n\n5678"


def test_pdf_extraction_counts_utf8_bytes_in_text_budget(monkeypatch):
    _install_pdfplumber(monkeypatch, ["가"])
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_PDF_TEXT_BYTES",
        2,
    )

    result = CrossValidator()._extract_pdfplumber("multibyte-text.pdf")

    assert result.error == "PDF extracted text exceeds the 2-byte limit"


def test_pdf_extraction_rejects_cumulative_table_cells_above_limit(monkeypatch):
    _install_pdfplumber(
        monkeypatch,
        ["first", "second"],
        page_tables={
            0: [[['a', 'b']]],
            1: [[['c', 'd']]],
        },
    )
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_PDF_TABLE_CELLS",
        3,
    )

    result = CrossValidator()._extract_pdfplumber("too-many-cells.pdf")

    assert result.error == "PDF extracted table cells exceed the 3-cell limit"
    assert result.raw_text == ""
    assert result.clean_text == ""
    assert result.table_count == 0
    assert result.image_count == 0


def test_pdf_extraction_rejects_table_rows_above_limit(monkeypatch):
    _install_pdfplumber(
        monkeypatch,
        ["body"],
        page_tables={0: [[[], []]]},
    )
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_PDF_TABLE_ROWS",
        1,
    )

    result = CrossValidator()._extract_pdfplumber("too-many-table-rows.pdf")

    assert result.error == "PDF extracted table rows exceed the 1-row limit"
    assert result.raw_text == ""
    assert result.table_count == 0


def test_pdf_extraction_rejects_table_count_above_limit(monkeypatch):
    _install_pdfplumber(
        monkeypatch,
        ["body"],
        page_tables={0: [[], []]},
    )
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_PDF_TABLES",
        1,
    )

    result = CrossValidator()._extract_pdfplumber("too-many-tables.pdf")

    assert result.error == "PDF extracted table count exceeds the 1-table limit"
    assert result.raw_text == ""
    assert result.table_count == 0


def test_pdf_extraction_rejects_table_text_above_byte_limit(monkeypatch):
    _install_pdfplumber(
        monkeypatch,
        ["body"],
        page_tables={0: [[['four']]]},
    )
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_PDF_TABLE_TEXT_BYTES",
        3,
    )

    result = CrossValidator()._extract_pdfplumber("too-much-table-text.pdf")

    assert result.error == "PDF extracted table text exceeds the 3-byte limit"
    assert result.raw_text == ""
    assert result.table_count == 0


def test_pdf_budget_failure_makes_validation_unavailable(monkeypatch):
    validator = CrossValidator()
    _install_pdfplumber(monkeypatch, ["first", "second"])
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_PDF_PAGES",
        1,
    )
    monkeypatch.setattr(
        validator,
        "_extract_hwp",
        lambda path: SourceResult(
            raw_text="dochan body",
            clean_text="dochan body",
            char_count=11,
        ),
    )

    report = validator.validate(
        hwpx_path="sample.hwpx",
        pdf_path="too-many-pages.pdf",
    )

    assert report.sources["pdfplumber"].error == (
        "PDF page count exceeds the 1-page limit"
    )
    assert report.comparisons == []
    assert report.validation_available is False
    assert report.overall_score == 0.0


def test_odl_extraction_rejects_output_above_byte_limit(monkeypatch, tmp_path):
    output = tmp_path / "oversized.md"
    output.write_bytes(b"a" * 17)
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_TEXT_BYTES",
        16,
    )

    result = CrossValidator()._extract_odl(str(output))

    assert result.raw_text == ""
    assert "16-byte limit" in result.error


def test_odl_extraction_accepts_output_at_exact_byte_limit(monkeypatch, tmp_path):
    output = tmp_path / "bounded.md"
    output.write_text("1234567890abcdef", encoding="utf-8")
    monkeypatch.setattr(
        "dochan.quality.cross_validator.MAX_REFERENCE_TEXT_BYTES",
        16,
    )

    result = CrossValidator()._extract_odl(str(output))

    assert result.error == ""
    assert result.raw_text == "1234567890abcdef"


def test_hwp_extraction_separates_fatal_reader_errors_from_warnings(monkeypatch):
    class FakeReader:
        def __init__(self, path, ocr):
            self.doc = Document(
                sections=[Section()],
                errors=[
                    "WARN: parser wrote to stderr: parse error recovery succeeded",
                    "섹션 2 파싱 실패: truncated section was skipped",
                    "[HWPX] ERR: corrupt body",
                    "fatal parse error: document tree is unusable",
                ],
            )

        @property
        def errors(self):
            return self.doc.errors

        def to_markdown(self):
            return "partial text"

    monkeypatch.setattr("dochan.reader.Dochan", FakeReader)

    result = CrossValidator()._extract_hwp("sample.hwpx")

    assert result.error == (
        "[HWPX] ERR: corrupt body; "
        "fatal parse error: document tree is unusable"
    )
    assert result.warnings == [
        "WARN: parser wrote to stderr: parse error recovery succeeded",
        "섹션 2 파싱 실패: truncated section was skipped",
    ]


def test_hwp_extraction_counts_resolved_and_missing_image_assets_once(monkeypatch):
    class FakeReader:
        def __init__(self, path, ocr):
            resolved = AssetRef(
                id="rIdResolved",
                source_path="word/media/shared.png",
                filename="shared.png",
                content_type="image/png",
                metadata={"kind": "image", "missing": False},
            )
            self.doc = Document(
                sections=[Section()],
                assets=[
                    resolved,
                    resolved,
                    AssetRef(
                        id="rIdMissing",
                        source_path="word/media/missing.png",
                        filename="missing.png",
                        content_type="image/png",
                        metadata={"kind": "image", "missing": True},
                    ),
                ],
                errors=[
                    "WARN: DOCX image part not found: word/media/missing.png"
                ],
            )

        @property
        def errors(self):
            return self.doc.errors

        def to_markdown(self):
            return "two image references"

    monkeypatch.setattr("dochan.reader.Dochan", FakeReader)

    result = CrossValidator()._extract_hwp("sample.docx")

    assert result.image_count == 2
    assert result.error == ""
    assert result.warnings == [
        "WARN: DOCX image part not found: word/media/missing.png"
    ]


def test_automatic_keywords_are_local_to_each_validation(monkeypatch):
    validator = CrossValidator()
    keyword_batches = iter([["first-keyword"], ["second-keyword"]])
    monkeypatch.setattr(
        validator,
        "_auto_extract_keywords",
        lambda sources: next(keyword_batches),
    )

    def source(path):
        keyword = "first-keyword" if "first" in path else "second-keyword"
        return SourceResult(
            raw_text=keyword,
            clean_text=keyword,
            char_count=len(keyword),
        )

    monkeypatch.setattr(validator, "_extract_hwp", source)
    monkeypatch.setattr(validator, "_extract_pdfplumber", source)

    first = validator.validate(hwpx_path="first.hwpx", pdf_path="first.pdf")
    second = validator.validate(hwpx_path="second.hwpx", pdf_path="second.pdf")

    assert first.comparisons[0].keyword_matches == 1
    assert second.comparisons[0].keyword_matches == 1
    assert validator.keywords == []


def test_keyword_absent_from_both_sources_is_not_a_match():
    validator = CrossValidator(keywords=["shared", "absent"])
    a = SourceResult(raw_text="shared", clean_text="shared", char_count=6)
    b = SourceResult(raw_text="shared", clean_text="shared", char_count=6)

    comparison = validator._compare_pair(a, b, "a", "b")

    assert comparison.keyword_total == 2
    assert comparison.keyword_matches == 1


def test_batch_validation_json_preserves_source_warnings():
    report = CrossValidationReport(
        file_name="sample.hwpx",
        sources={
            "dochan": SourceResult(
                name="dochan",
                warnings=["WARN: image omitted"],
            )
        },
    )

    payload = _report_to_dict(report)

    assert payload["sources"]["dochan"]["warnings"] == ["WARN: image omitted"]


def test_failed_source_is_excluded_from_comparisons_and_score(monkeypatch):
    validator = CrossValidator()
    identical = SourceResult(
        raw_text="동일 문장이 충분히 길게 반복됩니다.",
        clean_text="동일 문장이 충분히 길게 반복됩니다.",
        char_count=20,
    )
    monkeypatch.setattr(validator, "_extract_hwp", lambda path: identical)
    monkeypatch.setattr(
        validator,
        "_extract_pdfplumber",
        lambda path: SourceResult(
            raw_text="실패소스키워드 " * 100,
            clean_text="실패소스키워드 " * 100,
            char_count=900,
            error="pdf extraction failed",
        ),
    )
    monkeypatch.setattr(validator, "_extract_odl", lambda path: identical)

    report = validator.validate(
        hwpx_path="sample.hwpx",
        pdf_path="sample.pdf",
        odl_output_path="sample.md",
    )

    assert report.sources["pdfplumber"].error == "pdf extraction failed"
    assert len(report.comparisons) == 1
    assert {
        report.comparisons[0].source_a,
        report.comparisons[0].source_b,
    } == {"dochan", "open_dataloader"}
    assert report.validation_available is True
    assert report.overall_score == 100.0


def test_all_reference_failures_report_validation_unavailable(monkeypatch):
    validator = CrossValidator()
    monkeypatch.setattr(
        validator,
        "_extract_hwp",
        lambda path: SourceResult(raw_text="부분 결과", clean_text="부분 결과"),
    )
    monkeypatch.setattr(
        validator,
        "_extract_pdfplumber",
        lambda path: SourceResult(error="pdf extraction failed"),
    )
    monkeypatch.setattr(
        validator,
        "_extract_odl",
        lambda path: SourceResult(error="odl extraction failed"),
    )

    report = validator.validate(
        hwpx_path="sample.hwpx",
        pdf_path="sample.pdf",
        odl_output_path="sample.md",
    )

    assert report.comparisons == []
    assert report.validation_available is False
    assert report.overall_score == 0.0
    assert report.verdict.startswith("검증 불가")
    assert "점수: 검증 불가" in report.summary()

    payload = _report_to_dict(report)
    assert payload["validation_available"] is False


def test_summary_marks_unavailable_pair_metrics_as_na():
    report = CrossValidationReport(
        comparisons=[
            PairComparison(
                source_a="dochan",
                source_b="pdfplumber",
                bigram_similarity=100.0,
                length_ratio=100.0,
                available_metrics=["bigram_similarity", "length_ratio"],
            )
        ]
    )

    summary = report.summary()

    assert "유사도 100.0%" in summary
    assert "키워드 N/A" in summary
    assert "문장커버 N/A" in summary
    assert "단어커버 N/A" in summary
    assert "길이비 100%" in summary


def test_empty_reference_text_is_excluded_from_keywords_comparisons_and_score(monkeypatch):
    validator = CrossValidator()
    valid = SourceResult(
        raw_text="공유키워드 동일 문장이 충분히 길게 반복됩니다.",
        clean_text="공유키워드 동일 문장이 충분히 길게 반복됩니다.",
        char_count=27,
    )
    empty_reference = SourceResult(
        raw_text="--- ![](image.png)",
        clean_text="",
        char_count=0,
    )
    keyword_source_names = []

    monkeypatch.setattr(validator, "_extract_hwp", lambda path: valid)
    monkeypatch.setattr(
        validator,
        "_extract_pdfplumber",
        lambda path: empty_reference,
    )
    monkeypatch.setattr(validator, "_extract_odl", lambda path: valid)

    def extract_keywords(sources):
        keyword_source_names.extend(sources)
        return ["공유키워드"]

    monkeypatch.setattr(validator, "_auto_extract_keywords", extract_keywords)

    report = validator.validate(
        hwpx_path="sample.hwpx",
        pdf_path="sample.pdf",
        odl_output_path="sample.md",
    )

    assert keyword_source_names == ["dochan", "open_dataloader"]
    assert len(report.comparisons) == 1
    assert {
        report.comparisons[0].source_a,
        report.comparisons[0].source_b,
    } == {"dochan", "open_dataloader"}
    assert report.validation_available is True
    assert report.overall_score == 100.0


def test_only_empty_reference_text_reports_validation_unavailable(monkeypatch):
    validator = CrossValidator()
    monkeypatch.setattr(
        validator,
        "_extract_hwp",
        lambda path: SourceResult(
            raw_text="정상 dochan 본문",
            clean_text="정상 dochan 본문",
            char_count=12,
        ),
    )
    monkeypatch.setattr(
        validator,
        "_extract_pdfplumber",
        lambda path: SourceResult(raw_text="", clean_text="", char_count=0),
    )
    monkeypatch.setattr(
        validator,
        "_extract_odl",
        lambda path: SourceResult(raw_text="---", clean_text="", char_count=0),
    )

    report = validator.validate(
        hwpx_path="sample.hwpx",
        pdf_path="sample.pdf",
        odl_output_path="sample.md",
    )

    assert report.comparisons == []
    assert report.validation_available is False
    assert report.overall_score == 0.0
    assert report.verdict.startswith("검증 불가")


def test_empty_dochan_text_is_compared_with_valid_reference_as_zero(monkeypatch):
    validator = CrossValidator()
    monkeypatch.setattr(
        validator,
        "_extract_hwp",
        lambda path: SourceResult(raw_text="", clean_text="", char_count=0),
    )
    monkeypatch.setattr(
        validator,
        "_extract_pdfplumber",
        lambda path: SourceResult(
            raw_text="유효한 참조 문장이 충분히 길게 존재합니다.",
            clean_text="유효한 참조 문장이 충분히 길게 존재합니다.",
            char_count=24,
        ),
    )

    report = validator.validate(
        hwpx_path="sample.hwpx",
        pdf_path="sample.pdf",
    )

    assert len(report.comparisons) == 1
    comparison = report.comparisons[0]
    assert comparison.source_a == "dochan"
    assert comparison.source_b == "pdfplumber"
    assert comparison.bigram_similarity == 0.0
    assert comparison.word_coverage == 0.0
    assert comparison.sentence_coverage == 0.0
    assert comparison.length_ratio == 0.0
    assert report.validation_available is True
    assert report.overall_score == 0.0


def test_score_summary_excludes_unavailable_reports():
    available = CrossValidationReport(
        overall_score=100.0,
        validation_available=True,
    )
    unavailable = CrossValidationReport(
        overall_score=0.0,
        validation_available=False,
    )

    assert _score_summary([available, unavailable]) == {
        "available": 1,
        "total": 2,
        "average": 100.0,
    }
    assert _score_summary([unavailable])["average"] is None


def test_report_without_comparison_evidence_defaults_to_unavailable():
    report = CrossValidationReport()

    assert report.validation_available is False
    assert _score_summary([report]) == {
        "available": 0,
        "total": 1,
        "average": None,
    }


def test_exact_single_character_similarity_is_complete():
    assert compare_with_gt("가", "가").text_similarity == 1.0
    assert CrossValidator._bigram_sim("가", "가") == 1.0


def test_identical_english_cross_validation_scores_one_hundred():
    validator = CrossValidator()
    text = "Identical English sentence with enough words."
    source = SourceResult(raw_text=text, clean_text=text, char_count=len(text))

    comparison = validator._compare_pair(
        source,
        source,
        "dochan",
        "pdfplumber",
        validator._auto_extract_keywords({"dochan": source}),
    )
    report = CrossValidationReport(comparisons=[comparison])

    assert validator._calc_overall_score(report) == 100.0


def test_unrelated_same_length_english_does_not_gain_length_only_score():
    validator = CrossValidator()
    first = "aaaa bbbb cccc"
    second = "xxxx yyyy zzzz"
    a = SourceResult(raw_text=first, clean_text=first, char_count=len(first))
    b = SourceResult(raw_text=second, clean_text=second, char_count=len(second))

    comparison = validator._compare_pair(
        a,
        b,
        "dochan",
        "pdfplumber",
        validator._auto_extract_keywords({"dochan": a}),
    )
    report = CrossValidationReport(comparisons=[comparison])

    assert validator._calc_overall_score(report) == 0.0
