"""XLSX 도형 글자를 제품 코드 없이 원시 drawing XML 에서 읽어 리더 출력과 대조한다.

정규식 토큰화로 wsDr 직계 앵커의 txBody 문단(a:p)마다 t 글자를 모으고(줄마다 앞뒤 공백 제거, 빈 줄 생략),
Markup Compatibility 의 AlternateContent 는 첫 갈래만 본다. 리더의 drawing 문단(그림 참조 제외)과
파일별 문구 다중집합을 비교한다(순서는 보지 않는다).

    python -m scripts.probe_xlsx_shape_text corpus/poi-src/test-data corpus/lo-src
"""
import argparse
import collections
import glob
import html
import json
import re
import zipfile

TOK = re.compile(r'<(/?)([A-Za-z_][\w.\-]*:)?([A-Za-z_][\w.\-]*)([^>]*?)(/?)>|([^<]+)', re.S)
ANCHORS = {'twoCellAnchor', 'oneCellAnchor', 'absoluteAnchor'}


def scan(xml):
    """Return the normalized txBody texts of the drawing part's direct anchors."""
    texts = []
    stack = []
    in_anchor = False
    alternates = []  # branches seen per open AlternateContent
    skip_depth = None
    body = None
    paragraph = None
    in_text = False
    for match in TOK.finditer(xml):
        close, _, name, _, self_closing, text = match.groups()
        if text is not None:
            if in_text and paragraph is not None and skip_depth is None:
                paragraph.append(html.unescape(text))
            continue
        if close:
            if stack:
                stack.pop()
            if skip_depth is not None and len(stack) < skip_depth:
                skip_depth = None
            if name == 't':
                in_text = False
            elif name == 'p' and body is not None and paragraph is not None:
                line = ''.join(paragraph).strip()
                if line:
                    body.append(line)
                paragraph = None
            elif name == 'txBody' and body is not None:
                if body and skip_depth is None:
                    texts.append('\n'.join(body))
                body = None
            elif name in ANCHORS and len(stack) == 1:
                in_anchor = False
            elif name == 'AlternateContent' and alternates:
                alternates.pop()
            continue
        depth = len(stack)
        if name in ANCHORS and depth == 1:
            in_anchor = True
        if in_anchor and name in ('Choice', 'Fallback') and alternates:
            # Markup Compatibility: a consumer processes one branch — the first here.
            if alternates[-1] >= 1 and skip_depth is None:
                skip_depth = depth + 1
            alternates[-1] += 1
        if in_anchor and skip_depth is None:
            if name == 'txBody':
                body = []
            elif name == 'p' and body is not None:
                paragraph = []
            elif name == 't' and paragraph is not None:
                in_text = True
        if not self_closing:
            stack.append(name)
            if name == 'AlternateContent':
                alternates.append(0)
    return texts


def main():
    from dochan import Dochan
    parser = argparse.ArgumentParser()
    parser.add_argument('roots', nargs='+')
    args = parser.parse_args()
    files = sorted(set(path for root in args.roots
                       for path in glob.glob(root + '/**/*.xls[xm]', recursive=True)))
    report = collections.Counter()
    diffs = []
    for f in files:
        try:
            z = zipfile.ZipFile(f)
            names = [n for n in z.namelist() if re.match(r'xl/drawings/drawing\d+\.xml$', n)]
            oracle = collections.Counter()
            for n in names:
                for t in scan(z.read(n).decode('utf-8', 'replace')):
                    oracle[t] += 1
        except Exception:
            report['not_zip'] += 1
            continue
        if not oracle:
            report['no_shape_text'] += 1
            continue
        try:
            doc = Dochan(f).doc
        except Exception:
            report['reader_exception'] += 1
            continue
        got = collections.Counter()
        for section in doc.sections:
            for e in section.elements:
                prov = getattr(e, 'provenance', None)
                if (type(e).__name__ == 'Paragraph' and prov is not None
                        and (prov.path or '').startswith('xl/drawings/') and not e.text.startswith('![')):
                    got[e.text] += 1
        report['files'] += 1
        report['oracle_texts'] += sum(oracle.values())
        report['matched'] += sum((oracle & got).values())
        if oracle != got:
            report['files_diff'] += 1
            diffs.append([f, sum(oracle.values()), sum(got.values()),
                          list((oracle - got).items())[:3], list((got - oracle).items())[:3]])
    print(json.dumps({'summary': report, 'diffs': diffs}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
