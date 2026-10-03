"""Compare embedded HWP chart caches with HWPX output and independent XML values.

Usage: python -m scripts.verify_hwp_charts HWP_DIR HWPX_DIR [--internal DIR]
The internal directory is summarized without disclosing filenames or content.
"""
import argparse
from collections import Counter
from pathlib import Path
import struct
import unicodedata
import zlib
import xml.etree.ElementTree as ET  # nosemgrep: use-defused-xml -- independent gold; declarations rejected before parsing

from dochan import Dochan, cfb
from dochan.hwp.header import FileHeader
from dochan.hwp.section import SectionParser
from dochan.model.table import Table
from dochan.utils.bounded_io import read_ole_stream
from dochan.utils.safe_decompress import safe_zlib_decompress


C = '{http://schemas.openxmlformats.org/drawingml/2006/chart}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
TYPE_NAMES = {
    'pieChart': 'pie', 'pie3DChart': '3-D pie', 'lineChart': 'line',
    'scatterChart': 'scatter', 'stockChart': 'stock', 'radarChart': 'radar',
}


def _embedded_xml(path):
    result = []
    contents_only = 0
    unreadable = 0
    with cfb.OleFileIO(str(path)) as outer:
        ole_paths = [parts for parts in outer.listdir()
                     if len(parts) == 2 and parts[0] == 'BinData'
                     and parts[1].upper().endswith('.OLE')]
        if not ole_paths:
            return result, contents_only, unreadable
        header = FileHeader.parse(read_ole_stream(outer, 'FileHeader', max_bytes=256))
        referenced = set()
        for parts in outer.listdir():
            if len(parts) != 2 or parts[0] != header.body_storage or not parts[1].startswith('Section'):
                continue
            body = read_ole_stream(outer, '/'.join(parts))
            if header.is_compressed:
                body = safe_zlib_decompress(body)
            for record in SectionParser()._read_all_records(body):
                if record.tag_id == 84 and len(record.data) >= 14:
                    referenced.add(struct.unpack_from('<H', record.data, 12)[0])
        for parts in ole_paths:
            try:
                storage_id = int(parts[1].split('.')[0][3:], 16)
            except ValueError:
                continue
            if storage_id not in referenced:
                continue
            try:
                raw = read_ole_stream(outer, '/'.join(parts))
                if header.is_compressed:
                    raw = safe_zlib_decompress(raw)
                if len(raw) < 4 or struct.unpack_from('<I', raw)[0] != len(raw) - 4:
                    unreadable += 1
                    continue
                with cfb.OleFileIO(raw[4:], strict_recovery=True) as inner:
                    if inner.exists('OOXMLChartContents'):
                        result.append(read_ole_stream(inner, 'OOXMLChartContents', max_bytes=4 * 1024 * 1024))
                    elif inner.exists('Contents'):
                        contents_only += 1
            except (cfb.CFBError, ValueError, OSError, zlib.error):
                unreadable += 1
    return result, contents_only, unreadable


def _xml_values(data):
    upper = data.upper()
    if b'<!DOCTYPE' in upper or b'<!ENTITY' in upper:
        raise ValueError('XML declaration forbidden')
    root = ET.fromstring(data)
    if root.tag != C + 'chartSpace':
        raise ValueError('chartSpace missing')
    chart = root.find(C + 'chart')
    if chart is None:
        raise ValueError('chart missing')
    values = Counter()
    names = []
    title_node = chart.find(C + 'title/' + C + 'tx')
    title = ''
    if title_node is not None:
        direct = title_node.find(C + 'v')
        if direct is not None and direct.text:
            title = direct.text.strip()
        else:
            title = ' '.join(node.text.strip() for node in title_node.findall('.//' + A + 't')
                             if node.text and node.text.strip())
    plot = chart.find(C + 'plotArea')
    groups = [node for node in plot if node.tag.endswith('Chart')] if plot is not None else []
    kind = ''
    if len(groups) == 1:
        group = groups[0]
        name = group.tag.split('}')[-1]
        if name in ('barChart', 'bar3DChart'):
            direction = group.find(C + 'barDir')
            kind = ('3-D ' if name == 'bar3DChart' else '') + (
                'bar' if direction is not None and direction.get('val') == 'bar' else 'column')
        elif name == 'ofPieChart':
            subtype = group.find(C + 'ofPieType')
            kind = 'bar of pie' if subtype is not None and subtype.get('val') == 'bar' else 'pie of pie'
        else:
            kind = TYPE_NAMES.get(name, '')
    for series in chart.findall('.//' + C + 'ser'):
        source_name = series.find(C + 'tx')
        if source_name is not None:
            direct_name = source_name.find(C + 'v')
            if direct_name is None:
                direct_name = source_name.find('.//' + C + 'pt/' + C + 'v')
            if direct_name is not None and direct_name.text:
                names.append(direct_name.text.strip())
        for axis in ('cat', 'val', 'xVal', 'yVal', 'bubbleSize'):
            node = series.find(C + axis)
            if node is None:
                continue
            for point in node.findall('.//' + C + 'pt'):
                value = point.find(C + 'v')
                if value is not None and value.text is not None:
                    values[value.text] += 1
    return values, title, kind, names


