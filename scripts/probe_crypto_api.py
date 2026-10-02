"""공용 API의 PDF 암호 연결과 HWP 명시적 거부를 읽기 전용으로 검증한다."""
import argparse
import json
from pathlib import Path
import struct

import olefile

from dochan import Dochan
from dochan.pdf.reader import PDFReader
from dochan.utils.bounded_io import read_ole_stream, validate_file_size


def probe_pdf(corpus):
    manifest = corpus.parent / 'test_manifest.json'
    rows = []
    for entry in json.loads(manifest.read_text(encoding='utf-8')):
        if 'password' not in entry:
            continue
        name = Path(entry['file']).name
        path = corpus / name
        if not path.is_file():
            continue
        password = entry['password']
        direct = PDFReader(password=password).read(str(path))
        public = Dochan(str(path), password=password)
        wrong = Dochan(str(path), password='incorrect-api-probe-password')
        missing = Dochan(str(path))
        from dochan.output.json_out import to_dict
        rows.append({'file': name,
                     'equal_to_pdf_reader': public.to_dict() == to_dict(direct),
                     'opened': bool(public.doc.sections),
                     'wrong_rejected': any(e.startswith('ERR: 암호화된 문서') for e in wrong.errors),
                     'missing_rejected': any(e.startswith('ERR: 암호화된 문서') for e in missing.errors)})
    return rows


def probe_hwp(corpus):
    # 파일명·내용을 기록하지 않으므로 내부 코퍼스에서도 집계만 생성한다.
    result = {'files': 0, 'headers': 0, 'encrypted': 0, 'rejected': 0, 'unreadable': 0}
    for path in sorted(corpus.rglob('*.hwp')):
        result['files'] += 1
        try:
            validate_file_size(str(path))
            with olefile.OleFileIO(str(path)) as ole:
                if not ole.exists('FileHeader'):
                    continue
                header = read_ole_stream(ole, 'FileHeader', max_bytes=256, expected_size=256)
                result['headers'] += 1
                if not struct.unpack_from('<I', header, 36)[0] & 2:
                    continue
            result['encrypted'] += 1
            reader = Dochan(str(path), password='probe-not-a-real-password')
            result['rejected'] += int(not reader.doc.sections and any(
                e.startswith('ERR: 암호화/DRM') for e in reader.errors))
        except Exception:
            result['unreadable'] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf-corpus', type=Path)
    parser.add_argument('--hwp-corpus', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {}
    if args.pdf_corpus:
        result['pdf'] = probe_pdf(args.pdf_corpus)
    if args.hwp_corpus:
        result['hwp'] = probe_hwp(args.hwp_corpus)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + '\n', encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    main()
