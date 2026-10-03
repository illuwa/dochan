"""Independently check HWP chart OLE references against output and HWPX.

Usage: python -m scripts.verify_hwp_charts HWP_DIR HWPX_DIR [--internal DIR]
Uses olefile only in this optional development probe, never in dochan runtime.
"""
import argparse
from collections import Counter
from pathlib import Path
import struct
import unicodedata
import zlib
import xml.etree.ElementTree as ET  # nosemgrep: use-defused-xml -- independent oracle; declarations rejected before parsing

import olefile

from dochan import Dochan
from dochan.model.table import Table


C = '{http://schemas.openxmlformats.org/drawingml/2006/chart}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
HANCOM_CHART_CLSID = '5A721580-5AF0-11CE-8384-0020AF2337F2'
EXCEL_CHART_CLSID = '00020821-0000-0000-C000-000000000046'
MAX_PROBE_BYTES = 16 * 1024 * 1024
TYPE_NAMES = {
    'pieChart': 'pie', 'pie3DChart': '3-D pie', 'lineChart': 'line',
    'scatterChart': 'scatter', 'stockChart': 'stock', 'radarChart': 'radar',
}


def _inflate(data):
    obj = zlib.decompressobj(-15)
    result = obj.decompress(data, MAX_PROBE_BYTES + 1)
    if len(result) > MAX_PROBE_BYTES or not obj.eof:
        raise ValueError('probe inflation limit or incomplete stream')
    return result


def _records(data):
    offset = 0
    while offset + 4 <= len(data):
        header = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        tag = header & 0x3ff
        level = (header >> 10) & 0x3ff
        size = header >> 20
        if size == 0xfff:
            if offset + 4 > len(data):
                raise ValueError('truncated record length')
            size = struct.unpack_from('<I', data, offset)[0]
            offset += 4
        if offset + size > len(data):
            raise ValueError('truncated record data')
        yield tag, level, data[offset:offset + size]
        offset += size


def _embedded_xml(path):
    """Read slot -> storage mapping and occurrence order without dochan parsers."""
    xmls = []
    kinds = Counter()
    with olefile.OleFileIO(str(path)) as outer:
        paths = outer.listdir(streams=True, storages=False)
        ole_paths = {int(parts[1].split('.')[0][3:], 16): parts for parts in paths
                     if len(parts) == 2 and parts[0] == 'BinData'
                     and parts[1].upper().endswith('.OLE')
                     and parts[1][:3].upper() == 'BIN'}
        if not ole_paths:
            return xmls, kinds
        flags = struct.unpack_from('<I', outer.openstream('FileHeader').read(), 36)[0]
        compressed = bool(flags & 1)

        def read(parts):
            raw = outer.openstream(parts).read()
            return _inflate(raw) if compressed else raw

        entries = []
        for tag, _, data in _records(read('DocInfo')):
            if tag == 18 and len(data) >= 2:
                kind = struct.unpack_from('<H', data)[0] & 15
                storage = struct.unpack_from('<H', data, 2)[0] if kind in (1, 2) and len(data) >= 4 else 0
                entries.append((kind, storage))
        refs = []
        for parts in sorted(paths):
            if len(parts) != 2 or parts[0] not in ('BodyText', 'ViewText') or not parts[1].startswith('Section'):
                continue
            for tag, _, data in _records(read(parts)):
                if tag == 84 and len(data) >= 14:
                    refs.append(struct.unpack_from('<H', data, 12)[0])
        parsed = {}
        for slot in refs:
            if not 0 < slot <= len(entries):
                kinds['missing_reference'] += 1
                continue
            kind, storage = entries[slot - 1]
            if kind != 2 or storage not in ole_paths:
                continue
            if storage not in parsed:
                try:
                    raw = read(ole_paths[storage])
                    if len(raw) < 4 or struct.unpack_from('<I', raw)[0] != len(raw) - 4:
                        raise ValueError('OLE length mismatch')
                    with olefile.OleFileIO(raw[4:]) as inner:
                        clsid = str(inner.root.clsid).upper()
                        if inner.exists('OOXMLChartContents'):
                            parsed[storage] = ('ooxml', inner.openstream('OOXMLChartContents').read())
                        elif clsid == HANCOM_CHART_CLSID:
                            parsed[storage] = ('hancom_legacy', None)
                        elif clsid == EXCEL_CHART_CLSID:
                            parsed[storage] = ('excel', None)
                        else:
                            parsed[storage] = ('other', None)
                except (OSError, ValueError):
                    parsed[storage] = ('unreadable', None)
            label, xml = parsed[storage]
            kinds[label] += 1
            if xml is not None:
                xmls.append(xml)
    return xmls, kinds


def _points(series, axis):
    node = series.find(C + axis)
    if node is None:
        return None
    for path in (C + 'numRef/' + C + 'numCache', C + 'strRef/' + C + 'strCache',
                 C + 'numLit', C + 'strLit'):
        cache = node.find(path)
        if cache is not None:
            break
    else:
        return None
    count = cache.find(C + 'ptCount')
    size = int(count.get('val')) if count is not None else 0
    if size > 50000:
        raise ValueError('point count limit')
    values = [''] * size
    for point in cache.findall(C + 'pt'):
        index = int(point.get('idx'))
        value = point.find(C + 'v')
        if 0 <= index < size and value is not None:
            values[index] = value.text or ''
    return values


