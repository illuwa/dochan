"""공개 Office ZIP 차트의 원시 캐시·축·출력 표를 기록한다.

코퍼스 경로를 --roots로 받으며 문서를 수정하거나 복사하지 않는다.
--baseline은 전후 출력 변경을 기록한다. 표시 서식이 바뀐 셀의 정답은 별도
실물 검증에서 확인해야 하며, 단순 문자열 차이를 데이터 손실로 판정하지 않는다.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import zipfile

from lxml import etree

from dochan.ooxml.charts import (
    chart_caption, chart_title, hydrate_chart_references, normalize_chart,
    workbook_chart_resolver,
)
from dochan.ooxml.package import OOXMLPackage
from dochan.ooxml.xlsx import XLSXReader
from scripts.probe_ooxml_charts import _classic_series, _extended_series, _compare

C = '{http://schemas.openxmlformats.org/drawingml/2006/chart}'
CX = '{http://schemas.microsoft.com/office/drawing/2014/chartex}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
EXTENSIONS = {'.xlsx', '.xlsm', '.xltx', '.xltm', '.pptx', '.pptm', '.potx', '.docx', '.docm', '.dotx'}
MAX_PART_BYTES = 32 * 1024 * 1024
MAX_PARTS = 10000


def _val(node, tag):
    child = node.find(C + tag)
    return child.get('val', '') if child is not None else ''


def _inventory(xml):
    axes = []
    for axis in xml.findall('.//' + C + 'plotArea/*'):
        if etree.QName(axis).localname not in ('catAx', 'valAx', 'dateAx'):
            continue
        title = axis.find(C + 'title')
        axes.append({
            'kind': etree.QName(axis).localname,
            'id': _val(axis, 'axId'), 'cross': _val(axis, 'crossAx'),
            'position': _val(axis, 'axPos'),
            'title': ' '.join(title.itertext()).strip() if title is not None else '',
            'numFmt': dict(axis.find(C + 'numFmt').attrib) if axis.find(C + 'numFmt') is not None else {},
        })
    groups = []
    for group in xml.findall('.//' + C + 'plotArea/*'):
        if group.findall(C + 'ser'):
            groups.append({'kind': etree.QName(group).localname,
                           'axes': [axis.get('val') for axis in group.findall(C + 'axId')]})
    return {
        'axes': axes, 'groups': groups,
        'layouts': [s.get('layoutId') for s in xml.findall('.//' + CX + 'series')],
        'tx_data_titles': [n.text for n in xml.findall('.//' + CX + 'title/' + CX + 'tx/' + CX + 'txData/' + CX + 'v')],
        'format_codes': sorted(set(n.text or '' for n in xml.findall('.//' + C + 'formatCode'))),
        'auto_title_deleted': [_val(n, 'autoTitleDeleted') for n in xml.findall(C + 'chart')],
        'explicit_title': xml.find(C + 'chart/' + C + 'title') is not None or xml.find(CX + 'chart/' + CX + 'title') is not None,
    }


def _raw_table(normal):
    """표시 서식만 제거한 복제본으로 캐시의 원시 값 보존을 검사한다."""
    plain = deepcopy(normal)
    for node in list(plain.iter()):
        for attribute in list(node.attrib):
            if attribute.startswith('{urn:dochan:chart-display}'):
                del node.attrib[attribute]
        if node.tag in (C + 'formatCode', C + 'numFmt'):
            node.getparent().remove(node)
    reader = XLSXReader()
    reader._errors = []
    table = reader._chart_series_table(plain)
    return [[cell.text for cell in row] for row in table.rows]


def _value_check(series, rows):
    """범주 정렬 검증과 구분하여 계열별 원시 Y 값만 검사한다."""
    expected = matched = 0
    failures = []
    indices = sorted(set(i for _, xs, ys, _ in series for i in set(xs) | set(ys)))
    long_form = bool(rows and rows[0][0] == 'Series')
    for position, (name, xs, ys, _) in enumerate(series):
        label = name or 'Series %d' % (position + 1)
        local_indices = sorted(set(xs) | set(ys))
        local_rows = [r for r in rows[1:] if r and r[0] == label] if long_form else []
        for index, value in ys.items():
            expected += 1
            if long_form:
                row_index = local_indices.index(index)
                column = rows[0].index('Y')
                actual = local_rows[row_index][column] if row_index < len(local_rows) else None
            else:
                row_index = indices.index(index) + 1
                actual = rows[row_index][position + 1] if row_index < len(rows) and position + 1 < len(rows[row_index]) else None
            if actual == value:
                matched += 1
            else:
                failures.append({'series': label, 'index': index, 'expected': value, 'actual': actual})
    return {'expected': expected, 'matched': matched, 'failures': failures}


def _independent_display_checks(xml, rows):
    """stdlib 날짜 산술과 원시 문자열로 알려진 표시 정책을 독립 검사한다.

    일반 셀 formatter를 정답지로 쓰지 않는다. 지원하지 않는 서식은 검사 수에
    넣지 않으며, 날짜는 XLSX 셀 출력 계약인 ISO 표기를 기대한다.
    """
    series = _classic_series(xml)
    elements = xml.findall('.//' + C + 'plotArea/*/' + C + 'ser')
    if not rows or rows[0][0] == 'Series' or len(elements) != len(series):
        return []
    indices = sorted(set(i for _, xs, ys, _ in series for i in set(xs) | set(ys)))
    checks = []
    for position, (element, (_, xs, ys, _)) in enumerate(zip(elements, series)):
        for name, points, column in (('cat', xs, 0), ('val', ys, position + 1)):
            parent = element.find(C + name)
            if parent is None:
                continue
            code = parent.findtext('.//' + C + 'formatCode', '')
            if code not in ('h:mm', 'm/d/yyyy', '0.0%'):
                continue
            for index, value in points.items():
                if code == '0.0%':
                    expected = value
                else:
                    serial = float(value)
                    dt = datetime(1899, 12, 30) + timedelta(seconds=round(serial * 86400))
                    expected = dt.strftime('%Y-%m-%d %H:%M') if code == 'h:mm' else dt.strftime('%Y-%m-%d')
                row = indices.index(index) + 1
                actual = rows[row][column] if row < len(rows) and column < len(rows[row]) else None
                checks.append({'series': position, 'point': index, 'dimension': name,
                               'format': code, 'raw': value, 'expected': expected,
                               'actual': actual, 'match': expected == actual})
    return checks


def probe(roots):
    results = []
    scanned = Counter()
    paths = sorted(set(p for root in roots for p in root.rglob('*') if p.suffix.lower() in EXTENSIONS))
    for path in paths:
        scanned[path.suffix.lower()] += 1
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_PARTS:
                    raise ValueError('ZIP part count limit')
                parts = []
                for info in infos:
                    part = info.filename
                    if '/charts/' not in part or '/_rels/' in part or not part.endswith('.xml'):
                        continue
                    if info.file_size > MAX_PART_BYTES:
                        raise ValueError('chart XML size limit')
                    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
                    xml = etree.fromstring(archive.read(info), parser)
                    if xml.tag in (C + 'chartSpace', CX + 'chartSpace'):
                        parts.append((part, xml))
            if not parts:
                continue
            with OOXMLPackage(str(path)) as package:
                for part, xml in parts:
                    errors = []
                    normal = normalize_chart(deepcopy(xml), errors)
                    resolver = workbook_chart_resolver(package, errors) if path.suffix.lower() in ('.xlsx', '.xlsm', '.xltx', '.xltm') else None
                    hydrate_chart_references(normal, package, part, errors, resolver)
                    reader = XLSXReader()
                    reader._errors = errors
                    table = reader._chart_series_table(normal)
                    raw = _extended_series(xml) if xml.tag.startswith(CX) else _classic_series(xml)
                    rows = [[c.text for c in row] for row in table.rows]
                    raw_rows = _raw_table(normal)
                    expected, matched, failures = _compare(raw, raw_rows)
                    results.append(dict(
                        file=str(path), part=part,
                        kind='chartEx' if xml.tag.startswith(CX) else 'classic',
                        raw_series=raw,
                        cached_values=sum(len(s[2]) for s in raw),
                        rows=rows, raw_rows=raw_rows,
                        raw_check={'expected': expected, 'matched': matched, 'failures': failures},
                        value_check=_value_check(raw, raw_rows),
                        display_checks=_independent_display_checks(xml, rows),
                        title=chart_title(normal), caption=chart_caption(normal), errors=errors,
                        **_inventory(xml)
                    ))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
            results.append({'file': str(path), 'scan_error': str(exc)})
    return {'scanned': dict(scanned), 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roots', nargs='+', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    result = probe(args.roots)
    parts = [r for r in result['results'] if 'part' in r]
    result['summary'] = {
        'chart_files': len(set(r['file'] for r in parts)), 'chart_parts': len(parts),
        'cached_values': sum(r['cached_values'] for r in parts),
        'chart_ex_parts': sum(r['kind'] == 'chartEx' for r in parts),
        'scan_errors': sum('scan_error' in r for r in result['results']),
        'raw_expected': sum(r['raw_check']['expected'] for r in parts),
        'raw_matched': sum(r['raw_check']['matched'] for r in parts),
        'values_expected': sum(r['value_check']['expected'] for r in parts),
        'values_matched': sum(r['value_check']['matched'] for r in parts),
        'display_expected': sum(len(r['display_checks']) for r in parts),
        'display_matched': sum(sum(c['match'] for c in r['display_checks']) for r in parts),
    }
    if args.baseline:
        previous = json.loads(args.baseline.read_text())
        old = {(r['file'], r['part']): r for r in previous['results'] if 'part' in r}
        result['changes'] = []
        same_raw_rows = compared_raw_rows = 0
        for row in parts:
            before = old.get((row['file'], row['part']))
            if before is None:
                result['changes'].append({'file': row['file'], 'part': row['part'], 'added': True})
            else:
                if 'raw_rows' in before:
                    compared_raw_rows += 1
                    same_raw_rows += before['raw_rows'] == row['raw_rows']
                changed = [key for key in ('rows', 'title', 'caption', 'errors', 'raw_series')
                           if before[key] != json.loads(json.dumps(row[key]))]
                if changed:
                    result['changes'].append({'file': row['file'], 'part': row['part'], 'changed': changed})
        result['summary']['baseline_parts'] = len(old)
        result['summary']['raw_rows_compared'] = compared_raw_rows
        result['summary']['raw_rows_unchanged'] = same_raw_rows
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['summary']))


if __name__ == '__main__':
    main()
