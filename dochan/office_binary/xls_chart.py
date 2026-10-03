"""Native BIFF8 chart substreams, reusable by embedded Office workbooks.

Record layouts follow [MS-XLS] BOF, Series, BRAI, SeriesText, ObjectLink,
SIIndex, Number, Label, Bar, Line, Pie, Area and Scatter. Chart caches use a
separate coordinate space: row is point index and column is series index.
They must never be interpreted as worksheet cells.
"""
import math
import struct
from dataclasses import dataclass, field
from typing import List, Optional

from ..conversion import Provenance
from ..model.document import Paragraph, TextRun
from ..ooxml.charts import format_chart_number, mixed_series_rows, text_table, xy_series_rows

MAX_CHARTS = 256
MAX_SERIES = 256
MAX_POINTS = 100000
MAX_OUTPUT_CELLS = 200000
MAX_CHART_RECORDS = 200000
MAX_CHART_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 64


class _CachedNumber(str):
    """NUMBER 캐시와 숫자처럼 생긴 LABEL 범주를 구분하는 표지다."""


@dataclass
class _Series:
    name: str = ''
    references: dict = field(default_factory=dict)
    source_types: dict = field(default_factory=dict)
    auxiliary: bool = False
    formats: dict = field(default_factory=dict)
    group: Optional[int] = None


@dataclass
class _Group:
    kind: str = ''


@dataclass
class _Text:
    text: str = ''
    link: int = 0


def _warn(errors, message):
    message = 'WARN: XLS chart ' + message
    if message not in errors:
        errors.append(message)


def _records(data, errors):
    offset = 0
    while offset + 4 <= len(data):
        sid, size = struct.unpack_from('<HH', data, offset)
        end = offset + 4 + size
        if end > len(data):
            _warn(errors, 'truncated BIFF record')
            return
        yield sid, data[offset + 4:end]
        offset = end


def parse_chart_substreams(data: bytes, sheets=None, external_sheets=None,
                           current_sheet: int = 0, path: str = 'Workbook',
                           sheet_name: Optional[str] = None, errors=None,
                           budget=None, internal_supbooks=None, formula_values=None,
                           category_start=0, excluded_series=None, number_formats=None,
                           date_1904=False) -> List[object]:
    """Read embedded charts or a chart sheet from a BIFF byte sequence.

    ``sheets`` holds zero-based worksheet cell mappings; ``external_sheets``
    maps EXTERNSHEET indices to (supbook, first sheet, last sheet). Legacy
    two-item entries are trusted internal links; triples require internal_supbooks.
    Resolved internal cells take precedence over chart caches. Unsupported/external formulas retain their cache, with a
    warning if no usable source exists. ``budget`` can be shared across calls
    and holds remaining output cells, visited points, and charts. A legacy
    one-item list is extended in place. formula_values parallels sheets and maps
    formula coordinates to cached scalars (None means no calculated value).
    ``category_start`` keeps the historical XLS fallback labels by default;
    native embedded Office charts request the one-based Office positions.
    All malformed chart diagnostics are warnings, never document failures.
    """
    errors = errors if errors is not None else []
    budget = budget if budget is not None else [MAX_OUTPUT_CELLS]
    if len(budget) == 1:
        budget.extend([MAX_POINTS, MAX_CHARTS])
    sheets = sheets or []
    external_sheets = external_sheets or []
    elements = []
    chart_records = None
    chart_bytes = 0
    depth = 0
    chart_index = 0
    oversized = False
    for sid, payload in _records(data, errors):
        if sid == 0x0809:
            if chart_records is not None:
                depth += 1
                if depth > MAX_DEPTH:
                    _warn(errors, 'BOF nesting limit exceeded')
                    break
                continue
            if len(payload) >= 4 and struct.unpack_from('<H', payload, 2)[0] == 0x0020:
                chart_index += 1
                if budget[2] <= 0:
                    _warn(errors, 'chart count limit exceeded')
                    break
                budget[2] -= 1
                chart_records = []
                chart_bytes = 0
                depth = 1
                oversized = False
            continue
        if chart_records is None:
            continue
        # These worksheet-only records cannot belong to a chart cache. BLANK
        # is deliberately allowed: real charts include it after SIIndex.
        if sid in (0x00fd, 0x027e, 0x00bd, 0x0006, 0x0208, 0x00be):
            _warn(errors, 'unterminated chart before worksheet record')
            if not oversized:
                elements.extend(_parse_chart(chart_records, sheets, external_sheets,
                                current_sheet, f'{path}#chart{chart_index}',
                                sheet_name, errors, budget, internal_supbooks, formula_values, category_start, excluded_series, number_formats, date_1904))
            chart_records = None
            depth = 0
            continue
        if sid == 0x000a:
            depth -= 1
            if depth:
                continue
            if not oversized:
                elements.extend(_parse_chart(chart_records, sheets, external_sheets,
                                current_sheet, f'{path}#chart{chart_index}',
                                sheet_name, errors, budget, internal_supbooks, formula_values, category_start, excluded_series, number_formats, date_1904))
            chart_records = None
            continue
        if depth != 1 or oversized:
            continue
        chart_bytes += len(payload) + 4
        if len(chart_records) >= MAX_CHART_RECORDS or chart_bytes > MAX_CHART_BYTES:
            _warn(errors, 'record/byte limit exceeded')
            chart_records.clear()
            oversized = True
        else:
            chart_records.append((sid, payload))
    if chart_records is not None:
        _warn(errors, 'unterminated chart substream')
        if not oversized and depth <= MAX_DEPTH:
            elements.extend(_parse_chart(chart_records, sheets, external_sheets,
                            current_sheet, f'{path}#chart{chart_index}', sheet_name,
                            errors, budget, internal_supbooks, formula_values, category_start, excluded_series, number_formats, date_1904))
    return elements


