"""Bounded, format-neutral OfficeArt records ([MS-ODRAW] 2.2/2.3).

Callers supply only the OfficeArt region, not an entire Word/BIFF stream.
Offsets are relative to the supplied buffer. Pass ``doc.errors`` as ``errors``
to retain warnings. No DOC/PPT/XLS interpretation or image model is imposed.
"""
import struct
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Limits:
    max_depth: int = 32
    max_records: int = 100000
    max_stream_bytes: int = 128 * 1024 * 1024
    max_record_bytes: int = 64 * 1024 * 1024
    max_image_bytes: int = 32 * 1024 * 1024
    max_total_image_bytes: int = 128 * 1024 * 1024


@dataclass(frozen=True)
class RecordHeader:
    rec_ver: int
    rec_instance: int
    rec_type: int
    rec_len: int


@dataclass
class Record:
    header: RecordHeader
    offset: int
    data: memoryview
    children: List['Record'] = field(default_factory=list)


@dataclass
class BlipEntry:
    index: int
    bt_win32: int = 0
    bt_macos: int = 0
    uid: bytes = b""
    size: int = 0
    c_ref: int = 0
    fo_delay: int = 0xFFFFFFFF
    cb_name: int = 0
    name: bytes = b""
    image: Optional[Tuple[str, bytes]] = None


@dataclass
class Property:
    id: int
    value: int
    is_blip_id: bool = False
    is_complex: bool = False
    data: bytes = b""


@dataclass
class Shape:
    spid: int = 0
    flags: int = 0
    shape_type: int = 0
    properties: Dict[int, Property] = field(default_factory=dict)
    property_tables: List[Dict[int, Property]] = field(default_factory=list)
    child_anchor: Optional[Tuple[int, int, int, int]] = None
    client_anchor: bytes = b""
    client_data: bytes = b""
    client_textbox: bytes = b""
    children: List['Shape'] = field(default_factory=list)
    record: Optional[Record] = None

    @property
    def is_group(self) -> bool:
        return bool(self.flags & 1)

    @property
    def is_child(self) -> bool:
        return bool(self.flags & 2)

    @property
    def is_patriarch(self) -> bool:
        return bool(self.flags & 4)

    def _value(self, prop_id: int) -> int:
        prop = self.properties.get(prop_id)
        return prop.value if prop and not prop.is_complex else 0

    def _text(self, prop_id: int) -> str:
        prop = self.properties.get(prop_id)
        if not prop or not prop.is_complex:
            return ""
        return prop.data.decode("utf-16le", errors="replace").rstrip("\x00")

    @property
    def pib(self) -> int:
        return self._value(0x0104)

    @property
    def name(self) -> str:
        return self._text(0x0380)

    @property
    def description(self) -> str:
        return self._text(0x0381)

    @property
    def textbox_id(self) -> int:
        return self._value(0x0080)


def _warn(errors, message):
    if errors is not None and len(errors) < 1000:
        message = "WARN: OfficeArt " + message
        if message not in errors:
            errors.append(message)


def parse_header(data, offset: int = 0) -> Optional[RecordHeader]:
    if offset < 0 or offset + 8 > len(data):
        return None
    options, kind, size = struct.unpack_from("<HHI", data, offset)
    return RecordHeader(options & 15, options >> 4, kind, size)


def parse_records(data, offset: int = 0, length: Optional[int] = None,
                  limits: Optional[Limits] = None, errors=None) -> List[Record]:
    """Parse complete records only; stop the affected container on damage.

    Payloads are zero-copy memoryviews, including containers. A single count
    budget covers the entire tree. Depth zero is the root record level.
    """
    limits = limits or Limits()
    length = len(data) - offset if length is None else length
    if offset < 0 or length < 0 or offset + length > len(data):
        _warn(errors, "invalid stream range")
        return []
    if length > limits.max_stream_bytes:
        _warn(errors, "stream byte limit exceeded")
        return []
    view = memoryview(data)
    remaining = [limits.max_records]

    def parse(start, end, depth):
        records = []
        while start < end:
            if remaining[0] <= 0:
                _warn(errors, "record count limit exceeded")
                break
            header = parse_header(view, start) if end - start >= 8 else None
            if header is None or header.rec_len > end - start - 8:
                _warn(errors, "truncated record at %d" % start)
                break
            if header.rec_len > limits.max_record_bytes:
                _warn(errors, "record byte limit exceeded at %d" % start)
                break
            stop = start + 8 + header.rec_len
            r = Record(header, start, view[start + 8:stop])
            records.append(r)
            remaining[0] -= 1
            if header.rec_ver == 15 and header.rec_len:
                if depth >= min(limits.max_depth, 64):
                    _warn(errors, "depth limit exceeded at %d" % start)
                else:
                    r.children = parse(start + 8, stop, depth + 1)
            start = stop
        return records

    return parse(offset, offset + length, 0)


