"""Snapshot public POI/LO DOC/PPT/XLS outputs against an isolated source tree.

Corpus files are read in place. Run once with --source pointing at an extracted
HEAD dochan package, then once with the working tree, and compare the JSON files.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import signal
import sys


class ProbeTimeout(BaseException):
    """Escape readers that intentionally catch ordinary document exceptions."""


def _timeout(signum, frame):
    raise ProbeTimeout('probe document exceeded 60 seconds')


def snapshot(job):
    source, root, filename = job
    sys.path.insert(0, source)
    from dochan import Dochan

    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(60)
    path = Path(filename)
    result = {'file': str(path.relative_to(root))}
    try:
        reader = Dochan(str(path))
        markdown = reader.to_markdown()
        document = reader.to_dict()
        document['metadata'].pop('errors', None)
        result.update(markdown=markdown if len(markdown) <= 200000 else None,
                      markdown_length=len(markdown),
                      markdown_sha256=hashlib.sha256(markdown.encode()).hexdigest(),
                      document_sha256=hashlib.sha256(json.dumps(
                          document, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':')).encode()).hexdigest(),
                      errors=list(reader.doc.errors))
        result['images'] = [hashlib.sha256(image.image_data).hexdigest()
                            for image in reader.doc.find_all('image')]
    except (Exception, ProbeTimeout) as exc:
        result['exception'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        signal.alarm(0)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    root = args.corpus.resolve()
    paths = sorted({path for base in (root / 'poi-src/test-data', root / 'lo-src')
                    for path in base.rglob('*')
                    if path.is_file() and path.suffix.lower() in ('.doc', '.ppt', '.xls')})
    jobs = [(str(args.source.resolve()), str(root), str(path)) for path in paths]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for index, result in enumerate(pool.map(snapshot, jobs), 1):
            results.append(result)
            if index % 100 == 0:
                print('%d/%d' % (index, len(paths)), flush=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps({'documents': len(results),
                      'exceptions': sum('exception' in item for item in results)}))


if __name__ == '__main__':
    main()
