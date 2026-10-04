"""메모 실물 프로브의 독립 XML 읽기와 제품 출력 대조를 분리한다.

정답 생성은 dochan을 import하지 않는다. OLE 운반층만 검증용 olefile을 쓴다.
XML은 독립 정답지가 필요하므로 DTD·엔티티를 거부한 Expat으로 읽는다.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import posixpath
import struct
import subprocess
import sys
import zipfile
from xml.parsers import expat  # nosemgrep: use-defused-xml -- independent oracle; declarations rejected before parsing

MAX_BYTES = 128 * 1024 * 1024
MAX_RECORDS = 1000000


class Node:
    def __init__(self, tag, attrs):
        self.tag, self.attrs, self.children, self.text = tag, attrs, [], ''

    def items(self, local):
        return [c for c in self.children if c.tag.rsplit('}', 1)[-1] == local]


def xml(data):
    if len(data) > 16 * 1024 * 1024:
        raise ValueError('oracle XML size limit')
    # Removing NULs also catches UTF-16/32 ASCII declaration spellings.
    declaration = data.replace(b'\0', b'').upper()
    if b'<!DOCTYPE' in declaration or b'<!ENTITY' in declaration:
        raise ValueError('oracle XML declaration forbidden')
    parser = expat.ParserCreate(namespace_separator='}')  # nosemgrep: use-defused-xml -- independent oracle with DTD/entity rejection and node/depth bounds
    stack, roots = [], []
    count = [0]

    def start(tag, attrs):
        count[0] += 1
        if len(stack) >= 128 or count[0] > 200000:
            raise ValueError('oracle XML node/depth limit')
        node = Node(tag, attrs)
        (stack[-1].children if stack else roots).append(node)
        stack.append(node)

    def reject(*_args):
        raise ValueError('oracle XML declaration forbidden')

    def chars(value):
        if stack:
            stack[-1].text += value

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda _tag: stack.pop()
    parser.CharacterDataHandler = chars
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.Parse(data, True)
    return roots[0]


def relationship_targets(package, part):
    folder, name = posixpath.split(part)
    rels = posixpath.join(folder, '_rels', name + '.rels')
    if rels not in package.namelist():
        return {}
    return {r.attrs['Id']: (r.attrs.get('Type', ''),
                           posixpath.normpath(posixpath.join(folder, r.attrs['Target'])).lstrip('/'))
            for r in xml(zip_read(package, rels)).items('Relationship')
            if r.attrs.get('TargetMode') != 'External'}


def zip_read(package, name):
    if package.getinfo(name).file_size > 16 * 1024 * 1024:
        raise ValueError('oracle ZIP part limit')
    return package.read(name)


def zip_package(path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('oracle file size limit')
    package = zipfile.ZipFile(path)
    infos = package.infolist()
    if len(infos) > 100000 or sum(n.file_size for n in infos) > MAX_BYTES:
        package.close()
        raise ValueError('oracle ZIP entry/expanded size limit')
    return package


def ole_streams(path, names):
    import olefile  # Verification-only container reader; no product code.
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('oracle file size limit')
    with olefile.OleFileIO(str(path)) as ole:
        result = {}
        for name in names:
            if ole.exists(name):
                if ole.get_size(name) > MAX_BYTES:
                    raise ValueError('oracle stream size limit')
                result[name] = ole.openstream(name).read()
        return result


def biff_records(data, start=0):
    for _ in range(MAX_RECORDS):
        if start + 4 > len(data):
            return
        kind, length = struct.unpack_from('<HH', data, start)
        end = start + 4 + length
        if end > len(data):
            raise ValueError('truncated oracle BIFF record')
        yield start, kind, data[start + 4:end]
        start = end
    raise ValueError('oracle BIFF record limit')


def annotation(author, body):
    value = author + ': ' + body if author and body else author or body
    return '[comment: ' + value + ']' if value else ''


def product(path):
    """제품 출력은 정답 해독 이후에만 읽는다. 원문은 디스크에 쓰지 않는다."""
    from dochan import Dochan
    from dochan.output.json_out import to_json
    from dochan.model.document import Paragraph
    from dochan.model.table import Table
    doc = Dochan(str(path)).doc
    from dochan.output.markdown import to_markdown
    markdown, encoded = to_markdown(doc), to_json(doc)
    paragraphs = []
    cells = []
    for section in doc.sections:
        for element in section.elements:
            if isinstance(element, Paragraph) and element.text.startswith('[comment: '):
                paragraphs.append({'slide': element.provenance.slide,
                                   'annotation': element.text})
            elif isinstance(element, Table):
                for row in element.rows:
                    for cell in row:
                        if '[comment: ' in cell.text:
                            cells.append({'sheet': cell.provenance.sheet,
                                          'cell': cell.provenance.cell,
                                          'annotation': cell.text[cell.text.index('[comment: '):]})
    return {'markdown_sha256': hashlib.sha256(markdown.encode('utf-8')).hexdigest(),
            'json_sha256': hashlib.sha256(encoded.encode('utf-8')).hexdigest(),
            'markdown_chars': len(markdown), 'json_chars': len(encoded),
            'errors': doc.errors, 'paragraphs': paragraphs, 'cells': cells}


def compare(expected, actual, fields):
    wanted = [{k: row[k] for k in fields} for row in expected if row['annotation']]
    return {'expected_count': len(wanted), 'actual_count': len(actual),
            'exact': wanted == actual,
            'matched': sum(a == b for a, b in zip(wanted, actual)),
            'mismatches': [{'index': i, 'expected': a, 'actual': b}
                           for i, (a, b) in enumerate(zip(wanted, actual)) if a != b],
            'missing': wanted[len(actual):], 'extra': actual[len(wanted):]}


def run_cli(inspect, suffixes):
    parser = argparse.ArgumentParser(description=inspect.__doc__)
    parser.add_argument('roots', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--one', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.one:
        try:
            result = inspect(args.roots[0])
        except Exception as exc:
            result = {'exception': type(exc).__name__ + ': ' + str(exc)}
        print(json.dumps(result, ensure_ascii=False))
        return
    jobs = [(index, root, path) for index, root in enumerate(args.roots)
            for path in sorted(root.rglob('*'))
            if path.is_file() and path.suffix.lower() in suffixes]

    def one(job):
        index, root, path = job
        command = [sys.executable, '-m', inspect.__module__, str(path), '--one']
        try:
            # nosemgrep: dangerous-subprocess-use-audit -- fixed module, argv paths; read-only isolated probe
            child = subprocess.run(command, capture_output=True, text=True, timeout=60)
            result = json.loads(child.stdout) if child.returncode == 0 else {'exception': child.stderr[-500:]}
        except (subprocess.TimeoutExpired, ValueError) as exc:
            result = {'exception': type(exc).__name__}
        return {'root': index, 'file': str(path.relative_to(root)),
                'format': path.suffix.lower()[1:], **result}

    # __main__ cannot be used as the subprocess module name.
    inspect.__module__ = 'scripts.' + Path(sys.argv[0]).stem
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        results = list(pool.map(one, jobs))
    if args.output:
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'files': len(results),
                      'with_comments': sum(r.get('raw_count', 0) > 0 for r in results),
                      'exact_files': sum(r.get('comparison', {}).get('exact', False)
                                         for r in results if r.get('raw_count', 0)),
                      'comment_part_documents': sum(bool(r.get('comment_parts')) for r in results),
                      'oracle_errors': sum('oracle_error' in r for r in results),
                      'excluded_documents': sum(bool(r.get('excluded')) for r in results),
                      'exceptions': sum('exception' in r for r in results)}, ensure_ascii=False))
    if any('exception' in r or (r.get('comparison') and not r['comparison']['exact'])
           for r in results):
        raise SystemExit(1)
