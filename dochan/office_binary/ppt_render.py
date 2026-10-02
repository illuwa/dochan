"""Render resolved PPT objects through the existing PPTX model contracts."""
import struct
from bisect import bisect_left
from dataclasses import replace

from ..conversion import AssetRef, Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from ..model.image import Image
from .officeart import Limits, parse_records, read_bstore, read_shapes, walk_records
from .ppt_structure import resolve_presentation, warn
from .ppt_text import TextBlock, apply_auto_numbers, read_hyperlinks, render_text, shape_hyperlink, text_blocks
from .ppt_shapes import positioned_shapes, table_from_shape
from .ppt_styles import merge_styles, read_master_styles

MAX_SHAPES = 100000
MAX_IMAGES = 10000
MAX_TEXT_CHARS = 8 * 1024 * 1024
MAX_OUTPUT_PARAGRAPHS = 100000
MAX_DOCUMENT_CELLS = 200000


def placeholder(shape):
    for atom in parse_records(shape.client_data):
        if atom.header.rec_type == 3011 and len(atom.data) >= 8:
            return atom.data[4]
    return None


def sheet_shapes(sheet, errors):
    shapes = []
    for drawing in sheet.record.children:
        if drawing.header.rec_type == 1036:
            shapes.extend(read_shapes(drawing.children or parse_records(drawing.data, errors=errors), errors=errors))
    return shapes


def read_structured_ppt(data, current_user, pictures, stream_name, errors):
    presentation = resolve_presentation(data, current_user, errors)
    if presentation is None:
        return None
    doc = Document(source_format="ppt", errors=errors)
    labels = {}
    links = read_hyperlinks(presentation.document.children, [s.slide_id for s in presentation.slides], labels)
    entries = read_bstore(presentation.document.children, delayed_stream=pictures, errors=errors)
    renderer = _Renderer(doc, entries, links, stream_name)
    renderer.slide_count = len(presentation.slides)
    renderer.link_labels = labels
    environment_styles = read_master_styles(walk_records(presentation.document.children), errors)
    style_cache = {}

    def defaults(sheet):
        # fFollowMasterObjects controls displayed objects, not character
        # inheritance. A slide can hide master graphics and still use its font.
        chain = []
        seen = set()
        current = sheet
        while current is not None and len(chain) < 32:
            current_record = current.recovery_record or current.record
            # Stream offsets remain stable when a recovery Sheet is replaced
            # and its temporary Python identity is later reused.
            key = current_record.offset
            if key in seen:
                break
            seen.add(key)
            if key not in style_cache:
                style_cache[key] = read_master_styles(current_record.children, errors)
            chain.append(style_cache[key])
            current = presentation.masters.get(current.master_id)
        return merge_styles(environment_styles, *reversed(chain))
    from .ole_objects import PptObjects
    renderer.objects = PptObjects(presentation.embedded, errors, presentation.embedded_progids)
    unresolved_reference = False
    renderer.font_names = {a.header.rec_instance: bytes(a.data[:64]).decode('utf-16le', errors='replace').split('\0')[0]
                           for a in walk_records(presentation.document.children) if a.header.rec_type == 4023}
    for index, slide in enumerate(presentation.slides, 1):
        if (renderer.remaining <= 0 or renderer.remaining_text <= 0 or renderer.remaining_paragraphs <= 0
                or renderer.shape_visit_budget[0] <= 0):
            warn(errors, "document rendering budget exceeded")
            break
        path = "%s#slide%d" % (stream_name, index)
        provenance = Provenance(source_format="ppt", slide=index, path=path)
        section = Section(provenance=provenance)
        images = []
        if getattr(slide, 'recovery_record', None) is not None:
            slide = replace(slide, record=slide.recovery_record)
        # fFollowMasterObjects is bit 0 of SlideAtom flags. Master placeholder
        # prompts are editing scaffolding, not inherited displayed text.
        seen = set()
        master_id = slide.master_id if slide.flags & 1 else 0
        masters = []
        while master_id and master_id not in seen and len(seen) < 32:
            seen.add(master_id)
            master = presentation.masters.get(master_id)
            if master is None:
                warn(errors, "master slide reference missing")
                unresolved_reference = True
                break
            masters.append(master)
            master_id = master.master_id if master.flags & 1 else 0
        if master_id and master_id in seen and len(masters) > 1:
            warn(errors, "master slide cycle")
        for master in reversed(masters):
            mp = Provenance(source_format="ppt", slide=index, path=path + "#master")
            section.elements.extend(renderer.sheet(master, mp, images, inherited=True, styles=defaults(master)))
        section.elements.extend(renderer.sheet(slide, provenance, images, styles=defaults(slide)))
        if slide.notes_id:
            notes = presentation.notes.get(slide.notes_id)
            if notes is not None:
                np = Provenance(source_format="ppt", slide=index, path=path + "#notes")
                section.elements.extend(renderer.sheet(notes, np, images, notes=True))
            else:
                warn(errors, "notes slide reference missing")
                unresolved_reference = True
        section.elements.extend(renderer.comments(slide, provenance))
        doc.sections.append(section)
    sheets = presentation.slides + list(presentation.masters.values()) + list(presentation.notes.values())
    empty_text = not any(p.text.strip() for p in doc.find_all('paragraph'))
    truncated_tree = any(error.startswith('WARN: OfficeArt truncated record at ') for error in errors)
    if (not presentation.slides or (empty_text and truncated_tree) or unresolved_reference
            or any(sheet.unresolved and sheet.recovery_record is None for sheet in sheets)):
        from .ppt import _supplement_legacy_text
        _supplement_legacy_text(doc, data, stream_name, renderer.remaining_text, renderer.remaining_paragraphs,
                                master_ids=presentation.masters)
    return doc