def walk_records(records):
    """Yield records in preorder without recursive Python calls."""
    stack = list(reversed(records))
    while stack:
        record = stack.pop()
        yield record
        stack.extend(reversed(record.children))


# [MS-ODRAW] OfficeArtBlip* recInstance signatures; the next value has two UIDs.
_BLIPS = {
    0xF01A: ("emf", (0x3D4,), True),
    0xF01B: ("wmf", (0x216,), True),
    0xF01C: ("pict", (0x542,), True),
    0xF01D: ("jpg", (0x46A, 0x6E2), False),
    0xF01E: ("png", (0x6E0,), False),
    0xF01F: ("bmp", (0x7A8,), False),
    0xF029: ("tiff", (0x6E4,), False),
    0xF02A: ("jpg", (0x6E2,), False),
}


def _bmp(dib, errors):
    if len(dib) < 12:
        _warn(errors, "truncated DIB header")
        return None
    header_size = struct.unpack_from("<I", dib)[0]
    if header_size == 12:
        bpp = struct.unpack_from("<H", dib, 10)[0]
        palette_bytes = (1 << bpp) * 3 if bpp <= 8 else 0
        masks = 0
    elif 40 <= header_size <= len(dib):
        bpp = struct.unpack_from("<H", dib, 14)[0]
        compression = struct.unpack_from("<I", dib, 16)[0]
        used = struct.unpack_from("<I", dib, 32)[0]
        palette_bytes = (used or ((1 << bpp) if bpp <= 8 else 0)) * 4
        masks = (12 if compression == 3 else 16 if compression == 6 else 0) if header_size == 40 else 0
    else:
        _warn(errors, "invalid DIB header size")
        return None
    pixels = header_size + palette_bytes + masks
    if pixels > len(dib):
        _warn(errors, "truncated DIB palette or masks")
        return None
    return struct.pack("<2sIHHI", b"BM", 14 + len(dib), 0, 0, 14 + pixels) + bytes(dib)


def decode_blip(record: Record, limits: Optional[Limits] = None,
                errors=None) -> Optional[Tuple[str, bytes]]:
    """Return (model image_format, image bytes), or None with a warning.

    EMF/WMF/PICT return the metafile payload (no synthetic placeable WMF or
    Macintosh file header). DIB returns a BMP file suitable for Pillow/OCR.
    """
    limits = limits or Limits()
    info = _BLIPS.get(record.header.rec_type)
    if info is None:
        _warn(errors, "unsupported BLIP type")
        return None
    fmt, instances, metafile = info
    instance = record.header.rec_instance
    uid_count = next((1 + instance - base for base in instances if instance in (base, base + 1)), 0)
    if not uid_count:
        _warn(errors, "unsupported BLIP instance 0x%x" % instance)
        return None
    data = record.data
    offset = uid_count * 16
    if not metafile:
        offset += 1  # OfficeArtBlipBitmap tag follows all UIDs.
        if len(data) <= offset or len(data) - offset > limits.max_image_bytes:
            _warn(errors, "truncated or oversized bitmap BLIP")
            return None
        pixels = _bmp(data[offset:], errors) if fmt == "bmp" else bytes(data[offset:])
        if pixels is None or len(pixels) > limits.max_image_bytes:
            _warn(errors, "invalid or oversized bitmap output")
            return None
        return fmt, pixels
    if len(data) < offset + 34:
        _warn(errors, "truncated metafile header")
        return None
    # OfficeArtMetafileHeader: cbSize, rcBounds, ptSize, cbSave, compression, filter.
    size, = struct.unpack_from("<I", data, offset)
    saved, compression, filter_kind = struct.unpack_from("<IBB", data, offset + 28)
    offset += 34
    if size > limits.max_image_bytes or saved > limits.max_record_bytes or saved > len(data) - offset:
        _warn(errors, "metafile byte limit or truncated payload")
        return None
    packed = data[offset:offset + saved]
    if filter_kind != 254:
        _warn(errors, "unsupported metafile filter")
        return None
    if compression == 254:
        pixels = bytes(packed)
    elif compression == 0:
        try:
            inflater = zlib.decompressobj()
            pixels = inflater.decompress(packed, min(size, limits.max_image_bytes) + 1)
            if len(pixels) > size or inflater.unconsumed_tail or not inflater.eof:
                _warn(errors, "metafile inflate limit or incomplete deflate")
                return None
        except zlib.error:
            _warn(errors, "invalid metafile deflate")
            return None
    else:
        _warn(errors, "unsupported metafile compression")
        return None
    if len(pixels) != size:
        _warn(errors, "metafile decoded length mismatch")
        return None
    return fmt, pixels


