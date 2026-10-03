"""POI document 코퍼스를 읽기 전용으로 스캔하고 DOCX 캐시·앵커를 검증한다.

실행: /usr/bin/python3 -m scripts.verify_ooxml_docx /path/to/poi/test-data/document
"""
import argparse
from collections import Counter
from difflib import SequenceMatcher
import json
import posixpath
from pathlib import Path
import re
import zipfile
from urllib.parse import unquote

from dochan.utils import safe_xml as etree

from dochan.model.document import Paragraph
from dochan.model.table import Table
from dochan.model.image import Image
from dochan.model.header_footer import Footnote, HeaderFooter
from dochan.ooxml.docx import DOCXReader

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
    'cx': 'http://schemas.microsoft.com/office/drawing/2014/chartex',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'v': 'urn:schemas-microsoft-com:vml',
    'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
}


def xml_texts(root, *paths):
    """Select text in document order, retaining XPath union deduplication."""
    selected = {node for path in paths for node in root.findall(path, NS)}
    texts = []
    stack = [(root, False)]
    while stack:
        node, tail = stack.pop()
        if tail:
            if node.tail is not None:
                texts.append(node.tail)
            continue
        if node in selected and node.text is not None:
            texts.append(node.text)
        for child in reversed(node):
            # XPath text() selects direct text and every child's tail, including
            # comments and processing instructions, but not descendant text.
            if node in selected:
                stack.append((child, True))
            stack.append((child, False))
    return texts


def has_local_name(root, names):
    return any(isinstance(node.tag, str) and etree.QName(node).localname in names
               for node in root.iter() if node is not root)


