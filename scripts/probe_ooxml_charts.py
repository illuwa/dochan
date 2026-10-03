"""POI 공개 OOXML 코퍼스의 모든 차트 파트 캐시와 리더 표를 독립 비교한다.

Usage: /usr/bin/python3 -m scripts.probe_ooxml_charts <test-data-dir> --output <json>
원본 패키지를 읽기만 하며 캐시 없는 참조는 별도로 집계한다.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import zipfile

from dochan.utils import safe_xml as etree

from dochan.ooxml.charts import normalize_chart, hydrate_chart_references, workbook_chart_resolver
from dochan.ooxml.package import OOXMLPackage
from dochan.ooxml.xlsx import XLSXReader
from dochan.ooxml.pptx import PPTXReader
from dochan.ooxml.docx import DOCXReader

C = '{http://schemas.openxmlformats.org/drawingml/2006/chart}'
CX = '{http://schemas.microsoft.com/office/drawing/2014/chartex}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'


def _cache_points(parent):
    if parent is None:
        return {}
    levels = parent.findall('.//' + C + 'multiLvlStrCache/' + C + 'lvl')
    if levels:
        maps = [{int(p.get('idx')): p.findtext(C + 'v', '') for p in level.findall(C + 'pt')} for level in levels]
        return {i: ' / '.join(m.get(i, '') for m in reversed(maps) if m.get(i, '')) for i in set(i for m in maps for i in m)}
    return {int(p.get('idx')): p.findtext(C + 'v', '') for p in parent.findall('.//' + C + 'pt') if p.get('idx', '').isdigit()}


def _classic_series(root):
    result = []
    plot = root.find(C + 'chart/' + C + 'plotArea')
    if plot is None:
        return result
    for group in plot:
        for series in group.findall(C + 'ser'):
            name = ' '.join(n.text or '' for n in series.findall(C + 'tx/.//' + C + 'v'))
            xs = _cache_points(series.find(C + 'cat')) or _cache_points(series.find(C + 'xVal'))
            ys = _cache_points(series.find(C + 'val')) or _cache_points(series.find(C + 'yVal'))
            sizes = _cache_points(series.find(C + 'bubbleSize'))
            result.append((name, xs, ys, sizes))
    return result


def _extended_series(root):
    datasets = {d.get('id'): d for d in root.findall(CX + 'chartData/' + CX + 'data')}
    result = []
    for series in root.findall(CX + 'chart/' + CX + 'plotArea/' + CX + 'plotAreaRegion/' + CX + 'series'):
        dataid = series.find(CX + 'dataId')
        data = datasets.get(dataid.get('val')) if dataid is not None else None
        if data is None:
            continue
        name = series.findtext(CX + 'tx/' + CX + 'txData/' + CX + 'v', '')
        xs, ys = {}, {}
        for dim in data:
            levels = [{int(p.get('idx')): p.text or '' for p in level.findall(CX + 'pt')} for level in dim.findall(CX + 'lvl')]
            if not levels:
                continue
            points = {i: ' / '.join(m.get(i, '') for m in reversed(levels) if m.get(i, '')) for i in set(i for m in levels for i in m)}
            if dim.get('type') == 'cat':
                xs = points
            else:
                ys = points
        result.append((name, xs, ys, {}))
    return result


def _xml_title(title, namespace):
    if title is None:
        return ''
    paragraphs = title.findall('.//' + namespace + 'rich/' + A + 'p')
    if paragraphs:
        return ' '.join(''.join(t.text or '' for t in p.findall('.//' + A + 't')) for p in paragraphs).strip()
    values = title.findall('.//' + namespace + 'strCache/' + namespace + 'pt/' + namespace + 'v')
    return ' '.join(v.text or '' for v in values).strip()


def _expected_annotations(root):
    namespace = CX if root.tag.startswith(CX) else C
    chart = root.find(namespace + 'chart')
    if chart is None:
        return '', ''
    title = _xml_title(chart.find(namespace + 'title'), namespace)
    plot = chart.find(namespace + 'plotArea')
    if plot is None:
        return title, ''
    labels = []
    axes = []
    mapping = {'lineChart': 'line', 'line3DChart': '3-D line', 'pieChart': 'pie',
               'pie3DChart': '3-D pie', 'areaChart': 'area', 'area3DChart': '3-D area',
               'doughnutChart': 'doughnut', 'scatterChart': 'scatter', 'bubbleChart': 'bubble',
               'radarChart': 'radar', 'stockChart': 'stock', 'surfaceChart': 'surface',
               'surface3DChart': '3-D surface'}
    if namespace == CX:
        layouts = {'boxWhisker': 'box and whisker', 'sunburst': 'sunburst', 'treemap': 'treemap'}
        for series in plot.findall(namespace + 'plotAreaRegion/' + namespace + 'series'):
            label = layouts.get(series.get('layoutId'), '')
            if label and label not in labels:
                labels.append(label)
    else:
        for child in plot:
            name = etree.QName(child).localname
            label = mapping.get(name, '')
            if name in ('barChart', 'bar3DChart'):
                direction = child.find(C + 'barDir')
                label = 'bar' if direction is not None and direction.get('val') == 'bar' else 'column'
                if name == 'bar3DChart':
                    label = '3-D ' + label
            if name == 'ofPieChart':
                pie_type = child.find(C + 'ofPieType')
                label = 'bar of pie' if pie_type is not None and pie_type.get('val') == 'bar' else 'pie of pie'
            if label and label not in labels:
                labels.append(label)
            axis_type = {'catAx': 'Category axis', 'valAx': 'Value axis', 'dateAx': 'Date axis', 'serAx': 'Series axis'}.get(name)
            deleted = child.find(C + 'delete')
            if axis_type and not (deleted is not None and deleted.get('val', '1') in ('1', 'true', 'on')):
                text = _xml_title(child.find(C + 'title'), C)
                if text:
                    axes.append(axis_type + ': ' + text)
    return title, '; '.join((['Chart type: ' + ' + '.join(labels)] if labels else []) + axes)


def _compare(series, rows):
    expected = 0
    matched = 0
    failures = []
    long_form = bool(rows and rows[0][:3] == ['Series', 'X', 'Y'])
    for position, (name, xs, ys, sizes) in enumerate(series):
        label = name or 'Series %d' % (position + 1)
        for index, value in ys.items():
            expected += 1
            if long_form:
                good = any(row[0] == label and row[1] == xs.get(index, str(index + 1)) and row[2] == value and (not sizes or len(row) > 3 and row[3] == sizes.get(index, '')) for row in rows[1:])
            else:
                indexes = sorted(set(i for _, x, y, _ in series for i in set(x) | set(y)))
                row_index = indexes.index(index) + 1
                good = row_index < len(rows) and position + 1 < len(rows[row_index]) and rows[row_index][position + 1] == value
                if xs.get(index):
                    good = good and rows[row_index][0] == xs[index]
            if good:
                matched += 1
            else:
                failures.append({'series': label, 'index': index, 'expected_x': xs.get(index), 'expected_y': value})
    return expected, matched, failures


def probe(root):
    results = []
    for folder, extension, reader_type in [('spreadsheet', 'xlsx', XLSXReader), ('slideshow', 'pptx', PPTXReader), ('document', 'docx', DOCXReader)]:
        for path in sorted((root / folder).rglob('*.' + extension)):
            try:
                with zipfile.ZipFile(path) as z:
                    parts = []
                    for part in z.namelist():
                        if '/charts/' not in part or '/_rels/' in part or not part.endswith('.xml'):
                            continue
                        xml = etree.fromstring(z.read(part))
                        if xml.tag in (C + 'chartSpace', CX + 'chartSpace'):
                            parts.append((part, xml))
                if not parts:
                    continue
                document = reader_type().read(str(path))
                tables = document.find_all('table')
                for part, original in parts:
                    table = next((t for t in tables if
                                  getattr(getattr(t, 'provenance', None), 'path', '') == part
                                  or any(getattr(getattr(p, 'provenance', None), 'path', '') == part
                                         for p in (getattr(t, 'caption', None) or []))), None)
                    emitted = table is not None
                    if table is None:
                        # 고아 파트와 미지원 앵커도 파트 단위 변환 결과를 별도로 검사한다.
                        chart_reader = XLSXReader()
                        chart_reader._errors = []
                        with OOXMLPackage(str(path)) as package:
                            normalized = normalize_chart(deepcopy(original), chart_reader._errors)
                            hydrate_chart_references(normalized, package, part, chart_reader._errors, workbook_chart_resolver(package, chart_reader._errors) if extension == 'xlsx' else None)
                            table = chart_reader._chart_series_table(normalized)
                    expected_title, expected_caption = _expected_annotations(original)
                    actual_titles = [p.text for p in document.find_all('paragraph')
                                     if p.heading_level == 3 and getattr(getattr(p, 'provenance', None), 'path', '') == part]
                    actual_caption = '; '.join(p.text for p in (getattr(table, 'caption', None) or []))
                    rows = [[cell.text for cell in row] for row in table.rows]
                    series = _extended_series(original) if original.tag.startswith(CX) else _classic_series(original)
                    expected, matched, failures = _compare(series, rows)
                    results.append({'format': extension, 'file': path.name, 'part': part, 'kind': 'chartEx' if original.tag.startswith(CX) else 'classic', 'emitted': emitted, 'cached_values': expected, 'matched': matched, 'failures': failures, 'rows': len(rows), 'errors': document.errors, 'expected_title': expected_title, 'actual_titles': actual_titles,
                                    'title_match': (actual_titles == [expected_title] if expected_title else not actual_titles),
                                    'expected_caption': expected_caption, 'actual_caption': actual_caption,
                                    'caption_match': (actual_caption == expected_caption) if emitted else None})
            except (OSError, ValueError, KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
                results.append({'format': extension, 'file': path.name, 'scan_error': str(exc)})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = probe(args.corpus)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    for extension in ['xlsx', 'pptx', 'docx']:
        selected = [r for r in results if r['format'] == extension and 'part' in r]
        print(extension, 'files', len(set(r['file'] for r in selected)), 'parts', len(selected), 'emitted', sum(r['emitted'] for r in selected), 'cached_values', sum(r['cached_values'] for r in selected), 'matched', sum(r['matched'] for r in selected), 'titled_parts', sum(bool(r['expected_title']) for r in selected),
              'title_matches', sum(r['title_match'] for r in selected if r['expected_title']),
              'caption_matches', sum(bool(r['caption_match']) for r in selected))
    print('scan_errors', sum('scan_error' in row for row in results))
    for row in results:
        if row.get('failures'):
            print('MISMATCH', row['file'], row['part'], row['failures'][:3])


if __name__ == '__main__':
    main()