def _unicode_text(data, offset, short_length=False):
    width = 1 if short_length else 2
    if offset + width + 1 > len(data):
        return ''
    count = data[offset] if short_length else struct.unpack_from('<H', data, offset)[0]
    flags = data[offset + width]
    start = offset + width + 1
    end = start + count * (2 if flags & 1 else 1)
    if end > len(data):
        return ''
    return bytes(data[start:end]).decode('utf-16le' if flags & 1 else 'latin1', errors='replace')


def _value(number):
    if not math.isfinite(number):
        return ''
    return str(int(number)) if number.is_integer() else str(number)


def _format_xls_chart_number(value, code, date_1904):
    if not code or code.lower() == 'general':
        from ..spreadsheet_format import SpreadsheetNumberFormatter
        return SpreadsheetNumberFormatter()._format_cell_value(value, 'General')
    return format_chart_number(value, code, date_1904)


def _cell_value(value):
    # XLS formula cells preserve 'value (=formula)' for normal output.
    # Charts consume its cached scalar; formulas without a cache are empty.
    if value.startswith(('(=', '=')):
        return ''
    return value.split(' (=', 1)[0]


def _reference_values(tokens, sheets, external_sheets, current_sheet, errors, budget,
                      internal_supbooks=None, formula_values=None,
                      format_code=None, date_1904=False):
    if not tokens:
        return None
    # BRAI chart formulas use absolute Ref/Area and Ref3d/Area3d tokens.
    # The class bits do not change the payload layout.
    opcode = ((tokens[0] & 0x1f) | 0x20) if tokens[0] >= 0x20 else tokens[0]
    offset = 1
    sheet = current_sheet
    if opcode in (0x3a, 0x3b):
        if len(tokens) < 3:
            _warn(errors, 'truncated BRAI reference')
            return None
        xti = struct.unpack_from('<H', tokens, offset)[0]
        offset += 2
        if xti >= len(external_sheets):
            _warn(errors, 'unresolved BRAI external sheet')
            return None
        entry = external_sheets[xti]
        if len(entry) == 3:
            supbook, first, last = entry
            if supbook not in (internal_supbooks or set()):
                _warn(errors, 'unresolved BRAI external workbook reference')
                return None
        else:
            first, last = entry
        if first != last or first >= len(sheets):
            _warn(errors, 'unsupported BRAI multi-sheet/external reference')
            return None
        sheet = first
    if opcode in (0x24, 0x3a) and len(tokens) == offset + 4:
        row, col = struct.unpack_from('<HH', tokens, offset)
        r1 = r2 = row
        c1 = c2 = col & 0xff
    elif opcode in (0x25, 0x3b) and len(tokens) == offset + 8:
        r1, r2, c1, c2 = struct.unpack_from('<4H', tokens, offset)
        c1 &= 0xff
        c2 &= 0xff
    else:
        _warn(errors, 'unsupported BRAI formula without cache')
        return None
    if r2 < r1 or c2 < c1:
        _warn(errors, 'invalid BRAI range')
        return None
    area = (r2 - r1 + 1) * (c2 - c1 + 1)
    if not 0 <= sheet < len(sheets):
        return None
    cells = sheets[sheet]
    # Large sparse ranges must not visit every possible BIFF coordinate.
    visits = min(area, len(cells))
    if area > MAX_POINTS:
        _warn(errors, 'BRAI range point limit exceeded; sparse cells retained')
    if visits > budget[1]:
        _warn(errors, 'BRAI range point limit exceeded')
        return None
    budget[1] -= visits
    if area > len(cells):
        candidates = ((r, c, value) for (r, c), value in cells.items()
                      if r1 <= r <= r2 and c1 <= c <= c2)
    else:
        candidates = ((r, c, cells.get((r, c), ''))
                      for r in range(r1, r2 + 1) for c in range(c1, c2 + 1))
    formulas = formula_values[sheet] if formula_values is not None and sheet < len(formula_values) else None
    values = {}
    for row, col, value in candidates:
        if formulas is not None:
            value = formulas.get((row, col), value)
            value = '' if value is None else value
        # XLS numeric cells retain their scalar before worksheet formatting.
        # Use it for both source-linked formats and explicit BRAI overrides.
        raw = getattr(value, 'number', None)
        if raw is not None:
            code = format_code if format_code is not None else value.number_format
            value = _format_xls_chart_number(_value(float(raw)), code, date_1904)
        else:
            # LABEL/LABELSST strings can look numeric (e.g. "001"). BRAI's
            # IFmt never changes their type; apply it only to numeric sources.
            value = str(value) if formulas is not None else _cell_value(str(value))
        if value:
            values[(row - r1) * (c2 - c1 + 1) + col - c1] = value
    return values


