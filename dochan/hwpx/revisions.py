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
OBJECTS = {"tbl", "pic", "equation", "rect", "ellipse", "line", "connectLine",
           "curve", "polygon", "arc", "container", "ole", "ctrl"}
TEXT_TOKENS = {HP + n for n in ("tab", "lineBreak", "fwSpace", "nbSpace")}
MARKER_PARENTS = {SECTION, HP + "p", HP + "run", HP + "t"}
FLOW_CONTENT = {HP + "p", HP + "run", HP + "t", HP + "compose"} | TEXT_TOKENS


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

    def _report(self, code, location):
        # Bound diagnostics by category, not by the number of hostile markers.
        if code not in self._problems:
            self._problems[code] = [0, location]
        self._problems[code][0] += 1

    def _flush(self, part):
        severity = "WARN" if self.mode == "preserve" else "ERR"
        for code, (count, location) in self._problems.items():
            self.errors.append(
                f"{severity}: HWPX revision partial [{code}] {part}: {location}; "
                f"occurrences={count}; revision_mode={self.mode}; "
                "unresolved content preserved"
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
                self._report("formatting", kind + " projection is unsupported")
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
            overlap = bool(flow.opened)
            if overlap:
                flow.invalidate_open()
                self._report("overlap", location)
            if key in flow.opened:
                flow.disabled = True
                self._report("duplicate-begin", location)
                return
            if len(flow.opened) >= MAX_OPEN_RANGES:
                flow.disabled = True
                self._report("range-limit", location)
                return
            flow.opened[key] = _Range(kind, tc_id, len(flow.slots), location,
                                      reference_valid and not overlap)
        else:
            span = flow.opened.pop(key, None)
            paraend_valid = element.get("paraend") == "0"
            if not paraend_valid:
                self._report("paraend", location + " (only paraend=0 is supported)")
            if span is None:
                flow.invalidate_open()
                self._report("missing-begin", location)
                return
            if span.tc_id != tc_id:
                self._report("reference-mismatch", location + " begin/end @TcId")
                span.valid = False
            span.valid = span.valid and reference_valid and paraend_valid
            flow.spans.append((span, len(flow.slots)))
        if len(element) or element.text:
            flow.disabled = True
            self._report("marker-content", location + " (expected empty marker)")

    def project_section(self, root, part="section"):
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

        def walk(element, flow, in_text=False, location="section", blocked=False):
            if not isinstance(element.tag, str):
                return
            name = element.tag.rsplit("}", 1)[-1]
            # Isolate a story before visiting *any* of its children. Waiting
            # until hp:p would let a marker directly under subList/tc/a note
            # open a range in the surrounding body. Unknown containers are
            # boundaries too; only established inline content shares a flow.
            if element is not root and name not in MARKERS and element.tag not in FLOW_CONTENT:
                if flow.opened:
                    flow.invalidate_open()
                    # Alternate/unknown wrappers may contain an object: keep
                    # the existing object diagnostic without sharing ranges.
                    has_object = any(
                        isinstance(e.tag, str) and e.tag.rsplit("}", 1)[-1] in OBJECTS
                        for e in element.iter()
                    )
                    code = "object" if has_object else "flow-boundary"
                    self._report(code, location + "/" + name + " (text-only projection)")
                flow = flows.setdefault(element, _Flow())
                in_text = False
                location += "/" + name
            if element.tag == HP + "p":
                flow = flows.setdefault(element.getparent(), _Flow())
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
                parent = element.getparent()
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
                walk(child, flow, in_text, location, blocked)
                if in_text and child.tail:
                    flow.add(child, "tail")

        walk(root, flows[root])
        excluded = {"final": "Delete", "original": "Insert"}.get(self.mode)
        for flow in flows.values():
            for span in flow.opened.values():
                self._report("missing-end", span.location)
            if flow.disabled or excluded is None:
                continue
            for span, end in flow.spans:
                if not span.valid or span.kind != excluded:
                    continue
                for element, attribute in flow.slots[span.start:end]:
                    if attribute == "tag":
                        # Keep the element and its tail in place. The parser
                        # ignores this empty token rather than losing its tail.
                        element.tag = HP + "revisionSuppressed"
                    elif attribute == "composeText":
                        element.set(attribute, "")
                    else:
                        setattr(element, attribute, "")
        self._flush(part)
