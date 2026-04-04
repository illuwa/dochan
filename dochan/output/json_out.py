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
        'sections': [_section_to_dict(s) for s in doc.sections],
    }


def _section_to_dict(section) -> dict:
    return {
        'elements': [_element_to_dict(e) for e in section.elements],
    }


def _element_to_dict(elem) -> dict:
    if isinstance(elem, Paragraph):
        return {
            'type': 'paragraph',
            'text': elem.text,
            'runs': [
                {
                    'text': r.text,
                    'bold': r.bold,
                    'italic': r.italic,
                    'font_size_pt': r.font_size_pt,
                }
                for r in elem.runs
            ],
            'style_id': elem.style_id,
        }
    elif isinstance(elem, Table):
        return {
            'type': 'table',
            'rows': [
                [
                    {
                        'text': cell.text,
                        'row_span': cell.row_span,
                        'col_span': cell.col_span,
                    }
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
        }
    return {'type': 'unknown'}