def logical_body_text(package, structural=False):
    """원시 XML과 관계에서 기존 출력 계약의 기대열을 만든다.

    출력 문자열을 정규식으로 지우지 않는다. 이미지 참조·링크·목록·주석도
    원래 위치의 기대값에 포함하여 이동/중복/누락을 그대로 검출한다.
    수식의 LaTeX 변환만 공용 변환기를 쓰며 수식 순서는 XML에서 결정한다.
    지원하지 않는 검증 구문은 성공으로 취급하지 않고 ValueError를 낸다.
    """
    parents = {}

    def xml(name):
        if name not in package.namelist():
            return None
        if package.getinfo(name).file_size > 32 * 1024 * 1024:
            raise ValueError('oracle XML size limit')
        root = etree.fromstring(package.read(name))
        parents.update(etree.parent_map(root))
        return root

    def attr(node, key='val', ns='w'):
        return node.get('{%s}%s' % (NS[ns], key), '') if node is not None else ''

    rels = {}
    relroot = xml('word/_rels/document.xml.rels')
    for rel in relroot if relroot is not None else []:
        target = rel.get('Target', '')
        if rel.get('TargetMode') != 'External':
            target = unquote(target)
        rels[rel.get('Id')] = (target if rel.get('TargetMode') == 'External' else
                              posixpath.normpath(posixpath.join('word', target)) if not target.startswith('/') else target.lstrip('/'))
    notes = {}
    for kind, part in [('footnote', 'footnotes'), ('endnote', 'endnotes'), ('comment', 'comments')]:
        root = xml('word/%s.xml' % part)
        for node in root if root is not None else []:
            if not attr(node, 'id').startswith('-'):
                notes[kind, attr(node, 'id')] = node
    note_numbers, comment_numbers = {}, {}
    annotated_comments = set()
    levels, counts = {}, {}
    numbering = xml('word/numbering.xml')
    if numbering is not None:
        abstracts = {attr(a, 'abstractNumId'): a for a in numbering.findall('w:abstractNum', NS)}
        for num in numbering.findall('w:num', NS):
            abstract = abstracts.get(attr(num.find('w:abstractNumId', NS)))
            for level in abstract if abstract is not None else []:
                if level.tag.endswith('}lvl'):
                    levels[attr(num, 'numId'), attr(level, 'ilvl')] = level

    def marker(fmt, n):
        if not 1 <= n <= 100000:
            raise ValueError('oracle numbering limit')
        if fmt == 'bullet':
            return '•'
        if fmt in ('lowerLetter', 'upperLetter'):
            value = ''
            while n:
                n, digit = divmod(n - 1, 26)
                value = chr(65 + digit) + value
            return value.lower() if fmt == 'lowerLetter' else value
        if fmt in ('lowerRoman', 'upperRoman'):
            value = ''
            for k, s in [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]:
                q, n = divmod(n, k)
                value += s * q
            return value.lower() if fmt == 'lowerRoman' else value
        return str(n)

    def numbering_prefix(para):
        props = para.find('w:pPr/w:numPr', NS)
        if props is None:
            return ''
        num = attr(props.find('w:numId', NS))
        depth = attr(props.find('w:ilvl', NS)) or '0'
        level = levels.get((num, depth))
        if level is None:
            return ''
        key = num, depth
        counts[key] = counts.get(key, int(attr(level.find('w:start', NS)) or '1') - 1) + 1
        for k in list(counts):
            if k[0] == num and int(k[1]) > int(depth):
                del counts[k]
        fmt = attr(level.find('w:numFmt', NS))
        if fmt == 'bullet':
            return '• '
        value = attr(level.find('w:lvlText', NS)) or '%1.'
        for i in range(int(depth) + 1):
            ancestor = levels.get((num, str(i)))
            if ancestor is not None:
                n = counts.get((num, str(i)), int(attr(ancestor.find('w:start', NS)) or '1'))
                value = value.replace('%%%d' % (i + 1), marker(attr(ancestor.find('w:numFmt', NS)), n))
        return value + ' '

    def visit(node, depth=0, annotations=None):
        if depth > 200:
            raise ValueError('oracle depth limit')
        if not isinstance(node.tag, str):
            return ''
        q = etree.QName(node)
        name, ns = q.localname, q.namespace
        if ns == NS['w'] and name in ('del', 'moveFrom', 'instrText', 'delText', 'pPr', 'rPr', 'sdtPr', 'sdtEndPr', 'tblPr', 'trPr', 'tcPr'):
            return ''
        if ns == NS['mc'] and name == 'AlternateContent':
            branch = node.find('mc:Choice', NS)
            if branch is None:
                branch = node.find('mc:Fallback', NS)
            return visit(branch, depth + 1, annotations) if branch is not None else ''
        if ns == NS['w'] and name == 't':
            return node.text or ''
        if ns == NS['w'] and name in ('tab', 'br', 'cr'):
            return ' '
        if ns == NS['w'] and name == 'bookmarkStart':
            return ''  # 문단 선두의 보이는 북마크로 아래에서 한 번 구성한다.
        if ns == NS['w'] and name in ('footnoteReference', 'endnoteReference'):
            key = name.replace('Reference', ''), attr(node, 'id')
            if key not in notes:
                return ''
            number = note_numbers.setdefault(key, len(note_numbers) + 1)
            return '[%d]' % number
        if ns == NS['w'] and name in ('commentRangeEnd', 'commentReference'):
            key = attr(node, 'id')
            if ('comment', key) not in notes or name == 'commentReference' and key in annotated_comments:
                return ''
            number = comment_numbers.setdefault(key, len(comment_numbers) + 1)
            if name == 'commentRangeEnd':
                annotated_comments.add(key)
                first = next((xml_body_text(p).strip() for p in notes['comment', key].findall('w:p', NS) if xml_body_text(p).strip()), '')
                return ' [comment %d%s]' % (number, ': ' + first if first else '')
            return '[comment %d]' % number
        if ns == NS['w'] and name == 'fldChar':
            box = node.find('w:ffData/w:checkBox', NS)
            if box is None:
                return ''
            checked = box.find('w:checked', NS)
            value = attr(checked) if checked is not None else attr(box.find('w:default', NS))
            return '[x]' if value.lower() in ('1', 'true', 'on', 'yes') or checked is not None and not value else '[ ]'
        if (ns, name) in ((NS['a'], 'blip'), (NS['v'], 'imagedata')):
            target = rels.get(attr(node, 'embed', 'r') or attr(node, 'id', 'r'))
            if not target:
                return ''
            label = ''
            for parent in etree.ancestors(node, parents):
                docpr = parent.find('wp:docPr', NS)
                if docpr is not None:
                    label = ' '.join(docpr.get(k) for k in ('title', 'descr', 'name') if docpr.get(k))
                    break
                if parent.tag in ('{%s}drawing' % NS['w'], '{%s}pict' % NS['w'], '{%s}txbxContent' % NS['w']):
                    break
            return '![%s](%s)' % (label or 'image', target)
        if ns == NS['wp'] and name == 'docPr':
            parent = parents.get(node)
            blips = parent.findall('.//a:blip', NS) if parent is not None else []
            if any(attr(b, 'embed', 'r') in rels for b in blips):
                return ''
            return ' '.join(node.get(k) for k in ('title', 'descr') if node.get(k))
        if ns == NS['m'] and name == 'oMath':
            from dochan.ooxml.math import _omml_to_latex
            return '\n' + _omml_to_latex(node) + '\n'
        if name == 'chart' and ns in (NS['c'], NS['cx']):
            target = rels.get(attr(node, 'id', 'r'))
            chart = xml(target) if target else None
            if chart is None:
                raise ValueError('oracle chart part missing')
            return '\n' + chart_logical_text(chart, structural) + '\n'
        if ns == NS['w'] and name == 'altChunk':
            raise ValueError('oracle altChunk not implemented')
        if ns == NS['w'] and name == 'tc':
            merge = node.find('w:tcPr/w:vMerge', NS)
            if merge is not None and attr(merge) != 'restart':
                return ''
        if ns == NS['w'] and name == 'p':
            annotations = set()
        prefix = numbering_prefix(node) if ns == NS['w'] and name == 'p' else ''
        value = ''.join(visit(c, depth + 1, annotations) for c in node)
        if ns == NS['w'] and name == 'hyperlink' and value:
            target = rels.get(attr(node, 'id', 'r')) or ('#' + attr(node, 'anchor') if attr(node, 'anchor') else '')
            value += ' <%s>' % target if target else ''
        if ns == NS['w'] and name == 'p':
            bookmarks = ''.join('[bookmark: %s] ' % attr(b, 'name') for b in active_nodes(node, stop_at_paragraph=True)
                                if b.tag == '{%s}bookmarkStart' % NS['w'] and attr(b, 'name') and not attr(b, 'name').startswith('_'))
            return '\n' + prefix + bookmarks + value + '\n'
        if ns == NS['w'] and name == 'tbl' and structural:
            return '\n⟦TABLE⟧\n' + value + '\n⟦/TABLE⟧\n'
        return value

    body = xml('word/document.xml').find('w:body', NS)
    if body is None:
        raise ValueError('oracle body namespace unsupported')
    return visit(body)


