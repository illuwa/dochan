"""
tests/test_quality.py — 품질 검증 테스트
"""

import pytest
from dochan.model.document import Document, Section, Paragraph, TextRun
from dochan.model.table import Table, Cell
from dochan.model.equation import Equation
from dochan.model.image import Image
from dochan.quality.checker import check_quality, QualityReport


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
        assert report.empty_cells == 0

    def test_failed_equation(self):
        doc = self._make_doc([
            Equation(script="[수식 파싱 실패]"),
        ])
        report = check_quality(doc)
        assert report.total_equations == 1
        assert report.failed_equations == 1

    def test_missing_image(self):
        doc = self._make_doc([
            Image(bin_id=-1),
        ])
        report = check_quality(doc)
        assert report.total_images == 1
        assert report.missing_images == 1

    def test_perfect_score(self):
        doc = self._make_doc([
            Paragraph(runs=[TextRun(text="문단")]),
            Table(rows=[[Cell(paragraphs=[Paragraph(runs=[TextRun(text="셀")])])]]),
            Equation(script="x^2 + y^2 = z^2"),
            Image(bin_id=1, filename="test.png"),
        ])
        report = check_quality(doc)
        assert report.score == 100.0
