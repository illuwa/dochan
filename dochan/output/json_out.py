"""
output/json_out.py — 구조화 JSON 출력
"""

import json
from ..model.document import Document, Paragraph
from ..model.table import Table
from ..model.equation import Equation
from ..model.image import Image
from ..model.header_footer import HeaderFooter, Footnote


def to_json(doc: Document, indent: int = 2) -> str:
    """Document → JSON 문자열"""
    return json.dumps(to_dict(doc), ensure_ascii=False, indent=indent)


def to_dict(doc: Document) -> dict:
    """Document → dict"""
    return {
        'metadata': doc.metadata,
        'assets': [_asset_to_dict(asset) for asset in doc.assets],
        'sections': [_section_to_dict(s) for s in doc.sections],
    }


def _asset_to_dict(asset) -> dict:
    return {
        'id': asset.id,
        'source_path': asset.source_path,
        'filename': asset.filename,
        'content_type': asset.content_type,
        'metadata': dict(getattr(asset, 'metadata', {}) or {}),
    }


def _section_to_dict(section) -> dict:
    result = {
        'elements': [_element_to_dict(e) for e in section.elements],
    }
    provenance = _provenance_to_dict(getattr(section, 'provenance', None))
    if provenance:
        result['provenance'] = provenance
    return result


def _provenance_to_dict(provenance) -> dict:
    if provenance is None:
        return {}
    result = {}
    for name in ('source_format', 'page', 'slide', 'sheet', 'cell', 'section', 'paragraph', 'path'):
        value = getattr(provenance, name, None)
        if value not in (None, ''):
            result[name] = value
    return result


def _element_to_dict(elem) -> dict:
    if isinstance(elem, Paragraph):
        return _paragraph_to_dict(elem)
    elif isinstance(elem, Table):
        return {
            'type': 'table',
            'row_count': elem.row_count,
            'col_count': elem.col_count,
            'rows': [
                [
                    _cell_to_dict(cell)
                    for cell in row
                ]
                for row in elem.rows
            ],
        }
    elif isinstance(elem, Equation):
        return {
            'type': 'equation',
            'script': elem.script,
        }
    elif isinstance(elem, Image):
        return {
            'type': 'image',
            'bin_id': elem.bin_id,
            'filename': elem.filename,
        }
    elif isinstance(elem, HeaderFooter):
        return {
            'type': elem.type,
            'text': elem.text,
        }
    elif isinstance(elem, Footnote):
        return {
            'type': elem.type,
            'text': elem.text,
            'elements': [_element_to_dict(item) for item in elem.paragraphs],
        }
    return {'type': 'unknown'}


def _paragraph_to_dict(para) -> dict:
    result = {
        'type': 'paragraph',
        'text': para.text,
        'runs': [
            _run_to_dict(r)
            for r in para.runs
        ],
        'style_id': para.style_id,
        'heading_level': para.heading_level,
    }
    provenance = _provenance_to_dict(getattr(para, 'provenance', None))
    if provenance:
        result['provenance'] = provenance
    return result


def _run_to_dict(run) -> dict:
    result = {
        'text': run.text,
        'bold': run.bold,
        'italic': run.italic,
        'underline': run.underline,
        'strikeout': run.strikeout,
        'superscript': run.superscript,
        'subscript': run.subscript,
        'font_size_pt': run.font_size_pt,
    }
    provenance = _provenance_to_dict(getattr(run, 'provenance', None))
    if provenance:
        result['provenance'] = provenance
    return result


def _cell_to_dict(cell) -> dict:
    result = {
        'text': cell.text,
        'row_span': cell.row_span,
        'col_span': cell.col_span,
        'paragraphs': [
            _element_to_dict(paragraph)
            for paragraph in cell.paragraphs
        ],
    }
    if cell.row is not None:
        result['row'] = cell.row
    if cell.col is not None:
        result['col'] = cell.col
    provenance = _provenance_to_dict(getattr(cell, 'provenance', None))
    if provenance:
        result['provenance'] = provenance
    return result
