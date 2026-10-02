"""Assemble MS-DOC PAPX table boundaries into the existing Table model.

TDefTable supplies a row-local grid and 20-byte TC80 descriptors. The union
of row boundaries supplies column coordinates, including implicit grid spans.
No whitespace or text-content heuristics participate in table detection.
"""
import struct

from ..model.table import Cell, Table

MAX_DEPTH = 32
MAX_CELLS = 100000


def _definition(data, warnings):
    if not data:
        return [], []
    count = data[0]
    tc_start = 1 + (count + 1) * 2
    if not count or count > 63 or tc_start > len(data):
        warnings.append('WARN: DOC truncated TDefTable; cell text retained')
        return [], []
    edges = list(struct.unpack_from('<%dh' % (count + 1), data, 1))
    if any(a >= b for a, b in zip(edges, edges[1:])):
        warnings.append('WARN: DOC invalid table grid; cell text retained')
        return [], []
    # TC records can be absent; in that case all flags have their defaults.
    flags = [struct.unpack_from('<H', data, tc_start + i * 20)[0]
             if tc_start + (i + 1) * 20 <= len(data) else 0
             for i in range(count)]
    return edges, flags


class _TableBuilder:
    def __init__(self, depth, warnings):
        self.depth = depth
        self.warnings = warnings
        self.rows = []
        self.cells = []
        self.blocks = []
        self.cell_count = 0
        self.fallback = None

    @staticmethod
    def _flatten(blocks):
        for block in blocks:
            if isinstance(block, Table):
                for row in block.rows:
                    for cell in row:
                        yield from _TableBuilder._flatten(cell.paragraphs)
            else:
                yield block

    def degrade(self):
        if self.fallback is not None:
            return
        self.warnings.append('WARN: DOC table cell limit exceeded; table retained as paragraphs')
        self.fallback = list(self._flatten(
            block for cells, _, _ in self.rows for cell in cells for block in cell.paragraphs))
        self.blocks = list(self._flatten(
            block for cell in self.cells for block in cell.paragraphs)) + self.blocks
        self.rows = []
        self.cells = []

    def cell(self):
        if self.fallback is not None:
            return
        if self.cell_count + len(self.cells) + 1 > MAX_CELLS:
            self.degrade()
            return
        self.cells.append(Cell(paragraphs=self.blocks))
        self.blocks = []

    def row(self, props):
        # A deleted row mark removes the whole row in the accepted view.
        if props.get('deleted_mark'):
            self.blocks = []
            self.cells = []
            return
        if self.fallback is not None:
            self.fallback.extend(self._flatten(self.blocks))
            self.blocks = []
            return
        if self.blocks:
            self.cell()
        if self.fallback is not None:
            self.row(props)
            return
        edges, flags = _definition(props.get('table_def', b''), self.warnings)
        count = max(len(self.cells), len(edges) - 1)
        if self.cell_count + count > MAX_CELLS:
            self.degrade()
            self.row(props)
            return
        self.cell_count += count
        for operand in props.get('vert_merge', []):
            # sprmTVertMerge: itc (one byte), fVertMerge (two-bit value).
            if len(operand) >= 2 and operand[0] < len(flags):
                i, value = operand[:2]
                flags[i] = (flags[i] & ~0x60) | ((value & 3) << 5)
        while edges and len(self.cells) < len(edges) - 1:
            self.cells.append(Cell())
        if self.cells:
            self.rows.append((self.cells, edges, flags))
        self.cells = []

    def finish(self):
        if self.blocks or self.cells:
            self.row({})
        if self.fallback is not None:
            return self.fallback
        grid = sorted({edge for _, edges, _ in self.rows for edge in edges})
        # Every cell allocation, including grid expansion, counts toward limit.
        width = max([len(grid) - 1] + [len(c) for c, _, _ in self.rows])
        if width * len(self.rows) > MAX_CELLS:
            self.degrade()
            return self.fallback
        indices = {edge: i for i, edge in enumerate(grid)}
        table = Table()
        vertical = {}
        for row_index, (cells, edges, flags) in enumerate(self.rows):
            row = [Cell(row=row_index, col=c) for c in range(width)]
            previous = None
            active = {}
            vertical_flags = []
            for i, cell in enumerate(cells):
                col = indices[edges[i]] if i + 1 < len(edges) else i
                right = indices[edges[i + 1]] if i + 1 < len(edges) else col + 1
                if col >= width:
                    continue
                cell.row, cell.col, cell.col_span = row_index, col, max(1, right - col)
                flag = flags[i] if i < len(flags) else 0
                row[col] = cell
                for covered in range(col + 1, min(right, width)):
                    row[covered].col_span = 0
                if flag & 2 and previous is not None:
                    previous.col_span = right - previous.col
                    previous.paragraphs.extend(cell.paragraphs)
                    cell.paragraphs = []
                    cell.col_span = 0
                else:
                    previous = cell if flag & 1 else None
                vertical_flags.append((cell, flag))
            # Horizontal merges must finish before matching vertical grids;
            # following rows may encode the same span as a single wide TC.
            for cell, flag in vertical_flags:
                if cell.is_merged_away:
                    continue
                key = (cell.col, cell.col + cell.col_span)
                if flag & 0x20:
                    if flag & 0x40:
                        active[key] = cell
                    elif key in vertical:
                        origin = vertical[key]
                        origin.row_span += 1
                        origin.paragraphs.extend(cell.paragraphs)
                        cell.paragraphs = []
                        cell.row_span = 0
                        active[key] = origin
                # A non-merged row terminates any prior vertical continuation.
            vertical = active
            table.rows.append(row)
        return table


def assemble_blocks(records, render, warnings):
    """Render paragraph records, nesting tables at their actual host-cell CP."""
    output = []
    stack = []

    def close():
        table = stack.pop().finish()
        destination = stack[-1].blocks if stack else output
        if isinstance(table, list):
            destination.extend(table)
        elif table.rows:
            destination.append(table)

    for record in records:
        props = record.props
        depth = max(1, props.get('itap', 0)) if props.get('in_table') else 0
        if depth > MAX_DEPTH:
            warnings.append('WARN: DOC table nesting limit exceeded; text retained')
            depth = 0
        while stack and stack[-1].depth > depth:
            close()
        if not depth:
            output.extend(render(record))
            continue
        while not stack or stack[-1].depth < depth:
            stack.append(_TableBuilder(stack[-1].depth + 1 if stack else 1, warnings))
        builder = stack[-1]
        if props.get('row_end') or props.get('inner_row'):
            builder.row(props)
        else:
            builder.blocks.extend(render(record))
            if record.text.endswith('\x07') or props.get('inner_cell'):
                builder.cell()
    while stack:
        close()
    return output