def _chart_groups(doc):
    groups = []
    for section in doc.sections:
        current = None
        previous = None
        for block in section.elements:
            if isinstance(block, Table) and block.caption_text.startswith('Chart type:'):
                current = [block]
                title = previous.text if getattr(previous, 'heading_level', 0) == 3 else ''
                groups.append((title, current))
            elif isinstance(block, Table) and current is not None and not block.caption:
                current.append(block)
            elif isinstance(block, Table):
                current = None
            elif getattr(block, 'heading_level', 0) != 3:
                current = None
            previous = block
    return groups


def _signature(group):
    title, tables = group
    return (title, [(table.caption_text, [[cell.text for cell in row] for row in table.rows])
                    for table in tables])


def verify(hwp_dir, hwpx_dir, private=False):
    hwpx = {unicodedata.normalize('NFC', path.stem): path
            for path in Path(hwpx_dir).glob('*.hwpx')}
    stats = Counter()
    failures = []
    for path in sorted(Path(hwp_dir).glob('*.hwp')):
        try:
            xmls, binary_count, unreadable = _embedded_xml(path)
            if not xmls and not binary_count and not unreadable:
                continue
            stats['ole_documents'] += 1
            stats['xml_charts'] += len(xmls)
            stats['contents_only_streams'] += binary_count
            stats['unreadable_ole_streams'] += unreadable
            if not xmls:
                continue
            reader = Dochan(str(path))
            groups = _chart_groups(reader.doc)
            if len(groups) != len(xmls):
                stats['placement_mismatch'] += 1
                failures.append((path.name, 'placement'))
                continue
            for data, group in zip(xmls, groups):
                gold, title, kind, names = _xml_values(data)
                actual_title, tables = group
                output = Counter(cell.text for table in tables for row in table.rows for cell in row)
                if any(output[value] < count for value, count in gold.items()):
                    stats['xml_value_mismatch'] += 1
                    failures.append((path.name, 'independent XML values'))
                else:
                    stats['xml_values_match'] += 1
                if title:
                    stats['explicit_titles'] += 1
                    if title == actual_title:
                        stats['explicit_titles_match'] += 1
                    else:
                        failures.append((path.name, 'independent XML title'))
                if kind:
                    stats['known_kinds'] += 1
                    if tables[0].caption_text.startswith('Chart type: ' + kind):
                        stats['known_kinds_match'] += 1
                    else:
                        failures.append((path.name, 'independent XML kind'))
                stats['explicit_series_names'] += len(names)
                for name in names:
                    if any(name in cell for cell in output):
                        stats['explicit_series_names_match'] += 1
                    else:
                        failures.append((path.name, 'independent XML series name'))
            partner = hwpx.get(unicodedata.normalize('NFC', path.stem))
            if partner is not None:
                stats['paired_documents'] += 1
                answer = _chart_groups(Dochan(str(partner)).doc)
                if [_signature(group) for group in groups] == [_signature(group) for group in answer]:
                    stats['paired_exact'] += 1
                else:
                    failures.append((path.name, 'HWPX chart tables'))
        except Exception as exc:
            stats['exceptions'] += 1
            failures.append((path.name, type(exc).__name__))
    if private:
        return dict(stats), len(failures)
    return dict(stats), failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hwp_dir')
    parser.add_argument('hwpx_dir')
    parser.add_argument('--internal')
    args = parser.parse_args()
    public, failures = verify(args.hwp_dir, args.hwpx_dir)
    print('공개 표본:', public)
    print('공개 불일치:', failures)
    if args.internal:
        internal, failure_count = verify(args.internal, args.internal, private=True)
        print('내부 표본 집계:', internal, '불일치 수:', failure_count)


if __name__ == '__main__':
    main()
