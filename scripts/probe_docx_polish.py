"""공개 DOCX 코퍼스의 문단·제목·Markdown을 리비전별로 비교한다.

실물 파일은 읽기만 하며 출력에는 공개 표본 이름과 파싱 결과를 기록한다.
예: python -m scripts.probe_docx_polish CORPUS OUTPUT --revision 785c0e0
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import resource
import zipfile


def load_revision_module(revision, path, name):
    source = subprocess.check_output(['git', 'show', revision + ':' + path], text=True)
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(source, path, 'exec'), module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--revision')
    parser.add_argument('--chart-benchmark', action='store_true',
                        help='코퍼스 대신 20,000점 차트를 500회 참조하는 합성 패키지를 측정한다.')
    args = parser.parse_args()
    from dochan.ooxml.docx import DOCXReader
    from dochan.output.markdown import to_markdown
    if args.revision:
        DOCXReader = load_revision_module(args.revision, 'dochan/ooxml/docx.py',
                                         'dochan.ooxml._probe_docx').DOCXReader
        to_markdown = load_revision_module(args.revision, 'dochan/output/markdown.py',
                                          'dochan.output._probe_markdown').to_markdown
    if args.chart_benchmark:
        benchmark_chart(DOCXReader, args.output)
        return
    results = {}
    start = time.perf_counter()
    for path in sorted(args.corpus.glob('*.docx')):
        doc = DOCXReader().read(str(path))
        paragraphs = doc.find_all('paragraph')
        results[path.name] = {
            'paragraphs': [(p.heading_level, p.text) for p in paragraphs],
            'headings': [p.text for p in paragraphs if p.heading_level],
            'images': len(doc.find_all('image')),
            'tables': len(doc.find_all('table')),
            'errors': doc.errors,
            'markdown': to_markdown(doc),
        }
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print('%s: %d documents, %.2fs' % (args.revision or 'working tree', len(results),
                                      time.perf_counter() - start))


def benchmark_chart(reader_class, output):
    w = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    c = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
    points = ''.join('<c:pt idx="%d"><c:v>%d</c:v></c:pt>' % (i, i) for i in range(20000))
    chart = ('<c:chartSpace xmlns:c="%s"><c:chart><c:plotArea><c:barChart><c:ser>'
             '<c:val><c:numLit>%s</c:numLit></c:val></c:ser></c:barChart>'
             '</c:plotArea></c:chart></c:chartSpace>') % (c, points)
    body = '<w:p><w:r><w:drawing><c:chart r:id="chart"/></w:drawing></w:r></w:p>' * 500
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'repeated-chart.docx'
        with zipfile.ZipFile(path, 'w') as package:
            package.writestr('[Content_Types].xml', '<Types/>')
            package.writestr('word/document.xml',
                            '<w:document xmlns:w="%s" xmlns:r="%s" xmlns:c="%s">'
                            '<w:body>%s</w:body></w:document>' % (w, r, c, body))
            package.writestr('word/_rels/document.xml.rels',
                            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                            '<Relationship Id="chart" Type="%s/chart" Target="charts/chart1.xml"/>'
                            '</Relationships>' % r)
            package.writestr('word/charts/chart1.xml', chart)
        start = time.perf_counter()
        doc = reader_class().read(str(path))
        elapsed = time.perf_counter() - start
        tables = doc.find_all('table')
        result = {'seconds': elapsed,
                  'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  'tables': len(tables), 'cells': sum(len(row) for t in tables for row in t.rows),
                  'first_value': tables[0].rows[1][1].text,
                  'last_value': tables[-1].rows[-1][1].text, 'errors': doc.errors}
        output.write_text(json.dumps(result, indent=2))
        print(json.dumps(result))


if __name__ == '__main__':
    main()
