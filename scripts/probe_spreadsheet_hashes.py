"""Hash public XLS/XLSX Markdown and JSON output without writing document text."""
import argparse
import hashlib
import json
from pathlib import Path

from dochan.office_binary.xls import XLSReader
from dochan.ooxml.xlsx import XLSXReader
from dochan.output.json_out import to_json
from dochan.output.markdown import to_markdown


def hashes(root, extension, paired_only=False):
    result = {}
    reader_type = XLSReader if extension == 'xls' else XLSXReader
    if extension == 'xls':
        from scripts.probe_xls_tokens import public_paths
        paths = public_paths(root)
    else:
        paths = sorted(root.rglob('*.xlsx'))
    for path in paths:
        if paired_only and not path.with_suffix('.xls').is_file():
            continue
        doc = reader_type().read(str(path))
        result[str(path.relative_to(root))] = {
            'markdown_sha256': hashlib.sha256(to_markdown(doc).encode('utf-8')).hexdigest(),
            'json_sha256': hashlib.sha256(to_json(doc).encode('utf-8')).hexdigest(),
            'errors': len(doc.errors),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--extension', choices=('xls', 'xlsx'), default='xlsx')
    parser.add_argument('--paired-only', action='store_true')
    args = parser.parse_args()
    result = hashes(args.corpus, args.extension, args.paired_only)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('hashed %d %s documents' % (len(result), args.extension.upper()))


if __name__ == '__main__':
    main()
