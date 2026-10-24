"""Recover consecutive local records, per PKWARE APPNOTE 4.3.7–4.3.16.

Only the directory is reconstructed: local bytes are never recompressed or
searched for signatures. A recovered archive needs a separate body proof.
"""
from io import BytesIO
import os
import posixpath
import re
import struct
from urllib.parse import unquote, urlsplit
import zipfile
import zlib

from ..ooxml.package import (
    MAX_ARCHIVE_ENTRIES, MAX_ARCHIVE_UNCOMPRESSED_SIZE, MAX_COMPRESSION_RATIO,
    MAX_PART_SIZE, MAX_XML_ELEMENTS, MAX_XML_PART_SIZE, _validate_part_name,
)
from . import safe_xml as etree

MAX_INPUT_SIZE = 512 * 1024 * 1024
_CHUNK = 64 * 1024
_LOCAL = struct.Struct('<4s5H3I2H')
_CENTRAL = struct.Struct('<4s6H3I5H2I')
_END = struct.Struct('<4s4H2IH')
_NO_BODY = 'ERR: 손상된 ZIP 문서 — 중앙 디렉터리가 없고 본문 부품을 찾지 못함'
_OPTIONAL_TYPES = {
    'image', 'audio', 'video', 'media', 'oleObject', 'package', 'embeddedPackage',
    'thumbnail', 'core-properties', 'extended-properties', 'custom-properties',
    'extendedProperties', 'customProperties',
    'presProps', 'viewProps', 'tags',
}
_REL_NS = {
    'http://schemas.openxmlformats.org/package/2006/relationships',
    'http://purl.oclc.org/ooxml/package/relationships',
}


class ZipSalvageError(ValueError):
    def __init__(self, message, diagnostics=()):
        super().__init__(message)
        self.diagnostics = list(diagnostics)
        if message not in self.diagnostics:
            self.diagnostics.append(message)


def _extra_is_safe(extra):
    offset = 0
    while offset < len(extra):
        if offset + 4 > len(extra):
            return False
        tag, size = struct.unpack_from('<HH', extra, offset)
        offset += 4 + size
        if tag == 1 or offset > len(extra):  # ZIP64 needs its own directory.
            return False
    return True


def _inflate_end(data, start, budget):
    """Find raw DEFLATE EOF without retaining the expanded member."""
    inflater = zlib.decompressobj(-15)
    offset, size, crc = start, 0, 0
    while offset < len(data):
        chunk = data[offset:offset + _CHUNK]
        out = inflater.decompress(chunk, min(_CHUNK, budget - size + 1))
        size += len(out)
        if size > budget:
            return None
        crc = zlib.crc32(out, crc)
        if inflater.eof:
            offset += len(chunk) - len(inflater.unused_data)
            return offset, size, crc & 0xffffffff
        consumed = len(chunk) - len(inflater.unconsumed_tail)
        if not consumed and not out:
            return None
        offset += consumed
    return None


def _descriptor(data, offset, crc, compressed, size):
    # Both signed and unsigned descriptors are permitted by APPNOTE 4.3.9.
    starts = [offset + 4, offset] if data[offset:offset + 4] == b'PK\x07\x08' else [offset]
    for start in starts:
        if start + 12 <= len(data):
            actual = struct.unpack_from('<III', data, start)
            if actual == (crc, compressed, size):
                return start + 12
    return None


