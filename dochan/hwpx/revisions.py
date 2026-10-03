"""Conservative text-only projections of HWPX change-tracking ranges.

Validate the whole section before changing text: an unmatched or overlapping
range must never silently consume the rest of a document. Unknown ranges keep
their content and produce diagnostics, including in the default preserve mode.
"""

from dataclasses import dataclass, field


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
                HP + "titleMark"} | TEXT_TOKENS


def validate_revision_mode(mode):
    if mode not in ("preserve", "final", "original"):
        raise ValueError("revision_mode must be 'preserve', 'final', or 'original'")


@dataclass
class _Range:
    kind: str
    tc_id: str
    start: int
    location: str
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

    def add(self, element, attribute):
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
        self._problems = {}
        self._formatting_reported = False
        self._section_ranges = 0

    def _report(self, code, location):
        if code == "formatting":
            if self._formatting_reported:
                return
            self._formatting_reported = True
        # Bound diagnostics by category, not by the number of hostile markers.
        if code not in self._problems:
            self._problems[code] = [0, location]
        self._problems[code][0] += 1

    def _flush(self, part):
        for code, (count, location) in self._problems.items():
            severity = "WARN" if self.mode == "preserve" or code == "formatting" else "ERR"
            label = "info" if code == "formatting" else "partial"
            outcome = ("text projection unchanged" if code == "formatting"
                       else "unresolved content preserved")
            self.errors.append(
                f"{severity}: HWPX revision {label} [{code}] {part}: {location}; "
                f"occurrences={count}; revision_mode={self.mode}; {outcome}"
            )
        self._problems.clear()

    def read_header(self, root):
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
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
                self._report("formatting", kind + " does not change text projection")
            elif kind not in ("Insert", "Delete"):
                self._report("unsupported-type", "trackChange@type")
        self._flush("Contents/header.xml")

    def _marker(self, element, flow, location):
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
                                      reference_valid)
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
                flow.invalidate_open()
                self._report("missing-begin", location)
                return
            if span.tc_id != tc_id:
                self._report("reference-mismatch", location + " begin/end @TcId")
                span.valid = False
            span.valid = span.valid and reference_valid and paraend_valid
            flow.spans.append((span, len(flow.slots)))
            if paraend == "1" and span.valid:
                paragraph = next((p for p in element.iterancestors()
                                  if p.tag == HP + "p"), None)
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
        if not any(
            isinstance(e.tag, str) and (
                e.tag.rsplit("}", 1)[-1] in MARKERS
                or "paraTcId" in e.attrib or "charTcId" in e.attrib
            ) for e in root.iter()
        ):
            return
        flows = {root: _Flow()}
        counts = {"paragraph": 0, "run": 0, "marker": 0}

        def walk(element, flow, in_text=False, location="section", blocked=False, parent=None):
            if not isinstance(element.tag, str):
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
                elif flow.opened:
                    flow.invalidate_open()
                    # Alternate/unknown wrappers may contain an object: keep
                    # the existing object diagnostic without sharing ranges.
                    has_object = any(isinstance(e.tag, str) and
                                     e.tag.rsplit("}", 1)[-1] in OBJECTS
                                     for e in element.iter())
                    code = "object" if has_object else "flow-boundary"
                    self._report(code, location + "/" + name + " (text-only projection)")
                flow = flows.setdefault(element, _Flow())
                in_text = False
                location += "/" + name
            if element.tag == HP + "p":
                flow = flows.setdefault(parent, _Flow())
                in_text = False
                counts["paragraph"] += 1
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
            if name in MARKERS:
                counts["marker"] += 1
                if parent is None or parent.tag not in MARKER_PARENTS:
                    flow.disabled = True
                    self._report("marker-position", location + "/" + name)
                self._marker(element, flow, location + f"/{name}#{counts['marker']}")
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
                walk(child, flow, in_text, location, blocked, element)
                if in_text and child.tail:
                    flow.add(child, "tail")

        walk(root, flows[root])
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
                        # Keep the XML node so its tail, which can contain
                        # following visible text in mixed content, survives.
                        element.tag = HP + "revisionSuppressed"
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
            following_paragraph = {paragraph: paragraph.getnext()
                                   for _, paragraph in flow.paragraph_ends}
            candidates = set(following_paragraph)
            candidates.update(p for p in following_paragraph.values() if p is not None)

            def has_visible_content(paragraph):
                pending = [paragraph]
                while pending:
                    node = pending.pop()
                    if node is not paragraph and node.tail and node.tail.strip():
                        return True
                    if node.tag == HP + "revisionSuppressed":
                        continue
                    if isinstance(node.tag, str) and node.tag.startswith(HP):
                        if node.tag.rsplit("}", 1)[-1] in OBJECTS:
                            return True
                    if node.text and node.text.strip():
                        return True
                    pending.extend(node)
                return False

            visible = {}
            for candidate in candidates:
                visible[candidate] = has_visible_content(candidate)
            for span, paragraph in flow.paragraph_ends:
                if span.kind != excluded:
                    continue
                current = representative.get(paragraph, paragraph)
                following = following_paragraph[paragraph]
                if following is None or following.tag != HP + "p":
                    continue
                parent = following.getparent()
                if parent is None or current.getparent() is not parent:
                    continue
                if not visible[current]:
                    parent.remove(current)
                    representative[following] = following
                    continue
                for child in list(following):
                    current.append(child)
                parent.remove(following)
                representative[following] = current
                visible[current] = visible[current] or visible[following]
        self._flush(part)