def read_bstore(records, delayed_stream=None, limits: Optional[Limits] = None,
                errors=None) -> List[BlipEntry]:
    """Read FBSEs in BStore order, preserving failed entries and 1-based pib.

    delayed_stream is the caller-selected WordDocument/Pictures byte buffer.
    Embedded BLIPs take precedence. foDelay is relative to that buffer.
    """
    limits = limits or Limits()
    entries = []
    total = 0
    for store in walk_records(records):
        if store.header.rec_type != 0xF001:
            continue
        for r in store.children:
            if r.header.rec_type != 0xF007:
                continue
            if len(entries) >= limits.max_records:
                _warn(errors, "BStore count limit exceeded")
                return entries
            entry = BlipEntry(len(entries) + 1)
            entries.append(entry)
            if len(r.data) < 36:
                _warn(errors, "truncated FBSE")
                continue
            values = struct.unpack_from("<BB16sHIIIBBBB", r.data)
            (entry.bt_win32, entry.bt_macos, entry.uid, _tag, entry.size,
             entry.c_ref, entry.fo_delay, _usage, entry.cb_name, _unused2, _unused3) = values
            if entry.c_ref == 0 or entry.bt_win32 == 0:
                # Unused BStore slots still occupy a pib index but have no BLIP.
                continue
            offset = 36 + entry.cb_name
            if offset > len(r.data):
                _warn(errors, "truncated FBSE name")
                continue
            entry.name = bytes(r.data[36:offset])
            source = r.data
            if len(source) == offset:
                if delayed_stream is None or entry.fo_delay == 0xFFFFFFFF:
                    continue
                # Some PowerPoint writers leave the FBSE size hint at zero.
                # The referenced BLIP header supplies the bounded record length.
                source = delayed_stream
                offset = entry.fo_delay
            header = parse_header(source, offset)
            if (header is None or header.rec_len > len(source) - offset - 8
                    or header.rec_len > limits.max_record_bytes):
                _warn(errors, "invalid delayed or embedded BLIP")
                continue
            if total >= limits.max_total_image_bytes:
                _warn(errors, "total image byte limit exceeded")
                continue
            budget = Limits(max_image_bytes=min(limits.max_image_bytes, limits.max_total_image_bytes - total),
                            max_record_bytes=limits.max_record_bytes)
            image = decode_blip(Record(header, offset, memoryview(source)[offset + 8:offset + 8 + header.rec_len]),
                                limits=budget, errors=errors)
            if image is not None:
                entry.image = image
                total += len(image[1])
    return entries


def parse_properties(record: Record, errors=None) -> Dict[int, Property]:
    """Decode FOPT/secondary/tertiary fixed entries followed by complex data."""
    count = record.header.rec_instance
    fixed_size = count * 6
    if fixed_size > len(record.data):
        _warn(errors, "truncated FOPT fixed table")
        return {}
    properties = {}
    offset = fixed_size
    for i in range(count):
        opid, value = struct.unpack_from("<HI", record.data, i * 6)
        prop = Property(opid & 0x3FFF, value, bool(opid & 0x4000), bool(opid & 0x8000))
        if prop.is_complex:
            if value > len(record.data) - offset:
                _warn(errors, "truncated FOPT complex data")
                break  # Never assign later bytes to a different property.
            prop.data = bytes(record.data[offset:offset + value])
            offset += value
        properties[prop.id] = prop
    return properties


def read_shapes(records, errors=None) -> List[Shape]:
    """Return shapes with Spgr nesting. Keep raw format-specific client atoms.

    The first SpContainer in a SpgrContainer is the group shape; subsequent
    shape/group containers become its children. FOPT tables remain separately
    available; the convenience property map applies later table overrides.
    """
    def shape_from_record(r):
        shape = Shape(record=r)
        for atom in r.children:
            kind = atom.header.rec_type
            if kind == 0xF00A:
                if len(atom.data) < 8:
                    _warn(errors, "truncated FSP")
                    continue
                shape.spid, shape.flags = struct.unpack_from("<II", atom.data)
                shape.shape_type = atom.header.rec_instance
            elif kind in (0xF00B, 0xF121, 0xF122):
                props = parse_properties(atom, errors)
                shape.property_tables.append(props)
                shape.properties.update(props)
            elif kind == 0xF00F:
                if len(atom.data) >= 16:
                    shape.child_anchor = struct.unpack_from("<4i", atom.data)
                else:
                    _warn(errors, "truncated child anchor")
            elif kind == 0xF010:
                shape.client_anchor = bytes(atom.data)
            elif kind == 0xF011:
                shape.client_data = bytes(atom.data)
            elif kind == 0xF00D:
                shape.client_textbox = bytes(atom.data)
        return shape

    def collect(nodes, depth=0):
        if depth > 64:
            _warn(errors, "shape depth limit exceeded")
            return []
        result = []
        for r in nodes:
            if r.header.rec_type == 0xF004:
                result.append(shape_from_record(r))
            elif r.header.rec_type == 0xF003:
                shapes = collect(r.children, depth + 1)
                if shapes and shapes[0].is_group:
                    shapes[0].children.extend(shapes[1:])
                    result.append(shapes[0])
                else:
                    result.extend(shapes)
            else:
                result.extend(collect(r.children, depth + 1))
        return result

    return collect(records)
