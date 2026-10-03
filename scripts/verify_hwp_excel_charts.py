"""Compare dochan's HWP embedded Excel.Chart.8 tables with an independent BIFF reading.

Usage: python -m scripts.verify_hwp_excel_charts HWP_DIR

The census (scripts.hwp_chart_ole_census) and the BIFF oracle
(scripts.hwp_excel_chart_oracle) read the HWP and the embedded workbook with
olefile and their own record walkers; they share no code with dochan. Values
follow the worksheet cells the chart's BRAI references point to. Scatter
charts are compared point by point (dochan writes them as Series | X | Y).
olefile is a local verification tool only, not a dochan dependency.
"""
import sys
from pathlib import Path

import olefile

from dochan import Dochan
from scripts.hwp_chart_ole_census import doc as census, inflate
from scripts.hwp_excel_chart_oracle import parse

EXCEL_CHART_CLSID = '00020821'


def _same(expected, text):
    if expected is None:
        return text in ('', None)
    if isinstance(expected, float):
        try:
            return abs(float(text) - expected) <= 1e-9 * max(1.0, abs(expected))
        except (TypeError, ValueError):
            return False
    return str(expected) == text


def _compare(table, series):
    head = [cell.text for cell in table.rows[0]]
    body = table.rows[1:]
    if head[:3] == ['Series', 'X', 'Y']:
        expected = [(x, y) for item in series for x, y in zip(item['cats'] or [], item['values'] or [])]
        got = [(row[1].text, row[2].text) for row in body]
        return len(expected) == len(got) and all(
            _same(x, gx) and _same(y, gy) for (x, y), (gx, gy) in zip(expected, got))
    if len(head) - 1 != len(series):
        return False
    for index, item in enumerate(series):
        values = item['values'] or []
        column = [row[index + 1].text for row in body]
        size = max(len(values), len(column))
        if not all(_same(values[k] if k < len(values) else None, column[k] if k < len(column) else '')
                   for k in range(size)):
            return False
        if index == 0:
            first = [row[0].text for row in body]
            categories = item['cats'] or [float(k + 1) for k in range(len(first))]
            if not all(_same(categories[k] if k < len(categories) else None, first[k])
                       for k in range(len(first))):
                return False
    return True


def main():
    root = Path(sys.argv[1])
    total = matched = 0
    for path in sorted(p for p in root.iterdir() if p.suffix.lower() == '.hwp'):
        record = census(path)
        if not record.get('ole_count') or 'refs' not in record:
            continue
        storages = []
        for ref in record['refs']:
            if not 1 <= ref['bin'] <= len(record['bin_entries']):
                continue
            _, storage = record['bin_entries'][ref['bin'] - 1]
            clsid = (record['oles'].get(str(storage), {}).get('clsid') or '')
            if clsid.startswith(EXCEL_CHART_CLSID):
                storages.append(storage)
        if not storages:
            continue
        ole = olefile.OleFileIO(str(path))
        tables = [t for t in Dochan(str(path)).doc.find_all('table')
                  if (t.caption_text or '').startswith('Chart type:')]
        for storage, table in zip(storages, tables):
            raw = ole.openstream('BinData/BIN%04X.OLE' % storage).read()
            if record['compressed']:
                raw = inflate(raw)
            workbook = olefile.OleFileIO(raw[4:]).openstream('Workbook').read()
            ok = _compare(table, parse(workbook)['series'])
            total += 1
            matched += ok
            print(path.name, storage, table.caption_text, 'ok' if ok else 'MISMATCH')
        total += max(0, len(storages) - len(tables))
    print('excel charts', total, 'matched worksheet cells', matched)


if __name__ == '__main__':
    main()
