"""독립 판독 라벨의 접두어를 같은 newsId PDF 최상위 문단과 유일 대응하여 채점한다.

사용법: python -m scripts.score_pdf_heading_labels --labels LABELS --corpus CORPUS
묶음마다 두 인자를 반복할 수 있다. 출력에는 집계와 공개 newsId만 기록한다.
재현율의 전체 분모에는 누락·모호 대응 제목도 포함한다.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from dochan import Dochan
from dochan.model.document import Paragraph

MAX_LABEL_BYTES = 16 * 1024 * 1024
MAX_LABEL_ROWS = 200_000
_PUBLIC_DOC = re.compile(r'([0-9]{1,20})\.hwpx?')


def compact(text):
    return re.sub(r'\s+', '', text or '')


def load_labels(path):
    path = Path(path)
    if path.stat().st_size > MAX_LABEL_BYTES:
        raise ValueError('label byte limit exceeded')
    rows = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(rows, list) or len(rows) > MAX_LABEL_ROWS:
        raise ValueError('label row limit exceeded')
    grouped = defaultdict(list)
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('doc'), str)
                or not isinstance(row.get('t'), str) or row.get('label') not in ('H', 'B')):
            raise ValueError('invalid label row')
        match = _PUBLIC_DOC.fullmatch(row['doc'])
        if match is None:
            raise ValueError('only public newsId labels are accepted')
        grouped[match.group(1)].append(row)
    return grouped


def score_rows(rows, paragraphs):
    counts = Counter()
    paragraphs = [(compact(text), level) for text, level in paragraphs if compact(text)]
    for row in rows:
        heading = row['label'] == 'H'
        counts['rows'] += 1
        counts['heading_rows'] += heading
        key = compact(row['t'])
        hits = [level for text, level in paragraphs if key and (
            text.startswith(key) or (len(text) >= 4 and key.startswith(text)))]
        if len(hits) != 1:
            reason = 'ambiguous' if hits else 'unmatched'
            counts[reason] += 1
            counts[reason + '_headings'] += heading
            continue
        counts['matched'] += 1
        counts['heading_matched'] += heading
        counts['tp' if heading else 'fp'] += hits[0] > 0
    return dict(counts)


def score_document(corpus, news_id, rows):
    if not re.fullmatch(r'[0-9]{1,20}', news_id):
        raise ValueError('invalid public newsId')
    path = Path(corpus) / (news_id + '.pdf')
    failure = None
    paragraphs = []
    if not path.is_file():
        failure = 'missing'
    else:
        try:
            doc = Dochan(str(path)).doc
            paragraphs = [(p.text, p.heading_level) for section in doc.sections
                          for p in section.elements if isinstance(p, Paragraph)]
            if any(str(error).startswith('ERR:') for error in doc.errors):
                failure = 'parser_error'
        except Exception as exc:
            failure = type(exc).__name__
    return {'news_id': news_id, 'counts': score_rows(rows, paragraphs), 'failure': failure}


def score_bundle(labels, corpus):
    documents = [score_document(corpus, news_id, rows)
                 for news_id, rows in sorted(load_labels(labels).items())]
    counts = Counter()
    for doc in documents:
        counts.update(doc['counts'])
    tp, fp = counts['tp'], counts['fp']
    return {'counts': dict(counts), 'documents': documents,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall_matched': tp / counts['heading_matched'] if counts['heading_matched'] else None,
            'recall_all': tp / counts['heading_rows'] if counts['heading_rows'] else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', action='append', type=Path, required=True)
    parser.add_argument('--corpus', action='append', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if len(args.labels) != len(args.corpus):
        parser.error('each --labels requires one --corpus')
    result = [score_bundle(labels, corpus) for labels, corpus in zip(args.labels, args.corpus)]
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(encoded, encoding='utf-8')
    print(json.dumps([dict(bundle, documents=len(bundle['documents'])) for bundle in result],
                     ensure_ascii=False, indent=2))
    return int(any(doc['failure'] for bundle in result for doc in bundle['documents']))


if __name__ == '__main__':
    raise SystemExit(main())