def chart_logical_text(root, structural=False):
    """일반/산포 차트의 저장된 캐시를 독립적으로 읽는다. 수화·추정은 하지 않는다."""
    plot = root.find('c:chart/c:plotArea', NS)
    if plot is None:
        raise ValueError('oracle chart format unsupported')
    groups = [node for node in plot if node.find('c:ser', NS) is not None]
    types = []
    labels = {'pieChart': 'pie', 'pie3DChart': '3-D pie', 'surface3DChart': '3-D surface',
              'lineChart': 'line', 'scatterChart': 'scatter'}
    for group in groups:
        kind = etree.QName(group).localname
        if kind in ('barChart', 'bar3DChart'):
            direction = group.find('c:barDir', NS)
            label = 'bar' if direction is not None and direction.get('val') == 'bar' else 'column'
            if kind == 'bar3DChart':
                label = '3-D ' + label
        elif kind in labels:
            label = labels[kind]
        else:
            raise ValueError('oracle chart type unsupported: ' + kind)
        if label not in types:
            types.append(label)
    title = ''.join(xml_texts(root, 'c:chart/c:title/c:tx/c:rich//a:t', 'c:chart/c:title/c:tx/c:strRef/c:strCache/c:pt/c:v'))
    captions = ['Chart type: ' + ' + '.join(types)] if types else []
    for axis in plot:
        name = etree.QName(axis).localname
        if name not in ('catAx', 'valAx', 'dateAx', 'serAx'):
            continue
        deleted = axis.find('c:delete', NS)
        if deleted is not None and deleted.get('val', '1') not in ('0', 'false', 'off'):
            continue
        text = ''.join(xml_texts(axis, 'c:title/c:tx/c:rich//a:t'))
        if text:
            captions.append({'catAx': 'Category', 'valAx': 'Value', 'dateAx': 'Date', 'serAx': 'Series'}[name] + ' axis: ' + text)
    if types == ['scatter']:
        rows = [['Series', 'X', 'Y']]
        for index, series in enumerate(plot.findall('c:scatterChart/c:ser', NS)):
            name = ''.join(xml_texts(series, 'c:tx/c:v', 'c:tx/c:strRef/c:strCache/c:pt/c:v')) or 'Series %d' % (index + 1)
            xs, ys = points(series.find('c:xVal', NS)), points(series.find('c:yVal', NS))
            for key in sorted(set(xs) | set(ys)):
                rows.append([name, xs.get(key, ''), ys.get(key, '')])
    else:
        rows = cached_rows(root)
        for index, row in enumerate(rows[1:]):
            if not row[0]:
                row[0] = str(index)
    chunks = [title, '; '.join(captions)]
    if structural:
        chunks.append('⟦TABLE⟧')
    chunks.extend(cell for row in rows for cell in row)
    if structural:
        chunks.append('⟦/TABLE⟧')
    return '\n'.join(chunks)


