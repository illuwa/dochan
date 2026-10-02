"""출력 비교에서 바뀐 시트 셀을 원시 XML·BIFF 숫자와 연결한다.

형식 해석은 검사 대상 formatter를 호출하지 않고 XML 속성과 레코드 바이트를
그대로 기록한다. 입력과 출력 디렉터리는 명령행으로 받는다.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import posixpath
import struct
import zipfile

from lxml import etree


def xml(data):
    return etree.fromstring(data, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True))


def ooxml_cells(path, resolve_strings=False):
    result = {}
    with zipfile.ZipFile(path) as archive:
        strings = []
        if resolve_strings and 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(n.itertext()) for n in xml(archive.read('xl/sharedStrings.xml'))]
        workbook = xml(archive.read('xl/workbook.xml'))
        date1904 = any(etree.QName(n).localname == 'workbookPr' and n.get('date1904') in ('1', 'true') for n in workbook.iter())
        rels = xml(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {r.get('Id'): r.get('Target') for r in rels}
        styles = xml(archive.read('xl/styles.xml')) if 'xl/styles.xml' in archive.namelist() else None
        formats = {int(n.get('numFmtId')): n.get('formatCode') for n in styles.iter()
                   if etree.QName(n).localname == 'numFmt'} if styles is not None else {}
        xfs = []
        if styles is not None:
            for element in styles:
                if etree.QName(element).localname == 'cellXfs':
                    xfs = [int(n.get('numFmtId', '0')) for n in element]
        for sheet in workbook.iter():
            if etree.QName(sheet).localname != 'sheet':
                continue
            rid = next((v for k, v in sheet.attrib.items() if k.endswith('}id')), '')
            target = targets.get(rid, '')
            part = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            if part not in archive.namelist():
                continue
            root = xml(archive.read(part))
            for cell in root.iter():
                if etree.QName(cell).localname != 'c':
                    continue
                value = next((n.text for n in cell if etree.QName(n).localname == 'v'), None)
                style = int(cell.get('s', '0'))
                format_id = xfs[style] if style < len(xfs) else 0
                result[sheet.get('name', '') + '!' + cell.get('r', '')] = {
                    'raw': value, 'type': cell.get('t', 'n'), 'date1904': date1904,
                    'literal': strings[int(value)] if cell.get('t') == 's' and value is not None and int(value) < len(strings) else None,
                    'format': formats.get(format_id, 'builtin:' + str(format_id)),
                    'source': part + ':' + cell.get('r', '')}
    return result


def records(data, start=0):
    while start + 4 <= len(data):
        kind, size = struct.unpack_from('<HH', data, start)
        end = start + 4 + size
        if end > len(data):
            return
        yield start, kind, data[start + 4:end]
        start = end


def unicode_string(data, offset):
    size, flags = struct.unpack_from('<HB', data, offset)
    raw = data[offset + 3:offset + 3 + size * (2 if flags & 1 else 1)]
    return raw.decode('utf-16-le' if flags & 1 else 'cp1252', errors='replace')


def cell_ref(row, col):
    letters = ''
    col += 1
    while col:
        col, mod = divmod(col - 1, 26)
        letters = chr(65 + mod) + letters
    return letters + str(row + 1)


def rk(value):
    if value & 2:
        number = (value >> 2) - (0x40000000 if value & 0x80000000 else 0)
    else:
        number = struct.unpack('<d', b'\0' * 4 + struct.pack('<I', value & 0xfffffffc))[0]
    return number / 100 if value & 1 else number


def xls_cells(path):
    import olefile
    with olefile.OleFileIO(str(path)) as archive:
        stream = 'Workbook' if archive.exists('Workbook') else 'Book'
        data = archive.openstream(stream).read()
    sheets, formats, xfs = [], {}, []
    for _, kind, payload in records(data):
        if kind == 0x85 and len(payload) >= 8:
            start = struct.unpack_from('<I', payload)[0]
            size, flags = payload[6:8]
            name = payload[8:8 + size * (2 if flags & 1 else 1)].decode(
                'utf-16-le' if flags & 1 else 'cp1252', errors='replace')
            sheets.append((name, start))
        elif kind == 0x41e and len(payload) >= 5:
            formats[struct.unpack_from('<H', payload)[0]] = unicode_string(payload, 2)
        elif kind == 0xe0 and len(payload) >= 4:
            xfs.append(struct.unpack_from('<H', payload, 2)[0])
        elif kind == 0xa:
            break
    result = {}
    for sheet, start in sheets:
        for offset, kind, payload in records(data, start):
            values = []
            if kind in (0x203, 0x3, 0x6) and len(payload) >= 14:
                if kind != 0x6 or payload[12:14] != b'\xff\xff':
                    row, col, xf = struct.unpack_from('<HHH', payload)
                    values.append((row, col, xf, struct.unpack_from('<d', payload, 6)[0]))
            elif kind == 0x27e and len(payload) >= 10:
                row, col, xf, number = struct.unpack_from('<HHHI', payload)
                values.append((row, col, xf, rk(number)))
            elif kind == 0xbd and len(payload) >= 12:
                row, first = struct.unpack_from('<HH', payload)
                for index in range((len(payload) - 6) // 6):
                    xf, number = struct.unpack_from('<HI', payload, 4 + index * 6)
                    values.append((row, first + index, xf, rk(number)))
            for row, col, xf, value in values:
                format_id = xfs[xf] if xf < len(xfs) else 0
                result[sheet + '!' + cell_ref(row, col)] = {
                    'raw': repr(value), 'type': 'n',
                    'format': formats.get(format_id, 'builtin:' + str(format_id)),
                    'source': stream + '@' + str(offset) + ' record=0x%04X' % kind}
            if kind == 0xa:
                break
    return result



def chart_numbers(path):
    """차트의 모든 원시 숫자를 출력 값의 대조 근거로 수집한다."""
    result = []
    if path.suffix.lower() == '.xls':
        import olefile
        with olefile.OleFileIO(str(path)) as archive:
            stream = 'Workbook' if archive.exists('Workbook') else 'Book'
            data = archive.openstream(stream).read()
        for offset, kind, payload in records(data):
            values = []
            if kind in (0x203, 0x3) and len(payload) >= 14:
                values.append(struct.unpack_from('<d', payload, 6)[0])
            elif kind == 0x27e and len(payload) >= 10:
                values.append(rk(struct.unpack_from('<I', payload, 6)[0]))
            elif kind == 0xbd and len(payload) >= 12:
                values.extend(rk(struct.unpack_from('<I', payload, 6 + n * 6)[0])
                              for n in range((len(payload) - 6) // 6))
            for value in values:
                result.append({'raw': repr(value), 'source': stream + '@' + str(offset), 'format': ''})
    else:
        with zipfile.ZipFile(path) as archive:
            for part in archive.namelist():
                if 'chart' not in part.lower() or not part.endswith('.xml'):
                    continue
                root = xml(archive.read(part))
                for node in root.iter():
                    if etree.QName(node).localname != 'v' or node.text is None:
                        continue
                    try:
                        float(node.text)
                    except ValueError:
                        continue
                    parent = node.getparent()
                    cache = parent.getparent() if parent is not None else None
                    fmt = ''
                    if cache is not None:
                        fmt = next((n.text or '' for n in cache
                                    if etree.QName(n).localname == 'formatCode'), '')
                    result.append({'raw': node.text, 'format': fmt,
                                   'source': part + ':' + root.getroottree().getpath(node)})
    return result



def auto_titles(corpus, manifest, snapshot):
    from scripts.probe_chart_review_outputs import load
    groups = json.loads(manifest.read_text())
    namespace = '{http://schemas.openxmlformats.org/drawingml/2006/chart}'
    result = []
    for filename in groups['ooxml'] + groups['hwpx']:
        with zipfile.ZipFile(corpus / filename) as archive:
            for part in archive.namelist():
                if 'chart' not in part.lower() or not part.endswith('.xml'):
                    continue
                try:
                    root = xml(archive.read(part))
                except (etree.XMLSyntaxError, zipfile.BadZipFile):
                    continue
                chart = root.find(namespace + 'chart')
                if chart is None:
                    continue
                title = chart.find(namespace + 'title')
                deleted = chart.find(namespace + 'autoTitleDeleted')
                series = chart.findall('.//' + namespace + 'ser')
                if (title is None or title.find(namespace + 'tx') is not None
                        or deleted is None or deleted.get('val') not in ('0', 'false')
                        or len(series) != 1):
                    continue
                tx = series[0].find(namespace + 'tx')
                name = (tx.findtext(namespace + 'v') or tx.findtext('.//' + namespace + 'v') or '') if tx is not None else ''
                output = load(snapshot, filename)
                texts = [element.get('text')
                         for section in output.get('json', {}).get('sections', [])
                         for element in section.get('elements', [])
                         if element.get('type') == 'paragraph' and element.get('heading_level') == 3]
                result.append({'file': filename, 'part': part, 'title': name,
                               'emitted': bool(name) and name in texts})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--comparison', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.snapshot:
        result = auto_titles(args.corpus, args.manifest, args.snapshot)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print('automatic title candidates:', len(result), 'emitted:', sum(r['emitted'] for r in result))
        return
    comparison = json.loads(args.comparison.read_text())
    grouped = defaultdict(list)
    for cell in comparison['cells']:
        grouped[cell['file']].append(cell)
    result = []
    for filename, cells in grouped.items():
        path = args.corpus / filename
        try:
            raw = xls_cells(path) if path.suffix.lower() == '.xls' else ooxml_cells(path)
        except Exception as error:
            raw = {}
            print(filename, type(error).__name__)
        for cell in cells:
            entry = dict(cell)
            entry['evidence'] = raw.get(cell['cell'])
            result.append(entry)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('changed cells:', len(result), 'raw evidence:', sum(x['evidence'] is not None for x in result))


if __name__ == '__main__':
    main()
