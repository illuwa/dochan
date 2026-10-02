"""합성 최악 입력으로 연결형 표 분석 시간을 측정한다. 코퍼스는 사용하지 않는다."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter


def rejected_boxes(count):
    from dochan.pdf.content import Fragment
    from dochan.pdf.paths import Segment

    height = 40 * count + 40
    segments = [Segment(0, 0, 300, 0), Segment(0, height, 300, height),
                Segment(0, 0, 0, height), Segment(300, 0, 300, height)]
    fragments = []
    for i in range(count):
        y = 40 * i + 20
        segments.extend([Segment(0, y, 100, y), Segment(0, y + 10, 100, y + 10),
                         Segment(0, y + 20, 100, y + 20), Segment(100, y, 100, y + 20)])
        fragments.append(Fragment(10, y + 2, 2, 4, 'x', 2, order=i))
    return segments, fragments


def stairs(steps, components):
    from dochan.pdf.content import Fragment
    from dochan.pdf.paths import Segment

    segments = []
    for j in range(components):
        for i in range(steps):
            x, y = 10 * i, 20000 * j + 10 * i
            segments.extend([Segment(x, y, x + 10, y),
                             Segment(x + 10, y, x + 10, y + 10),
                             Segment(x + 5, y - 3, x + 5, y),
                             Segment(x + 10, y + 5, x + 13, y + 5)])
    return segments, [Fragment(3, 50, 5, 8, 't', 3)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--repeat', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 10:
        parser.error('repeat must be 1..10')
    sys.path.insert(0, str(args.repo.resolve()))
    from dochan.pdf.tables import build_tables

    cases = [('rejected_boxes_{}'.format(n), rejected_boxes(n)) for n in (100, 200, 300)]
    cases.extend([('stairs_2000_lines_x10', stairs(500, 10)),
                  ('stairs_1000_lines_x20', stairs(250, 20)),
                  ('stairs_400_lines_x20', stairs(100, 20))])
    rows = {}
    for name, (segments, fragments) in cases:
        elapsed = []
        for _ in range(args.repeat):
            warnings = []
            start = perf_counter()
            found = build_tables(segments, fragments, warnings=warnings)
            elapsed.append(perf_counter() - start)
        rows[name] = {'seconds': elapsed, 'median_seconds': median(elapsed),
                      'segments': len(segments), 'tables': len(found), 'warnings': warnings}
        print('{}: {:.6f}s'.format(name, median(elapsed)), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
