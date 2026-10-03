"""Bounded XML parsing, including hosts linked to expat before 2.4.

The prolog is checked with expat *before* ElementTree sees any input. Raising
from TreeBuilder.doctype alone does not stop the C parser's entity expansion.
No parser here installs a resource resolver or performs network/file I/O.
"""
import codecs
import re
from html import unescape
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
MAX_DTD_SUBSET_BYTES = 64 * 1024
MAX_VML_FALLBACK_BYTES = 8 * 1024 * 1024
_namespaces = WeakKeyDictionary()
_declared_uris = WeakKeyDictionary()
_encoding = re.compile(br'^\s*<\?xml\s[^?]*encoding\s*=\s*[\'"]([^\'"]+)[\'"]', re.I)
_dtd_delimiter = re.compile(br'[\[\]<>\'\"]')
_vml_tokens = re.compile(r'<!--.*?(?:-->|$)|<!\[CDATA\[.*?(?:\]\]>|$)|<\?.*?(?:\?>|$)|<(?:[^<>"\']|"[^"]*"|\'[^\']*\')*>', re.S)
_vml_attributes = re.compile(r'([^\s=/>]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))')
_vml_xmlns_attributes = re.compile(r'(?:^|\s)(xmlns(?::[^\s=/>]+)?)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))')
_expat_numbers = tuple(int(value) for value in re.findall(r'\d+', expat.EXPAT_VERSION)[:3])
EXPAT_BELOW_RECOMMENDED = _expat_numbers < (2, 4, 0)


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
        if normalized == 'utf-8' and name.lower() not in ('utf-8', 'utf_8'):
            return _encoding.sub(lambda m: m[0].replace(m[1], b'UTF-8'), data, count=1)
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
    # A single forward scan avoids retrying every incomplete declaration over
    # the same suffix. Quotes and the internal subset both protect '>'.
    upper = data.upper()
    chunks = []
    cursor = 0
    search = 0
    while True:
        start = upper.find(b'<!DOCTYPE', search)
        if start < 0:
            chunks.append(data[cursor:])
            break
        after = start + len(b'<!DOCTYPE')
        if after < len(data) and (65 <= upper[after] <= 90 or upper[after] == 95):
            search = after
            continue
        chunks.append(data[cursor:start])
        position = after
        subset = 0
        subset_start = None
        while position < len(data):
            match = _dtd_delimiter.search(data, position)
            if match is None:
                if subset_start is not None and len(data) - subset_start > MAX_DTD_SUBSET_BYTES:
                    raise ValueError('DTD internal subset limit exceeded')
                position = len(data)
                break
            position = match.start()
            if subset_start is not None and position - subset_start > MAX_DTD_SUBSET_BYTES:
                raise ValueError('DTD internal subset limit exceeded')
            char = data[position]
            if data.startswith(b'<!--', position):
                end = data.find(b'-->', position + 4)
                if end < 0:
                    if subset_start is not None and len(data) - subset_start > MAX_DTD_SUBSET_BYTES:
                        raise ValueError('DTD internal subset limit exceeded')
                    position = len(data)
                    break
                if subset_start is not None and end + 3 - subset_start > MAX_DTD_SUBSET_BYTES:
                    raise ValueError('DTD internal subset limit exceeded')
                position = end + 3
                continue
            if char in (34, 39):
                end = data.find(bytes((char,)), position + 1)
                if end < 0:
                    if subset_start is not None and len(data) - subset_start > MAX_DTD_SUBSET_BYTES:
                        raise ValueError('DTD internal subset limit exceeded')
                    position = len(data)
                    break
                if subset_start is not None and end + 1 - subset_start > MAX_DTD_SUBSET_BYTES:
                    raise ValueError('DTD internal subset limit exceeded')
                position = end + 1
                continue
            if char == 91:
                subset += 1
                if subset_start is None:
                    subset_start = position
            elif char == 93 and subset:
                subset -= 1
                if not subset:
                    subset_start = None
            elif char == 62 and not subset:
                position += 1
                break
            position += 1
        cursor = position
        search = cursor
        if cursor == len(data):
            break
    data = b''.join(chunks)
    predefined = {b'amp', b'lt', b'gt', b'apos', b'quot'}
    return re.sub(br'&([A-Za-z_][A-Za-z0-9_.:-]*);',
                  lambda match: match[0] if match[1] in predefined else b'', data)


