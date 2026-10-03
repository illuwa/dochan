"""Compare corpus HWPX Markdown and errors using compact per-file hashes.

Usage: python -m scripts.probe_hwpx_encryption_regression inventory CORPUS FILES_JSON
       python -m scripts.probe_hwpx_encryption_regression measure SOURCE CORPUS FILES_JSON OUT_JSON
"""
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
import sys


def inventory(corpus):
    root = Path(corpus)
    files = []
    for folder, suffixes in (('hwp-public/hwpx', ('.hwpx', '.hwp')),
                             ('hwp-public/hwp', ('.hwpx',)),
                             ('press-pairs', ('.hwpx',))):
        directory = root / folder
        if directory.exists():
            files.extend(str(path.relative_to(root)) for path in directory.iterdir()
                         if path.is_file() and path.suffix.lower() in suffixes
                         and path.name != 'encrypt.hwpx')
    return sorted(files)


def _init(source, corpus):
    sys.path.insert(0, source)
    global _root, _reader, _markdown
    _root = Path(corpus)
    from dochan import Dochan
    from dochan.output.markdown import to_markdown
    _reader = Dochan
    _markdown = to_markdown


def _hash_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _measure(relative):
    path = _root / relative
    file_hash = _hash_file(path)
    try:
        doc = _reader(str(path)).doc
        markdown = _markdown(doc)
        result = {'file': file_hash,
                  'markdown': hashlib.sha256(markdown.encode('utf-8')).hexdigest(),
                  'characters': len(markdown), 'errors': doc.errors}
    except Exception as exc:
        result = {'file': file_hash, 'exception': type(exc).__name__}
    return relative, result


def main():
    mode = sys.argv[1]
    if mode == 'inventory':
        paths = inventory(sys.argv[2])
        Path(sys.argv[3]).write_text(json.dumps(paths, ensure_ascii=False))
        print(len(paths))
    elif mode == 'measure':
        source, corpus, files_json, out_json = sys.argv[2:6]
        paths = json.loads(Path(files_json).read_text())
        with mp.Pool(3, initializer=_init, initargs=(source, corpus)) as pool:
            results = dict(pool.imap_unordered(_measure, paths, chunksize=4))
        Path(out_json).write_text(json.dumps(results, ensure_ascii=False, sort_keys=True))
        print(len(results))
    else:
        raise SystemExit('unknown mode')


if __name__ == '__main__':
    main()
