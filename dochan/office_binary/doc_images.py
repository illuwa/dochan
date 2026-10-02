"""Native [MS-DOC] PICFAndOfficeArtData and OfficeArtContent pictures.

CP anchors come from PlcfSpa; image payloads and description properties are
interpreted by the shared, bounded [MS-ODRAW] decoder. No stream scanning or
signature guessing is used to associate a picture with a character.
"""
import struct
from dataclasses import replace
from typing import Optional

from ..conversion import AssetRef, Provenance
from ..model.image import Image
from .officeart import (Limits, Record, RecordHeader, parse_header, parse_records,
                        read_bstore, read_shapes)

_MAX_PICTURES = 10000
_MIME = {'png': 'image/png', 'jpg': 'image/jpeg', 'bmp': 'image/bmp',
         'tiff': 'image/tiff', 'emf': 'image/x-emf', 'wmf': 'image/x-wmf',
         'pict': 'image/x-pict'}


class DocImages:
    """Resolve one image placement without changing the document's reading order.

    ``image_at`` returns an Image for a special 0x01/0x08 character, or None.
    The caller inserts that Image in its CP-ordered element stream. AssetRef
    entries are deduplicated, while repeated image placements stay distinct.
    """
    def __init__(self, binary, doc):
        self.binary = binary
        self.doc = doc
        self.limits = Limits()
        self._inline = {}
        self._assets = {}
        self._total = 0
        self._decoded_total = 0
        self._shapes = {}
        self._anchors = {}
        self._entries = []
        self._read_drawings()
        self._read_anchors(40, 0)
        header_start = getattr(binary, 'stories', {}).get('header', (0, 0))[0]
        self._read_anchors(41, header_start)

    def _warn(self, message):
        warning = 'WARN: DOC image ' + message
        if len(self.doc.errors) < 1000 and warning not in self.doc.errors:
            self.doc.errors.append(warning)

    def _read_drawings(self):
        data = self.binary.blob(50)  # FibRgFcLcb97.fcDggInfo
        if not data:
            return
        if len(data) > self.limits.max_stream_bytes:
            self._warn('OfficeArtContent size limit exceeded')
            return
        offset = 0
        records = []
        # OfficeArtContent = DggContainer, followed by up to two
        # OfficeArtWordDrawing entries (one byte dgglbl then DgContainer).
        for drawing_index in range(3):
            if offset >= len(data):
                break
            if drawing_index:
                label = data[offset]
                offset += 1
                if label not in (0, 1):
                    self._warn('invalid OfficeArt drawing label')
                    break
            header = parse_header(data, offset)
            expected = 0xf000 if drawing_index == 0 else 0xf002
            if (header is None or header.rec_type != expected or header.rec_ver != 15
                    or header.rec_len > len(data) - offset - 8):
                self._warn('truncated or invalid OfficeArtContent')
                break
            records.extend(parse_records(data, offset, header.rec_len + 8,
                                         self.limits, self.doc.errors))
            offset += header.rec_len + 8
        if offset < len(data):
            self._warn('unparsed OfficeArtContent tail')
        self._entries = read_bstore(records, delayed_stream=self.binary.word,
                                    limits=self.limits, errors=self.doc.errors)
        self._decoded_total = sum(len(entry.image[1]) for entry in self._entries if entry.image)
        stack = read_shapes(records, self.doc.errors)
        while stack and len(self._shapes) < _MAX_PICTURES:
            shape = stack.pop()
            self._shapes[shape.spid] = shape
            stack.extend(shape.children)
        if stack:
            self._warn('shape count limit exceeded')

    def _read_anchors(self, index, start):
        data = self.binary.blob(index)
        if not data:
            return
        # PlcfSpa: (n+1) CPs, n 26-byte SPA records. SPA starts with spid.
        if len(data) < 4 or (len(data) - 4) % 30:
            self._warn('invalid PlcfSpa size')
            return
        count = (len(data) - 4) // 30
        if count > _MAX_PICTURES:
            self._warn('PlcfSpa count limit exceeded')
            return
        previous = -1
        for i in range(count):
            cp, = struct.unpack_from('<I', data, i * 4)
            next_cp, = struct.unpack_from('<I', data, (i + 1) * 4)
            if cp < previous or cp > next_cp:
                self._warn('invalid PlcfSpa CP order')
                break
            previous = cp
            spid, = struct.unpack_from('<I', data, (count + 1) * 4 + i * 26)
            self._anchors[start + cp] = spid

    def _inline_picture(self, location):
        if location in self._inline:
            return self._inline[location]
        if len(self._inline) >= _MAX_PICTURES:
            self._warn('PICF count limit exceeded')
            return None
        self._inline[location] = None
        data = self.binary.data
        if location < 0 or location + 8 > len(data):
            self._warn('PICF location outside Data stream')
            return None
        size, header_size, mapping_mode = struct.unpack_from('<IHH', data, location)
        if (header_size < 68 or header_size > size or size > len(data) - location
                or size > self.limits.max_record_bytes):
            self._warn('truncated or oversized PICF')
            return None
        if mapping_mode not in (0x64, 0x66):
            # Other PICF variants can be OLE objects rather than pictures.
            return None
        begin, end = location + header_size, location + size
        if mapping_mode == 0x66:
            if begin >= end or data[begin] > end - begin - 1:
                self._warn('truncated PICF picture name')
                return None
            begin += data[begin] + 1
        remaining = self.limits.max_total_image_bytes - self._decoded_total
        if remaining <= 0:
            self._warn('total decoded image byte limit exceeded')
            return None
        budget = replace(self.limits, max_total_image_bytes=remaining,
                         max_image_bytes=min(remaining, self.limits.max_image_bytes))
        records = parse_records(data, begin, end - begin, self.limits, self.doc.errors)
        shapes = read_shapes(records, self.doc.errors)
        # Inline PICF stores FBSE directly after its SpContainer, without a
        # BStore container. Wrap parsed records, preserving their real bytes.
        entries = read_bstore([Record(RecordHeader(15, 0, 0xf001, 0), begin,
                                      memoryview(b''), records)],
                              limits=budget, errors=self.doc.errors)
        self._decoded_total += sum(len(entry.image[1]) for entry in entries if entry.image)
        picture = next((entry.image for entry in entries if entry.image), None)
        description = next((shape.description for shape in shapes if shape.description), '')
        if picture is None and shapes:
            pib = shapes[0].pib
            if 0 < pib <= len(self._entries):
                picture = self._entries[pib - 1].image
        if picture is not None:
            self._inline[location] = (picture, description)
        return self._inline[location]

    def textbox_at(self, cp: int) -> Optional[int]:
        """Return the zero-based PlcftxbxTxt index at a floating shape anchor.

        [MS-DOC] OfficeArt textId uses a one-based textbox index in its high
        16 bits; low bits identify the linked textbox sequence.
        """
        shape = self._shapes.get(self._anchors.get(cp))
        if shape is None:
            return None
        index = shape.textbox_id >> 16
        return index - 1 if index else None

    def image_at(self, cp: int, props=None) -> Optional[Image]:
        if cp < 0 or cp >= len(self.binary.text):
            return None
        marker = self.binary.text[cp]
        if marker not in ('\x01', '\x08'):
            return None
        props = self.binary.char_props(cp) if props is None else props
        if not props.get('special', False):
            return None
        if marker == '\x01':
            location = props.get('pic_location')
            if not isinstance(location, int):
                return None
            result = self._inline_picture(location)
            if result is None:
                return None
            picture, description = result
            key = ('inline', location)
        else:
            shape = self._shapes.get(self._anchors.get(cp))
            if shape is None or not 0 < shape.pib <= len(self._entries):
                return None
            picture = self._entries[shape.pib - 1].image
            if picture is None:
                return None
            description = shape.description
            key = ('floating', shape.pib)
        fmt, payload = picture
        if key not in self._assets:
            if (len(self._assets) >= _MAX_PICTURES
                    or self._total + len(payload) > self.limits.max_total_image_bytes):
                self._warn('total image byte or count limit exceeded')
                return None
            self._total += len(payload)
            number = len(self._assets) + 1
            filename = 'image%d.%s' % (number, fmt)
            source = 'doc/images/' + filename
            self._assets[key] = (number, filename, source)
            self.doc.assets.append(AssetRef(id='doc-image-%d' % number,
                source_path=source, filename=filename, content_type=_MIME.get(fmt, 'application/octet-stream'),
                metadata={'kind': 'image', 'label': description, 'missing': False, 'source_format': 'doc'}))
        number, filename, source = self._assets[key]
        return Image(bin_id=number, filename=filename, image_data=payload, image_format=fmt,
                     alt_text=description, provenance=Provenance(source_format='doc', path=source))
