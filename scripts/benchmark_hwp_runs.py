"""합성 HWP/HWPX의 공개 API 시간과 새 프로세스 최고 RSS를 측정한다.

예: python -m scripts.benchmark_hwp_runs --source-root . --format hwp
    --count 1000000 --style alternating

입력 준비는 부모에서 끝낸 뒤 별도 인터프리터를 실행한다. HWP는 압축된
세 개의 레코드와 DocInfo를 공급하는 OLE 경계 대역을 쓰며, HWPX는 실제
ZIP 패키지를 쓴다. OLE 디렉터리 디코딩 비용은 HWP 측정에 포함하지 않는다.
"""
import argparse
import io
import json
from pathlib import Path
import re
import resource
import struct
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import zipfile
import zlib


def _record(tag, level, data):
    if len(data) >= 0xFFF:
        return struct.pack('<II', tag | level << 10 | 0xFFF << 20, len(data)) + data
    return struct.pack('<I', tag | level << 10 | len(data) << 20) + data


def _compress(data):
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(data) + compressor.flush()


def prepare(directory, kind, count, style, pattern='runs'):
    """컨테이너 입력을 준비하고 원시/압축 크기를 돌려준다."""
    if kind == 'hwp':
        if pattern == 'paragraphs':
            # 문서 레코드 상한 안에서 두 섹션의 일반 문단 팬아웃을 측정한다.
            sizes = prepare(directory, kind, 1, style)
            (directory / 'body').unlink()
            one = _record(66, 0, bytes(22)) + _record(67, 1, b'x\x00\r\x00')
            raw_bytes = len((directory / 'header').read_bytes()) + len(
                zlib.decompress((directory / 'docinfo').read_bytes(), -15))
            compressed_bytes = sum((directory / name).stat().st_size for name in ('header', 'docinfo'))
            for index, offset in enumerate(range(0, count, 320000)):
                body = one * min(320000, count - offset)
                compressed = _compress(body)
                (directory / ('body%d' % index)).write_bytes(compressed)
                raw_bytes += len(body)
                compressed_bytes += len(compressed)
            sizes.update(raw_bytes=raw_bytes, compressed_bytes=compressed_bytes)
            return sizes
        text = b'x\x00' * count + b'\r\x00'
        pairs = bytearray(count * 8)
        for index in range(count):
            struct.pack_into('<II', pairs, index * 8, index, index & 1)
        body = (_record(66, 0, bytes(22)) + _record(67, 1, text)
                + _record(68, 1, pairs))
        shape0 = bytearray(72)
        struct.pack_into('<i', shape0, 42, 1000)
        shape1 = bytearray(shape0)
        if style == 'alternating':
            struct.pack_into('<I', shape1, 46, 2)
        docinfo = _record(21, 0, shape0) + _record(21, 0, shape1)
        header = bytearray(256)
        header[:32] = b'HWP Document File'.ljust(32, b'\x00')
        struct.pack_into('<BBBBI', header, 32, 0, 0, 0, 5, 1)
        streams = {'header': bytes(header), 'docinfo': _compress(docinfo),
                   'body': _compress(body)}
        for name, data in streams.items():
            (directory / name).write_bytes(data)
        (directory / 'input.hwp').write_bytes(b'\xd0\xcf\x11\xe0')
        return {'raw_bytes': len(body) + len(docinfo) + len(header),
                'compressed_bytes': sum(len(data) for data in streams.values())}

    namespaces = ('xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
                  'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
                  'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"')
    run0 = '<hp:run charPrIDRef="0"><hp:t>x</hp:t></hp:run>'
    run1 = '<hp:run charPrIDRef="1"><hp:t>x</hp:t></hp:run>'
    bold = '<hh:bold/>' if style == 'alternating' else ''
    header = ('<hh:head %s><hh:charProperties>' % namespaces
              + '<hh:charPr id="0" height="1000"/>'
              + '<hh:charPr id="1" height="1000">%s</hh:charPr>' % bold
              + '</hh:charProperties></hh:head>')
    path = directory / 'input.hwpx'
    raw_bytes = len(header.encode()) + 19
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('mimetype', 'application/hwp+zip')
        archive.writestr('Contents/header.xml', header)
        # 기존 섹션 XML 토큰 상한과 분리하여 문서 총 run 수를 측정한다.
        for index, offset in enumerate(range(0, count, 100000)):
            length = min(100000, count - offset)
            if pattern == 'paragraphs':
                body = '<hp:p><hp:run><hp:t>x</hp:t></hp:run></hp:p>' * length
            elif pattern == 'notes':
                body = '<hp:p><hp:run>' + '<hp:ctrl><hp:footNote/></hp:ctrl>' * length
                body += '<hp:t>' + 'x' * length + '</hp:t></hp:run></hp:p>'
            elif pattern == 'bookmarks':
                body = '<hp:p><hp:run>' + ('<hp:t>x</hp:t><hp:ctrl><hp:bookmark name="b"/></hp:ctrl>') * length + '</hp:run></hp:p>'
            elif pattern in ('empty-drawings', 'empty-controls'):
                control = ('<hp:rect/>' if pattern == 'empty-drawings'
                           else '<hp:ctrl><hp:unknown/></hp:ctrl>')
                body = '<hp:p><hp:run>' + ('<hp:t>' + 'x' * 1000 + '</hp:t>' + control) * length + '</hp:run></hp:p>'
            else:
                body = ('<hp:p>' + (run0 + run1) * (length // 2)
                        + (run0 if length % 2 else '') + '</hp:p>')
            section = '<hs:sec %s>%s</hs:sec>' % (namespaces, body)
            archive.writestr('Contents/section%d.xml' % index, section)
            raw_bytes += len(section.encode())
    return {'raw_bytes': raw_bytes,
            'compressed_bytes': path.stat().st_size}


class _StreamsOle:
    def __init__(self, streams):
        self.streams = streams

    def exists(self, name):
        return name in self.streams

    def openstream(self, name):
        return io.BytesIO(self.streams[name])

    def get_size(self, name):
        return len(self.streams[name])

    def listdir(self, **kwargs):
        return [name.split('/') for name in self.streams]

    def close(self):
        pass


def _rss_mib():
    scale = 2 ** 20 if sys.platform == 'darwin' else 1024
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / scale


def measure(source_root, directory, kind, count):
    """새 인터프리터에서만 실행하며 준비 입력은 계측 전에 읽는다."""
    sys.path.insert(0, str(source_root))
    import dochan
    from dochan import Dochan

    if not Path(dochan.__file__).resolve().is_relative_to(source_root):
        raise RuntimeError('selected source root was not imported')
    streams = {}
    if kind == 'hwp':
        streams = {'FileHeader': (directory / 'header').read_bytes(),
                   'DocInfo': (directory / 'docinfo').read_bytes()}
        for index, path in enumerate(sorted(directory.glob('body*'))):
            streams['BodyText/Section%d' % index] = path.read_bytes()
    with patch('dochan.reader.olefile.OleFileIO', lambda path: _StreamsOle(streams)):
        start = time.perf_counter()
        reader = Dochan(str(directory / ('input.' + kind)))
        parsed = time.perf_counter()
        parse_rss = _rss_mib()
        markdown = reader.to_markdown()
        rendered = time.perf_counter()
        json_output = reader.to_json()
        finished = time.perf_counter()
        peak_rss = _rss_mib()

    # JSON 복사 디코딩으로 최고 RSS를 부풀리지 않는다. 이 입력의 본문은
    # ASCII x뿐이고 JSON은 문단 text와 각 run text를 각각 한 번 기록한다.
    elements = reader.doc.find_all('paragraph')
    runs = [run for element in elements for run in getattr(element, 'runs', [])]
    model_chars = sum(run.text.count('x') for run in runs)
    md_chars = markdown.count('x')
    json_chars = sum(match.group(1).count('x') for match in re.finditer(r'"text": "([^"\n]*)"', json_output))
    preserved = model_chars == count and md_chars == count and json_chars == count * 2
    result = {'parse_s': parsed - start, 'markdown_s': rendered - parsed,
              'json_s': finished - rendered, 'total_s': finished - start,
              'parse_peak_rss_mib': parse_rss, 'peak_rss_mib': peak_rss,
              'runs': len(runs), 'bold_runs': sum(run.bold for run in runs),
              'paragraphs': len(elements), 'notes': len(reader.doc.find_all('note')),
              'model_text_chars': model_chars, 'markdown_text_chars': md_chars,
              'json_text_chars': json_chars, 'text_preserved': preserved,
              'errors': reader.errors}
    if not preserved:
        raise RuntimeError('public API lost synthetic body text: %r' % result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--format', choices=['hwp', 'hwpx'], required=True)
    parser.add_argument('--count', type=int, required=True)
    parser.add_argument('--style', choices=['alternating', 'same'], default='alternating')
    parser.add_argument('--pattern', choices=[
        'runs', 'paragraphs', 'notes', 'bookmarks', 'empty-drawings', 'empty-controls',
    ], default='runs')
    parser.add_argument('--prepared-dir', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 0 < args.count <= 10_000_000:
        parser.error('--count must be in 1..10000000')
    if args.format == 'hwp' and args.pattern not in ('runs', 'paragraphs'):
        parser.error('HWP supports runs and paragraphs patterns')
    root = args.source_root.resolve()
    if args.prepared_dir:
        text_count = args.count * (1000 if args.pattern in ('empty-drawings', 'empty-controls') else 1)
        print(json.dumps(measure(root, args.prepared_dir, args.format, text_count)))
        return
    with tempfile.TemporaryDirectory(prefix='dochan-runs-') as temporary:
        directory = Path(temporary)
        start = time.perf_counter()
        sizes = prepare(directory, args.format, args.count, args.style, args.pattern)
        preparation_s = time.perf_counter() - start
        command = [sys.executable, str(Path(__file__).resolve()), '--source-root', str(root),
                   '--format', args.format, '--count', str(args.count), '--style', args.style,
                   '--pattern', args.pattern,
                   '--prepared-dir', str(directory)]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
        if completed.returncode:
            raise RuntimeError('measurement worker failed: ' + completed.stderr)
        result = json.loads(completed.stdout)
        result.update(sizes)
        result.update(format=args.format, count=args.count, style=args.style, pattern=args.pattern,
                      preparation_s=preparation_s)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
