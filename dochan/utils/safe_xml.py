"""Bounded XML parsing, including hosts linked to expat before 2.4.

The prolog is checked with expat *before* ElementTree sees any input. Raising
from TreeBuilder.doctype alone does not stop the C parser's entity expansion.
No parser here installs a resource resolver or performs network/file I/O.
"""
import codecs
import re
from html.parser import HTMLParser
from weakref import WeakKeyDictionary
from xml.parsers import expat  # nosemgrep: use-defused-xml -- declaration-rejecting prolog only
from xml.etree import ElementTree as _ET  # nosemgrep: use-defused-xml -- guarded by this module

Element = _ET.Element
SubElement = _ET.SubElement
Comment = _ET.Comment
ProcessingInstruction = _ET.ProcessingInstruction
XMLSyntaxError = _ET.ParseError
ParseError = _ET.ParseError
MAX_BYTES = 100 * 1024 * 1024
MAX_DEPTH = 256
MAX_NAMESPACE_WORK = 1000000
CHUNK_SIZE = 1024 * 1024
_namespaces = WeakKeyDictionary()
_encoding = re.compile(br'^\s*<\?xml\s[^?]*encoding\s*=\s*[\'"]([^\'"]+)[\'"]', re.I)


class ForbiddenDTD(ValueError):
    """A declaration was rejected before tree construction."""


class _RootReached(Exception):
    pass


def _reject(*args):
    raise ForbiddenDTD("XML DTD/entity declarations are not allowed")


def _root(*args):
    raise _RootReached()


def _prolog_parser():
    parser = expat.ParserCreate()  # nosemgrep: use-defused-xml -- stops at DTD or first element
    parser.StartDoctypeDeclHandler = _reject
    parser.EntityDeclHandler = _reject
    parser.ExternalEntityRefHandler = _reject
    parser.StartElementHandler = _root
    return parser


