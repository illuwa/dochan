"""Measure synthetic BIFF diagnostic amplification and a public embedded failure."""
import argparse
import io
import json
from pathlib import Path
import struct
import sys
import time

from dochan import cfb


def record(sid, data=b''):
    return struct.pack('<HH', sid, len(data)) + data


def hostile_workbook(count):
    globals_bof = record(0x809, struct.pack('<HHHHII', 0x600, 5, 0, 0, 0, 0))
    window = record(0x3d, struct.pack('<9H', 0, 0, 1000, 1000, 0, 0, 0, 1, 600))

    def sheet(offset):
        return record(0x85, struct.pack('<IBBBB', offset, 0, 2, 6, 0) + b'Chart1')

    header_size = len(globals_bof + window + sheet(0) + record(10))
    head = globals_bof + window + sheet(header_size) + record(10)
    body = record(0x809, struct.pack('<HHHHII', 0x600, 0x20, 0, 0, 0, 0))
    body += record(0x200, struct.pack('<IIHHH', 0, 1, 0, 1, 0))
    return head + body + b''.join(
        record(0x27e, struct.pack('<HHHI', 5 + row, 300, 0, 0))
        for row in range(count)) + record(10)


class Streams:
    """A read-only stream adapter; original corpus bytes remain in memory."""
    def __init__(self, workbook):
        self.streams = {'Workbook': workbook, '\x01CompObj': b'Excel.Chart.8\0'}

    def exists(self, name):
        return (name[-1] if isinstance(name, list) else name) in self.streams

    def get_size(self, name):
        return len(self.streams[name[-1] if isinstance(name, list) else name])

    def openstream(self, name):
        return io.BytesIO(self.streams[name[-1] if isinstance(name, list) else name])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve()))
    from dochan.office_binary.xls import parse_biff_workbook
    from dochan.office_binary.ole_objects import EmbeddedObjects
    from dochan.utils.diagnostics import is_fatal_diagnostic

    results = []
    for count in (10000, 20000, 40000):
        data = hostile_workbook(count)
        start = time.perf_counter()
        doc = parse_biff_workbook(data)
        seconds = time.perf_counter() - start
        errors = []
        start = time.perf_counter()
        output = EmbeddedObjects(errors).read(Streams(data), [], None)
        results.append(dict(records=count, standalone_seconds=seconds,
                            standalone_errors=len(doc.errors),
                            embedded_seconds=time.perf_counter() - start,
                            embedded_errors=len(errors), elements=len(output),
                            host_fatal=any(is_fatal_diagnostic(e) for e in errors)))
    with cfb.OleFileIO(str(args.corpus / 'poi-src/test-data/spreadsheet/SimpleWithColours.xls')) as ole:
        data = ole.openstream('Workbook').read()
    errors = []
    output = EmbeddedObjects(errors).read(Streams(data), [], None)
    result = dict(synthetic=results, public_sample={
        'file': 'SimpleWithColours.xls', 'elements': len(output), 'errors': errors,
        'host_fatal': any(is_fatal_diagnostic(e) for e in errors)})
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