def salvage_zip(data):
    """Return rebuilt ZIP bytes, or None if no complete local member remains.

    A bad/unsupported member stops the walk. Duplicate canonical names keep
    their first directory entry, but all encountered records consume budgets.
    """
    if len(data) > MAX_INPUT_SIZE or not data.startswith(b'PK\x03\x04'):
        return None
    offset, count, total = 0, 0, 0
    entries, seen = [], set()
    while offset + _LOCAL.size <= len(data) and count < MAX_ARCHIVE_ENTRIES:
        fields = _LOCAL.unpack_from(data, offset)
        signature, version, flags, method, mtime, mdate, crc, compressed, size, nlen, xlen = fields
        if (signature != b'PK\x03\x04' or version >= 45 or flags & (1 | 0x40 | 0x2000)
                or method not in (0, 8) or compressed == 0xffffffff or size == 0xffffffff):
            break
        start = offset + _LOCAL.size + nlen + xlen
        if not nlen or start > len(data):
            break
        name_bytes = data[offset + _LOCAL.size:offset + _LOCAL.size + nlen]
        extra = data[offset + _LOCAL.size + nlen:start]
        try:
            name = name_bytes.decode('utf-8' if flags & 0x800 else 'cp437')
            normalized = _validate_part_name(name)
            if normalized == '.' or '\0' in name or not _extra_is_safe(extra):
                break
        except (UnicodeError, ValueError):
            break
        if size > MAX_PART_SIZE or total + size > MAX_ARCHIVE_UNCOMPRESSED_SIZE:
            break
        end = start + compressed
        if flags & 8:
            if method == 8:
                try:
                    result = _inflate_end(data, start, min(MAX_PART_SIZE, MAX_ARCHIVE_UNCOMPRESSED_SIZE - total))
                except zlib.error:
                    break
                if result is None:
                    break
                end, actual_size, actual_crc = result
                actual_compressed = end - start
                if ((compressed and compressed != actual_compressed)
                        or (size and size != actual_size) or (crc and crc != actual_crc)):
                    break
                compressed, size, crc = actual_compressed, actual_size, actual_crc
            elif not compressed or end > len(data) or size != compressed:
                # A size-less stored stream has no EOF marker. Do not search
                # its payload for a plausible descriptor/signature.
                break
            next_offset = _descriptor(data, end, crc, compressed, size)
            if next_offset is None:
                break
        else:
            if end > len(data) or (method == 0 and compressed != size):
                break
            next_offset = end
        if (size > MAX_PART_SIZE or total + size > MAX_ARCHIVE_UNCOMPRESSED_SIZE
                or (compressed == 0 and size > 0)
                or (compressed and size / compressed > MAX_COMPRESSION_RATIO)):
            break
        count += 1
        total += size
        if normalized not in seen:
            seen.add(normalized)
            central = _CENTRAL.pack(b'PK\x01\x02', 20, version, flags, method, mtime, mdate,
                                    crc, compressed, size, nlen, xlen, 0, 0, 0, 0, offset)
            entries.append(central + name_bytes + extra)
        offset = next_offset
    if not entries:
        return None
    directory = b''.join(entries)
    return (data[:offset] + directory + _END.pack(b'PK\x05\x06', 0, 0, len(entries),
                                                len(entries), len(directory), offset, 0))


def _append(errors, message):
    if errors is not None and message not in errors:
        errors.append(message)


def _read_input(source):
    if isinstance(source, (str, bytes, os.PathLike)):
        with open(source, 'rb') as stream:
            if os.fstat(stream.fileno()).st_size > MAX_INPUT_SIZE:
                return b''
            return stream.read(MAX_INPUT_SIZE + 1)
    position = source.tell()
    try:
        source.seek(0, 2)
        if source.tell() > MAX_INPUT_SIZE:
            return b''
        source.seek(0)
        return source.read(MAX_INPUT_SIZE + 1)
    finally:
        source.seek(position)


def _signature(source):
    if isinstance(source, (str, bytes, os.PathLike)):
        with open(source, 'rb') as stream:
            return stream.read(4)
    position = source.tell()
    try:
        source.seek(0)
        return source.read(4)
    finally:
        source.seek(position)


def open_document_zip(source, errors=None, kind=None):
    """Open normally; only BadZipFile and a local signature enable recovery.

    kind=None is detection only. Parsers must pass 'ooxml' or 'hwpx' so an
    incomplete body cannot enter their normal output path.
    """
    try:
        archive = zipfile.ZipFile(source, 'r')
    except zipfile.BadZipFile:
        if _signature(source) != b'PK\x03\x04':
            raise
        data = _read_input(source)
        rebuilt = salvage_zip(data)
        if rebuilt is None:
            warning = 'WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 0개를 복구함'
            _append(errors, warning)
            raise ZipSalvageError(_NO_BODY, [warning]) from None
        buffer = BytesIO(rebuilt)
        archive = zipfile.ZipFile(buffer, 'r')
        buffer._zip_salvage_count = len(archive.filelist)
    count = getattr(archive.fp, '_zip_salvage_count', None)
    archive._zip_salvage_count = count
    if count is not None:
        warning = f'WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 {count}개를 복구함'
        _append(errors, warning)
        if kind is not None:
            try:
                _prove_body(archive, kind)
            except Exception as exc:
                archive.close()
                reason = str(exc).replace('\r', ' ').replace('\n', ' ')[:384]
                message = f'ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음({reason})'
                _append(errors, message)
                raise ZipSalvageError(message, [warning]) from exc
    return archive


def _part_map(archive):
    return {_validate_part_name(info.filename): info.filename for info in archive.infolist()}


