"""Count HWPX tables embedded between text fragments in one source paragraph.

The JSON output contains counts and short public-document context, never full documents.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import zipfile

from dochan.utils import safe_xml


MAX_SECTION_BYTES = 64 * 1024 * 1024
MAX_PREVIEW_BYTES = 4 * 1024 * 1024


def _tag(element):
    return element.tag.rsplit('}', 1)[-1] if isinstance(element.tag, str) else ''


def _own_parts(paragraph):
    """Only immediate run text and immediate run tables belong to this paragraph."""
    for run in paragraph:
        if _tag(run) != 'run':
            continue
        for child in run:
            tag = _tag(child)
            if tag == 't':
                yield ('text', ''.join(child.itertext()))
            elif tag == 'compose':
                yield ('text', child.get('composeText', ''))
            elif tag == 'dutmal':
                yield ('text', ''.join(child.itertext()))
            elif tag == 'tbl':
                yield ('table', child)
            elif tag == 'ctrl':
                for nested in child:
                    if _tag(nested) == 'tbl':
                        yield ('table', nested)


def _preview_contains(preview, before, after):
    if not preview:
        return False
    head = ''.join(before.split())[-12:]
    tail = ''.join(after.split())[:12]
    joined = ''.join(preview.split())
    return bool(head and tail and head + tail in joined)


def inspect(path):
    rows = []
    with zipfile.ZipFile(path) as archive:
        preview = ''
        try:
            info = archive.getinfo('Preview/PrvText.txt')
            if info.file_size <= MAX_PREVIEW_BYTES:
                preview = archive.read(info).decode('utf-8-sig', 'replace')
        except KeyError:
            pass
        for info in archive.infolist():
            if not re.fullmatch(r'Contents/section\d+\.xml', info.filename):
                continue
            if info.file_size > MAX_SECTION_BYTES:
                continue
            root = safe_xml.fromstring(archive.read(info))
            for paragraph in root.iter():
                if _tag(paragraph) != 'p':
                    continue
                parts = list(_own_parts(paragraph))
                for index, (kind, value) in enumerate(parts):
                    if kind != 'table':
                        continue
                    before = ''.join(text for typ, text in parts[:index] if typ == 'text')
                    after = ''.join(text for typ, text in parts[index + 1:] if typ == 'text')
                    if not before.strip() or not after.strip():
                        continue
                    position = next((x for x in value if _tag(x) == 'pos'), None)
                    attr = {name: (position.get(name, '') if position is not None else '')
                            for name in ('vertRelTo', 'horzRelTo', 'treatAsChar')}
                    attr['textWrap'] = value.get('textWrap', '')
                    if not attr['treatAsChar']:
                        attr['treatAsChar'] = value.get('treatAsChar', '')
                    rows.append({'section': info.filename, 'attrs': attr,
                                 'before': before[-36:], 'after': after[:36],
                                 'preview_joined': _preview_contains(preview, before, after)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('roots', nargs='+', type=Path)
    args = parser.parse_args()
    counts = Counter()
    examples = []
    errors = Counter()
    files = 0
    matched_files = 0
    for root in args.roots:
        for path in sorted(root.rglob('*.hwpx')):
            files += 1
            try:
                rows = inspect(path)
            except (ValueError, RuntimeError, zipfile.BadZipFile, OSError,
                    safe_xml.XMLSyntaxError) as exc:
                errors[type(exc).__name__] += 1
                continue
            if rows:
                matched_files += 1
            for row in rows:
                for key, value in row['attrs'].items():
                    counts[key + '=' + value] += 1
                counts['preview_joined=' + str(row['preview_joined'])] += 1
                examples.append({'file': str(path.relative_to(root)), 'root': root.name, **row})
    result = {'files': files, 'matched_files': matched_files, 'matches': len(examples),
              'attrs': dict(counts), 'errors': dict(errors), 'examples': examples}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'examples'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
