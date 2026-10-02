"""POI document 코퍼스를 읽기 전용으로 스캔하고 DOCX 캐시·앵커를 검증한다.

실행: /usr/bin/python3 -m scripts.verify_ooxml_docx /path/to/poi/test-data/document
"""
import argparse
from collections import Counter
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import zipfile

from lxml import etree

from dochan.model.document import Paragraph
from dochan.model.table import Table
from dochan.model.image import Image
from dochan.ooxml.docx import DOCXReader

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
    'cx': 'http://schemas.microsoft.com/office/drawing/2014/chartex',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
}


def points(container):
    if container is None:
        return {}
    result = {}
    for point in container.findall('.//c:pt', NS):
        value = point.find('c:v', NS)
        result[int(point.get('idx'))] = value.text or '' if value is not None else ''
    return result


def cached_rows(root):
    """리더를 호출하지 않고 원시 XML의 계열명·범주·값을 표와 대조한다."""
    items = []
    if etree.QName(root).namespace == NS['c']:
        for position, series in enumerate(root.findall('.//c:plotArea/*/c:ser', NS)):
            name = ''.join(series.xpath('c:tx/c:v/text()|c:tx/c:strRef/c:strCache/c:pt/c:v/text()', namespaces=NS))
            categories = points(series.find('c:cat', NS))
            values = points(series.find('c:val', NS))
            items.append((name or 'Series %d' % (position + 1), categories, values))
    else:
        datasets = {data.get('id'): data for data in root.findall('cx:chartData/cx:data', NS)}
        for position, series in enumerate(root.findall('.//cx:plotAreaRegion/cx:series', NS)):
            data = datasets[series.find('cx:dataId', NS).get('val')]
            levels = []
            for level in data.findall('cx:strDim/cx:lvl', NS):
                levels.append({int(p.get('idx')): p.text or '' for p in level.findall('cx:pt', NS)})
            categories = {}
            for index in set(i for level in levels for i in level):
                categories[index] = ' / '.join(level.get(index, '') for level in reversed(levels) if level.get(index, ''))
            values = {int(p.get('idx')): p.text or '' for p in data.findall('cx:numDim/cx:lvl/cx:pt', NS)}
            name = ''.join(series.xpath('cx:tx/cx:txData/cx:v/text()', namespaces=NS))
            items.append((name or 'Series %d' % (position + 1), categories, values))
    indices = sorted(set(i for _, cats, vals in items for i in set(cats) | set(vals)))
    rows = [['Category'] + [name for name, _, _ in items]]
    for index in indices:
        category = next((cats[index] for _, cats, _ in items if index in cats), '')
        rows.append([category] + [vals.get(index, '') for _, _, vals in items])
    return rows


