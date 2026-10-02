"""Probe public DOC/DOCX font and bookmark regressions without copying samples."""
import argparse
import json
import struct
from pathlib import Path
from zipfile import ZipFile

import olefile
from lxml import etree

from dochan.model.table import flatten_block_texts
from dochan.office_binary.doc import DOCReader
from dochan.office_binary.doc_binary import DocBinary
from dochan.ooxml.docx import DOCXReader
from dochan.output.markdown import to_markdown


def _texts(document):
    return [text for section in document.sections
            for text in flatten_block_texts(section.elements)]


def check(poi_document, lo_ww8):
    results = []
    path = lo_ww8 / 'tdf90408.doc'
    doc = DOCReader().read(str(path))
    with olefile.OleFileIO(str(path)) as ole:
        word = ole.openstream('WordDocument').read()
        table_name = '1Table' if struct.unpack_from('<H', word, 10)[0] & 512 else '0Table'
        binary = DocBinary(word, ole.openstream(table_name).read())
    actual = _texts(doc)
    results.append({'file': path.name, 'check': 'Wingdings MACROBUTTON',
                    'expected': ['☐unchecked', '☑checked'], 'actual': actual,
                    'source': [{'cp': cp, 'raw': binary.text[cp],
                                'font_id': binary.char_props(cp).get('font'),
                                'font': binary.font_names.get(binary.char_props(cp).get('font'))}
                               for cp in (22, 56)],
                    'passed': actual == ['☐unchecked', '☑checked'], 'warnings': doc.errors})
    path = poi_document / 'Bug45877.doc'
    doc = DOCReader().read(str(path))
    actual = next((line for line in to_markdown(doc).splitlines() if '[bookmark: SG12]' in line), '')
    expected = '[bookmark: SG12] ***Paragraph with table***'
    results.append({'file': path.name, 'check': 'DOC bookmark word boundary',
                    'expected': expected, 'actual': actual,
                    'passed': actual == expected, 'warnings': doc.errors})
    path = poi_document / 'bug59058.docx'
    doc = DOCXReader().read(str(path))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with ZipFile(str(path)) as archive:
        root = etree.fromstring(archive.read('word/document.xml'))
    raw = next(para for para in root.findall('.//w:p', ns)
               if any(mark.get('{%s}name' % ns['w']) == 'back-bib1'
                      for mark in para.findall('w:bookmarkStart', ns)))
    raw_text = ''.join(node.text or '' for node in raw.findall('.//w:t', ns))
    actual = next((text for text in _texts(doc) if '[bookmark: back-bib1]' in text), '')
    expected = '[bookmark: back-bib1] ' + raw_text
    results.append({'file': path.name, 'check': 'DOCX bookmark paragraph anchor',
                    'expected_prefix': expected[:60], 'actual_prefix': actual[:60],
                    'passed': actual == expected, 'warnings': doc.errors})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--poi-document', required=True, type=Path)
    parser.add_argument('--lo-ww8', required=True, type=Path)
    args = parser.parse_args()
    results = check(args.poi_document, args.lo_ww8)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(result['passed'] for result in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
