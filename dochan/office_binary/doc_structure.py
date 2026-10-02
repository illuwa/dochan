"""Render native DOC structures through the established document model."""
import re

from ..conversion import Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from .doc_binary import DocBinary
from .doc_tables import assemble_blocks

_FORMATS = ('bold', 'italic', 'underline', 'strikeout', 'superscript', 'subscript')
_SPECIAL = re.compile(r'[\x00-\x1f\u00ad\u2011]')


def _unicode(text):
    # Join UTF-16 surrogate code units only after all CP-indexed operations.
    return text.encode('utf-16-le', errors='surrogatepass').decode('utf-16-le', errors='replace')


class StructureRenderer:
    def __init__(self, binary, doc, stories, pictures, objects=None):
        self.binary = binary
        self.doc = doc
        self.stories = stories
        self.pictures = pictures
        self.objects = objects
        self.depth = 0
        self.section_breaks = frozenset(getattr(binary, 'section_boundaries', ()))

    def _chunks(self, record):
        """Batch ordinary characters while preserving every CP annotation."""
        if not hasattr(self.binary, 'iter_char_runs'):
            for cp in range(record.start, record.end):
                yield cp, self.binary.text[cp], self.binary.char_props(cp)
            return
        for start, end, props in self.binary.iter_char_runs(record.start, record.end):
            if props.get('deleted'):
                continue
            events = set(self.stories.event_positions(start, end))
            events.update(match.start() for match in _SPECIAL.finditer(self.binary.text, start, end))
            pos = start
            for cp in sorted(events):
                if pos < cp:
                    yield pos, self.binary.text[pos:cp], props
                yield cp, self.binary.text[cp], props
                pos = cp + 1
            if pos < end:
                yield pos, self.binary.text[pos:end], props

    def paragraph(self, record):
        provenance = Provenance(source_format='doc', path='WordDocument#cp%d' % record.start)
        blocks = []
        runs = []
        bookmarks = []
        last_signature = None
        chunks = []

        def settle():
            if chunks:
                runs[-1].text = ''.join(chunks)
                chunks.clear()

        def append(text, props):
            nonlocal last_signature
            if not text:
                return
            signature = tuple(bool(props.get(name, False)) for name in _FORMATS)
            if runs and signature == last_signature and not runs[-1].note_ref:
                chunks.append(text)
            else:
                settle()
                runs.append(TextRun(provenance=provenance,
                                    **dict(zip(_FORMATS, signature))))
                chunks.append(text)
            last_signature = signature

        def flush():
            nonlocal runs, last_signature, bookmarks
            settle()
            # Anchors annotate the paragraph; they must never split a word.
            runs = bookmarks + runs
            bookmarks = []
            if runs:
                for run in runs:
                    run.text = _unicode(run.text)
                blocks.append(Paragraph(runs=runs, style_id=record.props.get('istd', -1),
                                        heading_level=min(6, record.props.get('heading_level', 0)),
                                        provenance=provenance))
            runs = []
            last_signature = None

        for cp, char, props in self._chunks(record):
            if props.get('deleted'):
                continue
            markers = self.stories.markers(cp)
            if markers:
                for marker in markers:
                    if getattr(marker, '_bookmark_annotation', False):
                        bookmarks.append(marker)
                    else:
                        settle()
                        runs.append(marker)
                        last_signature = None
            append(self.stories.suffix(cp), props)
            if self.stories.hidden(cp):
                continue
            if char in ('\x01', '\x08'):
                embedded = self.objects.at(cp, props, provenance) if self.objects is not None else []
                if embedded:
                    flush()
                    blocks.extend(embedded)
                    continue
                image = self.pictures.image_at(cp, props)
                if image is not None:
                    flush()
                    blocks.append(image)
                elif self.objects is not None and cp in self.objects.labels:
                    flush()
                    blocks.append(Paragraph(runs=[TextRun(text=self.objects.labels[cp])], provenance=provenance))
                if char == '\x08' and hasattr(self.pictures, 'textbox_at'):
                    index = self.pictures.textbox_at(cp)
                    if index is not None:
                        start, end = self.binary.stories.get('header', (0, 0))
                        content = self.stories.textbox(index, self.render, start <= cp < end)
                        if content:
                            flush()
                            blocks.extend(content)
                continue
            if char == '\x0c' and cp + 1 in self.section_breaks:
                continue
            if char in ('\x0b', '\x0c', '\x0e'):
                char = '\n'
            elif char in ('\u2011', '\x1e'):
                char = '-'
            elif char == '\u00ad' or (len(char) == 1 and ord(char) < 32 and char not in '\t\n'):
                continue
            if hasattr(self.binary, 'display_text'):
                char = self.binary.display_text(char, props)
            append(char, props)
        flush()
        return blocks

    def render(self, start, end):
        if self.depth >= 32:
            self.doc.errors.append('WARN: DOC story nesting limit exceeded')
            return []
        self.depth += 1
        try:
            return assemble_blocks(self.binary.paragraphs(start, end), self.paragraph, self.doc.errors)
        finally:
            self.depth -= 1


def parse_structured_doc(word, table, data=b'', ole=None):
    """Return None for pre-97/invalid FIBs so callers retain text recovery."""
    from .doc_images import DocImages
    from .doc_stories import Stories

    binary = DocBinary(word, table, data)
    if not binary.valid:
        return None
    doc = Document(source_format='doc')
    stories = Stories(binary, doc)
    from .ole_objects import DocObjects
    objects = DocObjects(ole, binary, stories.fields, doc.errors) if ole is not None else None
    renderer = StructureRenderer(binary, doc, stories, DocImages(binary, doc), objects)
    start, end = binary.stories['main']
    # PlcfSed is the section authority. Inline page breaks remain within their
    # field result or cell paragraph and cannot allocate model Sections.
    boundaries = binary.section_boundaries
    for stop in boundaries + [end]:
        if start < stop or not doc.sections:
            doc.sections.append(Section(elements=renderer.render(start, stop),
                provenance=Provenance(source_format='doc', path='WordDocument#cp%d' % start)))
        start = stop
    headers, trailers = stories.extras(renderer.render)
    doc.sections[0].elements[0:0] = headers
    doc.sections[-1].elements.extend(trailers)
    doc.errors.extend('WARN: ' + message if not message.startswith('WARN:') else message
                      for message in binary.warnings)
    return doc
