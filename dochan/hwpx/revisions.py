"""Conservative text-only projections of HWPX change-tracking ranges.

Validate the whole section before changing text: an unmatched or overlapping
range must never silently consume the rest of a document. Unknown ranges keep
their content and produce diagnostics, including in the default preserve mode.
"""

from dataclasses import dataclass, field

from ..utils.safe_xml import parent_map


PARAGRAPH_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HEAD_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HP = "{" + PARAGRAPH_NS + "}"
HH = "{" + HEAD_NS + "}"
SECTION = "{http://www.hancom.co.kr/hwpml/2011/section}sec"
MARKERS = {"insertBegin": "Insert", "insertEnd": "Insert",
           "deleteBegin": "Delete", "deleteEnd": "Delete"}
MAX_OPEN_RANGES = 128
MAX_RANGES = 10000
OBJECTS = {"tbl", "pic", "equation", "rect", "ellipse", "line", "connectLine",
           "curve", "polygon", "arc", "container", "ole", "ctrl"}
TEXT_TOKENS = {HP + n for n in ("tab", "lineBreak", "fwSpace", "nbSpace")}
MARKER_PARENTS = {SECTION, HP + "p", HP + "run", HP + "t"}
FLOW_CONTENT = {HP + "p", HP + "run", HP + "t", HP + "compose",
                HP + "titleMark", HP + "markpenBegin", HP + "markpenEnd",
                HP + "hyphen"} | TEXT_TOKENS


def _collect_relevant(root, parents=None):
    relevant = set()
    for element in root.iter():
        if isinstance(element.tag, str) and (
            element.tag.rsplit("}", 1)[-1] in MARKERS
            or "paraTcId" in element.attrib or "charTcId" in element.attrib
        ):
            relevant.add(element)
    if not relevant:
        return relevant
    links = parent_map(root)
    if parents is not None:
        parents.update(links)
    for element in tuple(relevant):
        ancestor = links.get(element)
        while ancestor is not None and ancestor not in relevant:
            relevant.add(ancestor)
            ancestor = links.get(ancestor)
    return relevant


def validate_revision_mode(mode):
    if mode not in ("preserve", "final", "original"):
        raise ValueError("revision_mode must be 'preserve', 'final', or 'original'")


@dataclass
class _Range:
    kind: str
    tc_id: str
    start: int
    location: str
    paragraph: object = None
    valid: bool = True


@dataclass
class _Flow:
    # Separate text stories (body, table cell, note, caption, etc.) cannot close
    # one another's markers, even when Id happens to match.
    slots: list = field(default_factory=list)
    opened: dict = field(default_factory=dict)
    spans: list = field(default_factory=list)
    disabled: bool = False
    range_count: int = 0
    paragraph_ends: list = field(default_factory=list)
    last_closed: dict = field(default_factory=dict)
    position: int = 0

    def add(self, element, attribute):
        self.position += 1
        if self.opened:
            self.slots.append((element, attribute))

    def invalidate_open(self):
        for span in self.opened.values():
            span.valid = False