def visible_text_nodes(root):
    """AlternateContent의 한 갈래를 원시 XML 순서로 읽고 삭제 이력을 제외한다."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.tag in {'{%s}del' % NS['w'], '{%s}moveFrom' % NS['w']}:
            continue
        if node.tag == '{%s}AlternateContent' % NS['mc']:
            choice = node.find('mc:Choice', NS)
            if choice is None:
                choice = node.find('mc:Fallback', NS)
            if choice is not None:
                stack.append(choice)
            continue
        if node.tag == '{%s}t' % NS['w'] and (node.text or '').strip():
            yield node.text
        stack.extend(reversed(list(node)))


def align_tokens(expected, actual):
    """공백만 정규화하고 삽입·삭제·대체를 모두 분모에 포함한다."""
    expected = re.findall(r'\w+|[^\w\s]', expected, re.UNICODE)
    actual = re.findall(r'\w+|[^\w\s]', actual, re.UNICODE)
    matcher = SequenceMatcher(None, expected, actual, autojunk=False)
    counts = Counter()
    differences = []
    for tag, i, j, a, b in matcher.get_opcodes():
        if tag == 'equal':
            counts['matched'] += j - i
        else:
            counts['deleted'] += j - i
            counts['inserted'] += b - a
            if len(differences) < 8:
                differences.append({'operation': tag, 'expected': expected[i:j][:12],
                                    'actual': actual[a:b][:12]})
    return {'expected_tokens': len(expected), 'actual_tokens': len(actual),
            'matched': counts['matched'], 'deleted': counts['deleted'],
            'inserted': counts['inserted'], 'exact': expected == actual,
            'alignment_ratio': matcher.ratio(), 'differences': differences}


def xml_body_text(root):
    """w:t 원문을 XML 순서로 읽는다. 같은 문단의 런은 이어 붙인다."""
    if root is None:
        return ''
    chunks = []
    stack = [(root, False)]
    while stack:
        node, closing = stack.pop()
        if closing:
            if node.tag == '{%s}p' % NS['w']:
                chunks.append('\n')
            continue
        if node.tag in {'{%s}del' % NS['w'], '{%s}moveFrom' % NS['w']}:
            continue
        if node.tag == '{%s}AlternateContent' % NS['mc']:
            branch = node.find('mc:Choice', NS)
            if branch is None:
                branch = node.find('mc:Fallback', NS)
            if branch is not None:
                stack.append((branch, False))
            continue
        if node.tag == '{%s}p' % NS['w']:
            chunks.append('\n')
        if node.tag == '{%s}t' % NS['w']:
            chunks.append(node.text or '')
        if node.tag in {'{%s}%s' % (NS['w'], tag) for tag in ('tab', 'br', 'cr')}:
            chunks.append(' ')
        stack.append((node, True))
        stack.extend((child, False) for child in reversed(list(node)))
    return ''.join(chunks)


def model_body_text(elements):
    """본문 및 셀과 이동한 캡션을 출력 순서대로 읽는다. 메타데이터/주석은 제외한다."""
    chunks = []
    for elem in elements:
        path = getattr(getattr(elem, 'provenance', None), 'path', '')
        if isinstance(elem, Paragraph) and path and path != 'word/document.xml':
            continue
        caption = getattr(elem, 'caption', [])
        before = getattr(elem, 'caption_side', '') in ('TOP', 'LEFT')
        if before:
            chunks.append(model_body_text(caption))
        if isinstance(elem, Paragraph):
            chunks.append(elem.text)
        elif isinstance(elem, Table):
            for row in elem.rows:
                for cell in row:
                    if not cell.is_merged_away:
                        chunks.append(model_body_text(cell.paragraphs))
        elif isinstance(elem, Image):
            # XML에 없는 OCR 및 이미지 대체 설명은 본문 비교 대상이 아니다.
            pass
        elif hasattr(elem, 'latex'):
            chunks.append(elem.latex or elem.script)
        if not before:
            chunks.append(model_body_text(caption))
    return '\n'.join(chunks)


def active_nodes(root, stop_at_paragraph=False):
    """호환 갈래 하나만 선택하여 비활성 대체 표현의 중복을 세지 않는다."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.tag in {'{%s}del' % NS['w'], '{%s}moveFrom' % NS['w']}:
            continue
        if stop_at_paragraph and node is not root and node.tag == '{%s}p' % NS['w']:
            continue
        yield node
        if node.tag == '{%s}AlternateContent' % NS['mc']:
            branch = node.find('mc:Choice', NS)
            if branch is None:
                branch = node.find('mc:Fallback', NS)
            if branch is not None:
                stack.append(branch)
        else:
            stack.extend(reversed(list(node)))


def caption_evidence(root, style_ids, doc):
    attached = Counter(' '.join(elem.caption_text.split())
                       for kind in ('table', 'image') for elem in doc.find_all(kind)
                       if elem.caption_text)
    actual = ' '.join(model_body_text([elem for section in doc.sections
                                      for elem in section.elements]).split())
    rows = []
    for para in active_nodes(root):
        if para.tag != '{%s}p' % NS['w']:
            continue
        style = para.find('w:pPr/w:pStyle', NS)
        style_id = style.get('{%s}val' % NS['w'], '') if style is not None else ''
        owned_nodes = list(active_nodes(para, stop_at_paragraph=True))
        fields = ''.join(node.text or '' if node.tag == '{%s}instrText' % NS['w']
                         else node.get('{%s}instr' % NS['w'], '')
                         for node in owned_nodes
                         if node.tag in {'{%s}instrText' % NS['w'], '{%s}fldSimple' % NS['w']})
        if style_id not in style_ids and style_id.casefold() != 'caption' and not re.search(r'\bSEQ\s', fields):
            continue
        text = ' '.join(''.join(node.text or '' for node in owned_nodes
                               if node.tag == '{%s}t' % NS['w']).split())
        if not text:
            continue
        in_cell = any(node.tag == '{%s}tc' % NS['w'] for node in para.iterancestors())
        rows.append({'text': text, 'style': style_id, 'field': fields,
                     'in_cell': in_cell, 'attached': attached[text] > 0,
                     'preserved': text in actual})
    return rows