def _xml_values(data):
    upper = data.upper()
    if b'<!DOCTYPE' in upper or b'<!ENTITY' in upper or len(data) > MAX_PROBE_BYTES:
        raise ValueError('XML declaration or size forbidden')
    root = ET.fromstring(data)
    if root.tag != C + 'chartSpace':
        raise ValueError('chartSpace missing')
    chart = root.find(C + 'chart')
    if chart is None:
        raise ValueError('chart missing')
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
    series = []
    for item in chart.findall('.//' + C + 'ser'):
        values = _points(item, 'val') or _points(item, 'yVal')
        if values is not None:
            series.append((_points(item, 'cat') or _points(item, 'xVal'), values))
    return title, kind, series


def _chart_groups(doc):
    """Yield chart groups and local before/after anchors in reading order."""
    results = []

    def visit(blocks, depth=0):
        if depth > 32:
            return
        i = 0
        while i < len(blocks):
            block = blocks[i]
            if isinstance(block, Table) and (block.caption_text or '').startswith('Chart type:'):
                tables = [block]
                end = i + 1
                while end < len(blocks) and isinstance(blocks[end], Table) and not blocks[end].caption:
                    tables.append(blocks[end])
                    end += 1
                before = i - 1
                title = ''
                if before >= 0 and getattr(blocks[before], 'heading_level', 0) == 3:
                    title = blocks[before].text
                    before -= 1
                prev = getattr(blocks[before], 'text', '')[-30:] if before >= 0 else '<start>'
                nxt = getattr(blocks[end], 'text', '')[:30] if end < len(blocks) else '<end>'
                results.append((title, tables, (prev, nxt)))
                i = end
                continue
            if isinstance(block, Table):
                for row in block.rows:
                    for cell in row:
                        visit(cell.paragraphs, depth + 1)
                visit(block.caption, depth + 1)
            elif hasattr(block, 'paragraphs'):
                visit(block.paragraphs, depth + 1)
            elif hasattr(block, 'caption'):
                visit(block.caption, depth + 1)
            i += 1

    for section in doc.sections:
        visit(section.elements)
    return results


def _signature(group):
    title, tables, _ = group
    return (title, [(table.caption_text, [[cell.text for cell in row] for row in table.rows])
                    for table in tables])


def verify(hwp_dir, hwpx_dir, private=False):
    hwpx = {unicodedata.normalize('NFC', path.stem): path
            for path in Path(hwpx_dir).glob('*.hwpx')}
    stats = Counter()
    failures = []
    for path in sorted(Path(hwp_dir).glob('*.hwp')):
        try:
            xmls, kinds = _embedded_xml(path)
            if not kinds:
                continue
            stats['ole_documents'] += 1
            stats.update(kinds)
            if kinds['ooxml'] or kinds['excel'] or kinds['hancom_legacy']:
                stats['chart_documents'] += 1
            for label in ('ooxml', 'excel', 'hancom_legacy'):
                if kinds[label]:
                    stats[label + '_documents'] += 1
            if not xmls:
                continue
            groups = _chart_groups(Dochan(str(path)).doc)
            if len(groups) != len(xmls):
                stats['placement_mismatch'] += 1
                failures.append((path.name, 'placement count'))
                continue
            for data, group in zip(xmls, groups):
                title, kind, series = _xml_values(data)
                actual_title, tables, _ = group
                if len(series) != len(tables):
                    failures.append((path.name, 'series count'))
                    continue
                ordered = True
                for (cats, vals), table in zip(series, tables):
                    rows = [[cell.text for cell in row] for row in table.rows[1:]]
                    if [row[-1] for row in rows] != vals or (cats is not None and [row[0] for row in rows] != cats):
                        ordered = False
                if ordered:
                    stats['ordered_charts_match'] += 1
                else:
                    failures.append((path.name, 'ordered values'))
                if title:
                    stats['explicit_titles'] += 1
                    if title == actual_title:
                        stats['explicit_titles_match'] += 1
                    else:
                        failures.append((path.name, 'title'))
                if kind:
                    stats['known_kinds'] += 1
                    if tables[0].caption_text.startswith('Chart type: ' + kind):
                        stats['known_kinds_match'] += 1
                    else:
                        failures.append((path.name, 'kind'))
            stem = unicodedata.normalize('NFC', path.stem)
            partner = hwpx.get(stem) or hwpx.get(stem.removeprefix('rhwp-'))
            if partner is not None:
                stats['paired_documents'] += 1
                answer = _chart_groups(Dochan(str(partner)).doc)
                if [_signature(group) for group in groups] == [_signature(group) for group in answer]:
                    stats['paired_exact'] += 1
                else:
                    failures.append((path.name, 'HWPX tables'))
                if [group[2] for group in groups] == [group[2] for group in answer]:
                    stats['paired_anchors_exact'] += 1
                else:
                    failures.append((path.name, 'HWPX anchors'))
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
