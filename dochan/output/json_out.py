"""
output/json_out.py — 구조화 JSON 출력
"""

import json
from copy import deepcopy
from ..model.document import Document, Paragraph
from ..model.table import Table
from ..model.equation import Equation
from ..model.image import Image
from ..model.header_footer import Comment, Footnote, HeaderFooter


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
        'metadata': deepcopy(getattr(asset, 'metadata', {}) or {}),
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
    # 0 means visible and False means not hidden, so both are meaningful values.
    for name in ('visibility', 'hidden'):
        value = getattr(provenance, name, None)
        if value is not None:
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
            'width': elem.width,
            'height': elem.height,
            'ocr_text': elem.ocr_text,
        }
    elif isinstance(elem, HeaderFooter):
        return {
            'type': elem.type,
            'text': elem.text,
            'elements': [_element_to_dict(item) for item in elem.paragraphs],
        }
    elif isinstance(elem, Footnote):
        result = {
            'type': elem.type,
            'text': elem.text,
            'elements': [_element_to_dict(item) for item in elem.paragraphs],
        }
        if elem.number is not None:
            result['number'] = elem.number
        if isinstance(elem, Comment):
            result['author'] = elem.author
        return result
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
    note_type = getattr(run, 'note_reference_type', '')
    note_number = getattr(run, 'note_reference_number', None)
    if note_type in {'footnote', 'endnote', 'comment'} and note_number is not None:
        result['note_reference_type'] = note_type
        result['note_reference_number'] = note_number
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