def _decode(data):
    if isinstance(data, str):
        return data
    if data.startswith((b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')):
        return data.decode('utf-32')
    match = _encoding.match(data)
    if match:
        name = match.group(1).decode('ascii')
        try:
            normalized = codecs.lookup(name).name
        except LookupError as exc:
            raise XMLSyntaxError('unknown XML encoding') from exc
        if normalized not in ('utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'ascii', 'iso8859-1'):
            return data.decode(name)
    return data


def sanitize_dtd(data):
    """Neutralize declarations/references for readers with that legacy policy.

    This is compatibility preprocessing, never the security boundary: the
    resulting bytes must still pass check_prolog before tree construction.
    """
    if data.startswith((b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')):
        text = data.decode('utf-32')
    elif data.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = data.decode('utf-16')
    elif data[:4] in (b'<\x00?\x00', b'<\x00!\x00'):
        text = data.decode('utf-16-le')
    elif data[:4] in (b'\x00<\x00?', b'\x00<\x00!'):
        text = data.decode('utf-16-be')
    else:
        text = None
    if text is not None:
        if '<!DOCTYPE' not in text.upper():
            return data
        text = re.sub(r'(<\?xml\s[^?]*encoding\s*=\s*)([\'"])[^\'"]+\2',
                      r'\1"UTF-8"', text, count=1, flags=re.I)
        data = text.encode('utf-8')
    if b'<!DOCTYPE' not in data.upper():
        return data
    data = re.sub(br'<!DOCTYPE\b[^[]*\[[\s\S]*?\]\s*>', b'', data, flags=re.I)
    data = re.sub(br'<!DOCTYPE\b[^>]*>', b'', data, flags=re.I)
    predefined = {b'amp', b'lt', b'gt', b'apos', b'quot'}
    return re.sub(br'&([A-Za-z_][A-Za-z0-9_.:-]*);',
                  lambda match: match[0] if match[1] in predefined else b'', data)


def check_prolog(data):
    parser = _prolog_parser()
    try:
        parser.Parse(data, True)
    except _RootReached:
        return
    except expat.ExpatError as exc:
        # Keep the reader's public diagnostic for non-XML package parts. This
        # is based on the XML prolog grammar, not a corpus filename or payload.
        if isinstance(data, bytes):
            if data.startswith((b'\xff\xfe', b'\xfe\xff')):
                text = data.decode('utf-16', errors='replace')
            elif data[:2] == b'<\x00':
                text = data.decode('utf-16-le', errors='replace')
            elif data[:2] == b'\x00<':
                text = data.decode('utf-16-be', errors='replace')
            else:
                text = data.decode('utf-8-sig', errors='replace')
        else:
            text = data
        stripped = text.lstrip(' \t\r\n')
        if stripped and not stripped.startswith('<'):
            prefix = text[:len(text) - len(stripped)]
            line = prefix.count('\n') + 1
            column = len(prefix.rsplit('\n', 1)[-1]) + 1
            raise XMLSyntaxError("Start tag expected, '<' not found, line %d, column %d (<string>, line %d)"
                                 % (line, column, line)) from exc
        raise XMLSyntaxError(str(exc)) from exc


class XMLParser:
    """Options for the single safe parser, retained at call sites for clarity."""
    def __init__(self, *, resolve_entities=False, load_dtd=False, no_network=True,
                 huge_tree=False, recover=False, remove_comments=False, remove_pis=False):
        if resolve_entities or load_dtd or not no_network:
            raise ValueError('unsafe XML parser options')
        self.max_depth = 2048 if huge_tree else MAX_DEPTH
        self.recover = recover
        self.remove_comments = remove_comments
        self.remove_pis = remove_pis


def parent_map(root):
    return {child: parent for parent in root.iter() for child in parent}


def ancestors(node, parents):
    node = parents.get(node)
    while node is not None:
        yield node
        node = parents.get(node)


def namespace_map(node):
    return _namespaces.get(node, {})


def map_namespaces(root, mapping):
    seen = set()
    for node in root.iter():
        scope = _namespaces.get(node)
        if scope is not None and id(scope) not in seen:
            seen.add(id(scope))
            for prefix, uri in list(scope.items()):
                scope[prefix] = mapping.get(uri, uri)


def itertext(root):
    # ElementTree.itertext includes comment/PI contents; XML text does not.
    stack = [(root, False)]
    while stack:
        node, tail = stack.pop()
        if tail:
            if node.tail:
                yield node.tail
        elif isinstance(node.tag, str):
            if node.text:
                yield node.text
            for child in reversed(node):
                stack.append((child, True))
                stack.append((child, False))


class QName:
    def __init__(self, node):
        tag = node if isinstance(node, str) else node.tag
        if tag.startswith('{'):
            self.namespace, self.localname = tag[1:].split('}', 1)
        else:
            self.namespace, self.localname = None, tag


def _check_depth(root, max_depth, truncate=False):
    stack = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        if depth >= max_depth and len(node):
            if not truncate:
                raise ValueError('XML depth limit exceeded')
            del node[:]
        else:
            stack.extend((child, depth + 1) for child in node)


def _parse_tree(data, options, namespaces, max_namespaces):
    builder = _ET.TreeBuilder(insert_comments=not options.remove_comments,
                              insert_pis=not options.remove_pis)
    parser = _ET.XMLParser(target=builder)  # nosemgrep: use-defused-xml -- prolog already rejected declarations
    if not namespaces and not options.recover:
        return _ET.fromstring(data, parser=parser)  # nosemgrep: use-defused-xml -- size/prolog guards precede this call
    pull = _ET.XMLPullParser(events=('start', 'end', 'start-ns'), _parser=parser)  # nosemgrep: use-defused-xml -- guarded input
    root = None
    scopes = []
    pending = {}
    count = 0
    scope_work = 0
    def tree_events():
        yield from pull.read_events()
        pull.close()
        yield from pull.read_events()

    try:
        pull.feed(data)
        for event, value in tree_events():
            if event == 'start-ns':
                count += 1
                if count > max_namespaces:
                    raise ValueError('package XML namespace limit exceeded')
                pending[value[0]] = value[1]
            elif event == 'start':
                if root is None:
                    root = value
                scope = scopes[-1] if scopes else {}
                if pending:
                    scope_work += len(scope) + len(pending)
                    if scope_work > max_namespaces:
                        raise ValueError('package XML namespace limit exceeded')
                    scope = dict(scope, **pending)
                    pending = {}
                scopes.append(scope)
                if namespaces:
                    _namespaces[value] = scope
            else:
                scopes.pop()
    except XMLSyntaxError:
        if not options.recover or root is None:
            raise
    return root


def fromstring(data, parser=None, *, max_bytes=MAX_BYTES, max_depth=None,
               namespaces=None, max_namespaces=1000000, recover=False, truncate=False):
    if len(data) > max_bytes:
        raise ValueError('XML size limit exceeded')
    data = _decode(data)
    if namespaces is None:
        namespaces = ('Requires' if isinstance(data, str) else b'Requires') in data
    check_prolog(data)
    options = parser or XMLParser(recover=recover)
    root = _parse_tree(data, options, namespaces, max_namespaces)
    if root is not None:
        _check_depth(root, options.max_depth if max_depth is None else max_depth, truncate)
    return root


def iterparse(source, events=('end',), tag=None, *, max_bytes=MAX_BYTES,
              max_depth=MAX_DEPTH, clear=False):
    """Pull events in >=1MiB chunks; optionally release completed selected nodes.

    The stream belongs to the caller. Prolog chunks are quarantined until the
    first element, so even a declaration crossing chunk boundaries is rejected.
    """
    guard = _prolog_parser()
    pending = []
    total = 0
    parser = _ET.XMLParser(target=_ET.TreeBuilder(insert_comments=True, insert_pis=True))  # nosemgrep: use-defused-xml -- input quarantined until prolog check
    pull = _ET.XMLPullParser(events=('start', 'end'), _parser=parser)  # nosemgrep: use-defused-xml -- each prolog guarded before feed
    stack = []
    decoder = None
    selected = (tag,) if isinstance(tag, str) else tag
    def drain():
        for event, node in pull.read_events():
            if event == 'start':
                stack.append(node)
                if len(stack) > max_depth:
                    raise ValueError('XML depth limit exceeded')
            matched = selected is None or node.tag in selected
            if matched and event in events:
                yield event, node
            if event == 'end':
                stack.pop()
                if clear and matched:
                    node.clear()
                    if stack:
                        stack[-1].remove(node)

    while True:
        chunk = source.read(CHUNK_SIZE)
        if not chunk:
            break
        first = total == 0
        if first and chunk.startswith(b'<?xml') and b'?>' not in chunk:
            declaration_chunks = [chunk]
            declaration_size = len(chunk)
            while b'?>' not in chunk:
                chunk = source.read(CHUNK_SIZE)
                if not chunk:
                    break
                declaration_size += len(chunk)
                if declaration_size > max_bytes:
                    raise ValueError('XML size limit exceeded')
                declaration_chunks.append(chunk)
            chunk = b''.join(declaration_chunks)
        total += len(chunk)
        if total > max_bytes:
            raise ValueError('XML size limit exceeded')
        if first:
            declaration = _encoding.match(chunk)
            if declaration:
                name = declaration.group(1).decode('ascii')
                try:
                    normalized = codecs.lookup(name).name
                except LookupError as exc:
                    raise XMLSyntaxError('unknown XML encoding') from exc
                if normalized not in ('utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'ascii', 'iso8859-1'):
                    decoder = codecs.getincrementaldecoder(name)()
        if decoder is not None:
            chunk = decoder.decode(chunk)
        if guard is not None:
            pending.append(chunk)
            try:
                guard.Parse(chunk, False)
                continue
            except _RootReached:
                guard = None
                chunk = ('' if decoder else b'').join(pending)
                pending.clear()
            except expat.ExpatError as exc:
                raise XMLSyntaxError(str(exc)) from exc
        pull.feed(chunk)
        yield from drain()
    if guard is not None:
        buffered = ('' if decoder else b'').join(pending)
        check_prolog(buffered)
        pull.feed(buffered)
    if decoder is not None:
        pull.feed(decoder.decode(b'', final=True))
    pull.close()
    yield from drain()


def parse(source, parser=None):
    data = source.read(MAX_BYTES + 1) if hasattr(source, 'read') else None
    if data is None:
        with open(source, 'rb') as stream:
            data = stream.read(MAX_BYTES + 1)
    return _ET.ElementTree(fromstring(data, parser))


def tostring(node, *args, **kwargs):
    return _ET.tostring(node, *args, **kwargs)


def XML(data):
    return fromstring(data)


def vml_fromstring(data):
    """Read VML strictly first, then extract only image references from HTML.

    Excel sometimes emits HTML void br elements inside a VML text box. The
    reader consumes only imagedata; reconstructing arbitrary broken XML would
    invent document structure. Namespace declarations still determine identity.
    """
    try:
        return fromstring(data)
    except XMLSyntaxError:
        pass
    if len(data) > MAX_BYTES:
        raise ValueError('XML size limit exceeded')
    data = _decode(data)
    check_prolog(data)
    if isinstance(data, bytes):
        data = data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    root = Element('xml')

    class Images(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.scopes = [({}, '')]
            self.count = 0
            self.namespace_work = 0

        def handle_starttag(self, tag, attrs):
            self.count += 1
            if self.count > 1000000:
                raise ValueError('XML element limit exceeded')
            scope = self.scopes[-1][0]
            declarations = {}
            for name, value in attrs:
                if name == 'xmlns':
                    declarations[''] = value
                elif name.startswith('xmlns:'):
                    declarations[name[6:]] = value
            if declarations:
                self.namespace_work += len(scope) + len(declarations)
                if self.namespace_work > MAX_NAMESPACE_WORK:
                    raise ValueError('XML namespace limit exceeded')
                scope = dict(scope, **declarations)

            def expanded(name):
                prefix, sep, local = name.partition(':')
                uri = scope.get(prefix if sep else '')
                return '{%s}%s' % (uri, local if sep else name) if uri else name

            if expanded(tag) == '{urn:schemas-microsoft-com:vml}imagedata':
                SubElement(root, expanded(tag), {expanded(k) if ':' in k else k: v or ''
                                                for k, v in attrs if not k.startswith('xmlns')})
            if tag not in ('br', 'hr', 'img', 'meta', 'link', 'input'):
                self.scopes.append((scope, tag))
                if len(self.scopes) > MAX_DEPTH:
                    raise ValueError('XML depth limit exceeded')

        def handle_endtag(self, tag):
            for index in range(len(self.scopes) - 1, 0, -1):
                if self.scopes[index][1] == tag:
                    del self.scopes[index:]
                    break

    parser = Images()
    parser.feed(data)
    parser.close()
    return root