def check_prolog(data):
    parser = _prolog_parser()
    try:
        parser.Parse(data, True)
    except _RootReached:
        return
    except LookupError as exc:
        raise XMLSyntaxError('unknown XML encoding') from exc
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


def namespace_uris(root):
    return _declared_uris.get(root, ()) if root is not None else ()


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


class _BoundedTree:
    """TreeBuilder target that checks limits before each node is allocated."""
    def __init__(self, options, namespaces, max_namespaces, max_depth, truncate):
        self.builder = _ET.TreeBuilder(insert_comments=not options.remove_comments,
                                       insert_pis=not options.remove_pis)
        self.data = self.builder.data
        self.comment = self.builder.comment
        self.pi = self.builder.pi
        self.close = self.builder.close
        self.namespaces = namespaces
        self.track_namespaces = bool(namespaces)
        self.max_namespaces = max_namespaces
        self.max_depth = max_depth * 8 if truncate else max_depth
        self.depth = 0
        self.greatest_depth = 0
        self.elements = 0
        self.declarations = 0
        self.uris = set()
        self.scope_work = 0
        self.scopes = [{}] if self.track_namespaces else None
        self.pending = {} if self.track_namespaces else None
        self.root = None

    def start_ns(self, prefix, uri):
        if uri is not None and '}' in uri:
            suffix = '; Expat 2.4.0 or newer is recommended' if EXPAT_BELOW_RECOMMENDED else ''
            raise ValueError('XML namespace URI contains a closing brace' + suffix)
        self.declarations += 1
        if uri:
            self.uris.add(uri)
        if self.declarations > self.max_namespaces:
            raise ValueError('package XML namespace limit exceeded')
        if self.track_namespaces:
            self.pending[prefix] = uri

    def start(self, tag, attrs):
        depth = self.depth + 1
        self.depth = depth
        if depth > self.greatest_depth:
            self.greatest_depth = depth
        self.elements += 1
        if depth > self.max_depth:
            raise ValueError('XML depth limit exceeded')
        if self.elements > 1000000:
            raise ValueError('XML element limit exceeded')
        if self.track_namespaces:
            scope = self.scopes[-1]
            declared = bool(self.pending)
            if declared:
                self.scope_work += len(scope) + len(self.pending)
                if self.scope_work > self.max_namespaces:
                    raise ValueError('package XML namespace limit exceeded')
                scope = dict(scope, **self.pending)
                self.pending.clear()
            self.scopes.append(scope)
        node = self.builder.start(tag, attrs)
        if self.root is None:
            self.root = node
        if self.namespaces is True or (self.namespaces == 'choices' and
                (self.root is node or declared or tag.endswith('}Choice'))):
            _namespaces[node] = scope
        return node

    def end(self, tag):
        node = self.builder.end(tag)
        if self.track_namespaces:
            self.scopes.pop()
        self.depth -= 1
        return node


def _parse_tree(data, options, namespaces, max_namespaces, max_depth, truncate):
    target = _BoundedTree(options, namespaces, max_namespaces, max_depth, truncate)
    parser = _ET.XMLParser(target=target)  # nosemgrep: use-defused-xml -- prolog rejected; target checks before allocation
    try:
        parser.feed(data)
        root = parser.close()
    except XMLSyntaxError:
        if not options.recover or target.root is None:
            raise
        root = target.root
    if root is not None and truncate and target.greatest_depth >= max_depth:
        _check_depth(root, max_depth, truncate=True)
    if root is not None and target.uris:
        _declared_uris[root] = frozenset(target.uris)
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
    depth = options.max_depth if max_depth is None else max_depth
    try:
        root = _parse_tree(data, options, namespaces, max_namespaces, depth, truncate)
    except LookupError as exc:
        raise XMLSyntaxError('unknown XML encoding') from exc
    return root


