"""PresentationML shape character defaults (ECMA-376 Part 1, 19.3/21.1).

Only character attributes are cascaded. Paragraph/list content, hyperlinks,
sample master text and endParaRPr are not copied into slide content.
"""
import posixpath
import re
from decimal import Decimal, InvalidOperation
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


# PowerPoint(Mac), measured decks 1/2, 2026-10-03: only title/body use
# txStyles. Other placeholders inherit their own master, free shapes only
# presentation defaults. Ancestor sample paragraphs never supply defaults.
TITLE_PLACEHOLDERS = frozenset({'title', 'ctrTitle'})
INDEPENDENT_PLACEHOLDERS = frozenset({'dt', 'ftr', 'sldNum'})
UNDERLINE_VALUES = frozenset({
    'none', 'words', 'sng', 'dbl', 'heavy', 'dotted', 'dottedHeavy', 'dash',
    'dashHeavy', 'dashLong', 'dashLongHeavy', 'dotDash', 'dotDashHeavy',
    'dotDotDash', 'dotDotDashHeavy', 'wavy', 'wavyHeavy', 'wavyDbl',
})


def _family(kind):
    if kind is None or kind in INDEPENDENT_PLACEHOLDERS:
        return kind
    return 'title' if kind in TITLE_PLACEHOLDERS else 'body'


def _baseline(value):
    """Normalize ST_Percentage integer/percent forms to thousandths of percent."""
    if len(value) > 64:
        return None
    try:
        if re.fullmatch(r'[+-]?[0-9]+', value):
            number = Decimal(value)
        elif re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]+)?%', value):
            number = Decimal(value[:-1]) * 1000
        else:
            return None
        return number if -2147483648 <= number <= 2147483647 else None
    except InvalidOperation:
        return None


