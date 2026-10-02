"""PPT OfficeArt geometry and native table groups ([MS-PPT], [MS-ODRAW]).

PPT's compact ClientAnchor stores top/left/right/bottom whereas OfficeArt
ChildAnchor and FSPGR store left/top/right/bottom. Tables are explicitly
marked by the tableProperties property; visual resemblance is not enough.
"""
import struct
from dataclasses import replace
from fractions import Fraction

from ..model.table import Cell, Table


MAX_SHAPES = 100000
MAX_GROUP_DEPTH = 32
MAX_TABLE_CELLS = 100000


def _warn(errors, message):
    message = "WARN: PPT " + message
    if errors is not None and len(errors) < 1000 and message not in errors:
        errors.append(message)


def shape_bounds(shape):
    """Return left, top, right, bottom in the containing coordinate system."""
    if shape.child_anchor is not None:
        return shape.child_anchor
    anchor = shape.client_anchor
    if len(anchor) == 8:
        top, left, right, bottom = struct.unpack("<4h", anchor)
        return left, top, right, bottom
    if len(anchor) == 16:
        top, left, right, bottom = struct.unpack("<4i", anchor)
        return left, top, right, bottom
    return (0, 0, 0, 0)


def _group_bounds(shape):
    if shape.record is not None:
        for record in shape.record.children:
            if record.header.rec_type == 0xF009 and len(record.data) >= 16:
                return struct.unpack_from("<4i", record.data)
    return None


def is_table_shape(shape):
    prop = shape.properties.get(0x039F)
    return bool(shape.is_group and prop is not None and not prop.is_complex and prop.value & 1)


def positioned_shapes(shapes, errors=None, shape_budget=None):
    """Flatten groups and return stable (y, x, ordinal, Shape) reading order.

    Table frames remain intact for ``table_from_shape``. Fraction arithmetic
    prevents rounding at successive nested group transforms. The patriarch
    is the drawing root, not a shape with its own slide-space anchor.
    ``shape_budget`` counts every visited node, including empty groups, and
    can be shared across all sheets in a document.
    """
    positioned = []
    seen = set()
    ordinal = [0]

    def collect(items, transform, depth):
        if depth > MAX_GROUP_DEPTH:
            _warn(errors, "group depth limit exceeded")
            return
        sx, sy, dx, dy = transform
        for shape in items:
            if shape_budget is not None:
                if shape_budget[0] <= 0:
                    _warn(errors, "document shape traversal budget exceeded")
                    return
                shape_budget[0] -= 1
            if len(seen) >= MAX_SHAPES:
                _warn(errors, "shape count limit exceeded")
                return
            identity = id(shape)
            if identity in seen:
                _warn(errors, "repeated or cyclic group shape")
                continue
            seen.add(identity)
            left, top, right, bottom = shape_bounds(shape)
            if shape.is_group and not is_table_shape(shape):
                child_transform = transform
                local = _group_bounds(shape)
                if local is not None and not shape.is_patriarch:
                    x0, y0, x1, y1 = local
                    if x1 == x0 or y1 == y0:
                        _warn(errors, "degenerate group coordinate bounds")
                    elif shape.child_anchor is not None or shape.client_anchor:
                        ax = Fraction(right - left, x1 - x0)
                        ay = Fraction(bottom - top, y1 - y0)
                        origin_x, origin_y = left, top
                        if shape.flags & 0x40:  # OfficeArtFSP.fFlipH
                            ax, origin_x = -ax, right
                        if shape.flags & 0x80:  # OfficeArtFSP.fFlipV
                            ay, origin_y = -ay, bottom
                        child_transform = (sx * ax, sy * ay,
                                           dx + sx * (origin_x - x0 * ax),
                                           dy + sy * (origin_y - y0 * ay))
                collect(shape.children, child_transform, depth + 1)
            else:
                # Mirrored/scaled groups can reverse the rectangle endpoints.
                x = min(sx * left + dx, sx * right + dx)
                y = min(sy * top + dy, sy * bottom + dy)
                positioned.append((y, x, ordinal[0], shape))
                ordinal[0] += 1

    collect(shapes, (Fraction(1), Fraction(1), Fraction(0), Fraction(0)), 0)
    return sorted(positioned, key=lambda item: item[:3])


def table_from_shape(shape, render_shape, provenance, errors=None,
                     max_cells=MAX_TABLE_CELLS, cell_budget=None):
    """Build the existing Table/Cell model from a table's rectangular cells.

    Shared exact cell edges define the grid; a rectangle crossing multiple
    intervals becomes a merged cell. Line shapes are table borders, not cells.
    Table row-height metadata is rounded independently by Office, so it must
    not invent thin rows that do not exist in the actual cell rectangles.
    Invalid overlapping or oversized grids return None for caller fallback.
    ``max_cells`` supplies the caller's remaining whole-document budget; both
    this budget and the per-table ceiling apply before allocating Cell models.
    """
    if not is_table_shape(shape):
        return None
    cells = []
    if len(shape.children) > MAX_SHAPES:
        _warn(errors, "table shape count limit exceeded")
        return None
    for child in shape.children:
        if child.shape_type != 1:
            continue
        left, top, right, bottom = shape_bounds(child)
        if right <= left or bottom <= top:
            continue
        cells.append((left, top, right, bottom, child))
    if not cells:
        _warn(errors, "table has no rectangular cells")
        return None
    xs = sorted({value for left, _, right, _, _ in cells for value in (left, right)})
    ys = sorted({value for _, top, _, bottom, _ in cells for value in (top, bottom)})
    cols, rows = len(xs) - 1, len(ys) - 1
    available = min(MAX_TABLE_CELLS, max_cells, cell_budget[0] if cell_budget is not None else MAX_TABLE_CELLS)
    if rows * cols > available:
        _warn(errors, "table grid cell limit exceeded")
        return None
    xi = {value: index for index, value in enumerate(xs)}
    yi = {value: index for index, value in enumerate(ys)}
    occupied = set()
    placements = []
    for left, top, right, bottom, child in cells:
        col, row = xi[left], yi[top]
        col_end, row_end = xi[right], yi[bottom]
        for r in range(row, row_end):
            for c in range(col, col_end):
                if (r, c) in occupied:
                    _warn(errors, "overlapping table cell rectangles")
                    return None
                occupied.add((r, c))
        placements.append((row, col, row_end - row, col_end - col, child))

    def cell_provenance(row, col):
        return replace(provenance, cell="R%dC%d" % (row + 1, col + 1)) if provenance is not None else None

    # Reserve before callbacks, which may themselves render another table.
    if cell_budget is not None:
        cell_budget[0] -= rows * cols
    grid = [[Cell(row=r, col=c, provenance=cell_provenance(r, c))
             for c in range(cols)] for r in range(rows)]
    for row, col, row_span, col_span, child in placements:
        cell = grid[row][col]
        cell.row_span, cell.col_span = row_span, col_span
        cell.paragraphs = render_shape(child)
        for r in range(row, row + row_span):
            for c in range(col, col + col_span):
                if r != row:
                    grid[r][c].row_span = 0
                if c != col:
                    grid[r][c].col_span = 0
    return Table(rows=grid)
