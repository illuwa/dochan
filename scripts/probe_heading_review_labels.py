"""독립 PDF 제목 라벨과 부모·앞선 커밋·현재 리더 판정을 대조한다.

라벨 JSON의 b/a는 각각 부모/앞선 커밋에서 저장한 제목 수준이다.
현재 수준은 입력 코퍼스를 다시 읽는다. 라벨과 코퍼스 경로는 인자로 받는다.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from scripts.probe_heading_relative import _paragraphs


def _marker_type(text):
    text = text.lstrip()
    if text.startswith(('□', '■')):
        return 'square'
    if re.match(r'(?:\d+(?:-\d+)?|[가나다라마바사아자차카타파하]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[IVX]+)[.)](?=\s|[<〈\[【])', text):
        return 'number'
    if text.startswith(('<', '〈', '[', '【')):
        return 'bracket'
    if text and unicodedata.category(text[0]) == 'Co':
        return 'pua'
    return ''


def score(corpus, labels_path, overrides_path, details=None):
    from dochan import Dochan
    if details is not None:
        from dochan.utils.heading_font import body_font_size, first_visible_font_size

    labels = json.loads(labels_path.read_text(encoding='utf-8'))
    overrides = (json.loads(overrides_path.read_text(encoding='utf-8'))
                 if overrides_path else {})
    by_file = defaultdict(list)
    for row in labels:
        by_file[row['doc']].append(row)
    scores = defaultdict(Counter)
    for filename, rows in by_file.items():
        path = corpus / filename
        options = {'include_assets': False} if path.suffix.lower() == '.hwpx' else {}
        try:
            doc = Dochan(str(path), **options).doc
        except TypeError as exc:
            if 'include_assets' not in str(exc):
                raise
            doc = Dochan(str(path)).doc
        paragraphs = list(_paragraphs(doc))
        if details is not None:
            top = [para for key, para in paragraphs
                   if re.fullmatch(r's\d+\.elements\d+', key)]
            body_size = body_font_size(top, doc=doc)
        for row in rows:
            index = row['i']
            if index >= len(paragraphs):
                raise ValueError('문단 인덱스 불일치: ' + filename)
            text = ' '.join(paragraphs[index][1].text.split())[:100]
            if text != row['t']:
                raise ValueError('라벨 문단 텍스트 불일치: ' + filename)
            expected = overrides.get('%s#%d' % (filename, row['idx']), row['auto']) == 'H'
            if details is not None and expected and not paragraphs[index][1].heading_level:
                para = paragraphs[index][1]
                visible = [run for run in para.runs if run.text.strip()]
                nonspace = sum(len(''.join(run.text.split())) for run in visible)
                bold = sum(len(''.join(run.text.split())) for run in visible if run.bold)
                style = (doc.styles[para.style_id].name
                         if 0 <= para.style_id < len(doc.styles) else '')
                shape = (doc.para_shapes[para.para_shape_id]
                         if 0 <= para.para_shape_id < len(doc.para_shapes) else None)
                details.append({
                    'file': filename, 'index': index, 'text': para.text[:100],
                    'path': paragraphs[index][0],
                    'first_size': first_visible_font_size(para.runs),
                    'body_size': body_size,
                    'bold_fraction': round(bold / nonspace, 3) if nonspace else 0,
                    'marker': _marker_type(para.text),
                    'style': style,
                    'outline_type': getattr(shape, 'heading_type', None),
                    'pdf_size': row.get('pdf_sz'), 'pdf_font': row.get('font'),
                })
            for version, predicted in (
                ('parent', bool(row['b'])),
                ('commit', bool(row['a'])),
                ('current', bool(paragraphs[index][1].heading_level)),
            ):
                for group in ('all', path.suffix.lower()):
                    result = scores[(version, group)]
                    result['N'] += 1
                    result['H'] += expected
                    result['TP'] += expected and predicted
                    result['FP'] += not expected and predicted
                    result['FN'] += expected and not predicted
                if expected:
                    kind = ('larger' if row['pdf_sz'] >= 1.1 * row['local_body']
                            else 'same_or_smaller')
                    result = scores[(version, kind)]
                    result['H'] += 1
                    result['TP'] += predicted
    return {'%s:%s' % key: dict(value) for key, value in scores.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('labels', type=Path)
    parser.add_argument('--overrides', type=Path)
    parser.add_argument('--source-root', type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument('--details-output', type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    details = [] if args.details_output else None
    result = score(args.corpus, args.labels, args.overrides, details=details)
    if args.details_output:
        args.details_output.write_text(json.dumps(details, ensure_ascii=False, indent=2),
                                       encoding='utf-8')
    print(json.dumps(result,
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
