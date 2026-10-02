"""Bounded native embedded charts and Equation Editor objects.

Connections follow [MS-DOC] EMBED fields/CPicLocation, [MS-PPT]
ExObjRefAtom -> ExOleObjAtom -> ExOleObjStg and [MS-XLS] BIFF records.
No OLE server is activated and no external object or link is followed.
MS Graph's 0x0680 datasheet records are normalized to the shared BIFF8
chart cache contract; unsupported layouts leave the existing preview intact.
"""
import io
import re
import struct
import zlib
from dataclasses import replace

import olefile

from ..model.equation import Equation
from ..utils.bounded_io import ByteBudget, read_ole_stream
from .xls_chart import parse_chart_substreams

MAX_OBJECT_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_OBJECTS = 256
MAX_RECORDS = 200000


def _warn(errors, message):
    message = 'WARN: embedded OLE ' + message
    if len(errors) < 1000 and message not in errors:
        errors.append(message)


def decompress_ppt_storage(data, instance, errors=None):
    """ExOleObjStgCompressedAtom has a uint32 size followed by zlib data."""
    if len(data) > MAX_OBJECT_BYTES:
        raise ValueError('storage byte limit exceeded')
    if instance == 0:
        return bytes(data)
    if instance != 1 or len(data) < 4:
        raise ValueError('unsupported or truncated storage header')
    size = struct.unpack_from('<I', data)[0]
    if size > MAX_OBJECT_BYTES:
        raise ValueError('uncompressed storage byte limit exceeded')
    inflater = zlib.decompressobj()
    try:
        result = inflater.decompress(data[4:], size + 1)
    except zlib.error as exc:
        raise ValueError('invalid compressed storage') from exc
    if len(result) != size or inflater.unconsumed_tail:
        raise ValueError('storage size mismatch')
    if not inflater.eof or inflater.unused_data:
        # Some producers omit the zlib checksum or append a padding byte.
        # Accept only an exactly sized compound file that its reader can open.
        try:
            with olefile.OleFileIO(io.BytesIO(result), raise_defects=olefile.DEFECT_INCORRECT):
                pass
        except Exception as exc:
            raise ValueError('incomplete compression without valid compound storage') from exc
        if errors is not None:
            _warn(errors, 'storage compression framing anomaly; complete compound storage retained')
    return result


def supported_progid(progid):
    return progid.lower().startswith(('equation.', 'excel.', 'msgraph.'))


def _records(data):
    if len(data) > MAX_OBJECT_BYTES:
        raise ValueError('chart byte limit exceeded')
    pos = 0
    count = 0
    while pos < len(data):
        # Compound streams may contain zero padding after the last BIFF EOF.
        if pos + 4 > len(data):
            raise ValueError('truncated chart record header')
        sid, size = struct.unpack_from('<HH', data, pos)
        if sid == size == 0:
            if any(data[pos:]):
                raise ValueError('invalid chart padding')
            return
        end = pos + 4 + size
        count += 1
        if end > len(data) or count > MAX_RECORDS:
            raise ValueError('truncated chart record or record limit exceeded')
        yield pos, sid, data[pos + 4:end]
        pos = end


def _rec(sid, payload=b''):
    return struct.pack('<HH', sid, len(payload)) + payload


