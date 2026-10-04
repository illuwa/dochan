"""관계로 연결된 XLSX·XLSM 메모의 독립 정답과 출력 해시를 전수 대조한다."""
import hashlib
import json
import re

from .comment_probe_common import (
    annotation, product, relationship_targets, run_cli, xml, zip_package, zip_read,
)


class _NormalizedPackage:
    """비표준 역슬래시 ZIP 이름도 독립 정답지에서 같은 파트로 찾는다."""
    def __init__(self, package):
        self.package = package
        self.names = {name.replace('\\', '/').lower(): name for name in package.namelist()}
        if len(self.names) != len(package.namelist()):
            raise ValueError('oracle duplicate normalized ZIP part')

    def namelist(self):
        return list(self.names)

    def getinfo(self, name):
        return self.package.getinfo(self.names[name.replace('\\', '/').lower()])

    def read(self, name):
        return self.package.read(self.names[name.replace('\\', '/').lower()])


def _relationships(package, part):
    result = relationship_targets(package, part.replace('\\', '/').lower())
    return {rid: (typ, target.replace('\\', '/').lower()) for rid, (typ, target) in result.items()}


def coordinates(ref):
    match = re.fullmatch(r'([A-Za-z]{1,3})([1-9][0-9]{0,6})', ref)
    if not match:
        raise ValueError('oracle invalid comment reference: ' + ref)
    col = 0
    for char in match[1].upper():
        col = col * 26 + ord(char) - ord('A') + 1
    row = int(match[2])
    if col > 16384 or row > 1048576:
        raise ValueError('oracle comment reference out of bounds: ' + ref)
    return row - 1, col - 1


def xlsx_oracle(path):
    """제품 import 없이 workbook→worksheet→comments 관계를 따라 원시 메모를 읽는다."""
    with zip_package(path) as original:
        package = _NormalizedPackage(original)
        book = xml(zip_read(package, 'xl/workbook.xml'))
        relationships = _relationships(package, 'xl/workbook.xml')
        comments, comment_parts, diagnostics = [], [], []
        for sheets in book.items('sheets'):
            for sheet in sheets.items('sheet'):
                rid = next((value for key, value in sheet.attrs.items()
                            if key.rsplit('}', 1)[-1] == 'id'), '')
                if rid not in relationships:
                    diagnostics.append('missing sheet relationship: ' + rid)
                    continue
                target = relationships[rid][1]
                linked = [(typ, part) for typ, part in _relationships(package, target).values()
                          if typ.endswith('/comments')]
                if not linked:
                    continue
                # Cells are needed only for sheets with a linked comment part.
                sheet_root = xml(zip_read(package, target))
                cells, rows = {}, set()
                for data in sheet_root.items('sheetData'):
                    for row in data.items('row'):
                        rows.add(row.attrs.get('r', ''))
                        for cell in row.items('c'):
                            cells[cell.attrs.get('r', '')] = cell
                sheet_comments = []
                for _, part in linked:
                    comment_parts.append(part)
                    root = xml(zip_read(package, part))
                    authors = [author.text for group in root.items('authors')
                               for author in group.items('author')]
                    for group in root.items('commentList'):
                        for cm in group.items('comment'):
                            ref = cm.attrs.get('ref', '')
                            row, col = coordinates(ref)
                            author_id = cm.attrs.get('authorId', '')
                            author = authors[int(author_id)] if author_id.isdigit() and int(author_id) < len(authors) else ''
                            body = ''.join(n.text if n.tag.rsplit('}', 1)[-1] == 't'
                                           else ''.join(t.text for t in n.items('t'))
                                           for text in cm.items('text') for n in text.children
                                           if n.tag.rsplit('}', 1)[-1] in ('t', 'r')).strip()
                            cell = cells.get(ref)
                            empty = cell is None or not any(n.text or n.children
                                                           for n in cell.children
                                                           if n.tag.rsplit('}', 1)[-1] in ('v', 'f', 'is'))
                            sheet_comments.append({'sheet': sheet.attrs['name'], 'cell': ref,
                                                   'row': row, 'col': col, 'author': author, 'body': body,
                                                   'annotation': annotation(author, body) if body else '',
                                                   'empty_cell': empty, 'absent_cell': cell is None,
                                                   'absent_row': str(row + 1) not in rows})
                comments.extend(sorted(sheet_comments, key=lambda cm: (cm['row'], cm['col'])))
        return {'comments': comments, 'raw_count': len(comments), 'comment_parts': comment_parts,
                'oracle_diagnostics': diagnostics}


def compare_cells(expected, actual):
    wanted = {(c['sheet'], c['cell']): c['annotation'] for c in expected if c['annotation']}
    found = {(c['sheet'], c['cell']): c['annotation'] for c in actual}
    missing = [{'sheet': sheet, 'cell': cell} for sheet, cell in wanted if (sheet, cell) not in found]
    mismatches = [{'sheet': key[0], 'cell': key[1], 'expected': value, 'actual': found[key]}
                  for key, value in wanted.items() if key in found and value != found[key]]
    extra = [{'sheet': sheet, 'cell': cell} for sheet, cell in found if (sheet, cell) not in wanted]
    return {'expected_count': len(wanted), 'actual_count': len(actual),
            'matched': sum(found.get(key) == value for key, value in wanted.items()),
            'missing': missing, 'mismatches': mismatches, 'extra': extra,
            'exact': not missing and not mismatches and not extra and len(found) == len(actual)}


def unchanged_content_sha256(path, expected):
    """셀 없는 메모를 제외한 기존 비어 있지 않은 셀과 표 밖 요소의 JSON 해시를 구한다."""
    from dochan import Dochan
    from dochan.output.json_out import to_json
    encoded = json.loads(to_json(Dochan(str(path)).doc))
    additions = {(c['sheet'], c['cell']) for c in expected if c['absent_cell']}
    for section in encoded.get('sections', []):
        elements = []
        for element in section.get('elements', []):
            if element.get('type') != 'table':
                elements.append(element)
                continue
            kept = []
            for row_index, row in enumerate(element.get('rows', [])):
                for col_index, cell in enumerate(row):
                    provenance = cell.get('provenance') or {}
                    if (provenance.get('sheet'), provenance.get('cell')) in additions:
                        continue
                    if cell.get('paragraphs'):
                        kept.append([row_index, col_index, cell])
            element['rows'] = kept
            element.pop('row_count', None)
            element.pop('col_count', None)
            if kept or element.get('caption'):
                elements.append(element)
        section['elements'] = elements
    canonical = json.dumps(encoded, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def inspect(path):
    """공개 통합 문서의 메모 위치·작성자·본문 및 Markdown·JSON 해시를 검사한다."""
    try:
        raw = xlsx_oracle(path)
    except Exception as exc:
        raw = {'oracle_error': type(exc).__name__ + ': ' + str(exc)}
    actual = product(path)
    cells = actual.pop('cells')
    actual.pop('paragraphs')
    if 'comments' in raw:
        raw['comparison'] = compare_cells(raw['comments'], cells)
        raw['empty_cell_comments'] = sum(c['empty_cell'] for c in raw['comments'])
        raw['absent_cell_comments'] = sum(c['absent_cell'] for c in raw['comments'])
        if raw.get('raw_count'):
            raw['unchanged_content_sha256'] = unchanged_content_sha256(path, raw['comments'])
    return {**raw, **actual}


if __name__ == '__main__':
    run_cli(inspect, {'.xlsx', '.xlsm'})