def probe(corpus):
    results = {'scanned_documents': 0, 'parseable_documents': 0, 'unreadable_documents': 0, 'caption_documents': [], 'chart_documents': [], 'reading_order': []}
    reading_candidates = {}
    for path in sorted(corpus.rglob('*.docx')):
        results['scanned_documents'] += 1
        try:
            with zipfile.ZipFile(path) as package:
                root = etree.fromstring(package.read('word/document.xml'))
                names = [n for n in package.namelist() if n.startswith('word/charts/') and n.endswith('.xml') and '/_rels/' not in n]
                chart_roots = [(n, etree.fromstring(package.read(n))) for n in names]
                chart_roots = [(n, r) for n, r in chart_roots if etree.QName(r).localname == 'chartSpace']
                results['parseable_documents'] += 1
                style_ids = set()
                if 'word/styles.xml' in package.namelist():
                    styles = etree.fromstring(package.read('word/styles.xml'))
                    based_on = {}
                    for style in styles.findall('w:style', NS):
                        style_id = style.get('{%s}styleId' % NS['w'], '')
                        name = style.find('w:name', NS)
                        if style_id.casefold() == 'caption' or name is not None and name.get('{%s}val' % NS['w'], '').casefold() == 'caption':
                            style_ids.add(style_id)
                        parent = style.find('w:basedOn', NS)
                        based_on[style_id] = parent.get('{%s}val' % NS['w'], '') if parent is not None else ''
                    for style_id in based_on:
                        visited = set()
                        ancestor = style_id
                        while ancestor and ancestor not in visited:
                            if ancestor in style_ids:
                                style_ids.add(style_id)
                                break
                            visited.add(ancestor)
                            ancestor = based_on.get(ancestor, '')
                cap_ids = root.xpath('.//w:pStyle/@w:val', namespaces=NS)
                seq = root.xpath('.//w:instrText/text()|.//w:fldSimple/@w:instr', namespaces=NS)
                if any('SEQ' in s for s in seq) or any(s in style_ids or s.casefold() == 'caption' for s in cap_ids):
                    doc = DOCXReader().read(str(path))
                    results['caption_documents'].append({'file': path.name,
                        'captions': caption_evidence(root, style_ids, doc), 'errors': doc.errors})
                if chart_roots:
                    doc = DOCXReader().read(str(path))
                    by_path = {}
                    for table in doc.find_all('table'):
                        if table.caption and getattr(table.caption[0], 'provenance', None):
                            by_path[table.caption[0].provenance.path] = table
                    rows = []
                    for name, chart in chart_roots:
                        expected = cached_rows(chart)
                        table = by_path.get(name)
                        actual = [[cell.text for cell in row] for row in table.rows] if table else []
                        title = ''.join(chart.xpath('c:chart/c:title/c:tx/c:rich/a:p/a:r/a:t/text()|cx:chart/cx:title/cx:tx/cx:rich/a:p/a:r/a:t/text()', namespaces=NS))
                        headings = [e.text for e in doc.sections[0].elements if isinstance(e, Paragraph) and e.heading_level == 3]
                        rows.append({'part': name, 'rows': len(expected) - 1, 'cells': sum(map(len, expected)), 'data_match': actual == expected, 'title': title, 'title_match': not title or title in headings, 'caption': table.caption_text if table else ''})
                    results['chart_documents'].append({'file': path.name, 'charts': rows, 'errors': doc.errors})
                features = []
                if root.find('.//w:txbxContent', NS) is not None:
                    features.append('textbox')
                if root.xpath('.//*[local-name()="anchor"]|.//*[local-name()="shape"]'):
                    features.append('floating_shape')
                if root.find('.//w:sdt', NS) is not None:
                    features.append('content_control')
                if features:
                    reading_candidates[path] = features
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, etree.XMLSyntaxError):
            results['unreadable_documents'] += 1
            continue
    # 결과를 보기 전에 종류마다 이름순 전체 구간에서 최대 30개를 균등 선택한다.
    selected = set()
    for feature in ('textbox', 'floating_shape', 'content_control'):
        candidates = sorted(path for path, features in reading_candidates.items() if feature in features)
        count = min(30, len(candidates))
        selected.update(candidates[i * (len(candidates) - 1) // max(count - 1, 1)] for i in range(count))
    results['reading_candidate_documents'] = len(reading_candidates)
    for path in sorted(selected):
        with zipfile.ZipFile(path) as package:
            root = etree.fromstring(package.read('word/document.xml'))
        doc = DOCXReader().read(str(path))
        actual = model_body_text([elem for section in doc.sections for elem in section.elements])
        result = align_tokens(xml_body_text(root.find('w:body', NS)), actual)
        result.update({'file': path.name, 'features': reading_candidates[path], 'errors': doc.errors})
        results['reading_order'].append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    args = parser.parse_args()
    print(json.dumps(probe(args.corpus), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
