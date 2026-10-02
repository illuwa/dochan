"""공개 POI/LibreOffice 코퍼스로 리뷰 수정 사항을 읽기 전용 검증한다."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import time
from unittest.mock import patch

import olefile

from dochan import Dochan
from dochan.cli import main as cli_main
from dochan.crypto.ooxml import decrypt_ooxml


class MemoryStreams:
    def __init__(self, streams):
        self.streams = streams

    def get_size(self, name):
        return len(self.streams[name])

    def openstream(self, name):
        return io.BytesIO(self.streams[name])


def probe(poi, lo):
    path = poi / 'spreadsheet/58616.xlsx'
    start = time.perf_counter()
    document = Dochan(str(path))
    duration = time.perf_counter() - start
    with patch.dict('os.environ', {'DOCHAN_PASSWORD': ''}):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cli_status = cli_main(['info', str(path)])
    xlsb = Dochan(str(poi / 'spreadsheet/protected_passtika.xlsb'), password='tika')
    source = lo / 'sw/qa/extras/ooxmlexport/data/Encrypted_MSO2013_abc.docx'
    with olefile.OleFileIO(str(source)) as ole:
        streams = {}
        for name in ('EncryptionInfo', 'EncryptedPackage'):
            with ole.openstream(name) as stream:
                streams[name] = stream.read()
    package = bytearray(streams['EncryptedPackage'])
    package[-17] ^= 1
    streams['EncryptedPackage'] = bytes(package)
    integrity_error = ''
    try:
        decrypt_ooxml(MemoryStreams(streams), 'abc')
    except ValueError as exc:
        integrity_error = str(exc)
    inventory = []
    for root in (poi / 'slideshow', lo / 'sd/qa/unit/data'):
        files = list(root.rglob('*.pptx'))
        encrypted = 0
        for candidate in files:
            with candidate.open('rb') as stream:
                encrypted += stream.read(8) == bytes.fromhex('d0cf11e0a1b11ae1')
        inventory.append({'files': len(files), 'cfb': encrypted})
    result = {
        'default_xlsx_opened': bool(document.doc.sections) and not document.errors,
        'default_xlsx_seconds': duration,
        'empty_environment_cli_status': cli_status,
        'xlsb_diagnostic': xlsb.errors,
        'tampered_agile_diagnostic': integrity_error,
        'pptx_inventory': inventory,
    }
    result['passed'] = all((result['default_xlsx_opened'], cli_status == 0,
                            any('XLSB' in error and '미지원' in error for error in xlsb.errors),
                            'HMAC' in integrity_error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--poi-corpus', type=Path, required=True)
    parser.add_argument('--lo-corpus', type=Path, required=True)
    args = parser.parse_args()
    result = probe(args.poi_corpus, args.lo_corpus)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