def iterparse(source, events=('end',), tag=None, *, max_bytes=MAX_BYTES,
              max_depth=MAX_DEPTH, clear=False, max_elements=1000000):
    """Pull events in >=1MiB chunks; optionally release completed selected nodes.

    The stream belongs to the caller. Prolog chunks are quarantined until the
    first element, so even a declaration crossing chunk boundaries is rejected.
    """
    guard = None
    pending = []
    total = 0
    parser = _ET.XMLParser(target=_ET.TreeBuilder(insert_comments=False, insert_pis=False))  # nosemgrep: use-defused-xml -- input quarantined until prolog check
    pull = _ET.XMLPullParser(events=('start', 'end', 'start-ns'), _parser=parser)  # nosemgrep: use-defused-xml -- each prolog guarded before feed
    stack = []
    elements = 0
    declarations = 0
    decoder = None
    selected = (tag,) if isinstance(tag, str) else tag
    def drain():
        nonlocal elements, declarations
        for event, node in pull.read_events():
            if event == 'start-ns':
                declarations += 1
                if declarations > MAX_NAMESPACE_WORK or (node[1] is not None and '}' in node[1]):
                    raise ValueError('XML namespace limit exceeded')
                continue
            if event == 'start':
                elements += 1
                if elements > max_elements:
                    raise ValueError('XML element limit exceeded')
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
                        del stack[-1][:]

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
        if first:
            guard = _prolog_parser()
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
            except LookupError as exc:
                raise XMLSyntaxError('unknown XML encoding') from exc
        pull.feed(chunk)
        yield from drain()
    if guard is not None:
        buffered = ('' if decoder else b'').join(pending)
        check_prolog(buffered)
        pull.feed(buffered)
    if decoder is not None:
        pull.feed(decoder.decode(b'', final=True))
    try:
        pull.close()
    except XMLSyntaxError:
        yield from drain()
        raise
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
    if len(data) > MAX_VML_FALLBACK_BYTES:
        raise ValueError('XML size limit exceeded')
    data = _decode(data)
    check_prolog(data)
    if isinstance(data, bytes):
        data = data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    root = Element('xml')

    scopes = [({}, '')]
    open_tags = {}
    count = 0
    namespace_work = 0
    for match in _vml_tokens.finditer(data):
        token = match.group()[1:-1].strip()
        if not token or token[0] in ('!', '?'):
            continue
        if token[0] == '/':
            tag = token[1:].strip().lower()
            positions = open_tags.get(tag)
            if positions:
                scope_index = positions[-1]
                for _, removed_tag in scopes[scope_index:]:
                    open_tags[removed_tag].pop()
                del scopes[scope_index:]
            continue
        self_closing = token.endswith('/')
        if self_closing:
            token = token[:-1].rstrip()
        parts = token.split(None, 1)
        tag = parts[0].lower() if parts else ''
        if not tag:
            continue
        count += 1
        if count > 1000000:
            raise ValueError('XML element limit exceeded')
        attrs = []
        attributes = _vml_attributes if tag.endswith('imagedata') else _vml_xmlns_attributes
        for attribute in attributes.finditer(parts[1] if len(parts) > 1 else ''):
            name = attribute.group(1).lower()
            attrs.append((name, unescape(next(value for value in attribute.groups()[1:] if value is not None))))
        scope = scopes[-1][0]
        declarations = {name[6:] if name.startswith('xmlns:') else '': value
                        for name, value in attrs if name == 'xmlns' or name.startswith('xmlns:')}
        if declarations:
            namespace_work += len(scope) + len(declarations)
            if namespace_work > MAX_NAMESPACE_WORK or any('}' in uri for uri in declarations.values()):
                raise ValueError('XML namespace limit exceeded')
            scope = dict(scope, **declarations)

        def expanded(name):
            prefix, sep, local = name.partition(':')
            uri = scope.get(prefix if sep else '')
            return '{%s}%s' % (uri, local if sep else name) if uri else name

        if expanded(tag) == '{urn:schemas-microsoft-com:vml}imagedata':
            SubElement(root, expanded(tag), {expanded(k) if ':' in k else k: value
                                            for k, value in attrs if not k.startswith('xmlns')})
        if not self_closing and tag not in ('br', 'hr', 'img', 'meta', 'link', 'input'):
            scopes.append((scope, tag))
            open_tags.setdefault(tag, []).append(len(scopes) - 1)
            if len(scopes) > MAX_DEPTH:
                raise ValueError('XML depth limit exceeded')
    return root
