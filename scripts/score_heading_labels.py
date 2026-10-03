"""외부 PDF 감수 라벨로 시작점과 현재 HWP/HWPX 제목을 독립 채점한다.

실행: python -m scripts.score_heading_labels CORPUS --labels LABELS --baseline SOURCE
SOURCE는 git archive 등으로 추출한 기준 dochan 소스 디렉터리다.
두 소스는 별도 프로세스에서 읽어 파이썬 모듈 캐시가 섞이지 않게 한다.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path


_TOP_LEVEL = re.compile(r's\d+\.elements\d+\Z')
_SUFFIXES = ('.hwp', '.hwpx')
_MAX_LABELS = 100_000
_MAX_ERROR_TEXT = 1_000


def validate_labels(rows):
    """외부 JSON의 필수 필드와 파일명·인덱스 범위를 검사한다."""
    if not isinstance(rows, list) or len(rows) > _MAX_LABELS:
        raise ValueError('라벨은 100000개 이하의 JSON 배열이어야 한다')
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('각 라벨은 JSON 객체여야 한다')
        filename, index, prefix = row.get('doc'), row.get('i'), row.get('t')
        if (not isinstance(filename, str) or Path(filename).name != filename
                or filename in ('.', '..') or Path(filename).suffix.lower() not in _SUFFIXES):
            raise ValueError('라벨 doc은 HWP/HWPX 파일 이름이어야 한다')
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError('라벨 i는 음수가 아닌 문단 인덱스여야 한다')
        if not isinstance(prefix, str) or not prefix or len(prefix) > 40:
            raise ValueError('라벨 t는 1~40자의 텍스트 접두어여야 한다')
        if row.get('label') not in ('H', 'B'):
            raise ValueError('라벨 label은 H 또는 B여야 한다')
        key = (filename, index)
        if key in seen:
            raise ValueError('중복 라벨: %s #%d' % key)
        seen.add(key)
    return rows


def snapshot(corpus, labels):
    """요청된 문단만 읽는다. 한 문서의 예외는 그 문서에만 기록한다."""
    from dochan import Dochan
    from scripts.probe_heading_relative import _paragraphs

    by_file = defaultdict(set)
    for row in labels:
        by_file[row['doc']].add(row['i'])
    result = {}
    for filename, indices in by_file.items():
        path = corpus / filename
        if not path.is_file():
            result[filename] = {'error': '파일 없음'}
            continue
        try:
            options = {'include_assets': False} if path.suffix.lower() == '.hwpx' else {}
            doc = Dochan(str(path), **options).doc
            entries = {}
            for index, (key, para) in enumerate(_paragraphs(doc)):
                if index in indices:
                    entries[str(index)] = {
                        'path': key, 'text': para.text[:_MAX_ERROR_TEXT + 1],
                        'level': para.heading_level,
                    }
            result[filename] = entries
        except Exception as exc:
            result[filename] = {'error': type(exc).__name__}
    return result


def evaluate(labels, baseline, current):
    """양쪽 소스 모두 같은 최상위 문단으로 확인된 행만 채점한다."""
    scores = defaultdict(Counter)
    errors = []
    skipped_rows = []
    for row in labels:
        filename, index, prefix = row['doc'], row['i'], row['t']
        before = baseline.get(filename, {})
        after = current.get(filename, {})
        old, new = before.get(str(index)), after.get(str(index))
        reason = None
        if 'error' in before or 'error' in after:
            reason = '문서 읽기 실패'
        elif old is None or new is None:
            reason = '문단 인덱스 불일치'
        elif (not _TOP_LEVEL.fullmatch(old['path'])
              or not _TOP_LEVEL.fullmatch(new['path'])
              or old['path'] != new['path']):
            reason = '최상위 문단 경로 불일치'
        elif not old['text'].startswith(prefix) or not new['text'].startswith(prefix):
            reason = '텍스트 접두어 불일치'
        if reason:
            skipped_rows.append({'doc': filename, 'i': index, 'reason': reason})
            continue
        expected = row['label'] == 'H'
        extension = Path(filename).suffix.lower()
        for version, item in (('baseline', old), ('current', new)):
            predicted = bool(item['level'])
            score = scores[(extension, version)]
            score['N'] += 1
            score['H'] += expected
            score['TP'] += expected and predicted
            score['FP'] += not expected and predicted
            score['FN'] += expected and not predicted
            if predicted != expected:
                errors.append({
                    'version': version, 'kind': 'FN' if expected else 'FP',
                    'doc': filename, 'i': index, 'text': item['text'][:_MAX_ERROR_TEXT],
                    'text_truncated': len(item['text']) > _MAX_ERROR_TEXT,
                })
    formats = {}
    for extension in _SUFFIXES:
        formats[extension] = {}
        for version in ('baseline', 'current'):
            score = scores[(extension, version)]
            tp, fp, fn = score['TP'], score['FP'], score['FN']
            formats[extension][version] = {
                key: score[key] for key in ('N', 'H', 'TP', 'FP', 'FN')}
            formats[extension][version]['precision'] = (
                tp / (tp + fp) if tp + fp else None)
            formats[extension][version]['recall'] = (
                tp / (tp + fn) if tp + fn else None)
    return {'formats': formats, 'skipped': len(skipped_rows),
            'skipped_rows': skipped_rows, 'errors': errors}


def _subprocess_snapshot(corpus, labels_path, source_root):
    command = [sys.executable, str(Path(__file__).resolve()), '_snapshot',
               str(corpus), '--labels', str(labels_path), '--source-root', str(source_root)]
    completed = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
        command, capture_output=True, text=True, check=False)
    if completed.returncode:
        raise RuntimeError('소스 읽기 실패 (%s): %s' % (
            source_root, completed.stderr.strip()[-1000:]))
    return json.loads(completed.stdout)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '_snapshot':
        parser = argparse.ArgumentParser()
        parser.add_argument('mode')
        parser.add_argument('corpus', type=Path)
        parser.add_argument('--labels', type=Path, required=True)
        parser.add_argument('--source-root', type=Path, required=True)
        args = parser.parse_args()
        # 문단 순서는 항상 현재 도구의 _paragraphs 정의를 사용한다.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from scripts.probe_heading_relative import _paragraphs  # noqa: F401
        sys.path.insert(0, str(args.source_root.resolve()))
        labels = validate_labels(json.loads(args.labels.read_text(encoding='utf-8')))
        print(json.dumps(snapshot(args.corpus, labels), ensure_ascii=False))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True,
                        help='기준 dochan 소스 디렉터리')
    args = parser.parse_args()
    current_root = Path(__file__).resolve().parents[1]
    if not (args.baseline / 'dochan' / '__init__.py').is_file():
        parser.error('--baseline은 dochan 패키지가 있는 소스 디렉터리여야 한다')
    labels = validate_labels(json.loads(args.labels.read_text(encoding='utf-8')))
    baseline = _subprocess_snapshot(args.corpus, args.labels, args.baseline)
    current = _subprocess_snapshot(args.corpus, args.labels, current_root)
    print(json.dumps(evaluate(labels, baseline, current), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