class _Renderer:
    def __init__(self, doc, entries, links, stream_name):
        self.doc = doc
        self.entries = entries
        self.links = links
        self.stream_name = stream_name
        self.remaining = MAX_SHAPES
        self.image_count = 0
        self.assets = set()
        self.remaining_text = MAX_TEXT_CHARS
        self.remaining_paragraphs = MAX_OUTPUT_PARAGRAPHS
        # Each nonempty fragment consumes at least one input character. Share
        # this processing bound across blocks rather than cutting a large atom
        # at 100,000 boundaries (including ordinary paragraph separators).
        self.fragment_budget = [MAX_TEXT_CHARS]
        self.cell_budget = [MAX_DOCUMENT_CELLS]
        self.shape_visit_budget = [MAX_SHAPES]
        self.drawing_record_budget = MAX_SHAPES * 16
        self.shape_cache = {}
        self.comment_cache = {}
        self.comment_record_budget = 100000
        self.font_names = {}
        self.field_values = {}
        self.objects = None
        self.slide_count = 0
        self.link_labels = {}
        self.default_styles = {}

    def text(self, block, provenance, link=""):
        if len(block.text) > self.remaining_text or self.remaining_paragraphs <= 0:
            self.remaining_text = 0
            warn(self.doc.errors, "document text budget exceeded")
            return []
        # Meta-character atoms identify a UTF-16 position. Never replace an
        # unmarked literal '*', or synthesize a date from the current clock.
        encoded = block.text.encode("utf-16le")
        fields = {struct.unpack_from('<I', a.data)[0]: a.header.rec_type
                  for a in block.records if a.header.rec_type in (4056, 4087, 4088, 4089, 4090, 4117)
                  and len(a.data) >= 4}
        styles = block.character_runs
        bullets = block.paragraph_bullets
        levels = block.paragraph_levels
        records = block.records
        changes = []
        pieces = []
        cursor = 0
        total_delta = 0
        for offset, kind in sorted(fields.items()):
            if encoded[offset * 2:offset * 2 + 2] != b"*\0":
                continue
            value = str(provenance.slide) if kind == 4056 else self.field_values.get(kind, '')
            if not value:
                warn(self.doc.errors, 'field has no saved display value; meta-character omitted')
            replacement = value.encode('utf-16le')
            delta = len(replacement) // 2 - 1
            if len(encoded) // 2 + total_delta + delta > MAX_TEXT_CHARS:
                warn(self.doc.errors, 'field expansion text budget exceeded')
                replacement = b''
                delta = -1
            pieces.extend((encoded[cursor:offset * 2], replacement))
            cursor = offset * 2 + 2
            total_delta += delta
            changes.append((offset, total_delta))
        if changes:
            pieces.append(encoded[cursor:])
            encoded = b''.join(pieces)
            offsets = [offset for offset, _delta in changes]
            def shift(position):
                i = bisect_left(offsets, position)
                return position + (changes[i - 1][1] if i else 0)
            styles = [(shift(start), shift(end), props) for start, end, props in styles]
            bullets = [(shift(start), shift(end), value) for start, end, value in bullets]
            levels = [(shift(start), shift(end), level) for start, end, level in levels]
            records = [replace(a, data=memoryview(struct.pack('<II', *[shift(v) for v in struct.unpack_from('<II', a.data)]) + bytes(a.data[8:])))
                       if a.header.rec_type == 4063 and len(a.data) >= 8 else a for a in records]
        if fields:
            block = replace(block, text=encoded.decode('utf-16le', errors='replace'), character_runs=styles,
                            paragraph_bullets=bullets, paragraph_levels=levels, records=records)
        paragraphs = render_text(block, provenance, self.links, link,
                                 max_output_chars=self.remaining_text, errors=self.doc.errors,
                                 font_names=self.font_names, fragment_budget=self.fragment_budget,
                                 slide_index=getattr(provenance, 'slide', 0) or 0, slide_count=self.slide_count,
                                 default_styles=self.default_styles)
        if len(paragraphs) > self.remaining_paragraphs:
            warn(self.doc.errors, "document paragraph count limit exceeded")
            paragraphs = paragraphs[:self.remaining_paragraphs]
        self.remaining_paragraphs -= len(paragraphs)
        self.remaining_text -= sum(len(run.text) for para in paragraphs for run in para.runs)
        return paragraphs

    def sheet(self, sheet, provenance, images, inherited=False, notes=False, styles=None):
        if (self.remaining <= 0 or self.remaining_text <= 0 or self.remaining_paragraphs <= 0
                or self.shape_visit_budget[0] <= 0):
            warn(self.doc.errors, "document rendering budget exceeded")
            return []
        if getattr(sheet, 'recovery_record', None) is not None:
            sheet = replace(sheet, record=sheet.recovery_record)
        self.field_values = {}
        self.default_styles = styles or {}
        # Local HeaderFooter values are saved display text, unlike master prompts.
        for container in sheet.record.children:
            if container.header.rec_type == 4057:
                for atom in container.children:
                    if atom.header.rec_type == 4026:
                        kind = {0: 4088, 1: 4089, 2: 4090}.get(atom.header.rec_instance)
                        if kind:
                            self.field_values[kind] = bytes(atom.data[:65536]).decode('utf-16le', errors='replace').rstrip('\0')
        outlines = text_blocks(sheet.text_records, self.doc.errors)
        consumed = set()
        key = sheet.record.offset
        if key not in self.shape_cache:
            count = 0
            for drawing in sheet.record.children:
                if drawing.header.rec_type == 1036:
                    for _record in walk_records(drawing.children):
                        count += 1
                        if count > self.drawing_record_budget:
                            warn(self.doc.errors, 'drawing parse budget exceeded')
                            self.remaining = 0
                            return []
            self.drawing_record_budget -= count
            shapes = sheet_shapes(sheet, self.doc.errors)
            positioned = positioned_shapes(shapes, self.doc.errors, shape_budget=self.shape_visit_budget)
            self.shape_cache[key] = (shapes, positioned)
        shapes, positioned = self.shape_cache[key]

        def render(shape):
            if self.remaining <= 0:
                warn(self.doc.errors, "document shape count limit exceeded")
                return []
            self.remaining -= 1
            ph = placeholder(shape)
            if inherited and ph is not None:
                return []
            if notes and ph in (5, 7, 8, 9, 10, 11):
                return []  # Slide thumbnails, date/header/footer/slide number.
            object_id = None
            if self.objects is not None:
                for atom in parse_records(shape.client_data, errors=self.doc.errors):
                    if atom.header.rec_type == 3009 and len(atom.data) >= 4:
                        object_id = struct.unpack_from('<I', atom.data)[0]
                        embedded = self.objects.at(object_id, provenance)
                        if embedded:
                            return embedded
            if shape.children:
                table = table_from_shape(shape, render, provenance, errors=self.doc.errors,
                                         cell_budget=self.cell_budget)
                if table is not None:
                    return [table]
                # A damaged table still retains readable child shape text.
                return [element for _y, _x, _ordinal, child in positioned_shapes(shape.children, self.doc.errors, shape_budget=self.shape_visit_budget)
                        for element in render(child)]
            records = parse_records(shape.client_textbox, errors=self.doc.errors)
            blocks = text_blocks(records, self.doc.errors)
            for atom in records:
                if atom.header.rec_type == 3998 and len(atom.data) >= 4:
                    reference = struct.unpack_from("<I", atom.data)[0]
                    if reference < len(outlines):
                        blocks.append(outlines[reference])
                        consumed.add(reference)
                    else:
                        warn(self.doc.errors, "OutlineTextRefAtom index out of range")
            client_records = parse_records(shape.client_data, errors=self.doc.errors)
            extensions = []
            for tag in walk_records(client_records):
                if tag.header.rec_type != 5002:
                    continue
                if not any(a.header.rec_type == 4026 and bytes(a.data) == '___PPT9'.encode('utf-16le')
                           for a in tag.children):
                    continue
                for binary in tag.children:
                    if binary.header.rec_type == 5003:
                        extensions.extend(a for a in parse_records(binary.data, errors=self.doc.errors)
                                          if a.header.rec_type == 4012)
            if extensions:
                # Do not mutate cached SlideListWithText blocks shared by
                # other placements or inherited sheets.
                blocks = [replace(b, paragraph_numbers=[]) for b in blocks]
                apply_auto_numbers(blocks, extensions[0].data, self.doc.errors)
            link = shape_hyperlink(client_records, self.links,
                                   slide_index=provenance.slide or 0, slide_count=self.slide_count)
            elements = [p for block in blocks for p in self.text(block, provenance, link)]
            if not any(block.text.strip() for block in blocks):
                wordart = shape._text(0x00C0)
                if wordart:
                    elements.extend(self.text(TextBlock(text=wordart, text_type=4), provenance, link))
            if link and not elements:
                label = shape.description or shape.name
                for atom in walk_records(client_records):
                    if atom.header.rec_type == 4083 and len(atom.data) >= 16 and atom.data[8] == 4:
                        label = label or self.link_labels.get(struct.unpack_from('<I', atom.data, 4)[0], '')
                        break
                if label:
                    elements.extend(self.text(TextBlock(text=label, text_type=4), provenance, link))
            # PPTX follows layout objects but does not traverse slide masters.
            # Keep the established inherited text contract, excluding recurring
            # master picture placements and their Markdown/image assets.
            if shape.pib and not inherited:
                elements.extend(self.image(shape, provenance, images))
            if object_id is not None and object_id in self.objects.supported and not elements:
                elements.extend(self.text(TextBlock(text=shape.description or shape.name or '[내장 개체]',
                                                    text_type=4), provenance))
            return elements

        elements = []
        for _y, _x, _ordinal, shape in positioned:
            elements.extend(render(shape))
        # Some producers store text exclusively in SlideListWithText, with no
        # OfficeArt textbox reference. Keep unreferenced blocks exactly once.
        for i, block in enumerate(outlines):
            if i not in consumed:
                elements.extend(self.text(block, provenance))
        if not shapes and not outlines:
            elements.extend(p for block in text_blocks(sheet.record.children, self.doc.errors)
                            for p in self.text(block, provenance))
        return elements

    def comments(self, sheet, provenance):
        """Only read comment extensions of the resolved latest slide object."""
        elements = []
        cp = replace(provenance, path=provenance.path + '#comments')
        key = sheet.record.offset
        if key not in self.comment_cache:
            self.comment_cache[key] = self.comment_values(sheet)
        for value in self.comment_cache[key]:
            if len(value) > self.remaining_text or self.remaining_paragraphs <= 0:
                warn(self.doc.errors, 'document comment output budget exceeded')
                break
            elements.append(Paragraph(runs=[TextRun(text=value, provenance=cp)], provenance=cp))
            self.remaining_text -= len(value)
            self.remaining_paragraphs -= 1
        return elements

    def comment_values(self, sheet):
        values_out = []
        for tag in walk_records(sheet.record.children):
            if self.comment_record_budget <= 0:
                warn(self.doc.errors, 'comment record scan budget exceeded')
                break
            self.comment_record_budget -= 1
            if tag.header.rec_type != 5002:
                continue
            names = [bytes(a.data).decode('utf-16le', errors='replace').rstrip('\0')
                     for a in tag.children if a.header.rec_type == 4026]
            if '___PPT10' not in names:
                continue
            for binary in tag.children:
                if binary.header.rec_type != 5003 or self.comment_record_budget <= 0:
                    continue
                records = parse_records(binary.data, limits=Limits(max_records=self.comment_record_budget), errors=self.doc.errors)
                for comment in walk_records(records):
                    self.comment_record_budget -= 1
                    if comment.header.rec_type != 12000:
                        continue
                    values = {a.header.rec_instance: bytes(a.data[:MAX_TEXT_CHARS * 2]).decode('utf-16le', errors='replace').rstrip('\0').strip()
                              for a in comment.children if a.header.rec_type == 4026}
                    body = values.get(1, '').replace('\r\n', '\n').replace('\r', '\n')
                    if body:
                        author = values.get(0, '')
                        value = '[comment: %s%s]' % (author + ': ' if author else '', body)
                        values_out.append(value)
        return values_out

    def image(self, shape, provenance, images):
        if self.image_count >= MAX_IMAGES:
            warn(self.doc.errors, "image placement count limit exceeded")
            return []
        self.image_count += 1
        entry = self.entries[shape.pib - 1] if 0 < shape.pib <= len(self.entries) else None
        fmt, pixels = entry.image if entry is not None and entry.image else ("", b"")
        if entry is None or not pixels:
            warn(self.doc.errors, "picture BLIP unavailable for pib %d" % shape.pib)
        filename = "image%d.%s" % (shape.pib, fmt or "bin")
        target = "Pictures/" + filename
        # PPTX's image label combines description and shape name. pibName is
        # the saved picture description when wzDescription is absent.
        label = ' '.join(part for part in (shape.description or shape._text(0x0105), shape.name)
                         if part).strip() or "image"
        reference_size = len(label) + len(target) + 5
        if reference_size > self.remaining_text or self.remaining_paragraphs <= 0:
            self.remaining_text = 0
            warn(self.doc.errors, "document text budget exceeded by picture description")
            return []
        self.remaining_text -= reference_size
        self.remaining_paragraphs -= 1
        if shape.pib not in self.assets:
            self.assets.add(shape.pib)
            self.doc.assets.append(AssetRef(
                id="ppt-image-%d" % shape.pib, source_path=target, filename=filename,
                content_type={"jpg": "image/jpeg", "png": "image/png", "bmp": "image/bmp",
                              "tiff": "image/tiff", "wmf": "image/x-wmf", "emf": "image/x-emf",
                              "pict": "image/x-pict"}.get(fmt, "application/octet-stream"),
                metadata={"kind": "image", "label": label},
            ))
        # Emit one Image at the drawing position. The Markdown writer owns
        # reference syntax; JSON/plain text must not contain Markdown runs.
        return [Image(bin_id=shape.pib, filename=target, image_data=pixels,
                      alt_text=label, image_format=fmt,
                      provenance=Provenance(source_format="ppt", slide=provenance.slide, path=target))]
