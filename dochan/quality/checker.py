"""
quality/checker.py — 품질 검증
파싱 결과의 품질을 정량적으로 측정
"""

from dataclasses import dataclass, field
from typing import List
from ..model.document import Document
from ..utils.diagnostics import is_fatal_diagnostic


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
        # A fatal parser diagnostic means the document cannot be trusted as a
        # whole.  It must not be diluted by a large number of otherwise valid
        # elements.
        if self.parse_errors:
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
    for diagnostic in doc.errors:
        if is_fatal_diagnostic(diagnostic):
            report.parse_errors += 1
        else:
            report.warnings.append(str(diagnostic))

    paragraphs = doc.find_all('paragraph')
    tables = doc.find_all('table')
    equations = doc.find_all('equation')
    images = doc.find_all('image')
    # Track unique package image parts rather than relationship occurrences.
    # A resolved observation wins over a stale/missing duplicate for the same
    # part, while a genuinely missing part remains a first-class image issue.
    image_assets = {}
    for asset in doc.assets:
        metadata = getattr(asset, 'metadata', {})
        if not isinstance(metadata, dict):
            metadata = {}
        content_type = str(getattr(asset, 'content_type', '')).lower()
        if not (
            content_type.startswith('image/')
            or str(metadata.get('kind', '')).lower() == 'image'
        ):
            continue

        source_path = str(getattr(asset, 'source_path', ''))
        asset_id = str(getattr(asset, 'id', ''))
        filename = str(getattr(asset, 'filename', ''))
        if source_path:
            key = ('path', source_path)
        elif asset_id:
            key = ('id', asset_id)
        elif filename:
            key = ('filename', filename)
        else:
            key = ('object', id(asset))

        missing = bool(metadata.get('missing', False))
        if key in image_assets:
            image_assets[key] = image_assets[key] and missing
        else:
            image_assets[key] = missing

    report.total_paragraphs = len(paragraphs)
    report.total_tables = len(tables)
    report.total_equations = len(equations)
    # OOXML readers expose resolved package images as AssetRef objects instead
    # of loading their bytes into Image elements.  Count each resolved asset
    # once; its presence in assets means the package relationship was resolved.
    report.total_images = len(images) + len(image_assets)

    report.empty_paragraphs = sum(not paragraph.text.strip() for paragraph in paragraphs)
    for table in tables:
        visible_cells = 0
        for row in table.rows:
            for cell in row:
                if not cell.is_merged_away:
                    visible_cells += 1
                    if not cell.text.strip():
                        report.empty_cells += 1
        if visible_cells == 0:
            report.empty_cells += 1

    report.failed_equations = sum(
        not (equation.script or equation.latex).strip()
        or '파싱 실패' in equation.script
        or '데이터 부족' in equation.script
        for equation in equations
    )
    report.missing_images = (
        sum(not image.has_data for image in images)
        + sum(image_assets.values())
    )

    return report
