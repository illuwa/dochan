"""BIFF8 formula link tables and RgbExtra, independent of stream decryption.

Layouts: [MS-XLS] SupBook, ExternName, XTI, Lbl, PtgNameX, PtgExtraArray,
SerAr (SerNum/SerStr/SerBool/SerErr/SerNil). No external workbook is opened.
"""
import math
import re
import struct
from dataclasses import dataclass, field
from typing import List


MAX_LINK_ENTRIES = 65535
# Workbook-wide wire-byte budget; bounding each SupBook alone still permits
# tens of thousands of records to retain unbounded decoded sheet names.
MAX_LINK_TEXT_BYTES = 1048576
MAX_EXTRA_BYTES = 1048576
MAX_ARRAY_CELLS = 65536
MAX_FORMULA_TEXT = 65535


class BoundedErrors(list):
    """Bound retained diagnostics and membership work, including direct append calls.

    Only retained messages enter the set: hostile unique messages cannot grow it.
    The summary counts omitted occurrences, rather than claiming a unique count.
    """

    def __init__(self, values=(), limit=100):
        super().__init__()
        self.limit = limit
        self.seen = set()
        self.omitted = 0
        self.has_error = False
        self.extend(values)

    def __contains__(self, value):
        return value in self.seen or (self.omitted and value == self[-1])

    def append(self, value):
        if value in self:
            return
        if len(self.seen) < self.limit:
            self.seen.add(value)
            self.has_error = self.has_error or value.startswith('ERR:')
            if self.omitted:
                self.insert(len(self) - 1, value)
            else:
                super().append(value)
            return
        if self.limit and value.startswith('ERR:') and not self.has_error:
            # The CLI derives failure from ERR messages. A preceding warning
            # flood must not turn a fatal standalone XLS failure into success.
            index = len(self.seen) - 1
            self.seen.remove(self[index])
            self[index] = value
            self.seen.add(value)
            self.has_error = True
        self._omit(1)

    def _omit(self, count):
        if not count:
            return
        had_summary = bool(self.omitted)
        self.omitted += count
        summary = 'WARN: XLS %d additional diagnostics omitted' % self.omitted
        if had_summary:
            self[-1] = summary
        else:
            super().append(summary)

    def extend(self, values):
        if isinstance(values, BoundedErrors):
            for value in values[:len(values.seen)]:
                self.append(value)
            self._omit(values.omitted)
        else:
            for value in values:
                self.append(value)


class FormulaDataError(ValueError):
    pass


def warn(errors, message):
    text = 'WARN: XLS formula ' + message
    if errors is not None and len(errors) < 1000 and text not in errors:
        errors.append(text)


class FormulaName(str):
    """Only resolved Name/NameX operands can supply a PtgFuncVar UDF name."""

    @property
    def function_name(self):
        # BIFF future-function names carry this compatibility namespace. Only
        # remove it in call position; _xll. identifies an add-in and is retained.
        return self[6:] if self.startswith('_xlfn.') else str(self)


def quote_reference(text):
    if re.fullmatch(r'(?:\[\d+\])?[A-Za-z_][A-Za-z0-9_.]*(?::[A-Za-z_][A-Za-z0-9_.]*)?', text):
        return text
    return "'" + text.replace("'", "''") + "'"


