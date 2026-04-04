"""
quality/checker.py — 품질 검증
파싱 결과의 품질을 정량적으로 측정
"""

from dataclasses import dataclass, field
from typing import List
from ..model.document import Document, Paragraph
from ..model.table import Table
from ..model.equation import Equation
from ..model.image import Image


@dataclass
class QualityReport:
    """품질 검증 결과"""
    total_paragraphs: int = 0
    total_tables: int = 0
    total_equations: int = 0
    total_images: int = 0
    empty_paragraphs: int = 0
    empty_cells: int = 0
    failed_equations: int = 0
    missing_images: int = 0
    parse_errors: int = 0
    warnings: List[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        """0~100 품질 점수"""
        if self.total_paragraphs == 0:
            return 0.0

        total = (self.total_paragraphs + self.total_tables +
                 self.total_equations + self.total_images)
        if total == 0:
            return 0.0

        issues = (self.empty_paragraphs + self.empty_cells +
                  self.failed_equations + self.missing_images +
                  self.parse_errors)

        return max(0.0, min(100.0, (1 - issues / max(total, 1)) * 100))


def check_quality(doc: Document) -> QualityReport:
    """Document 품질 검증"""
    report = QualityReport()
    report.parse_errors = len(doc.errors)

    for section in doc.sections:
        for elem in section.elements:
            if isinstance(elem, Paragraph):
                report.total_paragraphs += 1
                if not elem.text.strip():
                    report.empty_paragraphs += 1

            elif isinstance(elem, Table):
                report.total_tables += 1
                for row in elem.rows:
                    for cell in row:
                        if not cell.is_merged_away and not cell.text.strip():
                            report.empty_cells += 1

            elif isinstance(elem, Equation):
                report.total_equations += 1
                if '파싱 실패' in elem.script or '데이터 부족' in elem.script:
                    report.failed_equations += 1

            elif isinstance(elem, Image):
                report.total_images += 1
                if elem.bin_id < 0:
                    report.missing_images += 1

    return report