def _parse_chart(records, sheets, external_sheets, current_sheet, path, sheet_name, errors, budget,
                 internal_supbooks=None, formula_values=None, category_start=0, excluded_series=None,
                 number_formats=None, date_1904=False):
    if budget[0] < 2:
        _warn(errors, 'output cell limit exceeded')
        return []
    series = []
    groups = {}
    texts = []
    stack = []
    pending = None
    kinds = []
    cache = {}
    cache_role = 0
    three_d = False
    for sid, data in records:
        if sid == 0x1033:  # Begin: nesting belongs to the immediately preceding record.
            if len(stack) >= MAX_DEPTH:
                _warn(errors, 'nesting limit exceeded')
                return []
            stack.append(pending)
            pending = None
            continue
        if sid == 0x1034:  # End
            if stack:
                stack.pop()
            pending = None
            continue
        context = next((item for item in reversed(stack) if item is not None), None)
        pending = None
        if sid == 0x1003:  # Series
            if len(series) >= MAX_SERIES:
                _warn(errors, 'series count limit exceeded')
                return []
            item = _Series()
            series.append(item)
            pending = item
        elif sid == 0x1014 and len(data) >= 20:  # ChartFormat.icrt, [MS-XLS] 2.4.48.
            item = _Group()
            group_id = struct.unpack_from('<H', data, 18)[0]
            if group_id in groups:
                _warn(errors, 'duplicate ChartFormat group identifier')
            else:
                groups[group_id] = item
            pending = item
        elif sid == 0x1045 and len(data) >= 2 and isinstance(context, _Series):
            context.group = struct.unpack_from('<H', data)[0]
        elif sid == 0x104a and isinstance(context, _Series):
            context.auxiliary = True
        elif sid == 0x1025:  # Text, paired with ObjectLink for semantic role.
            item = _Text()
            texts.append(item)
            pending = item
        elif sid == 0x100d:  # SeriesText: id, cch (one byte), unicode flags, text.
            value = _unicode_text(data, 2, short_length=True)
            if isinstance(context, _Series):
                context.name = value
            elif isinstance(context, _Text):
                context.text = value
        elif sid == 0x1027 and len(data) >= 2 and isinstance(context, _Text):
            context.link = struct.unpack_from('<H', data)[0]
        elif sid == 0x1051 and len(data) >= 8:  # BRAI
            role, source = data[:2]
            size = struct.unpack_from('<H', data, 6)[0]
            if size > len(data) - 8:
                _warn(errors, 'truncated BRAI tokens')
                continue
            tokens = data[8:8 + size]
            if isinstance(context, _Series):
                context.references[role] = tokens
                context.source_types[role] = source
                flags, ifmt = struct.unpack_from('<HH', data, 2)
                context.formats[role] = (bool(flags & 1), ifmt)
            elif isinstance(context, _Text) and source == 2:
                values = _reference_values(tokens, sheets, external_sheets, current_sheet, errors, budget, internal_supbooks, formula_values)
                context.text = next(iter((values or {}).values()), '')
        elif sid == 0x1065 and len(data) >= 2:  # SIIndex
            cache_role = struct.unpack_from('<H', data)[0]
        elif sid in (0x0203, 0x0204, 0x0205) and cache_role in (1, 2, 3) and len(data) >= 6:
            row, col = struct.unpack_from('<HH', data)
            if col >= len(series):
                continue
            budget[1] -= 1
            if budget[1] < 0:
                _warn(errors, 'cached point limit exceeded')
                return []
            value = ''
            if sid == 0x0203 and len(data) >= 14:
                value = _CachedNumber(_value(struct.unpack_from('<d', data, 6)[0]))
            elif sid == 0x0204:
                value = _unicode_text(data, 6)
            elif sid == 0x0205 and len(data) >= 8:
                value = '#N/A' if data[7] else ('TRUE' if data[6] else 'FALSE')
            if value:
                cache.setdefault((col, cache_role), {})[row] = value
        elif sid == 0x103a:
            three_d = True
        else:
            kind = _chart_kind(sid, data)
            if kind:
                if isinstance(context, _Group):
                    context.kind = kind
                if kind not in kinds:
                    kinds.append(kind)
    if three_d:
        kinds = [('3-D ' + kind) if kind in ('column', 'bar', 'line', 'pie', 'area', 'surface') else kind for kind in kinds]
    title = next((t.text for t in texts if t.link == 1 and t.text), '')
    axes = []
    xy = any(kind in ('scatter', 'bubble') for kind in kinds)
    pure_xy = xy and all(kind in ('scatter', 'bubble') for kind in kinds)
    axis_labels = {2: 'Y axis', 3: 'X axis', 7: 'Series axis'} if pure_xy else {
        2: 'Value axis', 3: 'Category axis', 7: 'Series axis'}
    axis_texts = sorted(texts, key=lambda item: {3: 0, 2: 1}.get(item.link, 2)) if pure_xy else texts
    for item in axis_texts:
        label = axis_labels.get(item.link)
        if label and item.text and len(axes) < 8:
            axes.append(f'{label}: {item.text}')
    caption = '; '.join((['Chart type: ' + ' + '.join(kinds)] if kinds else []) + axes)

    def paragraph(value):
        return Paragraph(runs=[TextRun(text=value)], provenance=Provenance(
            source_format='xls', sheet=sheet_name, path=path))

    elements = []
    if title:
        heading = paragraph(title)
        heading.heading_level = 3
        elements.append(heading)
    items = []
    implicit = []
    xy_flags = []
    from ..ooxml.xlsx import BUILTIN_NUM_FORMATS
    for index, item in enumerate(series):
        if item.auxiliary or index in (excluded_series or ()):
            continue
        resolved = {}
        for role in (0, 1, 2):
            points = None
            unlinked, ifmt = item.formats.get(role, (False, 0))
            code = (number_formats or {}).get(ifmt, BUILTIN_NUM_FORMATS.get(ifmt, ''))
            if item.source_types.get(role) == 2:
                points = _reference_values(item.references.get(role, b''), sheets, external_sheets,
                                           current_sheet, errors, budget, internal_supbooks,
                                           formula_values, code if unlinked else None, date_1904)
            values = points if points is not None else cache.get((index, role), {})
            # A cache has no displayed strings, so its stored IFmt is the fallback.
            if points is None and code:
                values = {idx: _format_xls_chart_number(value, code, date_1904)
                          if isinstance(value, _CachedNumber) else value
                          for idx, value in values.items()}
            resolved[role] = values
        name = item.name or next(iter(resolved[0].values()), '')
        items.append((name, resolved[2], resolved[1]))
        implicit.append(item.source_types.get(2, 0) in (0, 1) and not resolved[2])
        group = groups.get(item.group)
        kind = group.kind if group is not None else ''
        xy_flags.append(kind in ('scatter', 'bubble') if kind else xy)
    if not items:
        if axes:
            elements.append(paragraph(caption))
        return elements
    mixed = any(xy_flags) and not all(xy_flags)
    # Bound the maximum long table before the shared helper allocates it.
    long_count = 1 + sum(len(set(xs) | set(ys)) for _, xs, ys in items)
    width = 4 if mixed else 3
    if xy and len(items) > 1 and width * long_count > budget[0]:
        _warn(errors, 'output cell limit exceeded')
        return elements
    rows = mixed_series_rows(items, xy_flags, implicit_x=implicit) if mixed else xy_series_rows(items, xy, implicit)
    if rows is None:
        indexes = set()
        labels = {}
        for _, xs, ys in items:
            indexes.update(xs)
            indexes.update(ys)
            for index, value in xs.items():
                labels.setdefault(index, value)
        count = (len(items) + 1) * (len(indexes) + 1)
        if count > budget[0]:
            _warn(errors, 'output cell limit exceeded')
            return elements
        rows = [['Category'] + [name or f'Series {i + 1}' for i, (name, _, _) in enumerate(items)]]
        rows.extend([[labels.get(i, str(i + category_start))] + [ys.get(i, '') for _, _, ys in items] for i in sorted(indexes)])
    count = sum(len(row) for row in rows)
    if count > budget[0]:
        _warn(errors, 'output cell limit exceeded')
        return elements
    budget[0] -= count
    table = text_table(rows)
    for row in table.rows:
        for cell in row:
            cell.provenance = Provenance(source_format='xls', sheet=sheet_name, path=path)
            for item in cell.paragraphs:
                item.provenance = cell.provenance
    if caption:
        table.caption = [paragraph(caption)]
        table.caption_side = 'TOP'
    elements.append(table)
    return elements


def _chart_kind(sid, data):
    if sid == 0x1017 and len(data) >= 6:  # Bar.fTranspose
        return 'bar' if struct.unpack_from('<H', data, 4)[0] & 1 else 'column'
    if sid == 0x1019 and len(data) >= 4:  # Pie.pcDonut
        return 'doughnut' if struct.unpack_from('<H', data, 2)[0] else 'pie'
    if sid == 0x101b and len(data) >= 6:  # Scatter.fBubbles
        return 'bubble' if struct.unpack_from('<H', data, 4)[0] & 1 else 'scatter'
    return {0x1018: 'line', 0x101a: 'area', 0x103e: 'radar', 0x103f: 'surface',
            0x1040: 'radar'}.get(sid, '')