def story_evidence(package, doc):
    """단순 텍스트 실물의 머리글/꼬리글/각주 내용과 배치 계약을 별도로 검증한다."""
    root = etree.fromstring(package.read('word/document.xml'))
    relationships = etree.fromstring(package.read('word/_rels/document.xml.rels'))
    rels = {r.get('Id'): posixpath.normpath(posixpath.join('word', r.get('Target', ''))).lstrip('/')
            for r in relationships if r.get('TargetMode') != 'External'}
    expected = []
    seen = set()
    for kind in ('header', 'footer'):
        for node in active_nodes(root):
            if node.tag != '{%s}%sReference' % (NS['w'], kind):
                continue
            target = rels.get(node.get('{%s}id' % NS['r']))
            if target and target not in seen:
                seen.add(target)
                expected.append((kind, 0, xml_body_text(etree.fromstring(package.read(target)))))
    seen_notes = set()
    for node in active_nodes(root.find('w:body', NS)):
        if node.tag not in ('{%s}footnoteReference' % NS['w'], '{%s}endnoteReference' % NS['w']):
            continue
        kind = etree.QName(node).localname.replace('Reference', '')
        key = kind, node.get('{%s}id' % NS['w'])
        if key in seen_notes:
            continue
        part = 'word/%ss.xml' % kind
        if part not in package.namelist():
            continue
        definitions = etree.fromstring(package.read(part))
        note = next((n for n in definitions if n.get('{%s}id' % NS['w']) == key[1]), None)
        if note is not None:
            seen_notes.add(key)
            text = xml_body_text(note)
            if text.strip():
                expected.append((kind, len(seen_notes), text))
    elements = [e for s in doc.sections for e in s.elements]
    actual = [(e.type, getattr(e, 'number', 0), e.text) for e in elements
              if isinstance(e, (HeaderFooter, Footnote)) and e.type != 'comment']
    comparisons = [e[:2] == a[:2] and align_tokens(e[2], a[2])['exact'] for e, a in zip(expected, actual)]
    phases = [('header', 'body', 'footer', 'note').index(
        'note' if isinstance(e, Footnote) else e.type if isinstance(e, HeaderFooter) else 'body') for e in elements]
    ordered = phases == sorted(phases)
    return {'exact': len(expected) == len(actual) and all(comparisons) and ordered,
            'expected_stories': len(expected), 'actual_stories': len(actual),
            'matching_stories': sum(comparisons), 'placement_match': ordered}


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
            name = ''.join(xml_texts(series, 'c:tx/c:v', 'c:tx/c:strRef/c:strCache/c:pt/c:v'))
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
            name = ''.join(xml_texts(series, 'cx:tx/cx:txData/cx:v'))
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


def model_body_text(elements, structural=False):
    """본문 및 셀과 이동한 캡션을 출력 순서대로 읽는다. 메타데이터/주석은 제외한다."""
    chunks = []
    for elem in elements:
        path = getattr(getattr(elem, 'provenance', None), 'path', '')
        if isinstance(elem, Paragraph) and path and path != 'word/document.xml' and not path.startswith('word/charts/'):
            continue
        caption = getattr(elem, 'caption', [])
        before = getattr(elem, 'caption_side', '') in ('TOP', 'LEFT')
        if before:
            chunks.append(model_body_text(caption, structural))
        if isinstance(elem, Paragraph):
            chunks.append(elem.text)
        elif isinstance(elem, Table):
            if structural:
                chunks.append('⟦TABLE⟧')
            for row in elem.rows:
                for cell in row:
                    if not cell.is_merged_away:
                        chunks.append(model_body_text(cell.paragraphs, structural))
            if structural:
                chunks.append('⟦/TABLE⟧')
        elif isinstance(elem, Image):
            # XML에 없는 OCR 및 이미지 대체 설명은 본문 비교 대상이 아니다.
            pass
        elif hasattr(elem, 'latex'):
            chunks.append(elem.latex or elem.script)
        if not before:
            chunks.append(model_body_text(caption, structural))
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
    parents = etree.parent_map(root)
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
        in_cell = any(node.tag == '{%s}tc' % NS['w'] for node in etree.ancestors(para, parents))
        rows.append({'text': text, 'style': style_id, 'field': fields,
                     'in_cell': in_cell, 'attached': attached[text] > 0,
                     'preserved': text in actual})
    return rows