class TextStyleResolver:
    def __init__(self, package, presentation, errors, alternate_branch):
        self.package = package
        self.default = presentation.find('p:defaultTextStyle', NS)
        self.errors = errors
        self.alternate_branch = alternate_branch
        self.parts = {}
        self.related = {}
        self.indexes = {}
        self.list_styles = {}
        self.shape_styles = {}
        self.bytes = 0
        self.nodes = {}
        self.root_paths = {presentation: "ppt/presentation.xml"}

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
            self.root_paths[root] = path
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
        self.root_paths[root] = path
        if root.tag == '{%s}sld' % P:
            layout_path, layout = self.related_part(path, 'slideLayout')
            _, master = self.related_part(layout_path, 'slideMaster') if layout is not None else ('', None)
            return layout, master
        if root.tag == '{%s}sldLayout' % P:
            _, master = self.related_part(path, 'slideMaster')
            return None, master
        return None  # Notes masters, tables, chart and SmartArt text are out of scope.

    def release_context(self, root):
        """Drop content trees; only budgeted ancestor trees stay resident."""
        path = self.root_paths.get(root)
        if self.parts.get(path) is not root:
            self.root_paths.pop(root, None)

    def _node_key(self, node):
        tree = node.getroottree()
        path = self.root_paths.get(tree.getroot())
        # Standalone nodes have no package identity. Package nodes use their
        # structural position, since cNvPr IDs can be missing or duplicated.
        return (path, tree.getpath(node)) if path is not None else node

    def _take_node(self, node):
        # Cache traversals and charge their work to the owning XML part, so one
        # malformed part cannot disable otherwise valid, unrelated parts.
        root = node.getroottree().getroot()
        part = self.root_paths.get(root, root)
        count = self.nodes.get(part, 0)
        if count >= MAX_STYLE_NODES:
            self.warn('shape traversal limit exceeded')
            return False
        self.nodes[part] = count + 1
        return True

    def _idx(self, ph):
        value = ph.get('idx', '0').strip()
        if len(value) <= 32 and re.fullmatch(r'[+-]?[0-9]+', value):
            number = int(value)
            if 0 <= number <= 4294967295:
                return number
        self.warn('invalid placeholder index')
        return None

    def _kind(self, ph):
        return ph.get('type') or ('title' if self._idx(ph) == 0 else 'body')

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
            if depth > MAX_STYLE_DEPTH or not self._take_node(node):
                self.warn('shape traversal limit exceeded')
                break
            if node.tag == '{%s}sp' % P:
                ph = _placeholder(node)
                if ph is not None:
                    idx, kind = self._idx(ph), self._kind(ph)
                    if idx is None:
                        continue
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
        kind, idx = self._kind(ph), self._idx(ph)
        if idx is None:
            return None
        if master:
            family = _family(kind)
            candidates = by_type.get(family) or by_family.get(family, {})
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
            kind = self._kind(parent_ph)
        family = _family(kind)
        style_name = {'title': 'titleStyle', 'body': 'bodyStyle'}.get(family)
        tx = (master.find('p:txStyles/p:' + style_name, NS)
              if master is not None and style_name is not None else None)
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
            elif name == 'u':
                valid = value in UNDERLINE_VALUES
            elif name == 'baseline':
                number = _baseline(value)
                valid = number is not None
                if valid:
                    value = str(number)
            elif name == 'sz':
                try:
                    number = int(value) if len(value) <= 12 else None
                    valid = number is not None and 100 <= number <= 400000
                except ValueError:
                    valid = False
            if valid:
                result[name] = value
            else:
                self.warn('invalid character attribute ' + name)
        return result

    def _list_properties(self, style, level, defaults=False):
        if style is None:
            return {}
        cache_key = self._node_key(style)
        if cache_key not in self.list_styles:
            indexed = {}
            tags = {'{%s}defPPr' % A: -1}
            tags.update(('{%s}lvl%dpPr' % (A, n + 1), n) for n in range(9))
            for child in style:
                if not self._take_node(child):
                    break
                key = tags.get(child.tag)
                if key is None or key in indexed:
                    continue
                indexed[key] = {}
                for prop in child:
                    if not self._take_node(prop):
                        break
                    if prop.tag == '{%s}defRPr' % A:
                        indexed[key] = self.properties(prop)
                        break
            # Retain scalar properties, never the content XML node. Reparsed
            # copies reuse the same result and do not spend the budget again.
            self.list_styles[cache_key] = indexed
        return self.list_styles[cache_key].get(-1 if defaults else level, {})

    def _shape_style(self, shape):
        if shape is None:
            return None
        return shape.find('p:txBody/a:lstStyle', NS)

    def paragraph_defaults(self, layers, paragraph):
        if layers is None:
            return None
        level = self.level(paragraph)
        tx, master, layout, shape = layers
        cache_key = (self._node_key(shape), level)
        if cache_key not in self.shape_styles:
            styles = (self.default, tx, self._shape_style(master),
                      self._shape_style(layout), self._shape_style(shape))
            values = {}
            # PowerPoint deck1 S7: even a nearer defPPr loses to a farther lvlNpPr.
            for defaults in (True, False):
                for style in styles:
                    values.update(self._list_properties(style, level, defaults))
            self.shape_styles[cache_key] = values
        # Paragraph overrides are local and must not contaminate the cache.
        values = dict(self.shape_styles[cache_key])
        values.update(self.properties(paragraph.find('a:pPr/a:defRPr', NS)))
        return values

    def apply(self, run, rpr, defaults):
        values = dict(defaults)
        values.update(self.properties(rpr))
        run.bold = values.get('b') in {'1', 'true'}
        run.italic = values.get('i') in {'1', 'true'}
        run.underline = values.get('u', 'none') != 'none'
        if 'sz' in values:
            run.font_size_pt = int(values['sz']) / 100
        baseline = Decimal(values.get('baseline', '0'))
        run.superscript = baseline > 0
        run.subscript = baseline < 0
