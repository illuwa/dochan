"""HWPX/PDF 병합 서명의 불일치를 파일명·본문 없는 집계로 감사한다.

사용법: python -m scripts.probe_pdf_spans <쌍 디렉터리> [--output 집계.json]
같은 행·열 수만으로 동일한 표라고 단정하지 않는다. 텍스트 집합 일치 역시
대응의 보조 증거이며, 시각적으로 숨긴 셀 경계를 복원할 근거는 아니다.
"""
import argparse
import json
from collections import Counter

from scripts.compare_pdf_pairs import (
    find_pairs, normalize_text, structure_matches, table_signature,
)

TOLERANCES = (0.25, 0.5, 0.75, 1.0, 2.0, 3.0)
FIELDS = (
    'exact', 'merged_total', 'merged_dims', 'merged_exact',
    'unmatched_with_same_dimensions', 'signature_multiplicity_only',
    'span_difference_candidates', 'equal_nonempty_text_sets',
    'partial_shared_text_candidates', 'no_shared_text_candidates',
    'missing_expected_boundary', 'present_inside_expected_merge',
    'equal_text_candidates_with_raw_geometry',
    'missing_boundary_without_raw_segment', 'missing_boundary_with_raw_segment',
    'tolerance_audited_candidates', 'tolerance_recovered_candidates',
)


def _texts(table):
    return {normalize_text(c.text) for row in table.rows for c in row
            if normalize_text(c.text)}


def _boundaries(table):
    owners = [[(r, c) for c in range(table.col_count)]
              for r in range(table.row_count)]
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row):
            if cell.is_merged_away:
                continue
            for rr in range(r, min(table.row_count, r + cell.row_span)):
                for cc in range(c, min(table.col_count, c + cell.col_span)):
                    owners[rr][cc] = (r, c)
    edges = set()
    for r in range(table.row_count):
        for c in range(table.col_count):
            if c + 1 < table.col_count and owners[r][c] != owners[r][c + 1]:
                edges.add(('v', r, c + 1))
            if r + 1 < table.row_count and owners[r][c] != owners[r + 1][c]:
                edges.add(('h', r + 1, c))
    return edges


def boundary_differences(answer, candidate):
    """동일 격자에서 정답 경계 누락과 정답 병합 내부 경계 수를 센다."""
    expected, actual = _boundaries(answer), _boundaries(candidate)
    return len(expected - actual), len(actual - expected)


def _raw_rule_present(edge, candidate, segments):
    direction, row, col = edge
    xs, ys = candidate.xs, candidate.ys
    if direction == 'h':
        return any(abs((s.y0 + s.y1) / 2 - ys[row]) <= 1.5
                   and abs(s.y1 - s.y0) <= 1.5
                   and min(s.x1, xs[col + 1]) - max(s.x0, xs[col]) > 0
                   for s in segments)
    return any(abs((s.x0 + s.x1) / 2 - xs[col]) <= 1.5
               and abs(s.x1 - s.x0) <= 1.5
               and min(s.y1, ys[row]) - max(s.y0, ys[row + 1]) > 0
               for s in segments)


def audit_tables(answer, candidate, geometry):
    """표 대응 후보를 감사하되 이름·텍스트·개별 좌표를 결과에 담지 않는다.

    geometry는 PDF 표 객체 id를 (TableCandidate, 선분, 텍스트 조각, 짧은 선분)에 매핑한다.
    원시 페이지를 보관하는 호출자는 문서 단위로 매핑을 비워야 한다.
    """
    from dochan.pdf.tables import build_tables

    result = Counter({key: 0 for key in FIELDS})
    expected = [table_signature(t) for t in answer]
    actual = [table_signature(t) for t in candidate]
    result.update(dict(zip(FIELDS[:4], structure_matches(expected, actual))))
    pool = Counter(actual)
    for source, signature in zip(answer, expected):
        if pool[signature]:
            pool[signature] -= 1
            continue
        if not signature[2]:
            continue
        options = [(t, s) for t, s in zip(candidate, actual)
                   if s[:2] == signature[:2]]
        if not options:
            continue
        result['unmatched_with_same_dimensions'] += 1
        if any(s == signature for _, s in options):
            result['signature_multiplicity_only'] += 1
            continue
        result['span_difference_candidates'] += 1
        source_text = _texts(source)
        target, _ = max(options, key=lambda item: len(source_text & _texts(item[0])))
        target_text = _texts(target)
        raw = geometry.get(id(target))
        if source_text and source_text == target_text:
            result['equal_nonempty_text_sets'] += 1
            missing, extra = boundary_differences(source, target)
            result['missing_expected_boundary'] += missing
            result['present_inside_expected_merge'] += extra
            if raw:
                tc, segments, _, short_segments = raw
                result['equal_text_candidates_with_raw_geometry'] += 1
                for edge in _boundaries(source) - _boundaries(target):
                    key = ('missing_boundary_with_raw_segment' if
                           _raw_rule_present(edge, tc, segments + short_segments) else
                           'missing_boundary_without_raw_segment')
                    result[key] += 1
        elif source_text & target_text:
            result['partial_shared_text_candidates'] += 1
        else:
            result['no_shared_text_candidates'] += 1
        if raw:
            result['tolerance_audited_candidates'] += 1
            _, segments, fragments, short_segments = raw
            recovered = False
            for tolerance in TOLERANCES:
                alternatives = build_tables(segments, fragments, tolerance=tolerance,
                                            short_segments=short_segments)
                recovered |= any(table_signature(t.table) == signature for t in alternatives)
            result['tolerance_recovered_candidates'] += recovered
    return dict(result)


def main(argv=None):
    from dochan import Dochan
    from dochan.pdf import reader

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pairs_dir')
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    original = reader.build_tables
    geometry = {}

    def capture(segments, fragments, *positional, **keywords):
        candidates = original(segments, fragments, *positional, **keywords)
        for table in candidates:
            geometry[id(table.table)] = (table, segments, fragments,
                                        keywords.get('short_segments') or [])
        return candidates

    summary = Counter({key: 0 for key in FIELDS})
    summary.update(pairs=0, failed_pairs=0)
    reader.build_tables = capture
    try:
        for _, hwpx, pdf in find_pairs(args.pairs_dir):
            geometry.clear()
            try:
                answer, candidate = Dochan(hwpx).doc, Dochan(pdf).doc
                summary.update(audit_tables(answer.find_all('table'),
                                            candidate.find_all('table'), geometry))
                summary['pairs'] += 1
            except Exception:
                # 예외 문자열에 내부 문서 경로·본문이 있을 수 있으므로 집계만 남긴다.
                summary['failed_pairs'] += 1
    finally:
        reader.build_tables = original
        geometry.clear()
    summary['merged_metric_gap'] = summary['merged_dims'] - summary['merged_exact']
    output = json.dumps(dict(summary), ensure_ascii=False, indent=2) + '\n'
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as stream:
            stream.write(output)
    print(output, end='')
    return int(bool(summary['failed_pairs']))


if __name__ == '__main__':
    raise SystemExit(main())
