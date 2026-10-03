"""Record Markdown hashes without writing document content to disk.

Usage: python -m scripts.probe_hwp_compose HASHES.jsonl DIR [DIR ...]
"""

import hashlib
import json
import sys
from pathlib import Path

from dochan import Dochan


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    output, *directories = args
    paths = sorted(
        path for directory in directories for path in Path(directory).iterdir()
        if path.suffix.lower() in ('.hwp', '.hwpx')
    )
    with open(output, 'w', encoding='utf-8') as handle:
        for index, path in enumerate(paths, 1):
            try:
                reader = Dochan(str(path))
                markdown = reader.to_markdown()
                row = {
                    'path': str(path),
                    'sha256': hashlib.sha256(markdown.encode('utf-8')).hexdigest(),
                    'chars': len(markdown),
                    'errors': reader.errors,
                }
            except Exception as exc:
                row = {'path': str(path), 'error': type(exc).__name__}
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
            if index % 500 == 0:
                print('%d/%d' % (index, len(paths)), flush=True)
    print('complete %d' % len(paths))


if __name__ == '__main__':
    main()
