"""Reproduce declared-range tail mutations of public SimpleMultiCell.xls.

Only one FAT word changes. Temporary corpus derivatives are removed immediately;
reports retain byte offsets, sizes, and output hashes, never document contents.
"""
import argparse
import json
from pathlib import Path
import struct
import tempfile

from scripts.probe_cfb_review import MAGIC, run_one

END = 0xfffffffe
FREE = 0xffffffff
SAMPLE = 'poi-src/test-data/spreadsheet/SimpleMultiCell.xls'


def replace_terminal(raw, name, value):
    """Locate a regular stream using [MS-CFB] header/directory/FAT fields."""
    if len(raw) < 512 or raw[:8] != MAGIC:
        raise ValueError('expected CFB header')
    shift = struct.unpack_from('<H', raw, 30)[0]
    if shift not in (9, 12):
        raise ValueError('unsupported sector shift')
    sector = 1 << shift
    count = struct.unpack_from('<I', raw, 44)[0]
    if not 0 < count <= 109:
        raise ValueError('probe requires header-contained FAT')
    fat_ids = struct.unpack_from('<109I', raw, 76)[:count]
    bound = len(raw) // sector - 1

    def fat_offset(sid):
        index, within = divmod(sid, sector // 4)
        if sid >= bound or index >= len(fat_ids) or fat_ids[index] >= bound:
            raise ValueError('allocation outside file')
        return (fat_ids[index] + 1) * sector + within * 4

    def chain(start):
        visited, output = set(), []
        while start != END:
            if start in visited:
                raise ValueError('input chain already cycles')
            visited.add(start)
            output.append(start)
            start = struct.unpack_from('<I', raw, fat_offset(start))[0]
        return output

    directory = chain(struct.unpack_from('<I', raw, 48)[0])
    for sid in directory:
        for pos in range((sid + 1) * sector, (sid + 2) * sector, 128):
            length = struct.unpack_from('<H', raw, pos + 64)[0]
            if not 2 <= length <= 64 or length % 2 or raw[pos + 66] != 2:
                continue
            entry_name = raw[pos:pos + length - 2].decode('utf-16le')
            if entry_name != name:
                continue
            start = struct.unpack_from('<I', raw, pos + 116)[0]
            version = struct.unpack_from('<H', raw, 26)[0]
            size = struct.unpack_from('<I' if version == 3 else '<Q', raw, pos + 120)[0]
            if size < 4096:
                raise ValueError('probe requires regular stream')
            sectors = chain(start)
            if len(sectors) != (size + sector - 1) // sector:
                raise ValueError('input stream already has a nonexact chain')
            offset = fat_offset(sectors[-1])
            replacement = start if value == 'cycle' else value
            changed = bytearray(raw)
            struct.pack_into('<I', changed, offset, replacement)
            return bytes(changed), {'fat_word_offset': offset, 'first_sector': start,
                                    'last_sector': sectors[-1], 'sectors': len(sectors),
                                    'declared_bytes': size, 'old_word': END,
                                    'new_word': replacement}
    raise ValueError('stream not found')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--baseline-tree', type=Path, required=True)
    parser.add_argument('--previous-tree', type=Path, required=True)
    parser.add_argument('--current-tree', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    raw = (args.corpus / SAMPLE).read_bytes()
    report = {'sample': SAMPLE, 'baseline': '107e18d / 1.7.0',
              'previous': '554ade6', 'cases': {}}
    trees = {'baseline': args.baseline_tree, 'previous': args.previous_tree,
             'current': args.current_tree}
    with tempfile.TemporaryDirectory(prefix='dochan-tail-probe-') as temporary:
        for label, value in (('original', None), ('FREESECT', FREE), ('cycle', 'cycle')):
            changed, evidence = (raw, {}) if value is None else replace_terminal(
                raw, 'Workbook', value)
            path = Path(temporary) / 'sample.xls'
            path.write_bytes(changed)
            results = {key: run_one(tree, path, 60) for key, tree in trees.items()}
            report['cases'][label] = {'byte_evidence': evidence, 'results': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
