"""POI/LO 공개 DOC·PPT 전수 결과를 동일한 모델 지표로 기록한다.

원본 문서는 읽기만 한다. --source-root로 수정 전 파서 사본을 선택할 수 있다.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import signal
import sys
import time


def paths(poi, lo, kind):
    folder = 'document' if kind == 'doc' else 'slideshow'
    for path in sorted((poi / folder).iterdir()):
        if path.is_file() and path.suffix.lower() == '.' + kind:
            yield 'poi/' + path.name, path
    base = lo / ('sw/qa/extras' if kind == 'doc' else 'sd/qa/unit/data')
    pattern = '*/data/*.doc' if kind == 'doc' else '**/*.ppt'
    for path in sorted(base.glob(pattern)):
        yield 'lo/' + str(path.relative_to(base)), path


def ppt_checks(poi, lo):
    from dochan.office_binary.ppt import PPTReader
    from dochan.ooxml.pptx import PPTXReader
    hang = PPTReader().read(str(lo / 'sd/qa/unit/data/ppt/pass/hang-3.ppt'))
    recovered = [p for p in hang.find_all('paragraph') if p.text == 'I am invisible']
    checks = [{'file': 'hang-3.ppt', 'expected': 'I am invisible',
               'actual': [p.text for p in recovered],
               'passed': len(recovered) == 1 and recovered[0].provenance.slide is None
               and recovered[0].provenance.path.endswith('#legacy-recovery')}]
    for name in ('alterman_security', 'customGeo'):
        legacy = PPTReader().read(str(poi / 'slideshow' / (name + '.ppt')))
        ooxml = PPTXReader().read(str(poi / 'slideshow' / (name + '.pptx')))
        images = legacy.find_all('image')
        inherited = [im for im in images if '#master' in (getattr(im.provenance, 'path', '') or '')]
        equal_required = name == 'alterman_security'
        checks.append({'file': name + '.ppt', 'ooxml_images': len(ooxml.find_all('image')),
                       'actual_images': len(images), 'master_images': len(inherited),
                       'pair_count_comparable': equal_required,
                       'passed': not inherited and (not equal_required or
                                  len(images) == len(ooxml.find_all('image'))),
                       'basis': 'PPTX excludes masters; customGeo stores diagram/table bitmaps as slide shapes'})
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--poi', required=True, type=Path, help='POI test-data 디렉터리')
    parser.add_argument('--lo', required=True, type=Path, help='LO 소스 루트')
    parser.add_argument('--kind', required=True, choices=('doc', 'ppt'))
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--verify-sections', action='store_true')
    parser.add_argument('--verify-features', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.source_root:
        sys.path.insert(0, str(args.source_root.resolve()))
    from dochan.office_binary.doc import DOCReader
    from dochan.office_binary.ppt import PPTReader
    from dochan.output.json_out import to_dict

    def timeout(signum, frame):
        raise TimeoutError('120 second document budget exceeded')

    signal.signal(signal.SIGALRM, timeout)
    reader = DOCReader() if args.kind == 'doc' else PPTReader()
    rows = []
    for key, path in paths(args.poi, args.lo, args.kind):
        started = time.monotonic()
        row = {'file': key}
        signal.alarm(120)
        try:
            doc = reader.read(str(path))
            text = '\n'.join(''.join(r.text for r in p.runs
                if not (r.provenance is None and re.fullmatch(r'\[bookmark: [^\]]+\] ', r.text)))
                for p in doc.find_all('paragraph'))
            master_images = [p.text for p in doc.find_all('paragraph')
                             if (getattr(p.provenance, 'path', '') or '').endswith('#master')
                             and re.fullmatch(r'!\[[^\n]*\]\([^\n]*\)', p.text)]
            row.update(errors=doc.errors, sections=len(doc.sections),
                       paragraphs=len(doc.find_all('paragraph')),
                       images=len(doc.find_all('image')), tables=len(doc.find_all('table')),
                       words=dict(Counter(re.findall(r'\w+', text))),
                       master_image_words=dict(Counter(re.findall(r'\w+', '\n'.join(master_images)))),
                       master_image_paragraphs=len(master_images),
                       text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
                       json_sha256=hashlib.sha256(json.dumps(to_dict(doc), sort_keys=True).encode()).hexdigest())
            if args.verify_sections and args.kind == 'doc' and doc.sections:
                import struct
                from scripts.check_doc_word_preservation import read_binary
                native = all(re.fullmatch(r'WordDocument#cp\d+',
                             getattr(section.provenance, 'path', '') or '') for section in doc.sections)
                if native:
                    binary, _ = read_binary(path)
                    raw = binary.blob(6)
                    if len(raw) >= 20 and (len(raw) - 4) % 16 == 0:
                        count = (len(raw) - 4) // 16
                        cps = struct.unpack_from('<%dI' % (count + 1), raw)
                        start, end = binary.stories['main']
                        expected = [start] + sorted(set(cp for cp in cps[1:-1] if start < cp < end))
                        actual = [int(section.provenance.path.split('#cp')[1]) for section in doc.sections]
                        row['section_check'] = {'raw_cps': cps, 'expected_starts': expected,
                                                'actual_starts': actual, 'passed': actual == expected}
        except Exception as exc:
            row['exception'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            signal.alarm(0)
        row['seconds'] = round(time.monotonic() - started, 4)
        rows.append(row)
    summary = {'documents': len(rows), 'exceptions': sum('exception' in r for r in rows),
               'fatal_documents': sum(any(e.startswith('ERR:') for e in r.get('errors', [])) for r in rows),
               'seconds': round(sum(r['seconds'] for r in rows), 3)}
    if args.verify_sections:
        checks = [r['section_check'] for r in rows if 'section_check' in r]
        summary['section_checks'] = len(checks)
        summary['section_checks_passed'] = sum(check['passed'] for check in checks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {'summary': summary, 'documents': rows}
    if args.verify_features:
        if args.kind == 'ppt':
            checks = ppt_checks(args.poi, args.lo)
        else:
            from scripts.check_doc_font_bookmark_polish import check
            checks = check(args.poi / 'document', args.lo / 'sw/qa/extras/ww8export/data')
        result['feature_checks'] = checks
        summary['feature_checks'] = len(checks)
        summary['feature_checks_passed'] = sum(check['passed'] for check in checks)
    args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2))
    print(json.dumps(summary))
    return int(bool(summary['exceptions']) or
               summary.get('section_checks') != summary.get('section_checks_passed') or
               summary.get('feature_checks') != summary.get('feature_checks_passed'))


if __name__ == '__main__':
    raise SystemExit(main())