class ExtraReader:
    def __init__(self, data):
        if len(data) > MAX_EXTRA_BYTES:
            raise FormulaDataError('extra data byte limit exceeded')
        self.data = data
        self.offset = 0

    def take(self, size):
        if size < 0 or size > len(self.data) - self.offset:
            raise FormulaDataError('truncated extra data')
        value = self.data[self.offset:self.offset + size]
        self.offset += size
        return value

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def string(self, short=False, max_bytes=None):
        length, = self.unpack('<B' if short else '<H')
        flags, = self.unpack('<B')
        if flags & ~1:
            raise FormulaDataError('invalid Unicode string flags')
        size = length * (2 if flags else 1)
        if max_bytes is not None and size + (2 if short else 3) > max_bytes:
            raise FormulaDataError('SupBook sheet name byte limit exceeded')
        raw = bytes(self.take(size))
        # Compressed BIFF Unicode stores the low byte, not the ANSI code page.
        return raw.decode('utf-16-le' if flags else 'latin1', errors='replace')

    def array(self):
        columns, rows = self.unpack('<BH')
        columns, rows = columns + 1, rows + 1
        if columns * rows > MAX_ARRAY_CELLS:
            raise FormulaDataError('array cell limit exceeded')
        values, text_size = [], 2
        for _ in range(rows * columns):
            kind, = self.unpack('<B')
            if kind == 0x02:  # SerStr
                value = '"' + self.string().replace('"', '""') + '"'
            else:
                raw = self.take(8)
                if kind == 0x01:  # SerNum
                    number, = struct.unpack('<d', raw)
                    if not math.isfinite(number):
                        raise FormulaDataError('non-finite array number')
                    value = str(int(number)) if number.is_integer() else str(number)
                elif kind == 0x04 and raw[0] in (0, 1):
                    value = 'TRUE' if raw[0] else 'FALSE'
                elif kind == 0x10:
                    errors = {0: '#NULL!', 7: '#DIV/0!', 15: '#VALUE!', 23: '#REF!',
                              29: '#NAME?', 36: '#NUM!', 42: '#N/A'}
                    if raw[0] not in errors:
                        raise FormulaDataError('invalid array error code')
                    value = errors[raw[0]]
                elif kind == 0x00:  # SerNil has no value.
                    value = ''
                else:
                    raise FormulaDataError('unsupported array value type 0x%02X' % kind)
            text_size += len(value) + 1
            if text_size > MAX_FORMULA_TEXT:
                raise FormulaDataError('array rendered text limit exceeded')
            values.append(value)
        return '{' + ';'.join(','.join(values[i:i + columns])
                              for i in range(0, len(values), columns)) + '}'

    def memory(self, legacy=False):
        """Consume PtgExtraMem in RgbExtra order without materializing ranges.

        [MS-XLS] 2.5.198.61: a count followed by that many Ref8U values.
        This is evaluation metadata, not another formula operand.
        """
        count, = self.unpack('<H')
        width = 6 if legacy else 8
        raw = self.take(count * width)
        for offset in range(0, len(raw), width):
            if legacy:
                first_row, last_row, first_col, last_col = struct.unpack_from('<HHBB', raw, offset)
            else:
                first_row, last_row, first_col, last_col = struct.unpack_from('<4H', raw, offset)
            if first_row > last_row or not 0 <= first_col <= last_col <= 255:
                raise FormulaDataError('invalid memory reference range')


@dataclass
class ExternalName:
    name: str = ''
    scope: int = 0


@dataclass
class SupBook:
    kind: str = 'invalid'
    ordinal: int = 0
    sheets: List[str] = field(default_factory=list)
    names: List[ExternalName] = field(default_factory=list)


