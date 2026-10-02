"""공개 PDF 주석 앵커를 독립 PDFium 문자 좌표와 대조한다.

PDFium은 검증 시에만 사용하는 로컬 도구이며 런타임 의존성이 아니다.
원시 주석 사각형의 문자 중심을 ray casting으로 판정하며, dochan의
기하 적중 함수와 안전성 판정 결과를 정답으로 재사용하지 않는다.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import signal
import unicodedata

from dochan.pdf import reader as reader_module
from dochan.pdf.objects import PDFRef, PDFStream
from dochan.pdf.structure import PDFFile
from scripts.probe_pdf_annotations import independent_rc, independent_string


class ProbeDeadline(BaseException):
    pass


def _inside(points, x, y):
    inside = False
    previous = points[-1]
    for current in points:
        xi, yi = current
        xj, yj = previous
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        previous = current
    return inside


def _areas(pdf, annot):
    subtype = str(annot.get('Subtype'))
    if subtype in ('Highlight', 'Underline', 'StrikeOut', 'Squiggly'):
        values = pdf.resolve(annot.get('QuadPoints'))
        if not isinstance(values, list) or len(values) % 8 or len(values) > 2048:
            return []
        groups = [values[pos:pos + 8] for pos in range(0, len(values), 8)]
    elif subtype == 'Text':
        rect = pdf.resolve(annot.get('Rect'))
        if not isinstance(rect, list) or len(rect) != 4:
            return []
        groups = [[rect[0], rect[1], rect[2], rect[1], rect[2], rect[3], rect[0], rect[3]]]
    else:
        return []
    result = []
    for values in groups:
        if not all(isinstance(n, (int, float)) and math.isfinite(n) for n in values):
            return []
        points = list(zip(values[::2], values[1::2]))
        center = (sum(x for x, _ in points) / 4, sum(y for _, y in points) / 4)
        result.append(sorted(points, key=lambda p: math.atan2(p[1] - center[1], p[0] - center[0])))
    return result


def _compact(text):
    return ''.join(unicodedata.normalize('NFKC', text).split()).replace('\u00ad', '')


def verify(path):
    import pypdfium2 as pdfium
    pdf = PDFFile(path.read_bytes())
    if pdf.encrypted and not pdf.decrypt_ok:
        return {'excluded': 'encrypted'}
    records = []
    seen = set()
    # ISO 32000-1 markup annotation subtypes; Popup/Link/Widget are not comments.
    kinds = {'Text', 'FreeText', 'Highlight', 'Underline', 'Squiggly', 'StrikeOut',
             'Caret', 'Stamp', 'Ink', 'Square', 'Circle', 'Line', 'Polygon', 'PolyLine',
             'FileAttachment', 'Sound', 'Redact'}
    for page_index, (page, _) in enumerate(pdf.pages()):
        annots = pdf.resolve(page.get('Annots'))
        if not isinstance(annots, list):
            continue
        for ref in annots[:256]:
            key = (ref.num, ref.gen) if isinstance(ref, PDFRef) else id(ref)
            if key in seen:
                continue
            seen.add(key)
            annot = pdf.resolve(ref)
            if not isinstance(annot, dict) or str(annot.get('Subtype')) not in kinds:
                continue
            contents = independent_string(pdf.resolve(annot.get('Contents'))).strip()
            if not contents:
                rich = pdf.resolve(annot.get('RC'))
                if isinstance(rich, PDFStream):
                    rich = pdf.decode_stream_bytes(rich)
                contents = independent_rc(rich)
            if contents:
                records.append({'number': len(records) + 1, 'page': page_index + 1,
                                'subtype': str(annot.get('Subtype')), 'areas': _areas(pdf, annot)})
    if not records:
        return {'records': []}
    selected = {}
    terminal = {}
    selected_points = {}
    original = reader_module.attach_comments

    def capture(fragments, regions, warnings):
        original(fragments, regions, warnings)
        for frag in fragments:
            for first, last, target in frag.comment_spans:
                number = int(target)
                selected[number] = selected.get(number, '') + frag.text[first:last]
                direction = math.hypot(frag.dir_x, frag.dir_y)
                up = math.hypot(frag.up_x, frag.up_y)
                for index in range(first, last):
                    distance = (frag.char_offsets[index] + frag.char_offsets[index + 1]) / 2
                    x = frag.x + frag.dir_x / direction * distance + frag.up_x / up * frag.size / 2
                    y = frag.y + frag.dir_y / direction * distance + frag.up_y / up * frag.size / 2
                    if frag.text[index].strip():
                        selected_points.setdefault(number, []).append((frag.text[index], x, y))
            for last, number in frag.comment_markers:
                terminal[number] = frag.text[:last]

    reader_module.attach_comments = capture
    try:
        document = reader_module.PDFReader().read(str(path))
    finally:
        reader_module.attach_comments = original
    final = {}
    fallback = set()
    for paragraph in document.find_all('paragraph'):
        prefix = ''
        for run in paragraph.runs:
            if run.note_reference_type == 'comment':
                if getattr(run.provenance, 'path', '') == 'annots':
                    fallback.add(run.note_reference_number)
                else:
                    final[run.note_reference_number] = prefix
            else:
                prefix += run.text
    oracle_error = None
    try:
        independent = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        independent = None
        oracle_error = str(exc)
    try:
        glyph_cache = {}
        for row in records:
            page_index = row['page'] - 1
            if independent is None:
                glyph_cache[page_index] = []
            if page_index not in glyph_cache:
                page = independent[page_index]
                textpage = page.get_textpage()
                try:
                    glyphs = []
                    for index in range(textpage.count_chars()):
                        char = textpage.get_text_range(index, 1)
                        if not char.strip():
                            continue
                        left, bottom, right, top = textpage.get_charbox(index)
                        glyphs.append((char, (left + right) / 2, (bottom + top) / 2))
                    glyph_cache[page_index] = glyphs
                finally:
                    textpage.close()
                    page.close()
            expected = ''.join(char for char, x, y in glyph_cache[page_index]
                               if any(_inside(area, x, y) for area in row['areas']))
            number = row['number']
            # Reading order is not geometry: PDFium returns logical Hebrew while
            # the content stream draws visual order. Compare character identities
            # in the same physical x/y order, retaining both original strings.
            expected_points = [(char, x, y) for char, x, y in glyph_cache[page_index]
                               if any(_inside(area, x, y) for area in row['areas'])]
            actual_points = selected_points.get(number, []) if number in final else []
            spatial_expected = ''.join(p[0] for p in sorted(expected_points, key=lambda p: (p[1], p[2])))
            spatial_actual = ''.join(p[0] for p in sorted(actual_points, key=lambda p: (p[1], p[2])))
            actual = selected.get(number, '') if number in final else ''
            row.update(expected=expected if independent is not None else None, actual=actual,
                       spatial_expected=spatial_expected, spatial_actual=spatial_actual,
                       expected_points=expected_points, actual_points=actual_points,
                       extraction_order_differs=bool(actual and _compact(actual) != _compact(expected)),
                       status=('unverified' if independent is None else 'deferred' if not actual
                               else 'match' if _compact(spatial_actual) == _compact(spatial_expected) else 'mismatch'),
                       fallback=number in fallback,
                       final_anchor_valid=(number not in final or
                                           _compact(final[number]).endswith(_compact(terminal.get(number, '\x00')))))
    finally:
        if independent is not None:
            independent.close()
    return {'records': records, 'oracle_error': oracle_error,
            'definitions': len(document.find_all('comment')),
            'warnings': document.errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--files', nargs='*')
    args = parser.parse_args()

    def timeout(_signum, _frame):
        raise ProbeDeadline('document deadline')

    signal.signal(signal.SIGALRM, timeout)
    results = {}
    paths = [args.corpus / name for name in args.files] if args.files else sorted(args.corpus.glob('*.pdf'))
    for path in paths:
        try:
            signal.alarm(15)
            results[path.name] = verify(path)
        except (Exception, ProbeDeadline) as exc:
            results[path.name] = {'error': type(exc).__name__}
        finally:
            signal.alarm(0)
    records = [row for result in results.values() for row in result.get('records', [])]
    summary = {'files': len(paths), 'comments': len(records),
               'statuses': dict(Counter(row['status'] for row in records)),
               'subtypes': dict(Counter(row['subtype'] for row in records)),
               'supported_geometry_subtypes': sum(row['subtype'] in (
                   'Text', 'Highlight', 'Underline', 'StrikeOut', 'Squiggly') for row in records),
               'nonempty_independent_regions': sum(bool(row['expected']) for row in records),
               'extraction_order_differences': sum(row['extraction_order_differs'] for row in records),
               'fallback': sum(row['fallback'] for row in records),
               'oracle_errors': {name: result['oracle_error'] for name, result in results.items()
                                 if result.get('oracle_error')},
               'anchor_position_mismatches': sum(not row['final_anchor_valid'] for row in records),
               'errors': {name: result['error'] for name, result in results.items() if 'error' in result}}
    args.output.write_text(json.dumps({'summary': summary, 'files': results}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