def _verify_deflate(archive, info):
    """ZipExtFile can stop at declared length before raw DEFLATE EOF.

    Verify exact compressed extent, decoded length and CRC with bounded
    chunks as well, so a missing terminator or forged length cannot pass.
    """
    stream = archive.fp
    with archive._lock:
        position = stream.tell()
        try:
            stream.seek(info.header_offset)
            header = stream.read(_LOCAL.size)
            fields = _LOCAL.unpack(header)
            stream.seek(fields[-2] + fields[-1], 1)
            inflater = zlib.decompressobj(-15)
            remaining, size, crc, pending = info.compress_size, 0, 0, b''
            while remaining or pending:
                if pending:
                    chunk, pending = pending, b''
                else:
                    chunk = stream.read(min(_CHUNK, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                out = inflater.decompress(chunk, min(_CHUNK, info.file_size - size + 1))
                size += len(out)
                crc = zlib.crc32(out, crc)
                if size > info.file_size:
                    raise ValueError(info.filename + ': deflate decoded size mismatch')
                if inflater.eof:
                    if remaining or inflater.unused_data or size != info.file_size or crc != info.CRC:
                        raise ValueError(info.filename + ': deflate extent/size/CRC mismatch')
                    return
                pending = inflater.unconsumed_tail
                if len(pending) == len(chunk) and not out:
                    break
            raise ValueError(info.filename + ': deflate EOF missing')
        finally:
            stream.seek(position)


def _checked_part(archive, names, name, *, xml=False, max_size=None):
    """Verify CRC and actual length by streaming; retain only small XML."""
    info = archive.getinfo(names[name])
    limit = MAX_XML_PART_SIZE if xml else MAX_PART_SIZE
    if max_size is not None:
        limit = min(limit, max_size)
    if info.file_size > limit or (info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO):
        raise ValueError(name + ': size/compression limit')
    if info.compress_type == 8:
        _verify_deflate(archive, info)
    chunks, size, crc, refs, tail = [], 0, 0, False, b''
    # ZIP's CRC covers decoded bytes. Checking the stream to EOF is mandatory
    # even for parts the downstream reader does not itself render.
    with archive.open(info) as stream:
        while True:
            chunk = stream.read(min(_CHUNK, limit - size + 1))
            if not chunk:
                break
            size += len(chunk)
            crc = zlib.crc32(chunk, crc)
            if size > limit:
                raise ValueError(name + ': expanded size limit')
            if xml:
                chunks.append(chunk)
            elif name.endswith(('.xml', '.vml')):
                # Retain only a small boundary window, including UTF-16's
                # ASCII bytes. A possible relationship attribute requires
                # its .rels; false positives fail closed on damaged input.
                scan = tail + chunk.replace(b'\0', b'')
                refs = refs or bool(re.search(rb':(?:id|embed|link|relid)\b', scan))
                tail = scan[-256:]
    if size != info.file_size or crc != info.CRC:
        raise ValueError(name + ': decoded size/CRC mismatch')
    if xml:
        data = b''.join(chunks)
        if data.count(b'<') > MAX_XML_ELEMENTS:
            raise ValueError(name + ': XML element limit')
        return etree.fromstring(data, max_bytes=limit, max_depth=2048)
    return refs


def _relationships(archive, names, name):
    root = _checked_part(archive, names, name, xml=True)
    if root.tag not in {'{' + ns + '}Relationships' for ns in _REL_NS}:
        raise ValueError(name + ': invalid relationship root')
    return [node for node in root if node.tag in {'{' + ns + '}Relationship' for ns in _REL_NS}]


def _target(part, target):
    decoded = unquote(target.replace('\\', '/'))
    parsed = urlsplit(decoded)
    if (not decoded or parsed.scheme or parsed.netloc or any(ord(c) < 32 for c in decoded)):
        raise ValueError('unsafe relationship target')
    path = parsed.path
    resolved = posixpath.normpath(path.lstrip('/') if path.startswith('/')
                                 else posixpath.join(posixpath.dirname(part), path))
    return _validate_part_name(resolved)


def _rels_name(part):
    return posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')


def _optional_relationship(node):
    kind = node.get('Type', '')
    recognized = kind.startswith((
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships/',
        'http://schemas.openxmlformats.org/package/2006/relationships/',
        'http://purl.oclc.org/ooxml/officeDocument/relationships/',
        'http://purl.oclc.org/ooxml/package/relationships/',
        'http://schemas.microsoft.com/office/',
    ))
    return recognized and kind.rsplit('/', 1)[-1] in _OPTIONAL_TYPES


def _has_relationship_refs(archive, names, part):
    namespaces = (
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
        'http://purl.oclc.org/ooxml/officeDocument/relationships',
    )
    keys = {'{' + ns + '}' + attr for ns in namespaces for attr in ('id', 'embed', 'link')}
    keys.add('{urn:schemas-microsoft-com:office:office}relid')
    with archive.open(names[part]) as stream:
        for _event, node in etree.iterparse(stream, max_bytes=MAX_PART_SIZE,
                                           max_depth=2048, max_elements=MAX_XML_ELEMENTS, clear=True):
            if any(key in node.attrib for key in keys):
                return True
    return False


def _prove_hwpx(archive, names):
    from ..hwpx.parser import MAX_SECTION_COUNT, MAX_SECTION_XML_SIZE

    header = _checked_part(archive, names, 'Contents/header.xml', xml=True)
    raw_count = header.get('secCnt', '')
    if not re.fullmatch(r'[0-9]{1,4}', raw_count):
        raise ValueError('Contents/header.xml: invalid secCnt')
    count = int(raw_count)
    if not 1 <= count <= MAX_SECTION_COUNT:
        raise ValueError('Contents/header.xml: secCnt limit')
    sections = {f'Contents/section{index}.xml' for index in range(count)}
    sections.update(name for name in names if re.fullmatch(r'Contents/section[0-9]+\.xml', name))
    if len(sections) > MAX_SECTION_COUNT:
        raise ValueError('HWPX section count limit')
    if 'META-INF/container.xml' in names:
        container = _checked_part(archive, names, 'META-INF/container.xml', xml=True)
        for node in container.iter():
            path = node.get('full-path')
            if path:
                _checked_part(archive, names, _validate_part_name(path))
    manifest = next((name for name in ('Contents/content.hpf', 'content.hpf') if name in names), None)
    if manifest:
        root = _checked_part(archive, names, manifest, xml=True)
        for node in root.iter():
            href = node.get('href', '')
            if not href or not href.endswith('.xml'):
                continue
            candidates = [_validate_part_name(href), _target(manifest, href)]
            target = next((name for name in candidates if name in names), candidates[0])
            if 'section' in target.lower():
                sections.add(target)
            elif target.startswith('Chart/'):
                _checked_part(archive, names, target, xml=True)
    else:
        ordered = [f'Contents/section{index}.xml' for index in range(count)]
        if sorted(ordered) != ordered:
            # Existing fallback sorts names lexically. The manifest is needed
            # to preserve reading order once the two orders differ.
            raise ValueError('Contents/content.hpf: section reading order unproven')
    charts = set()
    for section in sections:
        _checked_part(archive, names, section, max_size=MAX_SECTION_XML_SIZE)
        with archive.open(names[section]) as stream:
            for _event, node in etree.iterparse(stream, max_bytes=MAX_SECTION_XML_SIZE,
                                               max_depth=2048, max_elements=MAX_XML_ELEMENTS, clear=True):
                chart = node.get('chartIDRef', '')
                if chart:
                    charts.add(_validate_part_name(chart))
                    if len(charts) > MAX_ARCHIVE_ENTRIES:
                        raise ValueError('HWPX chart reference limit')
    for chart in charts:
        _checked_part(archive, names, chart, xml=True)


def _prove_body(archive, kind):
    names = _part_map(archive)
    if kind == 'hwpx':
        _prove_hwpx(archive, names)
        return
    relationships = _relationships(archive, names, '_rels/.rels')
    main = [node for node in relationships if node.get('Type', '').rsplit('/', 1)[-1] == 'officeDocument'
            and node.get('TargetMode', '') != 'External']
    if len(main) != 1:
        raise ValueError('_rels/.rels: main document relationship not found or ambiguous')
    main_part = _target('', main[0].get('Target', ''))
    queue = [main_part]
    scheduled = {main_part}

    def enqueue(target):
        if target not in names:
            raise ValueError(target)
        if target not in scheduled:
            scheduled.add(target)
            queue.append(target)
    # Root non-property relationships (e.g. digital signatures) must also be
    # present; external and opaque optional assets never become body parts.
    for node in relationships:
        if (node.get('TargetMode', '') != 'External'
                and not _optional_relationship(node)):
            enqueue(_target('', node.get('Target', '')))
    visited = set()
    while queue:
        part = queue.pop()
        if part in visited:
            continue
        visited.add(part)
        if len(visited) > MAX_ARCHIVE_ENTRIES:
            raise ValueError('relationship graph entry limit')
        refs = _checked_part(archive, names, part)
        rels = _rels_name(part)
        if rels not in names:
            if part == main_part or (refs and _has_relationship_refs(archive, names, part)):
                raise ValueError(rels)
            continue
        for node in _relationships(archive, names, rels):
            if (node.get('TargetMode', '') == 'External'
                    or _optional_relationship(node)):
                continue
            enqueue(_target(part, node.get('Target', '')))
