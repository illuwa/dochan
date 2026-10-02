"""Probe final XLS review fixes without retaining public corpus documents."""
import argparse
import json
from pathlib import Path
import struct
import time

from dochan import cfb

from dochan.office_binary.xls import _iter_records, parse_biff_workbook


def probe(corpus):
    results = {'public': [], 'synthetic_rk': []}
    for name in ('testEXCEL_5.xls', 'testEXCEL_95.xls'):
        with cfb.OleFileIO(str(corpus / name)) as ole:
            stream = 'Workbook' if ole.exists('Workbook') else 'Book'
            data = ole.openstream(stream).read()
        doc = parse_biff_workbook(data, stream)
        values = []
        for section in doc.sections:
            for element in section.elements:
                if hasattr(element, 'rows') and len(element.rows) > 18 and len(element.rows[18]) > 4:
                    values.append(element.rows[18][4].text)
        raw = []
        for _, kind, body in _iter_records(data):
            if kind == 6 and len(body) >= 22 and struct.unpack_from('<HH', body) == (18, 4):
                raw.append({'tokens': body[22:22 + struct.unpack_from('<H', body, 20)[0]].hex(),
                            'cached': struct.unpack_from('<d', body, 6)[0]})
        results['public'].append({'file': name, 'E19': values, 'raw_E19': raw,
                                  'warnings': doc.errors})
    for count in (10000, 20000, 40000):
        data = b''.join(struct.pack('<HHHHHI', 0x27e, 10, index, 300, 0, 2)
                        for index in range(count))
        start = time.monotonic()
        doc = parse_biff_workbook(data)
        results['synthetic_rk'].append({'records': count, 'seconds': time.monotonic() - start,
                                        'diagnostics': len(doc.errors), 'summary': doc.errors[-1]})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path, help='POI test-data/spreadsheet directory')
    args = parser.parse_args()
    print(json.dumps(probe(args.corpus), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
