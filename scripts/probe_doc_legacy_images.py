"""공개 코퍼스의 Word 6/95 그림 참조와 WMF 복원을 재현한다.

코퍼스 경로를 인자로 받으며 파일 내용이나 그림을 복사하지 않는다.
원시 PICF 후보 조사는 검증 전용이며 제품 reader는 CHPX 참조만 따른다.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import olefile

from dochan.model.document import Document
from dochan.office_binary.doc import DOCReader
from dochan.office_binary.doc_images import _direct_wmf, legacy_inline_images


def probe(path):
    if path.stat().st_size > 128 * 1024 * 1024:
        return None
    try:
        with olefile.OleFileIO(str(path)) as ole:
            if not ole.exists('WordDocument') or ole.get_size('WordDocument') > 128 * 1024 * 1024:
                return None
            word = ole.openstream('WordDocument').read()
    except Exception:
        return None
    if len(word) < 192:
        return None
    ident, version = struct.unpack_from('<HH', word)
    if version not in (101, 104):
        return None
    flags, = struct.unpack_from('<H', word, 10)
    candidates = []
    at = 0
    while True:
        at = word.find(b'\x3a\x00\x08\x00', at)
        if at < 0:
            break
        if at >= 4:
            size, = struct.unpack_from('<I', word, at - 4)
            if 58 < size <= len(word) - (at - 4):
                payload = _direct_wmf(word[at + 54:at - 4 + size])
                if payload:
                    candidates.append({'picf_fc': at - 4, 'picf_bytes': size,
                                       'wmf_bytes': len(payload),
                                       'sha256': hashlib.sha256(payload).hexdigest()})
        at += 4
    doc = Document()
    images = legacy_inline_images(word, doc)
    converted = DOCReader().read(str(path))
    return {'file': str(path), 'fib_ident': hex(ident), 'fib_version': version,
            'fib_flags': hex(flags), 'raw_valid_wmf_candidates': candidates,
            'referenced_images': [{'cp': cp, 'bytes': len(image.image_data),
                                   'sha256': hashlib.sha256(image.image_data).hexdigest()}
                                  for cp, image in images.items()],
            'reader_image_assets': sum(a.metadata.get('kind') == 'image' for a in converted.assets),
            'errors': converted.errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', nargs='+', type=Path)
    args = parser.parse_args()
    results = []
    checked = 0
    for root in args.corpus:
        paths = [root] if root.is_file() else sorted(root.rglob('*'))
        for path in paths:
            if not path.is_file() or path.suffix.lower() != '.doc':
                continue
            checked += 1
            result = probe(path)
            if result is not None:
                results.append(result)
    print(json.dumps({'doc_files_checked': checked, 'word6_95_files': len(results),
                      'files': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
