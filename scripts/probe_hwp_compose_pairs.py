"""Compare public source-matched HWP/HWPX compose and dutmal strings.

Usage: python -m scripts.probe_hwp_compose_pairs HWP_DIR HWPX_DIR SOURCES_JSON
"""

import json
import sys
import zlib
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
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


def source_pairs(hwp_dir, hwpx_dir, sources_path):
    """Pair by original source location, including Hancom's conversion folder."""
    hwp_dir, hwpx_dir = Path(hwp_dir), Path(hwpx_dir)
    entries = json.loads(Path(sources_path).read_text(encoding='utf-8'))
    groups = {}
    for entry in entries:
        relative = PurePosixPath(entry['path'])
        if relative.parts[0] not in ('hwp', 'hwpx'):
            continue
        directory = hwp_dir if relative.parts[0] == 'hwp' else hwpx_dir
        path = directory / relative.name
        if not path.is_file():
            continue
        url = urlsplit(entry['url'])
        url_path = PurePosixPath(url.path)
        parent = url_path.parent
        if parent.name == 'hancom-hwp':
            parent = parent.parent
        key = (entry['source'], url.netloc, str(parent), url_path.stem, url.query)
        groups.setdefault(key, {}).setdefault(relative.parts[0], path)
    return sorted({(group['hwp'], group['hwpx']) for group in groups.values()
                   if 'hwp' in group and 'hwpx' in group})


def main(argv=None):
    hwp_dir, hwpx_dir, sources_path = (sys.argv[1:] if argv is None else argv)
    total = {'compose': 0, 'dutmal': 0}
    exact = {'compose': 0, 'dutmal': 0}
    for hwp, hwpx in source_pairs(hwp_dir, hwpx_dir, sources_path):
        try:
            answer = hwpx_values(hwpx)
            if not any(answer.values()):
                continue
            candidate = hwp_values(hwp)
        except (OSError, ValueError, BadZipFile) as exc:
            print('%s: 읽기 실패 (%s)' % (hwpx.name, type(exc).__name__))
            continue
        for key in ('compose', 'dutmal'):
            if not answer[key]:
                continue
            total[key] += len(answer[key])
            matches = sum(a == b for a, b in zip(answer[key], candidate[key]))
            exact[key] += matches
            print('%s ↔ %s %s: %d/%d, HWP %d' %
                  (hwp.name, hwpx.name, key, matches, len(answer[key]), len(candidate[key])))
    print('TOTAL compose %d/%d dutmal %d/%d' %
          (exact['compose'], total['compose'], exact['dutmal'], total['dutmal']))


if __name__ == '__main__':
    main()
