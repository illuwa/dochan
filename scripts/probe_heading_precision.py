"""공개 판독 라벨의 제목 정밀도와 진술 형태를 재현한다.

python -m scripts.probe_heading_precision CORPUS --labels LABELS --baseline SOURCE
코퍼스는 인자로 지정하며, 문서 전체 출력은 저장하지 않는다. 외부 프로젝트
구현이나 PDF 자동 라벨을 정답으로 사용하지 않고 기존 독립 판독 라벨을 쓴다.
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from scripts.probe_heading_relative import _paragraphs
from scripts.score_heading_labels import (
    _subprocess_snapshot, evaluate, snapshot, validate_labels,
)


_TAG = re.compile(r'^\(([^()]+)\)\s*(.*)$')
_CLAUSE = re.compile(r'\S+(?:하여|하며|하고|하되)(?=\s)')
_PARTICLE = re.compile(r'\S+(?:에서|으로|에게|까지|은|는|이|가|을|를|의)(?=\s)')
_NOMINAL = re.compile(r'(?:필요|목표|추진|발표|출시|전환|구축|양성|확보|조성|유도|대출|최소화)\*?$')
_UNIT = re.compile(r'\d[\d,.~∼]*\s*(?:원|명|개|년|월|일|%|시간)\*?$')


def features(para, following):
    """조사·서술명사는 진단용 단서이며 런타임 어휘 예외가 아니다."""
    from dochan.utils.heading_font import _section_marker

    text = ' '.join(para.text.split())
    end, kind = _section_marker(text)
    content = text[end:].strip()
    tag = _TAG.match(content)
    tail = tag.group(2) if tag else ''
    if tag and tail:
        category = '괄호 태그+진술'
    elif tag:
        category = '값 목록 키 또는 태그 이름'
    elif kind == 'square':
        category = '태그 없는 네모 진술 또는 이름'
    elif text.startswith(('<', '〈', '[', '【')):
        category = '괄호 제목 또는 캡션'
    elif re.fullmatch(r'\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.', text):
        category = '날짜'
    else:
        category = '기타'
    next_types = []
    for element in following:
        if hasattr(element, 'rows'):
            next_types.append('표')
        elif hasattr(element, 'heading_level'):
            value = element.text.lstrip()
            if value.startswith(('○', 'ㅇ', '◦')):
                next_types.append('하위 목록')
            elif value.startswith(('*', '※')):
                next_types.append('주석')
            else:
                _, marker = _section_marker(value)
                next_types.append('표지:' + marker if marker else '일반 문단')
        else:
            next_types.append(type(element).__name__)
    return {
        'category': category, 'marker': kind, 'characters': len(content),
        'words': len(content.split()), 'tag_tail_characters': len(tail) if tag else None,
        'tag_tail_words': len(tail.split()) if tag else None,
        'end': text[-8:], 'particle': bool(_PARTICLE.search(content)),
        'nominal_predicate_end': bool(_NOMINAL.search(content)),
        'unit_end': bool(_UNIT.search(content)), 'comma': ',' in content,
        'arrow': '→' in content, 'clause': bool(_CLAUSE.search(content)),
        'following': next_types,
    }


def candidate_effects(rows):
    """고정한 후보를 두 라벨 묶음에서 집계하며 임계값 탐색은 하지 않는다."""
    result = {}
    for rule in ('tag_phrase', 'length60', 'words10', 'arrow', 'clause'):
        removed = Counter()
        for row in rows:
            item = row['features']
            if item['marker'] != 'square' or not row['before']:
                continue
            rejects = {
                'tag_phrase': (item['tag_tail_words'] or 0) >= 2,
                'length60': item['characters'] > 60,
                'words10': item['words'] > 10,
                'arrow': item['arrow'], 'clause': item['clause'],
            }
            if rejects[rule]:
                removed['TP_lost' if row['label'] == 'H' else 'FP_removed'] += 1
        result[rule] = {key: removed[key] for key in ('TP_lost', 'FP_removed')}
    return result


def main():
    from dochan import Dochan

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    labels = validate_labels(json.loads(args.labels.read_text(encoding='utf-8')))
    old = _subprocess_snapshot(args.corpus, args.labels, args.baseline)
    new = snapshot(args.corpus, labels)
    evaluation = evaluate(labels, old, new)
    rows = []
    docs = {}
    for row in labels:
        filename, index = row['doc'], str(row['i'])
        # 손상 문서나 접두어 불일치를 정상 판독 결과로 다루지 않는다.
        before, after = old[filename].get(index), new[filename].get(index)
        if before is None or after is None:
            continue
        if not all(' '.join(p['text'].split()).startswith(' '.join(row['t'].split()))
                   for p in (before, after)):
            continue
        if filename not in docs:
            options = {'include_assets': False} if filename.endswith('.hwpx') else {}
            doc = Dochan(str(args.corpus / filename), **options).doc
            docs[filename] = (doc, list(_paragraphs(doc)))
        doc, paragraphs = docs[filename]
        path, para = paragraphs[row['i']]
        match = re.fullmatch(r's(\d+)\.elements(\d+)', path)
        if not match:
            continue
        section, offset = map(int, match.groups())
        item = {
            'doc': filename, 'i': row['i'], 'label': row['label'],
            'prefix': row['t'], 'note': row.get('note', ''),
            'before': before['level'], 'after': after['level'],
            'sha256': hashlib.sha256(para.text.encode('utf-8')).hexdigest(),
            'features': features(para, doc.sections[section].elements[offset + 1:offset + 4]),
        }
        rows.append(item)
    # 문서 전체 출력 대신 특징과 해시를 남기고 공개 오검출을 따로 집계한다.
    failures = [row for row in rows if row['label'] == 'B' and row['before']]
    evaluation['baseline_false_positives'] = failures
    evaluation['baseline_fp_categories'] = dict(Counter(
        row['features']['category'] for row in failures))
    evaluation['candidate_effects'] = candidate_effects(rows)
    evaluation['features'] = rows
    evaluation['documents'] = len(docs)
    print(json.dumps(evaluation, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
