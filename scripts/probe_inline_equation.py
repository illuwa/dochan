"""Stream per-document inline-equation hashes and counts; keep source files read-only."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _multiset_digest(counter):
    return _digest(json.dumps(sorted(counter.items()), ensure_ascii=False, separators=(',', ':')))


def _elements(doc):
    from dochan.model.document import Paragraph
    from dochan.model.table import Table
    from dochan.model.header_footer import HeaderFooter, Footnote
    seen = set()
    stack = [element for section in reversed(doc.sections) for element in reversed(section.elements)]
    while stack:
        element = stack.pop()
        if id(element) in seen:
            continue
        seen.add(id(element))
        yield element
        if isinstance(element, Table):
            for row in reversed(element.rows):
                for cell in reversed(row):
                    stack.extend(reversed(cell.paragraphs))
            stack.extend(reversed(element.caption))
        elif isinstance(element, (HeaderFooter, Footnote)):
            stack.extend(reversed(element.paragraphs))
        elif hasattr(element, 'caption') and not isinstance(element, Paragraph):
            stack.extend(reversed(element.caption))


def _summary(path):
    from dochan import Dochan
    from dochan.model.document import Paragraph
    from dochan.model.equation import Equation
    from dochan.output.markdown import to_markdown

    if path.suffix.lower() == '.hwpx':
        try:
            reader = Dochan(str(path), include_assets=False)
        except ValueError as exc:
            if 'include_assets=False' not in str(exc):
                raise
            # Public corpora contain HWP bytes with a .hwpx filename.
            reader = Dochan(str(path))
    else:
        reader = Dochan(str(path))
    doc = reader.doc
    formulas = Counter()
    inline_formulas = Counter()
    other_chars = Counter()
    paragraphs = 0
    inline = 0
    inline_paragraphs = 0
    contexts = []
    for element in _elements(doc):
        if isinstance(element, Equation):
            formulas[element.latex] += 1
        elif isinstance(element, Paragraph):
            paragraphs += 1
            has_inline = False
            for run in element.runs:
                eq = getattr(run, 'equation', None)
                if eq is not None:
                    formulas[eq.latex] += 1
                    inline_formulas[eq.latex] += 1
                    inline += 1
                    has_inline = True
                else:
                    other_chars.update(run.text)
            if has_inline:
                inline_paragraphs += 1
            if has_inline and len(contexts) < 3:
                contexts.append(element.text[:120])
    markdown = to_markdown(doc)
    return {
        'paragraphs': paragraphs,
        'equations': sum(formulas.values()),
        'inline': inline,
        'inline_paragraphs': inline_paragraphs,
        'formula_hash': _multiset_digest(formulas),
        'inline_formula_hash': _multiset_digest(inline_formulas),
        'text_hash': _multiset_digest(other_chars),
        'nonspace_text_hash': _multiset_digest(Counter({char: count for char, count in other_chars.items()
                                                       if not char.isspace()})),
        'markdown_hash': _digest(markdown),
        'markdown_chars': len(markdown),
        'errors': len(doc.errors),
        'contexts': contexts,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', nargs='+', type=Path)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--retry-from', type=Path, help='Read only failed paths from an earlier JSONL probe')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str((args.source_root or Path(__file__).resolve().parent.parent).resolve()))
    paths = []
    if args.retry_from:
        with args.retry_from.open(encoding='utf-8') as source:
            paths = [Path(row['file']) for row in map(json.loads, source) if 'failure' in row]
    else:
        for root in args.corpus:
            if root.is_file():
                paths.append(root)
            else:
                paths.extend(path for path in root.rglob('*') if path.suffix.lower() in ('.hwp', '.hwpx', '.docx'))
    paths = sorted(set(paths))
    with args.output.open('w', encoding='utf-8') as out:
        for index, path in enumerate(paths, 1):
            result = {'file': str(path)}
            try:
                result.update(_summary(path))
            except Exception as exc:
                result['failure'] = type(exc).__name__ + ': ' + str(exc)[:160]
            out.write(json.dumps(result, ensure_ascii=False) + '\n')
            if index % 200 == 0:
                print('%d/%d' % (index, len(paths)), file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
