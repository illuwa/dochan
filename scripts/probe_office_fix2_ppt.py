"""최종 PPT 감수 표본을 읽기 전용으로 검증한다."""
import argparse
import json
from pathlib import Path
import re

from dochan import cfb

from dochan.office_binary.ppt import PPTReader
from dochan.office_binary.ppt_structure import resolve_presentation
from dochan.office_binary.ppt_text import read_hyperlinks
from dochan.ooxml.pptx import PPTXReader
from dochan.output.markdown import to_markdown


def probe(poi, lo):
    rows = []
    for name in ('hang-1.ppt', 'hang-5.ppt', 'hang-11.ppt', 'crash-2.ppt'):
        doc = PPTReader().read(str(lo / 'sd/qa/unit/data/ppt/pass' / name))
        paras = doc.find_all('paragraph')
        passed = (len(paras) == 1 and paras[0].text == 'I am invisible'
                  and paras[0].provenance.path.endswith('#legacy-recovery')
                  and any('legacy text' in e for e in doc.errors))
        rows.append({'file': name, 'check': 'legacy_recovery', 'passed': passed})
    for name, count in (('pictures', 5), ('alterman_security', 4)):
        doc = PPTReader().read(str(poi / 'slideshow' / (name + '.ppt')))
        images = doc.find_all('image')
        markdown_refs = to_markdown(doc).count('![')
        clean_runs = all('![' not in p.text for p in doc.find_all('paragraph'))
        rows.append({'file': name + '.ppt', 'check': 'single_picture_reference',
                     'images': len(images), 'markdown_refs': markdown_refs,
                     'passed': len(images) == count == markdown_refs and clean_runs})
        if name == 'alterman_security':
            ref = PPTXReader().read(str(poi / 'slideshow' / (name + '.pptx')))
            # OOXML adds generated shape names, which the legacy file lacks.
            expected = [re.sub(r' Picture \d+$', '', im.alt_text) for im in ref.find_all('image')]
            actual = [im.alt_text for im in images]
            rows.append({'file': name + '.ppt', 'check': 'picture_alt_text',
                         'expected': expected, 'actual': actual, 'passed': actual == expected})
    legacy = PPTReader().read(str(poi / 'slideshow/customGeo.ppt'))
    reference = PPTXReader().read(str(poi / 'slideshow/customGeo.pptx'))
    def numbered_notes(doc):
        return [p.text for p in doc.find_all('paragraph') if p.provenance
                and p.provenance.slide in (1, 20) and 'notes' in p.provenance.path
                and re.match(r'^[1-5]\. ', p.text)]
    actual, expected = numbered_notes(legacy), numbered_notes(reference)
    rows.append({'file': 'customGeo.ppt', 'check': 'auto_number_notes',
                 'expected_count': len(expected), 'actual_count': len(actual),
                 'passed': len(expected) == 9 and actual == expected})
    for name in ('tdf168736-1.ppt', 'tdf168736-2.ppt'):
        path = lo / 'sd/qa/unit/data/ppt' / name
        doc = PPTReader().read(str(path))
        links = [target for para in doc.find_all('paragraph')
                 for target in re.findall(r'<(#PowerPoint Document#slide\d+)>', para.text)]
        with cfb.OleFileIO(str(path)) as ole:
            presentation = resolve_presentation(ole.openstream('PowerPoint Document').read(),
                                                ole.openstream('Current User').read(), [])
        resolved = read_hyperlinks(presentation.document.children, [s.slide_id for s in presentation.slides])
        if name.endswith('-2.ppt'):
            # Latest document has 50 definitions, not the historical duplicates
            # found by scanning every edit in the stream.
            slide_two = [p.text for p in doc.find_all('paragraph') if p.provenance.slide == 2]
            passed = (len(links) == len(resolved) == 50 and
                      any('<#PowerPoint Document#slide1>' in text for text in slide_two))
        else:
            slide_one = [p.text for p in doc.find_all('paragraph') if p.provenance.slide == 1]
            passed = len(links) == 4 and any('<#PowerPoint Document#slide2>' in text for text in slide_one)
        rows.append({'file': name, 'check': 'internal_links', 'output_links': len(links),
                     'latest_definitions': len(resolved), 'passed': passed})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--poi', type=Path, required=True, help='POI test-data 디렉터리')
    parser.add_argument('--lo', type=Path, required=True, help='LibreOffice 소스 루트')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = probe(args.poi, args.lo)
    result = {'checks': len(rows), 'passed': sum(row['passed'] for row in rows), 'rows': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'checks': result['checks'], 'passed': result['passed']}))
    return int(result['checks'] != result['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
