"""
tests/test_quality.py — 품질 검증 테스트
"""

import pytest

from dochan.conversion import AssetRef
from dochan.model.document import Document, Section, Paragraph, TextRun
from dochan.model.header_footer import Footnote, HeaderFooter
from dochan.model.table import Table, Cell
from dochan.model.equation import Equation
from dochan.model.image import Image
from dochan.quality.checker import check_quality


class TestQualityChecker:

    def _make_doc(self, elements=None):
        doc = Document()
        section = Section()
        if elements:
            section.elements = elements
        doc.sections = [section]
        return doc

    def test_empty_document(self):
        doc = self._make_doc()
        report = check_quality(doc)
        assert report.score == 0.0
        assert report.total_paragraphs == 0

    def test_simple_paragraphs(self):
        doc = self._make_doc([
            Paragraph(runs=[TextRun(text="Hello")]),
            Paragraph(runs=[TextRun(text="World")]),
        ])
        report = check_quality(doc)
        assert report.total_paragraphs == 2
        assert report.empty_paragraphs == 0
        assert report.score > 90

    def test_with_empty_paragraph(self):
        doc = self._make_doc([
            Paragraph(runs=[TextRun(text="Hello")]),
            Paragraph(runs=[TextRun(text="")]),
        ])
        report = check_quality(doc)
        assert report.total_paragraphs == 2
        assert report.empty_paragraphs == 1

    def test_table_quality(self):
        table = Table(rows=[
            [Cell(paragraphs=[Paragraph(runs=[TextRun(text="A")])]),
             Cell(paragraphs=[Paragraph(runs=[TextRun(text="B")])])],
        ])
        doc = self._make_doc([table])
        report = check_quality(doc)
        assert report.total_tables == 1
        assert report.total_paragraphs == 2
        assert report.empty_cells == 0
        assert report.score == 100.0

    def test_failed_equation(self):
        doc = self._make_doc([
            Equation(script="[수식 파싱 실패]"),
        ])
        report = check_quality(doc)
        assert report.total_equations == 1
        assert report.failed_equations == 1

    @pytest.mark.parametrize("table", [Table(), Table(rows=[[]])])
    def test_table_without_visible_cells_is_not_perfect_quality(self, table):
        report = check_quality(self._make_doc([table]))

        assert report.total_tables == 1
        assert report.empty_cells == 1
        assert report.score == 0.0

    def test_empty_equation_is_failed(self):
        report = check_quality(self._make_doc([Equation()]))

        assert report.total_equations == 1
        assert report.failed_equations == 1
        assert report.score == 0.0

    def test_missing_image(self):
        doc = self._make_doc([
            Image(bin_id=-1),
        ])
        report = check_quality(doc)
        assert report.total_images == 1
        assert report.missing_images == 1

    def test_hwpx_image_with_loaded_data_is_not_missing_without_bin_id(self):
        image = Image(
            bin_id=-1,
            filename="image1.png",
            image_data=b"loaded HWPX image data",
        )
        assert image.has_data is True

        report = check_quality(self._make_doc([image]))

        assert report.total_images == 1
        assert report.missing_images == 0

    def test_positive_bin_id_without_loaded_data_is_still_missing(self):
        image = Image(bin_id=9, filename="missing.png", image_data=b"")

        report = check_quality(self._make_doc([image]))

        assert report.total_images == 1
        assert report.missing_images == 1

    def test_resolved_ooxml_image_assets_are_counted_once(self):
        doc = self._make_doc()
        asset = AssetRef(
            id="rId1",
            source_path="word/media/image1.png",
            filename="image1.png",
            content_type="image/png",
        )
        doc.assets = [asset, asset]

        report = check_quality(doc)

        assert report.total_images == 1
        assert report.missing_images == 0
        assert report.score == 100.0

    def test_missing_ooxml_image_assets_are_counted_once_and_reduce_score(self):
        doc = self._make_doc()
        missing = AssetRef(
            id="rIdMissing",
            source_path="word/media/missing.unknown",
            filename="missing.unknown",
            content_type="application/octet-stream",
            metadata={"kind": "image", "missing": True},
        )
        resolved_duplicate = AssetRef(
            id="rIdResolved",
            source_path="word/media/shared.png",
            filename="shared.png",
            content_type="image/png",
            metadata={"kind": "image", "missing": False},
        )
        stale_missing_duplicate = AssetRef(
            id="rIdStale",
            source_path="word/media/shared.png",
            filename="shared.png",
            content_type="image/png",
            metadata={"kind": "image", "missing": True},
        )
        doc.assets = [missing, missing, stale_missing_duplicate, resolved_duplicate]

        report = check_quality(doc)

        assert report.total_images == 2
        assert report.missing_images == 1
        assert report.score == 50.0

    def test_non_image_assets_do_not_inflate_image_quality(self):
        doc = self._make_doc()
        doc.assets = [
            AssetRef(
                id="rId2",
                source_path="word/embeddings/object.bin",
                filename="object.bin",
                content_type="application/octet-stream",
            )
        ]

        report = check_quality(doc)

        assert report.total_images == 0
        assert report.score == 0.0

    def test_perfect_score(self):
        doc = self._make_doc([
            Paragraph(runs=[TextRun(text="문단")]),
            Table(rows=[[Cell(paragraphs=[Paragraph(runs=[TextRun(text="셀")])])]]),
            Equation(script="x^2 + y^2 = z^2"),
            Image(bin_id=1, filename="test.png", image_data=b"loaded"),
        ])
        report = check_quality(doc)
        assert report.score == 100.0

    def test_warning_is_preserved_without_reducing_score(self):
        doc = self._make_doc([Paragraph(runs=[TextRun(text="Content")])])
        doc.errors.append("WARN: OCR skipped")

        report = check_quality(doc)

        assert report.parse_errors == 0
        assert report.warnings == ["WARN: OCR skipped"]
        assert report.score == 100.0

    def test_fatal_parser_error_reduces_score(self):
        doc = self._make_doc([Paragraph(runs=[TextRun(text="Content")])])
        doc.errors.append("ERR: malformed input")

        report = check_quality(doc)

        assert report.parse_errors == 1
        assert report.warnings == []
        assert report.score == 0.0

    def test_fatal_parser_error_fails_closed_even_with_many_valid_paragraphs(self):
        doc = self._make_doc([
            Paragraph(runs=[TextRun(text=f"Content {index}")])
            for index in range(100)
        ])
        doc.errors.append("[HWPX] ERROR: malformed document tree")

        report = check_quality(doc)

        assert report.total_paragraphs == 100
        assert report.parse_errors == 1
        assert report.score == 0.0

    def test_diagnostic_severity_is_anchored_and_context_aware(self):
        doc = self._make_doc([Paragraph(runs=[TextRun(text="Content")])])
        doc.errors.extend([
            "[DOCX] ERROR: malformed input",
            "fatal parse error: document tree is unusable",
            "WARN: parser wrote to stderr: parse error recovery succeeded",
            "섹션 2 파싱 실패: truncated section was skipped",
        ])

        report = check_quality(doc)

        assert report.parse_errors == 2
        assert report.warnings == [
            "WARN: parser wrote to stderr: parse error recovery succeeded",
            "섹션 2 파싱 실패: truncated section was skipped",
        ]

    def test_nested_note_header_and_table_elements_are_counted_once(self):
        shared_paragraph = Paragraph(runs=[TextRun(text="Nested")])
        nested_image = Image(bin_id=-1)
        nested_equation = Equation(script="[수식 파싱 실패]")
        inner_table = Table(
            rows=[[Cell(paragraphs=[shared_paragraph, nested_image, nested_equation])]],
        )
        note = Footnote(paragraphs=[shared_paragraph, inner_table])
        header = HeaderFooter(
            type="header",
            paragraphs=[Paragraph(runs=[TextRun(text="Header")])],
        )
        doc = self._make_doc([header, note])

        report = check_quality(doc)

        assert report.total_paragraphs == 2
        assert report.total_tables == 1
        assert report.total_equations == 1
        assert report.total_images == 1
        assert report.failed_equations == 1
        assert report.missing_images == 1