class FormulaContext:
    def __init__(self):
        self.biff_version = 0x0600
        self.codepage = 'cp1252'
        self.deleted_labels = []
        self.books = []  # type: List[SupBook]
        self.external_count = 0
        self.xtis = []
        self.sheets = []
        self.names = []
        self.current_book = None
        self.sheet_name_bytes = 0

    def add_deleted_label(self, data, errors):
        # [MS-XLS] Lel / PtgElfLel: ilel 2..2048 indexes this array at ilel-2.
        if len(self.deleted_labels) >= 2047:
            warn(errors, 'Lel count limit exceeded')
            return
        self.deleted_labels.append('')  # Malformed entries still own an index.
        try:
            label = ExtraReader(data).string()
            if not label or len(label) >= 252:
                raise FormulaDataError('invalid label length')
            self.deleted_labels[-1] = label
        except FormulaDataError as exc:
            warn(errors, 'invalid Lel: ' + str(exc))

    def deleted_label(self, index, quoted):
        if not 2 <= index <= 2048 or index - 2 >= len(self.deleted_labels):
            raise FormulaDataError('unresolved PtgElfLel index')
        label = self.deleted_labels[index - 2]
        if not label:
            raise FormulaDataError('unresolved PtgElfLel label')
        return "'" + label.replace("'", "''") + "'" if quoted else label

    def add_supbook(self, data, errors):
        self.current_book = None
        if len(self.books) >= MAX_LINK_ENTRIES:
            warn(errors, 'SupBook count limit exceeded')
            return
        book = SupBook()
        self.books.append(book)  # Preserve indices even for malformed records.
        self.current_book = book
        try:
            reader = ExtraReader(data)
            count, marker = reader.unpack('<HH')
            if marker == 0x0401:
                book.kind = 'internal'
            elif marker == 0x3a01:
                book.kind = 'addin'
            else:
                reader.offset = 2
                path = reader.string()  # virtPath is not formula display text.
                # [MS-XLS] SupBook: these special virtPath values do not
                # represent external books. Keep their XTI indices nonetheless.
                if path in ('\x00', ' '):
                    book.kind = 'current' if path == '\x00' else 'unused'
                    return
                # ctab counts sheets, not link type: external names can belong
                # to a workbook with no sheet list (e.g. macro-only links).
                self.external_count += 1
                book.ordinal = self.external_count
                # DDE/OLE virtPath uses service + 0x03 + topic. In encoded
                # workbook paths, 0x03 also separates directories. DDE has no
                # sheet list and exactly one service/topic separator.
                if (count == 0 and path[:1] not in ('\x01', '\x02', '\x04', '\x05')
                        and path.count('\x03') == 1):
                    book.kind = 'dde'
                    return
                sheets = []
                for _ in range(count):
                    start = reader.offset
                    label = reader.string(max_bytes=MAX_LINK_TEXT_BYTES - self.sheet_name_bytes)
                    self.sheet_name_bytes += reader.offset - start
                    sheets.append(label)
                book.sheets = sheets
                book.kind = 'external'
        except FormulaDataError as exc:
            warn(errors, 'invalid SupBook: ' + str(exc))

    def add_externname(self, data, errors):
        if self.current_book is None:
            warn(errors, 'ExternName without SupBook')
            return
        book = self.current_book
        if len(book.names) >= MAX_LINK_ENTRIES:
            warn(errors, 'ExternName count limit exceeded')
            return
        value = ExternalName()
        book.names.append(value)
        try:
            reader = ExtraReader(data)
            flags, scope, _ = reader.unpack('<HHH')
            # fWantAdvise/fWantPict, fOle/fOleLink, cf and fIcon describe
            # DDE/OLE bodies, not plain workbook names. fBuiltIn is bit 0.
            if flags & 0xfffe or book.kind not in ('external', 'addin'):
                raise FormulaDataError('unsupported DDE/OLE external name')
            label = reader.string(short=True)
            if not label:
                raise FormulaDataError('empty external name')
            value.name, value.scope = label, scope
        except FormulaDataError as exc:
            warn(errors, 'invalid ExternName: ' + str(exc))

    def link(self, index):
        if not 0 <= index < len(self.xtis) or len(self.xtis[index]) != 3:
            raise FormulaDataError('unresolved XTI index')
        book_index, first, last = self.xtis[index]
        if not 0 <= book_index < len(self.books):
            raise FormulaDataError('unresolved SupBook index')
        return self.books[book_index], first, last

    def prefix(self, index):
        book, first, last = self.link(index)
        sheets = self.sheets if book.kind == 'internal' else book.sheets
        if book.kind not in ('internal', 'external'):
            raise FormulaDataError('unresolved external workbook reference')
        if first == 0xffff or last == 0xffff:
            return '#REF!'
        if not 0 <= first <= last < len(sheets):
            raise FormulaDataError('unresolved external sheet index')
        label = sheets[first] + (':' + sheets[last] if last != first else '')
        if book.kind == 'external':
            label = '[%d]' % book.ordinal + label
        return quote_reference(label) + '!'

    def namex(self, index, name_index):
        book, _, _ = self.link(index)
        names = self.names if book.kind == 'internal' else book.names
        if not 1 <= name_index <= len(names) or not names[name_index - 1].name:
            raise FormulaDataError('unresolved NameX index')
        value = names[name_index - 1]
        if book.kind == 'addin':
            return FormulaName(value.name)
        if book.kind not in ('internal', 'external'):
            raise FormulaDataError('unsupported external name link')
        ordinal = 0 if book.kind == 'internal' else book.ordinal
        prefix = '[%d]' % ordinal
        if value.scope:
            sheets = self.sheets if book.kind == 'internal' else book.sheets
            if value.scope > len(sheets):
                raise FormulaDataError('unresolved external name scope')
            prefix = ('' if book.kind == 'internal' else prefix) + sheets[value.scope - 1]
            prefix = quote_reference(prefix)
        return FormulaName(prefix + '!' + value.name)