class RevisionProjector:
    """Header references and per-section validation, owned by one parser call."""

    def __init__(self, errors, mode="preserve"):
        validate_revision_mode(mode)
        self.errors = errors
        self.mode = mode
        self.changes = {}
        self._para_headings = {}
        self._old_para_shapes = {}
        self._problems = {}
        self._formatting_count = 0
        self._formatting_error_index = None
        self._section_ranges = 0

    def _report(self, code, location):
        # Bound diagnostics by category, not by the number of hostile markers.
        if code not in self._problems:
            self._problems[code] = [0, location]
        self._problems[code][0] += 1

    def _flush(self, part):
        for code, (count, location) in self._problems.items():
            if code == "formatting":
                self._formatting_count += count
                if self._formatting_error_index is not None:
                    old = self.errors[self._formatting_error_index]
                    prefix, suffix = old.split("occurrences=", 1)
                    _, suffix = suffix.split(";", 1)
                    self.errors[self._formatting_error_index] = (
                        f"{prefix}occurrences={self._formatting_count};{suffix}"
                    )
                    continue
            informational = code in ("formatting", "duplicate-end")
            severity = "WARN" if self.mode == "preserve" or informational else "ERR"
            label = "info" if informational else "partial"
            outcome = ("text projection unchanged" if code == "formatting"
                       else "adjacent duplicate ignored" if code == "duplicate-end"
                       else "unresolved content preserved")
            self.errors.append(
                f"{severity}: HWPX revision {label} [{code}] {part}: {location}; "
                f"occurrences={count}; revision_mode={self.mode}; {outcome}"
            )
            if code == "formatting":
                self._formatting_error_index = len(self.errors) - 1
        self._problems.clear()

    def read_header(self, root):
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            if element.tag == HH + "paraPr" and element.get("id") is not None:
                heading = element.find(HH + "heading")
                if heading is not None:
                    self._para_headings[element.get("id")] = (
                        heading.get("type"), heading.get("level")
                    )
            if element.tag.rsplit("}", 1)[-1] != "trackChange":
                continue
            if element.tag != HH + "trackChange":
                self._report("namespace", "trackChange")
                continue
            identity = element.get("id")
            kind = element.get("type")
            if not identity:
                self._report("missing-id", "trackChange@id")
                continue
            if identity in self.changes:
                self.changes[identity] = None
                self._report("header-reference", "duplicate trackChange@id")
            else:
                self.changes[identity] = kind
            if kind in ("ParaShape", "CharShape"):
                if kind == "ParaShape":
                    self._old_para_shapes[identity] = element.get("parashapeID")
                self._report("formatting", kind + " does not change text projection")
            elif kind not in ("Insert", "Delete"):
                self._report("unsupported-type", "trackChange@type")
        self._flush("Contents/header.xml")

    def _marker(self, element, flow, location, paragraph):
        position = flow.position
        flow.position += 1
        name = element.tag.rsplit("}", 1)[-1]
        if element.tag != HP + name:
            flow.invalidate_open()
            self._report("namespace", location)
            return
        identity, tc_id = element.get("Id"), element.get("TcId")
        if not identity:
            flow.disabled = True
            self._report("missing-id", location + " @Id")
            return
        kind = MARKERS[name]
        key = (kind, identity)
        reference_valid = bool(tc_id) and self.changes.get(tc_id) == kind
        if not reference_valid:
            self._report("header-reference", location + " @TcId/type")
        if name.endswith("Begin"):
            flow.last_closed.pop(key, None)
            self._section_ranges += 1
            if key in flow.opened:
                flow.disabled = True
                self._report("duplicate-begin", location)
                return
            if (len(flow.opened) >= MAX_OPEN_RANGES or
                    flow.range_count >= MAX_RANGES or
                    self._section_ranges > MAX_RANGES):
                flow.disabled = True
                self._report("range-limit", location)
                return
            flow.range_count += 1
            flow.opened[key] = _Range(kind, tc_id, len(flow.slots), location,
                                      paragraph, reference_valid)
        else:
            span = flow.opened.pop(key, None)
            # OWPML (KS X 6101:2011) hp:insertEnd/deleteEnd @paraend.
            # Per the task's interpretation, 1 includes the paragraph end;
            # the numbered normative clause was unavailable offline.
            paraend = element.get("paraend")
            paraend_valid = paraend in ("0", "1")
            if not paraend_valid:
                self._report("paraend", location + " (expected paraend=0 or 1)")
            if span is None:
                if flow.last_closed.get(key) == (tc_id, paraend, position):
                    self._report("duplicate-end", location)
                    return
                flow.invalidate_open()
                self._report("missing-begin", location)
                return
            if span.tc_id != tc_id:
                self._report("reference-mismatch", location + " begin/end @TcId")
                span.valid = False
            if span.paragraph is not paragraph:
                self._report("cross-paragraph", location)
                span.valid = False
            span.valid = span.valid and reference_valid and paraend_valid
            flow.spans.append((span, len(flow.slots)))
            flow.last_closed[key] = (tc_id, paraend, flow.position)
            if paraend == "1" and span.valid:
                if paragraph is None:
                    self._report("paraend-boundary", location)
                else:
                    flow.paragraph_ends.append((span, paragraph))
        if len(element) or element.text:
            flow.disabled = True
            self._report("marker-content", location + " (expected empty marker)")

    def project_section(self, root, part="section"):
        self._section_ranges = 0
        # No edits or extra text allocations for documents without revisions.
        parents = {}
        relevant = _collect_relevant(root, parents)
        if not relevant:
            return
        flows = {root: _Flow()}
        counts = {"paragraph": 0, "run": 0, "marker": 0}

        def count_skipped(element):
            # Keep diagnostic indices tied to the source, including branches
            # that require no revision projection.
            for node in element.iter():
                if node.tag == HP + "p":
                    counts["paragraph"] += 1
                elif node.tag == HP + "run":
                    counts["run"] += 1

        def walk(element, flow, in_text=False, location="section", blocked=False,
                 parent=None, paragraph=None):
            if not isinstance(element.tag, str):
                return
            if element not in relevant and not flow.opened:
                flow.position += 1
                count_skipped(element)
                return
            name = element.tag.rsplit("}", 1)[-1]
            # Isolate a story before visiting *any* of its children. Waiting
            # until hp:p would let a marker directly under subList/tc/a note
            # open a range in the surrounding body. Unknown containers are
            # boundaries too; only established inline content shares a flow.
            if element is not root and name not in MARKERS and element.tag not in FLOW_CONTENT:
                is_object = element.tag.startswith(HP) and name in OBJECTS
                if is_object:
                    # OWPML change markers delimit a content range. A complete
                    # object is one position in its parent's range; its own text
                    # story cannot close the parent's markers.
                    flow.add(element, "object")
                    if element not in relevant:
                        count_skipped(element)
                        return
                elif flow.opened:
                    flow.invalidate_open()
                    # Alternate/unknown wrappers may contain an object: keep
                    # the existing object diagnostic without sharing ranges.
                    has_object = any(isinstance(e.tag, str) and
                                     e.tag.rsplit("}", 1)[-1] in OBJECTS
                                     for e in element.iter())
                    code = "object" if has_object else "flow-boundary"
                    self._report(code, location + "/" + name + " (text-only projection)")
                    if element not in relevant:
                        count_skipped(element)
                        return
                flow = flows.setdefault(element, _Flow())
                in_text = False
                location += "/" + name
            if element.tag == HP + "p":
                flow = flows.setdefault(parent, _Flow())
                paragraph = element
                in_text = False
                counts["paragraph"] += 1
                flow.position += 1
                location = f"paragraph#{counts['paragraph']}"
            elif element.tag == HP + "run":
                counts["run"] += 1
                location += f"/run#{counts['run']}"
            if blocked:
                flow.disabled = True
            for attr in ("paraTcId", "charTcId"):
                if attr in element.attrib:
                    self._report("formatting", location + " @" + attr)
                    expected = "ParaShape" if attr == "paraTcId" else "CharShape"
                    if self.changes.get(element.get(attr)) != expected:
                        self._report("header-reference", location + " @" + attr)
                    if attr == "paraTcId" and element.tag == HP + "p":
                        old_id = self._old_para_shapes.get(element.get(attr))
                        new_id = element.get("paraPrIDRef")
                        old_heading = self._para_headings.get(old_id)
                        new_heading = self._para_headings.get(new_id)
                        if (old_heading is not None and new_heading is not None
                                and old_heading != new_heading
                                and (old_heading[0] != "NONE" or
                                     new_heading[0] != "NONE")):
                            self._report("formatting-heading", location +
                                         " (outline level may differ by mode)")
            if name in MARKERS:
                counts["marker"] += 1
                if parent is None or parent.tag not in MARKER_PARENTS:
                    flow.disabled = True
                    self._report("marker-position", location + "/" + name)
                self._marker(element, flow, location + f"/{name}#{counts['marker']}",
                             paragraph)
                if not in_text and element.tail and element.tail.strip():
                    flow.disabled = True
                    self._report("marker-tail", location + " (text outside hp:t)")
                return
            # Branch-local marker semantics are not established by the gold.
            if name == "switch" and any(
                isinstance(e.tag, str) and e.tag.rsplit("}", 1)[-1] in MARKERS
                for e in element.iter()
            ):
                flow.disabled = True
                blocked = True
                self._report("switch", location + " (revision in alternate branches)")
            in_text = in_text or element.tag == HP + "t"
            if in_text and element.text:
                flow.add(element, "text")
            if element.tag in TEXT_TOKENS:
                flow.add(element, "tag")
            elif element.tag == HP + "compose":
                flow.add(element, "composeText")
            for child in element:
                walk(child, flow, in_text, location, blocked, element, paragraph)
                if in_text and child.tail:
                    flow.add(child, "tail")

        walk(root, flows[root])
        paragraph_ends = {paragraph for flow in flows.values()
                          for _, paragraph in flow.paragraph_ends}
        following_paragraph = {}
        for parent in {parents[p] for p in paragraph_ends if p in parents}:
            previous = None
            for child in parent:
                if previous in paragraph_ends:
                    following_paragraph[previous] = child
                previous = child
        excluded = {"final": "Delete", "original": "Insert"}.get(self.mode)
        for flow in flows.values():
            for span in flow.opened.values():
                self._report("missing-end", span.location)
            if flow.disabled or excluded is None:
                continue
            # Difference array makes even deeply crossed ranges linear in the
            # number of markers and slots; no repeated span slices are copied.
            difference = [0] * (len(flow.slots) + 1)
            for span, end in flow.spans:
                if span.valid and span.kind == excluded:
                    difference[span.start] += 1
                    difference[end] -= 1
            active = 0
            for index, (element, attribute) in enumerate(flow.slots):
                active += difference[index]
                if active:
                    if attribute == "object":
                        # A field boundary changes parser state even when its
                        # own range is excluded. Preserve it to keep its mate
                        # balanced outside the range.
                        if (element.tag == HP + "ctrl" and any(
                            child.tag in (HP + "fieldBegin", HP + "fieldEnd")
                            for child in element
                        )):
                            continue
                        # clear() removes children which the body-budget and
                        # chart-discovery paths would otherwise parse again.
                        tail = element.tail
                        for child in element:
                            parents.pop(child, None)
                        element.clear()
                        element.tag = HP + "revisionSuppressed"
                        element.tail = tail
                    elif attribute == "tag":
                        # Keep the element and its tail in place. The parser
                        # ignores this empty token rather than losing its tail.
                        element.tag = HP + "revisionSuppressed"
                    elif attribute == "composeText":
                        element.set(attribute, "")
                    else:
                        setattr(element, attribute, "")
            # OWPML hp:p and change-end @paraend: removing the separator
            # joins the next sibling's runs to the surviving paragraph.
            # Its properties remain the anchor unless it has no content.
            representative = {}
            candidates = {paragraph for _, paragraph in flow.paragraph_ends}
            candidates.update(following_paragraph[p] for _, p in flow.paragraph_ends
                              if following_paragraph.get(p) is not None)

            def has_visible_content(paragraph):
                pending = [(paragraph, None)]
                while pending:
                    node, parent = pending.pop()
                    if (node is not paragraph and node.tail and
                            parent is not None and parent.tag == HP + "t"):
                        return True
                    if node.tag == HP + "revisionSuppressed":
                        continue
                    if isinstance(node.tag, str) and node.tag.startswith(HP):
                        if node.tag.rsplit("}", 1)[-1] in OBJECTS and not (
                            node.tag == HP + "ctrl" and any(
                                child.tag in (HP + "colPr", HP + "secPr",
                                              HP + "bookmark",
                                              HP + "fieldBegin", HP + "fieldEnd",
                                              HP + "pageNum", HP + "pageHiding")
                                for child in node
                            )
                        ):
                            return True
                    if node.tag in TEXT_TOKENS:
                        return True
                    if node.tag == HP + "compose" and node.get("composeText"):
                        return True
                    if node.tag == HP + "t" and node.text:
                        return True
                    pending.extend((child, node) for child in node)
                return False

            visible = {}
            for candidate in candidates:
                visible[candidate] = has_visible_content(candidate)
            for span, paragraph in flow.paragraph_ends:
                if span.kind != excluded:
                    continue
                current = representative.get(paragraph, paragraph)
                following = following_paragraph.get(paragraph)
                if following is None or following.tag != HP + "p":
                    continue
                parent = parents.get(following)
                if parent is None or parents.get(current) is not parent:
                    continue
                if not visible[current]:
                    # Content outside the excluded range (bookmarks and
                    # structural controls) still belongs to this paragraph.
                    # Keep it while adopting the surviving paragraph's style.
                    current.attrib.clear()
                    current.attrib.update(following.attrib)
                    for child in list(following):
                        current.append(child)
                        parents[child] = current
                    parent.remove(following)
                    parents.pop(following, None)
                    representative[following] = current
                    visible[current] = visible[following]
                    continue
                for child in list(following):
                    current.append(child)
                    parents[child] = current
                parent.remove(following)
                parents.pop(following, None)
                representative[following] = current
                visible[current] = visible[current] or visible[following]
        self._flush(part)
