"""Inventory public DOC textbox PLC bytes without copying corpus documents.

Pass public corpus directories explicitly. Output is JSON; it includes public
relative file names and numeric record values, never document text.
"""
import argparse
import json
from pathlib import Path
import struct

import olefile

from dochan.office_binary.doc_binary import DocBinary
from dochan.office_binary.doc_stories import _plc
from dochan.utils.bounded_io import (
    MAX_OLE_DOCUMENT_SIZE, read_ole_stream, validate_file_size,
)


def inspect(path):
    validate_file_size(str(path), MAX_OLE_DOCUMENT_SIZE)
    with olefile.OleFileIO(str(path)) as ole:
        if not ole.exists('WordDocument'):
            return None
        word = read_ole_stream(ole, 'WordDocument')
        if len(word) < 12 or word[:2] != b'\xec\xa5':
            return None
        if struct.unpack_from('<H', word, 10)[0] & 0x8100:
            return None
        table = '1Table' if struct.unpack_from('<H', word, 10)[0] & 0x200 else '0Table'
        if not ole.exists(table):
            return None
        binary = DocBinary(word, read_ole_stream(ole, table))
        stories = []
        for name, index in [('textbox', 56), ('header_textbox', 58)]:
            positions, records = _plc(binary.blob(index), 22)
            if not records:
                continue
            base, end = binary.stories.get(name, (0, 0))
            entries = []
            for i, record in enumerate(records):
                count, edited, flags, destination, lid, undo = struct.unpack('<IIHIII', record)
                entries.append({
                    'index': i, 'cp_start': positions[i], 'cp_end': positions[i + 1],
                    'last_record': i == len(records) - 1,
                    'within_story': 0 <= positions[i] < positions[i + 1] <= end - base,
                    'cTxbx': count, 'dword_at_4': edited, 'flags_at_8': flags,
                    'itxbxsDest': destination, 'lid': lid, 'dword_at_18': undo,
                })
            stories.append({'story': name, 'records': entries})
        return stories


def inventory(roots):
    result = {'doc_files': 0, 'word97_files': 0, 'textbox_files': 0,
              'active_nonterminal_records': 0, 'chain_candidates': 0, 'errors': [], 'files': []}
    for root in roots:
        for path in sorted(root.rglob('*')):
            if path.suffix.lower() != '.doc' or not path.is_file():
                continue
            result['doc_files'] += 1
            label = root.name + '/' + str(path.relative_to(root))
            try:
                stories = inspect(path)
            except (OSError, ValueError, struct.error, IndexError) as exc:
                result['errors'].append({'file': label, 'error': type(exc).__name__})
                continue
            if stories is None:
                continue
            result['word97_files'] += 1
            if not stories:
                continue
            result['textbox_files'] += 1
            for story in stories:
                for record in story['records']:
                    if (record['within_story'] and not record['last_record']
                            and not record['flags_at_8'] & 1):
                        result['active_nonterminal_records'] += 1
                        if record['cTxbx'] > 1 or record['itxbxsDest'] != 0xffffffff:
                            result['chain_candidates'] += 1
            result['files'].append({'file': label, 'stories': stories})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('public_corpus_roots', nargs='+', type=Path)
    args = parser.parse_args()
    print(json.dumps(inventory(args.public_corpus_roots), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
