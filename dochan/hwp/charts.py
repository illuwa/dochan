"""HWP GSO OLE chart placement and bounded embedded chart extraction."""
import struct
from dataclasses import dataclass

from .. import cfb
from ..hwpx.charts import MAX_XML_BYTES, parse_chart_xml
from ..model.header_footer import Footnote, HeaderFooter
from ..model.image import Image
from ..model.table import Table
from ..utils.bounded_io import BoundedIOError, read_ole_stream


MAX_CHARTS = 256
MAX_CHART_CFB_BYTES = 32 * 1024 * 1024
MAX_DOCUMENT_CHART_XML_BYTES = 32 * 1024 * 1024
MAX_DOCUMENT_CHART_CELLS = 200_000
MAX_EMBEDDED_STREAMS = 64


@dataclass
class ChartReference:
    """Temporary placement marker, replaced before output serialization."""
    bin_id: int


def _chart_elements(item, errors, chart_number, remaining_xml_bytes):
    data = item.data
    if len(data) < 4 or len(data) - 4 > MAX_CHART_CFB_BYTES:
        errors.append('WARN: HWP chart embedded CFB size limit or truncated header')
        return [], 0
    declared = struct.unpack_from('<I', data)[0]
    if declared != len(data) - 4:
        errors.append('WARN: HWP chart embedded CFB length mismatch')
        return [], 0
    try:
        with cfb.OleFileIO(data[4:], strict_recovery=True) as ole:
            streams = ole.listdir()
            if len(streams) > MAX_EMBEDDED_STREAMS:
                errors.append('WARN: HWP chart embedded CFB stream limit exceeded')
                return [], 0
            if not ole.exists('OOXMLChartContents'):
                return [], 0  # Hancom Contents-only or another OLE object.
            xml = read_ole_stream(ole, 'OOXMLChartContents',
                                  max_bytes=min(MAX_XML_BYTES, remaining_xml_bytes))
    except (cfb.CFBError, BoundedIOError, OSError, ValueError) as exc:
        errors.append('WARN: HWP chart embedded OLE unreadable (%s)' % type(exc).__name__)
        return [], 0
    elements, warnings = parse_chart_xml(xml, display_values=True)
    for warning in warnings:
        errors.append('WARN: HWP %s (chart #%d)' % (warning, chart_number))
    return elements, len(xml)


def resolve_charts(doc, bin_items, bin_entries):
    """Replace GSO chart markers in document order, including table cells."""
    count = 0
    xml_bytes = 0
    cells = 0

    def replace(blocks, depth=0):
        nonlocal count, xml_bytes, cells
        if depth > 32:
            doc.errors.append('WARN: HWP chart placement depth limit exceeded')
            return
        out = []
        for block in blocks:
            if isinstance(block, ChartReference):
                count += 1
                if count > MAX_CHARTS:
                    if count == MAX_CHARTS + 1:
                        doc.errors.append('WARN: HWP chart placement count limit exceeded')
                    continue
                index = block.bin_id - 1
                if index < 0 or index >= len(bin_entries):
                    doc.errors.append('WARN: HWP chart BinData reference missing')
                    continue
                entry = bin_entries[index]
                # STORAGE records use the one-based DocInfo slot as BINxxxx.OLE.
                if entry.type != 2:
                    doc.errors.append('WARN: HWP chart BinData is not embedded storage')
                    continue
                item = bin_items.get(block.bin_id)
                if item is None:
                    doc.errors.append('WARN: HWP chart BinData stream missing')
                    continue
                if item.extension != 'ole':
                    doc.errors.append('WARN: HWP chart BinData is not OLE')
                    continue
                elements, size = _chart_elements(
                    item, doc.errors, count, MAX_DOCUMENT_CHART_XML_BYTES - xml_bytes)
                xml_bytes += size
                output_cells = sum(len(row) for elem in elements if isinstance(elem, Table)
                                   for row in elem.rows)
                if cells + output_cells > MAX_DOCUMENT_CHART_CELLS:
                    doc.errors.append('WARN: HWP chart document cell limit exceeded')
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
