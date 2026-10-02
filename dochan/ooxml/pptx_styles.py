"""PresentationML shape character defaults (ECMA-376 Part 1, 19.3/21.1).

Only character attributes are cascaded. Paragraph/list content, hyperlinks,
sample master text and endParaRPr are not copied into slide content.
"""
import posixpath
import zipfile

from lxml import etree

P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
NS = {'p': P, 'a': A}
MAX_STYLE_PARTS = 1024
MAX_STYLE_BYTES = 64 * 1024 * 1024
MAX_STYLE_NODES = 100000
MAX_STYLE_DEPTH = 64
ATTRIBUTES = ('b', 'i', 'u', 'sz', 'baseline')


def _placeholder(shape):
    return shape.find('p:nvSpPr/p:nvPr/p:ph', NS)


def _family(kind):
    if kind in {'title', 'ctrTitle'}:
        return 'title'
    if kind in {'body', 'subTitle', 'obj'}:
        return 'body'
    return kind


class TextStyleResolver:
    def __init__(self, package, presentation, errors, alternate_branch):
        self.package = package
        self.default = presentation.find('p:defaultTextStyle', NS)
        self.errors = errors
        self.alternate_branch = alternate_branch
        self.parts = {}
        self.related = {}
        self.indexes = {}
        self.paragraphs = {}
        self.bytes = 0
        self.nodes = 0

    def warn(self, message):
        warning = 'WARN: PPTX text style ' + message
        if warning not in self.errors:
            self.errors.append(warning)

    def _load(self, path):
        if path in self.parts:
            return self.parts[path]
        if len(self.parts) >= MAX_STYLE_PARTS:
            self.warn('part limit exceeded')
            return None
        self.parts[path] = None
        try:
            if not self.package.exists(path):
                self.warn('part missing')
                return None
            size = self.package.part_size(path)
            if self.bytes + size > MAX_STYLE_BYTES:
                self.warn('byte limit exceeded')
                return None
            self.bytes += size
            root = self.package.read_xml_part(path)
            self.parts[path] = root
            return root
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, etree.XMLSyntaxError):
            self.warn('part could not be read')
            return None

    def related_part(self, path, kind):
        key = (path, kind)
        if key in self.related:
            return self.related[key]
        directory = posixpath.dirname(path)
        relpath = directory + '/_rels/' + posixpath.basename(path) + '.rels'
        result = ('', None)
        if self.package.exists(relpath):
            root = self._load(relpath)
            if root is not None:
                for rel in root:
                    if (rel.tag != '{%s}Relationship' % REL or
                            not rel.get('Type', '').endswith('/' + kind) or
                            rel.get('TargetMode') == 'External'):
                        continue
                    target = rel.get('Target', '')
                    if not target:
                        continue
                    target = target.replace('\\', '/')
                    target = posixpath.normpath(target.lstrip('/') if target.startswith('/')
                                               else posixpath.join(directory, target))
                    result = (target, self._load(target))
                    break
        self.related[key] = result
        return result

    def context(self, root, path):
        if root.tag == '{%s}sld' % P:
            layout_path, layout = self.related_part(path, 'slideLayout')
            _, master = self.related_part(layout_path, 'slideMaster') if layout is not None else ('', None)
            return layout, master
        if root.tag == '{%s}sldLayout' % P:
            _, master = self.related_part(path, 'slideMaster')
            return None, master
        return None  # Notes masters, tables, chart and SmartArt text are out of scope.

    def _index(self, root):
        if root is None:
            return {}, {}, {}
        if root in self.indexes:
            return self.indexes[root]
        by_idx, by_type, by_family = {}, {}, {}
        tree = root.find('p:cSld/p:spTree', NS)
        stack = [(tree, 0)] if tree is not None else []
        while stack:
            node, depth = stack.pop()
            self.nodes += 1
            if self.nodes > MAX_STYLE_NODES or depth > MAX_STYLE_DEPTH:
                self.warn('shape traversal limit exceeded')
                break
            if node.tag == '{%s}sp' % P:
                ph = _placeholder(node)
                if ph is not None:
                    idx, kind = ph.get('idx', '0'), ph.get('type', 'body')
                    exact, families, first = by_idx.setdefault(idx, ({}, {}, node))
                    exact.setdefault(kind, node)
                    families.setdefault(_family(kind), node)
                    by_type.setdefault(kind, {}).setdefault(idx, node)
                    by_family.setdefault(_family(kind), {}).setdefault(idx, node)
            elif node.tag == '{%s}AlternateContent' % MC:
                branch = self.alternate_branch(node)
                if branch is not None:
                    stack.append((branch, depth + 1))
            else:
                stack.extend((child, depth + 1) for child in reversed(node))
        self.indexes[root] = by_idx, by_type, by_family
        return self.indexes[root]

    def _match(self, root, ph, master=False):
        if ph is None:
            return None
        by_idx, by_type, by_family = self._index(root)
        kind, idx = ph.get('type', 'body'), ph.get('idx', '0')
        if master:
            candidates = by_type.get(kind) or by_family.get(_family(kind), {})
            return candidates.get(idx, next(iter(candidates.values()), None))
        group = by_idx.get(idx)
        if group is None:
            return None
        exact, families, first = group
        if kind in exact:
            return exact[kind]
        if _family(kind) in families:
            return families[_family(kind)]
        return first if ph.get('type') is None else None

    def shape_layers(self, shape, context):
        if context is None:
            return None
        layout, master = context
        ph = _placeholder(shape)
        layout_shape = self._match(layout, ph)
        # Slide placeholders frequently omit type and identify the layout by idx.
        parent_ph = _placeholder(layout_shape) if layout_shape is not None else ph
        master_shape = self._match(master, parent_ph, master=True)
        kind = (ph.get('type') if ph is not None else None)
        if not kind and parent_ph is not None:
            kind = parent_ph.get('type', 'body')
        family = _family(kind)
        style_name = {'title': 'titleStyle', 'body': 'bodyStyle'}.get(family, 'otherStyle')
        tx = master.find('p:txStyles/p:' + style_name, NS) if master is not None else None
        return tx, master_shape, layout_shape, shape

    def level(self, paragraph):
        ppr = paragraph.find('a:pPr', NS)
        value = ppr.get('lvl', '0') if ppr is not None else '0'
        if value not in tuple(str(n) for n in range(9)):
            self.warn('invalid paragraph level')
            return 0
        return int(value)

    def properties(self, node):
        result = {}
        if node is None:
            return result
        for name in ATTRIBUTES:
            value = node.get(name)
            if value is None:
                continue
            valid = True
            if name in {'b', 'i'}:
                valid = value in {'0', '1', 'true', 'false'}
            elif name in {'sz', 'baseline'}:
                try:
                    number = int(value) if len(value) <= 12 else None
                    valid = number is not None and (100 <= number <= 400000 if name == 'sz'
                                                    else -2147483648 <= number <= 2147483647)
                except ValueError:
                    valid = False
            if valid:
                result[name] = value
            else:
                self.warn('invalid character attribute ' + name)
        return result

    def _list_properties(self, style, level):
        result = {}
        if style is not None:
            for path in ('a:defPPr/a:defRPr', 'a:lvl%dpPr/a:defRPr' % (level + 1)):
                result.update(self.properties(style.find(path, NS)))
        return result

    def _ancestor_paragraphs(self, shape):
        if shape not in self.paragraphs:
            levels = {}
            body = shape.find('p:txBody', NS)
            if body is not None:
                for paragraph in body:
                    self.nodes += 1
                    if self.nodes > MAX_STYLE_NODES:
                        self.warn('shape traversal limit exceeded')
                        break
                    if paragraph.tag == '{%s}p' % A:
                        level = self.level(paragraph)
                        if level not in levels:
                            levels[level] = self.properties(paragraph.find('a:pPr/a:defRPr', NS))
                        if len(levels) == 9:
                            break
            self.paragraphs[shape] = levels
        return self.paragraphs[shape]

    def paragraph_defaults(self, layers, paragraph):
        if layers is None:
            return None
        level = self.level(paragraph)
        tx, master, layout, shape = layers
        values = self._list_properties(self.default, level)
        values.update(self._list_properties(tx, level))
        for ancestor in (master, layout, shape):
            if ancestor is None:
                continue
            values.update(self._list_properties(ancestor.find('p:txBody/a:lstStyle', NS), level))
            if ancestor is shape:
                values.update(self.properties(paragraph.find('a:pPr/a:defRPr', NS)))
            else:
                values.update(self._ancestor_paragraphs(ancestor).get(level, {}))
        return values

    def apply(self, run, rpr, defaults):
        values = dict(defaults)
        values.update(self.properties(rpr))
        run.bold = values.get('b') in {'1', 'true'}
        run.italic = values.get('i') in {'1', 'true'}
        run.underline = values.get('u', 'none') != 'none'
        if 'sz' in values:
            run.font_size_pt = int(values['sz']) / 100
        baseline = int(values.get('baseline', '0'))
        run.superscript = baseline > 0
        run.subscript = baseline < 0
