"""HWP GSO OLE chart placement and bounded embedded chart extraction."""
import copy
import struct
from dataclasses import dataclass

from .. import cfb
from ..hwpx.charts import MAX_XML_BYTES, parse_chart_xml
from ..model.header_footer import Footnote, HeaderFooter
from ..model.image import Image
from ..model.table import Table
from ..office_binary.ole_objects import parse_embedded_chart
from ..utils.bounded_io import BoundedIOError, read_ole_stream


MAX_CHARTS = 256
MAX_CHART_CFB_BYTES = 4 * 1024 * 1024
MAX_DOCUMENT_CHART_XML_BYTES = 32 * 1024 * 1024
MAX_DOCUMENT_CHART_CELLS = 200_000
MAX_EMBEDDED_STREAMS = 64


@dataclass
class ChartReference:
    """Temporary placement marker, replaced before output serialization."""
    bin_id: int


def discard_chart_references(doc):
    """Remove transient OLE markers after a failed extraction."""
    pending = [section.elements for section in doc.sections]
    seen = set()
    while pending:
        blocks = pending.pop()
        if id(blocks) in seen:
            continue
        seen.add(id(blocks))
        blocks[:] = [block for block in blocks if not isinstance(block, ChartReference)]
        for block in blocks:
            if isinstance(block, Table):
                for row in block.rows:
                    for cell in row:
                        pending.append(cell.paragraphs)
                pending.append(block.caption)
            elif isinstance(block, (Footnote, HeaderFooter)):
                pending.append(block.paragraphs)
            elif isinstance(block, Image):
                pending.append(block.caption)


def _chart_payload(item, errors, remaining_xml_bytes):
    data = item.data
    if len(data) < 4 or len(data) - 4 > MAX_CHART_CFB_BYTES:
        errors.append('WARN: HWP embedded CFB size limit or truncated header')
        return None
    declared = struct.unpack_from('<I', data)[0]
    if declared != len(data) - 4:
        errors.append('WARN: HWP embedded CFB length mismatch')
        return None
    try:
        with cfb.OleFileIO(data[4:], strict_recovery=True) as ole:
            streams = ole.listdir()
            if len(streams) > MAX_EMBEDDED_STREAMS:
                errors.append('WARN: HWP embedded CFB stream limit exceeded')
                return None
            if ole.exists('OOXMLChartContents'):
                if ole.get_size('OOXMLChartContents') > remaining_xml_bytes:
                    errors.append('WARN: HWP chart document byte budget exhausted')
                    return None
                xml = read_ole_stream(ole, 'OOXMLChartContents',
                                      max_bytes=min(MAX_XML_BYTES, remaining_xml_bytes))
                return 'xml', xml
            if ole.exists('\x01CompObj') and (ole.exists('Workbook') or ole.exists('Book')):
                comp = read_ole_stream(ole, '\x01CompObj', max_bytes=4096)
                if b'Excel.Chart.8\0' in comp:
                    name = 'Workbook' if ole.exists('Workbook') else 'Book'
                    if ole.get_size(name) > remaining_xml_bytes:
                        errors.append('WARN: HWP chart document byte budget exhausted')
                        return None
                    book = read_ole_stream(ole, name,
                                           max_bytes=min(MAX_CHART_CFB_BYTES, remaining_xml_bytes))
                    return 'excel', book
            return None  # Hancom Contents-only or another OLE object.
    except (cfb.CFBError, BoundedIOError, OSError, ValueError) as exc:
        errors.append('WARN: HWP embedded OLE unreadable (%s)' % type(exc).__name__)
        return None


def resolve_charts(doc, bin_items, bin_entries, *, existing_cells=0):
    """Replace GSO chart markers in document order, including table cells."""
    count = 0
    xml_bytes = 0
    cells = existing_cells
    cache = {}
    parsed = {}
    warned = set()
    too_deep = False

    def warn_once(message):
        if message not in warned:
            warned.add(message)
            doc.errors.append(message)

    def replace(blocks, depth=0):
        nonlocal count, xml_bytes, cells, too_deep
        if depth > 32:
            too_deep = True
            warn_once('WARN: HWP chart placement depth limit exceeded')
            return
        out = []
        for block in blocks:
            if isinstance(block, ChartReference):
                index = block.bin_id - 1
                if index < 0 or index >= len(bin_entries):
                    warn_once('WARN: HWP OLE BinData reference missing')
                    continue
                entry = bin_entries[index]
                if entry.type != 2:
                    continue
                storage_id = entry.bin_data_id
                item = bin_items.get(storage_id)
                if item is None:
                    warn_once('WARN: HWP OLE BinData stream missing')
                    continue
                if item.extension != 'ole':
                    continue
                if storage_id not in cache:
                    extraction_warnings = []
                    cache[storage_id] = _chart_payload(
                        item, extraction_warnings,
                        MAX_DOCUMENT_CHART_XML_BYTES - xml_bytes)
                    for warning in extraction_warnings:
                        warn_once(warning)
                payload = cache[storage_id]
                if payload is None:
                    continue
                count += 1
                if count > MAX_CHARTS:
                    warn_once('WARN: HWP chart placement count limit exceeded')
                    continue
                kind, data = payload
                if storage_id not in parsed:
                    # Parse each storage once and spend its bytes before
                    # parsing, so empty or failing charts cannot be
                    # re-parsed per reference.
                    if xml_bytes + len(data) > MAX_DOCUMENT_CHART_XML_BYTES:
                        warn_once('WARN: HWP chart document byte budget exhausted')
                        parsed[storage_id] = []
                        continue
                    xml_bytes += len(data)
                    try:
                        if kind == 'xml':
                            elements, warnings = parse_chart_xml(data, display_values=True)
                        else:
                            warnings = []
                            elements = parse_embedded_chart(data, warnings, False,
                                                            [MAX_DOCUMENT_CHART_CELLS - cells],
                                                            chart_object=True)
                    except (ValueError, BoundedIOError, TypeError) as exc:
                        warn_once('WARN: HWP chart payload unreadable (%s)' % type(exc).__name__)
                        elements, warnings = [], []
                    for warning in warnings:
                        warn_once('WARN: HWP %s' % warning.removeprefix('WARN: '))
                    parsed[storage_id] = elements
                    elements = parsed[storage_id]
                else:
                    # Each placement gets its own model objects.
                    elements = copy.deepcopy(parsed[storage_id])
                if not elements:
                    continue
                output_cells = sum(len(row) for elem in elements if isinstance(elem, Table)
                                   for row in elem.rows)
                if cells + output_cells > MAX_DOCUMENT_CHART_CELLS:
                    warn_once('WARN: HWP chart document cell limit exceeded')
                    continue
                cells += output_cells
                out.extend(elements)
            else:
                if isinstance(block, Table):
                    for row in block.rows:
                        for cell in row:
                            replace(cell.paragraphs, depth + 1)
                    replace(block.caption, depth + 1)
                elif isinstance(block, (Footnote, HeaderFooter)):
                    replace(block.paragraphs, depth + 1)
                elif isinstance(block, Image):
                    replace(block.caption, depth + 1)
                out.append(block)
        blocks[:] = out

    for section in doc.sections:
        replace(section.elements)
    if too_deep:
        discard_chart_references(doc)