def _graph_chart(data):
    """Normalize Graph datasheet values and BRAI row/column indices.

    Graph BOF has vers=0x0680, dt=0x8000. Datasheet Number/Label use
    row(2), column(2), attributes(3), value; BRAI's final uint16 is an
    index, not an Excel formula byte count. 0x1055 selects series in rows.
    Only contiguous included rows/columns are accepted, never guessed.
    """
    records = list(_records(data))
    codepage = next((struct.unpack_from('<H', p)[0] for _, s, p in records
                     if s == 0x42 and len(p) >= 2), 1252)
    cells = {}
    by_rows = None
    series = []
    selections = {}
    stack = []
    pending = None
    output = []
    output_size = 0

    def emit(record):
        nonlocal output_size
        output_size += len(record)
        if output_size > MAX_OBJECT_BYTES:
            raise ValueError('MS Graph normalized byte limit exceeded')
        output.append(record)

    in_chart = False
    chart_count = 0
    for _offset, sid, payload in records:
        if sid == 0x809:
            if len(payload) < 4 or struct.unpack_from('<H', payload)[0] != 0x680:
                raise ValueError('unsupported MS Graph version')
            in_chart = struct.unpack_from('<H', payload, 2)[0] == 0x8000
            if in_chart:
                chart_count += 1
                if chart_count > 1:
                    raise ValueError('unsupported multiple MS Graph chart substreams')
                emit(_rec(0x809, b'\0\x06\x20\0'))
            continue
        if not in_chart:
            continue
        if sid == 0x1033:
            if len(stack) >= 64:
                raise ValueError('MS Graph nesting limit exceeded')
            stack.append(pending)
            pending = None
        elif sid == 0x1034:
            if stack:
                stack.pop()
            pending = None
        else:
            pending = None
        if sid in (0x1053, 0x1054):
            if len(payload) != 4:
                raise ValueError('unsupported MS Graph noncontiguous datasheet selection')
            first, stop = struct.unpack('<HH', payload)
            # Public Graph samples use a contiguous included prefix including
            # row/column zero (labels). Other selection encodings are unknown.
            if first != 0 or stop < 1 or sid in selections:
                raise ValueError('unsupported MS Graph datasheet selection')
            selections[sid] = stop
        if sid == 0x1055:
            if len(payload) < 6 or payload[0] not in (0, 1):
                raise ValueError('unsupported MS Graph datasheet orientation')
            by_rows = bool(payload[0])
        if sid in (3, 4):
            if len(payload) < (15 if sid == 3 else 9):
                raise ValueError('truncated MS Graph datasheet cell')
            row, col = struct.unpack_from('<HH', payload)
            if len(cells) >= 100000:
                raise ValueError('MS Graph cell limit exceeded')
            if sid == 3:
                value = ('number', payload[7:15])
            else:
                size = struct.unpack_from('<H', payload, 7)[0]
                if len(payload) != 9 + size:
                    raise ValueError('unsupported MS Graph label encoding')
                # Graph's narrow datasheet strings use the workbook codepage.
                codec = ('ascii' if all(c < 128 for c in payload[9:]) else
                         'utf-8' if codepage == 65001 else 'cp%d' % codepage)
                try:
                    text = payload[9:].decode(codec)
                except (LookupError, UnicodeError) as exc:
                    raise ValueError('unsupported MS Graph label codepage') from exc
                value = ('label', text)
            cells[(row, col)] = value
            continue
        if sid == 0x1003:
            if len(series) >= 256:
                raise ValueError('MS Graph series limit exceeded')
            if len(payload) != 12:
                raise ValueError('truncated MS Graph Series')
            cats, values = struct.unpack_from('<HH', payload, 4)
            series.append({'counts': {1: values, 2: cats}})
            pending = len(series) - 1
        elif sid == 0x104a:
            context = next((v for v in reversed(stack) if v is not None), None)
            if context is not None:
                series[context]['auxiliary'] = True
        elif sid == 0x1051:
            if len(payload) != 8:
                raise ValueError('unsupported MS Graph BRAI')
            context = next((v for v in reversed(stack) if v is not None), None)
            if context is not None:
                series[context][payload[0]] = struct.unpack_from('<H', payload, 6)[0]
            payload = payload[:6] + b'\0\0'
        if sid == 10:
            if by_rows is None:
                raise ValueError('MS Graph datasheet orientation missing')
            if selections and len(selections) != 2:
                raise ValueError('incomplete MS Graph datasheet selection')
            point_stop = selections.get(0x1054 if by_rows else 0x1053)
            for refs in series:
                if refs.get('auxiliary'):
                    continue
                if point_stop is not None and any(
                        count != point_stop - 1 for count in refs['counts'].values()):
                    raise ValueError('MS Graph Series point count does not match selection')
            indexed = {}
            for (row, col), value in sorted(cells.items()):
                axis, point = (row, col) if by_rows else (col, row)
                if selections and (row >= selections[0x1053] or col >= selections[0x1054]):
                    continue
                if point:
                    indexed.setdefault(axis, []).append((point, value))
            remaining = 200000
            for role in (1, 2):
                emit(_rec(0x1065, struct.pack('<H', role)))
                for index, refs in enumerate(series):
                    if role not in refs or refs.get('auxiliary'):
                        continue
                    source = refs[role]
                    points = indexed.get(source, [])
                    if any(point > refs['counts'][role] for point, _ in points):
                        raise ValueError('MS Graph Series point count does not match datasheet')
                    for point, (kind, value) in points:
                        remaining -= 1
                        if remaining < 0:
                            raise ValueError('MS Graph cache cell limit exceeded')
                        prefix = struct.pack('<HHH', point - 1, index, 0)
                        if kind == 'number':
                            emit(_rec(0x203, prefix + value))
                        else:
                            encoded = value.encode('utf-16le')
                            emit(_rec(0x204, prefix + struct.pack('<HB', len(encoded)//2, 1) + encoded))
            emit(_rec(10))
            in_chart = False
        else:
            emit(_rec(sid, payload))
    if in_chart:
        raise ValueError('unterminated MS Graph chart')
    return b''.join(output)


def _visible_workbook_chart(data, chart_object=False):
    """Return active chart range; an active worksheet keeps its OLE preview."""
    bounds = []
    active = 0
    first_type = None
    for offset, sid, payload in _records(data):
        if sid == 0x2f:
            raise ValueError('encrypted embedded workbook')
        if sid == 0x809 and len(payload) >= 4:
            if struct.unpack_from('<H', payload)[0] != 0x600:
                raise ValueError('unsupported embedded workbook version')
            if first_type is None:
                first_type = struct.unpack_from('<H', payload, 2)[0]
        if sid == 0x85 and len(payload) >= 6:
            bounds.append((struct.unpack_from('<I', payload)[0], payload[5], len(payload) >= 8))
        if sid == 0x3d and len(payload) >= 12:
            active = struct.unpack_from('<H', payload, 10)[0]
        if sid == 10:
            break
    if not bounds:
        return (0, len(data), False) if first_type == 0x20 or chart_object else None
    if active >= len(bounds) or any(b[0] >= len(data) for b in bounds):
        raise ValueError('invalid embedded workbook active sheet')
    start, kind, named = bounds[active]
    if kind != 2 and not chart_object:
        return None
    end = min((b[0] for b in bounds if b[0] > start), default=len(data))
    return start, end, all(b[2] for b in bounds)


def parse_embedded_chart(data, errors, graph=False, budget=None, chart_object=False):
    try:
        if graph:
            elements = parse_chart_substreams(_graph_chart(data), errors=errors, budget=budget, category_start=1)
        else:
            selected = _visible_workbook_chart(data, chart_object)
            if selected is None:
                return []
            start, end, has_workbook = selected
            if has_workbook:
                # Reuse the XLS resolver with its SST, SupBook and formula-cache
                # handling; output only the selected chart, never worksheet cells.
                from .xls import parse_biff_workbook
                doc = parse_biff_workbook(data, embedded_chart_offset=start, chart_budget=budget)
                errors.extend(e for e in doc.errors if e not in errors)
                elements = [e for section in doc.sections for e in section.elements]
            else:
                elements = parse_chart_substreams(data[start:end], errors=errors, budget=budget, category_start=1)
        tables = [e for e in elements if hasattr(e, 'rows')]
        if not tables or any(not any(cell.text for row in t.rows[1:] for cell in row[1:])
                             for t in tables):
            _warn(errors, 'chart has no usable data; preview retained')
            return []
        return elements
    except (ValueError, struct.error) as exc:
        _warn(errors, str(exc))
        return []


def _provenance(elements, provenance):
    if provenance is None:
        return
    for element in elements:
        if hasattr(element, 'provenance'):
            element.provenance = provenance
        for name in ('runs', 'paragraphs', 'caption'):
            _provenance(getattr(element, name, []) or [], provenance)
        for row in getattr(element, 'rows', []):
            _provenance(row, provenance)


class EmbeddedObjects:
    def __init__(self, errors):
        self.errors = errors
        self.bytes = ByteBudget(MAX_TOTAL_BYTES)
        self.remaining = MAX_OBJECTS
        self.chart_budget = [200000]

    def read(self, ole, root, provenance):
        if self.remaining <= 0:
            _warn(self.errors, 'object count limit exceeded')
            return []
        self.remaining -= 1
        try:
            def read(name):
                return read_ole_stream(ole, root + [name], max_bytes=MAX_OBJECT_BYTES, budget=self.bytes)

            if ole.exists(root + ['Equation Native']):
                from .mtef import parse_equation_native
                latex = parse_equation_native(read('Equation Native'))
                return [Equation(latex_override=latex)] if latex else []
            name = next((n for n in ('Workbook', 'Book') if ole.exists(root + [n])), None)
            if name is None:
                return []
            comp = read('\x01CompObj') if ole.exists(root + ['\x01CompObj']) else b''
            elements = parse_embedded_chart(read(name), self.errors, b'MSGraph.Chart.8\0' in comp,
                                           self.chart_budget, chart_object=bool(re.search(
                                               rb'(?:Excel|MSGraph)\.Chart(?:\.|\x00)', comp)))
            _provenance(elements, provenance)
            return elements
        except Exception as exc:
            # One optional object never prevents rendering the surrounding document.
            _warn(self.errors, 'preview retained: %s' % exc)
            return []


class DocObjects:
    def __init__(self, ole, binary, fields, errors):
        self.ole = ole
        self.pool = EmbeddedObjects(errors)
        self.anchors = {}
        self.labels = {}
        for field in fields:
            if not re.match(r'\s*EMBED\s+(?:Equation\.|Excel\.|MSGraph\.)', field.instruction, re.I):
                continue
            if field.separator < 0:
                continue
            if len(self.anchors) >= MAX_OBJECTS:
                _warn(errors, 'DOC object count limit exceeded')
                break
            object_id = binary.char_props(field.separator).get('pic_location')
            if object_id is None:
                continue
            cp = binary.text.find('\x01', field.separator + 1, field.end)
            if cp >= 0:
                self.anchors[cp] = ['ObjectPool', '_%d' % object_id]
                self.labels[cp] = '[내장 수식]' if 'equation.' in field.instruction.lower() else '[내장 개체]'

    def at(self, cp, props, provenance):
        root = self.anchors.get(cp)
        if root is None:
            return []
        if provenance is not None:
            provenance = replace(provenance, path=(provenance.path or '') + '#' + '/'.join(root))
        return self.pool.read(self.ole, root, provenance)


class PptObjects:
    def __init__(self, records, errors, progids=None):
        self.records = records
        self.pool = EmbeddedObjects(errors)
        self.storage_bytes = ByteBudget(MAX_TOTAL_BYTES)
        self.progids = progids or {}
        self.supported = {key for key, value in self.progids.items() if supported_progid(value)}

    def at(self, object_id, provenance):
        if self.progids.get(object_id) and object_id not in self.supported:
            return []
        record = self.records.get(object_id)
        if record is None or self.pool.remaining <= 0:
            return []
        try:
            declared = (struct.unpack_from('<I', record.data)[0]
                        if record.header.rec_instance == 1 and len(record.data) >= 4 else len(record.data))
            if declared > self.storage_bytes.remaining:
                raise ValueError('PPT storage document byte limit exceeded')
            storage_errors = []
            raw = decompress_ppt_storage(record.data, record.header.rec_instance, storage_errors)
            self.storage_bytes.consume(len(raw), 'PPT embedded storage')
            with olefile.OleFileIO(io.BytesIO(raw)) as ole:
                if object_id not in self.supported:
                    if not any(ole.exists(name) for name in ('Equation Native', 'Workbook', 'Book')):
                        self.pool.remaining -= 1
                        return []
                    self.supported.add(object_id)
                for error in storage_errors:
                    _warn(self.pool.errors, error.removeprefix('WARN: embedded OLE '))
                if provenance is not None:
                    provenance = replace(provenance, path=(provenance.path or '') + '#ole%d' % object_id)
                return self.pool.read(ole, [], provenance)
        except Exception as exc:
            self.pool.remaining -= 1
            if object_id in self.supported:
                _warn(self.pool.errors, 'PPT preview retained: %s' % exc)
            return []
