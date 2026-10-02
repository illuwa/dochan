"""BIFF8 OfficeArt image placements ([MS-XLS] MsoDrawing/OfficeArtClientAnchor).

Workbook MsoDrawingGroup supplies the one-based BLIP store. Sheet drawing
fragments are interspersed with OBJ and TXO records; only drawing CONTINUE
payloads belong to OfficeArt. Image bytes use the common bounded decoder.
"""
import struct
from typing import List, Optional

from .officeart import Limits, parse_records, read_bstore, read_shapes
from ..conversion import AssetRef, Provenance
from ..model.document import Paragraph, TextRun
from ..model.image import Image


def _warn(errors, message):
    message = 'WARN: XLS drawing ' + message
    if len(errors) < 1000 and message not in errors:
        errors.append(message)


def _drawing_bytes(data, record_kind, limits, errors):
    """Collect one BIFF substream, excluding nested chart substreams."""
    offset, depth, count, total = 0, 0, 0, 0
    chunks = []
    continuing = False
    text_chars, text_runs = 0, 0
    while offset + 4 <= len(data):
        kind, size = struct.unpack_from('<HH', data, offset)
        offset += 4
        count += 1
        if count > limits.max_records:
            _warn(errors, 'BIFF record count limit exceeded')
            break
        if size > len(data) - offset:
            _warn(errors, 'truncated BIFF record')
            break
        payload = memoryview(data)[offset:offset + size]
        offset += size
        if kind in (0x0809, 0x0409, 0x0209, 0x0009):
            depth += 1
        if kind == 0x000A:
            depth -= 1
            if depth <= 0:
                break
        if depth <= 1 and record_kind == 0x00EC:
            if kind == 0x005D:  # OBJ is interleaved with the OfficeArt stream.
                continue
            if kind == 0x01B6:  # TXO text and runs have their own CONTINUEs.
                if len(payload) >= 14:
                    text_chars, text_runs = struct.unpack_from('<HH', payload, 10)
                else:
                    continuing = False
                continue
            if kind == 0x003C and text_chars:
                width = 2 if payload and payload[0] & 1 else 1
                text_chars = max(0, text_chars - max(0, len(payload) - 1) // width)
                continue
            if kind == 0x003C and text_runs:
                text_runs = max(0, text_runs - len(payload))
                continue
        selected = depth <= 1 and (kind == record_kind or (kind == 0x003C and continuing))
        continuing = selected
        if not selected:
            continue
        total += size
        if total > limits.max_stream_bytes:
            _warn(errors, 'OfficeArt stream byte limit exceeded')
            return b''
        chunks.append(payload)
    return b''.join(chunks)


def _cell(row, col):
    letters = ''
    col += 1
    while col:
        col, digit = divmod(col - 1, 26)
        letters = chr(65 + digit) + letters
    return '%s%d' % (letters, row + 1)


class XlsDrawingReader:
    """Read per-sheet images while retaining a workbook-wide asset registry."""

    def __init__(self, workbook_data: bytes, errors: Optional[List[str]] = None,
                 limits: Optional[Limits] = None):
        self.errors = errors if errors is not None else []
        self.limits = limits or Limits()
        self.assets = []
        self._seen = set()
        data = _drawing_bytes(workbook_data, 0x00EB, self.limits, self.errors)
        records = parse_records(data, limits=self.limits, errors=self.errors)
        self.entries = read_bstore(records, limits=self.limits, errors=self.errors)
        self._placements = 0

    def read_sheet(self, sheet_data: bytes, sheet_name: str) -> List[object]:
        data = _drawing_bytes(sheet_data, 0x00EC, self.limits, self.errors)
        records = parse_records(data, limits=self.limits, errors=self.errors)
        shapes = read_shapes(records, errors=self.errors)
        stack = [(shape, None) for shape in reversed(shapes)]
        positioned = []
        while stack:
            shape, inherited = stack.pop()
            anchor = inherited
            if shape.client_anchor:
                if len(shape.client_anchor) < 18:
                    _warn(self.errors, 'truncated client anchor')
                else:
                    _, col, dx, row, dy, end_col, end_dx, end_row, end_dy = struct.unpack_from('<9H', shape.client_anchor)
                    if col < 256 and end_col <= 256 and dx <= 1024 and end_dx <= 1024 and dy <= 256 and end_dy <= 256:
                        anchor = (row, col)
                    else:
                        _warn(self.errors, 'client anchor out of bounds')
            stack.extend((child, anchor) for child in reversed(shape.children))
            if not shape.pib:
                continue
            if self._placements >= min(self.limits.max_records, 10000):
                _warn(self.errors, 'image placement limit exceeded')
                break
            if not 1 <= shape.pib <= len(self.entries):
                _warn(self.errors, 'pib outside BStore: %d' % shape.pib)
                continue
            entry = self.entries[shape.pib - 1]
            if entry.image is None:
                _warn(self.errors, 'image data unavailable for pib %d' % shape.pib)
                continue
            fmt, pixels = entry.image
            filename = 'image%d.%s' % (entry.index, fmt)
            target = 'xls/media/' + filename
            label = shape.description or shape.name or 'image'
            cell = _cell(*anchor) if anchor is not None else None
            provenance = Provenance(source_format='xls', sheet=sheet_name, cell=cell, path=target)
            # A BStore entry is one asset regardless of its placement count.
            # Keep every anchor, but emit its bytes only once for the common
            # exporter/OCR path; repeated placements are ordinary image refs.
            image = Image(bin_id=entry.index, filename=filename,
                          image_data=pixels if entry.index not in self._seen else b'',
                          image_format=fmt, alt_text=label, provenance=provenance)
            paragraph = Paragraph(runs=[TextRun(text='![%s](%s)' % (label, target))], provenance=provenance)
            position = anchor if anchor is not None else (65536, 256)
            positioned.append((position, self._placements, paragraph, image))
            self._placements += 1
            if entry.index not in self._seen:
                self._seen.add(entry.index)
                mime = {'jpg': 'image/jpeg', 'png': 'image/png', 'bmp': 'image/bmp',
                        'tiff': 'image/tiff', 'wmf': 'image/x-wmf', 'emf': 'image/x-emf',
                        'pict': 'image/x-pict'}.get(fmt, 'application/octet-stream')
                self.assets.append(AssetRef(id='bse%d' % entry.index, source_path=target,
                    filename=filename, content_type=mime,
                    metadata={'kind': 'image', 'label': label, 'missing': False,
                              'source_format': 'xls', 'sheet': sheet_name, 'cell': cell}))
        return [element for _, _, paragraph, image in sorted(positioned, key=lambda item: item[:2])
                for element in (paragraph, image)]
