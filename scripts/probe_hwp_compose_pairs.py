"""Compare public same-stem HWP/HWPX compose and dutmal control strings.

Usage: python -m scripts.probe_hwp_compose_pairs HWP_DIR HWPX_DIR
"""

import sys
import zlib
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from dochan.cfb import OleFileIO
from dochan.constants import HWPTAG_CTRL_HEADER
from dochan.hwp.section import SectionParser
from dochan.hwpx.parser import MAX_SECTION_XML_SIZE, _dutmal_text
from dochan.utils.safe_decompress import safe_zlib_decompress
from dochan.utils.safe_xml import fromstring


def hwp_values(path):
    parser = SectionParser()
    values = {'compose': [], 'dutmal': []}
    with OleFileIO(str(path)) as ole:
        for section in sorted(ole.listdir()):
            if not section or section[0] != 'BodyText':
                continue
            data = ole.openstream(section).read()
            try:
                data = safe_zlib_decompress(data)
            except zlib.error:
                pass
            for record in parser._read_all_records(data):
                if record.tag_id != HWPTAG_CTRL_HEADER:
                    continue
                cid = record.data[:4]
                if cid in (b'spct', b'tudt'):
                    key = 'compose' if cid == b'spct' else 'dutmal'
                    values[key].append(parser._compose_dutmal_text(record.data, cid))
    return values


def hwpx_values(path):
    values = {'compose': [], 'dutmal': []}
    with ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not (name.startswith('Contents/section') and name.endswith('.xml')):
                continue
            if archive.getinfo(name).file_size > MAX_SECTION_XML_SIZE:
                raise ValueError('section exceeds size limit')
            root = fromstring(archive.read(name))
            for node in root.iter():
                if not isinstance(node.tag, str):
                    continue
                if node.tag.endswith('}compose'):
                    values['compose'].append(node.get('composeText', '') or '')
                elif node.tag.endswith('}dutmal'):
                    values['dutmal'].append(_dutmal_text(node))
    return values


def main(argv=None):
    hwp_dir, hwpx_dir = (sys.argv[1:] if argv is None else argv)
    hwp = {path.stem: path for path in Path(hwp_dir).glob('*.hwp')}
    total = {'compose': 0, 'dutmal': 0}
    exact = {'compose': 0, 'dutmal': 0}
    for hwpx in sorted(Path(hwpx_dir).glob('*.hwpx')):
        if hwpx.stem not in hwp:
            continue
        try:
            answer = hwpx_values(hwpx)
            if not any(answer.values()):
                continue
            candidate = hwp_values(hwp[hwpx.stem])
        except (OSError, ValueError, BadZipFile) as exc:
            print('%s: 읽기 실패 (%s)' % (hwpx.name, type(exc).__name__))
            continue
        for key in ('compose', 'dutmal'):
            if not answer[key]:
                continue
            total[key] += len(answer[key])
            matches = sum(a == b for a, b in zip(answer[key], candidate[key]))
            exact[key] += matches
            print('%s %s: %d/%d, HWP %d' %
                  (hwpx.name, key, matches, len(answer[key]), len(candidate[key])))
    print('TOTAL compose %d/%d dutmal %d/%d' %
          (exact['compose'], total['compose'], exact['dutmal'], total['dutmal']))


if __name__ == '__main__':
    main()
