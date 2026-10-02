"""본문 링크 보류의 원인을 원시 주석·폰트·콘텐츠 위치로 분류한다.

연결 정확도는 probe_pdf_link_boundaries의 독립 글리프 결과를 사용한다.
이 프로브의 기하 분류는 제품 좌표를 진단할 뿐 독립 정답으로 세지 않는다.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path

from dochan.pdf.annotations import DestinationResolver, _contains, link_regions
from dochan.pdf.content import ContentTextExtractor
from dochan.pdf.objects import PDFStream
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile


def _point(fragment, distance):
    direction = math.hypot(fragment.dir_x, fragment.dir_y)
    up = math.hypot(fragment.up_x, fragment.up_y)
    return (fragment.x + fragment.dir_x / direction * distance
            + fragment.up_x / up * fragment.size * 0.5,
            fragment.y + fragment.dir_y / direction * distance
            + fragment.up_y / up * fragment.size * 0.5)


def _form_intersects(pdf, resources, content, region):
    """직접 호출된 단위 행렬 Form의 BBox를 원시 주석과 대조한다."""
    forms = pdf.resolve(resources.get('XObject')) if isinstance(resources, dict) else None
    if not isinstance(forms, dict):
        return False
    for name, ref in list(forms.items())[:65536]:
        form = pdf.resolve(ref)
        if not isinstance(form, PDFStream) or str(form.dictionary.get('Subtype')) != 'Form':
            continue
        if ('/' + str(name) + ' Do').encode() not in content:
            continue
        matrix = pdf.resolve(form.dictionary.get('Matrix', [1, 0, 0, 1, 0, 0]))
        box = pdf.resolve(form.dictionary.get('BBox'))
        if matrix != [1, 0, 0, 1, 0, 0] or not isinstance(box, list) or len(box) != 4:
            continue
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box):
            continue
        if b'Tj' not in pdf.decode_stream_bytes(form) and b'TJ' not in pdf.decode_stream_bytes(form):
            continue
        x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        if any(_contains(poly, x, y) for poly in region.polygons):
            return True
    return False


def classify(pdf, resources, content, fragments, region, regions):
    cuts = False
    native_hit = False
    uncertain_line = False
    overlapping_target = False
    for frag in fragments:
        reliable = (frag.link_geometry_reliable and len(frag.char_offsets) == len(frag.text) + 1
                    and math.hypot(frag.dir_x, frag.dir_y) and math.hypot(frag.up_x, frag.up_y))
        if not reliable:
            for polygon in region.polygons:
                low, high = min(y for _, y in polygon), max(y for _, y in polygon)
                if min(frag.y, frag.y + frag.size) <= high and max(frag.y, frag.y + frag.size) >= low:
                    uncertain_line = True
            continue
        for index, char in enumerate(frag.text):
            if char.isspace():
                continue
            first, last = frag.char_offsets[index:index + 2]
            center = _point(frag, (first + last) / 2)
            inset = min(abs(last - first) / 4, 1e-5)
            edges = (_point(frag, first + inset), _point(frag, last - inset))
            for polygon in region.polygons:
                middle = _contains(polygon, *center)
                native_hit |= middle
                if middle and any(other.target != region.target and any(
                        _contains(poly, *center) for poly in other.polygons) for other in regions):
                    overlapping_target = True
                cuts |= any(_contains(polygon, *edge) != middle for edge in edges)
    if not native_hit and _form_intersects(pdf, resources, content, region):
        return 'unextracted_form_text'
    if uncertain_line:
        return 'unreliable_geometry_on_line'
    if cuts:
        return 'advance_boundary_cut'
    if not native_hit:
        return 'no_native_glyph_center'
    return 'different_destinations_overlap' if overlapping_target else 'final_output_filter'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before = json.loads(args.baseline.read_text())['results']
    after = json.loads(args.after.read_text())['results']
    records = []
    reader = PDFReader()
    for name, result in before.items():
        deferred = [row for row in result.get('records', []) if row['status'] == 'deferred']
        if not deferred:
            continue
        after_result = after.get(name)
        unavailable = None
        if after_result is None:
            unavailable = 'after_result_missing'
        elif 'error' in after_result:
            unavailable = 'after_probe_error'
        elif 'records' not in after_result:
            unavailable = 'after_records_missing'
        current = {(r['page'], r['annotation_index']): r
                   for r in after_result.get('records', [])} if not unavailable else {}
        available = []
        for row in deferred:
            cause = unavailable
            if cause is None and (row['page'], row['annotation_index']) not in current:
                cause = 'after_record_missing'
            if cause is None:
                available.append(row)
                continue
            record = {'file': name, 'page': row['page'],
                      'annotation_index': row['annotation_index'], 'cause': cause,
                      'after_status': 'error' if cause == 'after_probe_error' else 'missing',
                      'has_drawn_text': bool(row['expected'])}
            if cause == 'after_probe_error':
                record['error'] = after_result['error']
            records.append(record)
        deferred = available
        if not deferred:
            continue
        pdf = PDFFile((args.corpus / name).read_bytes())
        pages = pdf.pages()
        destinations = DestinationResolver(pdf, pages)
        cache = {}
        for page_number in sorted({row['page'] for row in deferred}):
            page, resources = pages[page_number - 1]
            content = b'\n'.join(reader._page_content_parts(pdf, page))
            fragments = ContentTextExtractor.from_fonts(reader._font_infos(pdf, resources, cache),
                                                        track_char_positions=True).extract_fragments(content)
            regions = link_regions(pdf, page, destinations)
            for row in (r for r in deferred if r['page'] == page_number):
                final = current[page_number, row['annotation_index']]
                if not row['expected']:
                    cause = 'no_independent_drawn_text'
                elif final['status'] == 'match':
                    cause = 'disjoint_same_destination_recovered'
                else:
                    cause = classify(pdf, resources, content, fragments, regions[row['annotation_index']], regions)
                records.append({'file': name, 'page': page_number,
                                'annotation_index': row['annotation_index'], 'cause': cause,
                                'after_status': final['status'], 'has_drawn_text': bool(row['expected'])})
    summary = dict(Counter(row['cause'] for row in records))
    by_document = {name: dict(Counter(row['cause'] for row in records if row['file'] == name))
                   for name in sorted({row['file'] for row in records})}
    args.output.write_text(json.dumps({'summary': summary, 'by_document': by_document,
                                      'records': records}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