def probe(corpus, per_feature=0):
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
                cap_ids = [node.get('{%s}val' % NS['w'], '') for node in root.findall('.//w:pStyle', NS)]
                seq = [node.text or '' if node.tag == '{%s}instrText' % NS['w'] else node.get('{%s}instr' % NS['w'], '')
                       for node in root.iter() if node.tag in {'{%s}instrText' % NS['w'], '{%s}fldSimple' % NS['w']}]
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
                        title = ''.join(xml_texts(chart, 'c:chart/c:title/c:tx/c:rich/a:p/a:r/a:t', 'cx:chart/cx:title/cx:tx/cx:rich/a:p/a:r/a:t'))
                        headings = [e.text for e in doc.sections[0].elements if isinstance(e, Paragraph) and e.heading_level == 3]
                        rows.append({'part': name, 'rows': len(expected) - 1, 'cells': sum(map(len, expected)), 'data_match': actual == expected, 'title': title, 'title_match': not title or title in headings, 'caption': table.caption_text if table else ''})
                    results['chart_documents'].append({'file': path.name, 'charts': rows, 'errors': doc.errors})
                features = []
                if root.find('.//w:txbxContent', NS) is not None:
                    features.append('textbox')
                if has_local_name(root, {'anchor', 'shape'}):
                    features.append('floating_shape')
                if root.find('.//w:sdt', NS) is not None:
                    features.append('content_control')
                if has_local_name(root, {'wgp', 'grpSp', 'group'}):
                    features.append('group_shape')
                if features:
                    reading_candidates[path] = features
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, etree.XMLSyntaxError):
            results['unreadable_documents'] += 1
            continue
    # 기본값은 조건에 맞는 파일 전수다. 30은 종전 84개 표본의 재현용이다.
    selected = set() if per_feature else set(reading_candidates)
    for feature in ('textbox', 'floating_shape', 'content_control') if per_feature else ():
        candidates = sorted(path for path, features in reading_candidates.items() if feature in features)
        count = min(per_feature, len(candidates))
        selected.update(candidates[i * (len(candidates) - 1) // max(count - 1, 1)] for i in range(count))
    results['reading_candidate_documents'] = len(reading_candidates)
    for path in sorted(selected):
        with zipfile.ZipFile(path) as package:
            root = etree.fromstring(package.read('word/document.xml'))
            try:
                logical = logical_body_text(package)
                structural = logical_body_text(package, structural=True)
                oracle_error = ''
            except (ValueError, KeyError, etree.XMLSyntaxError) as exc:
                logical, structural, oracle_error = '', '', str(exc)
        doc = DOCXReader().read(str(path))
        actual = model_body_text([elem for section in doc.sections for elem in section.elements])
        logical_result = align_tokens(logical, actual) if not oracle_error else {'exact': False, 'unverified': oracle_error}
        structural_result = align_tokens(structural, model_body_text([e for s in doc.sections for e in s.elements], structural=True)) if not oracle_error else {'exact': False, 'unverified': oracle_error}
        result = dict(structural_result)
        result.update({'file': path.name, 'features': reading_candidates[path], 'errors': doc.errors,
                       'raw_wt': align_tokens(xml_body_text(root.find('w:body', NS)), actual),
                       'logical': logical_result, 'structural': structural_result})
        results['reading_order'].append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--per-feature', type=int, default=0, help='0은 해당 특징 전수, 30은 종전 84개 표본이다.')
    parser.add_argument('--story-file', action='append', default=[], help='별도로 머리글/각주를 검증할 공개 파일 이름이다.')
    args = parser.parse_args()
    result = probe(args.corpus, args.per_feature)
    result['stories'] = []
    for name in args.story_file:
        path = args.corpus / name
        doc = DOCXReader().read(str(path))
        with zipfile.ZipFile(path) as package:
            evidence = story_evidence(package, doc)
        result['stories'].append(dict(evidence, file=name, errors=doc.errors))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
