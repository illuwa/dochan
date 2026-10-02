"""ISO 32000-2 14.7/14.13 Formula structure and associated semantic data.

Only explicit page/MCID ownership replaces glyphs. Unanchored or unsupported
formulae leave original text intact. No visual equation recognition is attempted.
"""
from dataclasses import dataclass, field
from bisect import bisect_left
import math
import re
from typing import Optional
from xml.sax.saxutils import escape, quoteattr  # nosemgrep: use-defused-xml (문자열 이스케이프만, XML 파싱은 lxml 안전 파서)

from lxml import etree

from ..model.equation import Equation
from .annotations import text_string
from .objects import PDFStream

MAX_NODES = 200000
MAX_DEPTH = 64
MAX_FORMULAS = 4096
MAX_SOURCE_BYTES = 256 * 1024
MAX_TOTAL_SOURCE = 8 * 1024 * 1024
MAX_FORMULA_GEOMETRY_CHECKS = 2000000
MATHML_NS = "http://www.w3.org/1998/Math/MathML"


@dataclass
class _Formula:
    node: dict
    page: object
    members: list = field(default_factory=list)
    unsupported: bool = False
    display: Optional[bool] = None
    preserve: bool = False


def _tex_without_comments(source):
    """Strip ordinary TeX comments without changing escaped percent tokens.

    A comment suppresses its end-of-line (including next-line indentation),
    but still terminates a control word. Decline altered lexical conventions.
    """
    if "^^" in source:
        raise ValueError("TeX 문자 재해석은 지원하지 않음")
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    parts = []
    index = 0
    control_word = False
    while index < len(source):
        char = source[index]
        if char == "%":
            end = source.find("\n", index)
            index = len(source) if end < 0 else end + 1
            while index < len(source) and source[index] in " \t":
                index += 1
            if control_word:
                parts.append(" ")
            control_word = False
        elif char == "\\":
            end = index + 1
            while end < len(source) and source[end].isascii() and source[end].isalpha():
                end += 1
            control_word = end > index + 1
            if control_word:
                if source[index + 1:end] in {"verb", "catcode", "endlinechar", "obeylines", "obeyspaces", "csname"}:
                    raise ValueError("TeX 주석 어휘 변경은 지원하지 않음")
            else:
                end = min(len(source), end + 1)
            parts.append(source[index:end])
            index = end
        else:
            parts.append(char)
            index += 1
            control_word = False
    return "".join(parts).strip()


class FormulaExtractor:
    def __init__(self, pdf):
        self.pdf = pdf
        self.records = []
        self._remaining = MAX_NODES
        self._source_budget = MAX_TOTAL_SOURCE
        self._seen = set()
        catalog = pdf.resolve(pdf.trailer.get("Root"))
        root = pdf.resolve(catalog.get("StructTreeRoot")) if isinstance(catalog, dict) else None
        self.roles = pdf.resolve(root.get("RoleMap")) if isinstance(root, dict) else {}
        if not isinstance(self.roles, dict):
            self.roles = {}
        self._root = root if isinstance(root, dict) else {}
        self._parent_tree = self.pdf.resolve(self._root.get("ParentTree"))
        self._loaded = False
        self._page_records = {}
        self._parent_indexes = {}
        self._parent_index_remaining = MAX_NODES

    def _warn(self, reason):
        self.pdf.warnings.append("WARN: PDF Formula " + reason)

    def _role(self, value):
        name = str(value)
        seen = set()
        while name in self.roles and name not in seen and len(seen) < 32:
            seen.add(name)
            name = str(self.roles[name])
        return name

    def _walk(self, value, page, owner, depth, protected=False):
        value = self.pdf.resolve(value)
        if type(value) is int:
            if owner is not None and value >= 0:
                owner.members.append((page, value))
            return
        if not isinstance(value, (list, dict)):
            return
        self._remaining -= 1
        if self._remaining < 0 or depth > MAX_DEPTH:
            raise ValueError("Formula 구조 순회 한도 초과")
        if id(value) in self._seen:
            if owner is not None:
                owner.unsupported = True
            return
        self._seen.add(id(value))
        if isinstance(value, list):
            if len(value) > MAX_NODES:
                raise ValueError("Formula 구조 자식 수 한도 초과")
            for child in value:
                self._walk(child, page, owner, depth + 1, protected)
            return
        page = value.get("Pg", page)
        if str(value.get("Type")) == "MCR" or "MCID" in value:
            if owner is not None:
                if "Stm" in value:
                    owner.unsupported = True  # Form XObject has its own MCID space.
                elif type(value.get("MCID")) is int and value["MCID"] >= 0:
                    owner.members.append((page, value["MCID"]))
            return
        role = self._role(value.get("S"))
        protected = protected or role in ("Code", "Note", "Table", "TR", "TD", "TH")
        if role == "Formula":
            if owner is not None:
                owner.unsupported = True
            if len(self.records) >= MAX_FORMULAS:
                raise ValueError("Formula 개수 한도 초과")
            owner = _Formula(value, page, preserve=protected)
            self.records.append(owner)
        self._walk(value.get("K"), page, owner, depth + 1, protected)

    def _parents(self, key):
        """ISO 32000 number-tree lookup visits only the requested page's path."""
        pending = [(self._parent_tree, 0)]
        seen = set()
        budget = MAX_NODES
        while pending:
            node, depth = pending.pop()
            node = self.pdf.resolve(node)
            if not isinstance(node, dict) or id(node) in seen:
                continue
            seen.add(id(node))
            budget -= 1
            if budget < 0 or depth > MAX_DEPTH:
                raise ValueError("Formula ParentTree 한도 초과")
            limits = self.pdf.resolve(node.get("Limits"))
            if (isinstance(limits, list) and len(limits) == 2
                    and all(type(v) is int for v in limits) and not limits[0] <= key <= limits[1]):
                continue
            nums = self.pdf.resolve(node.get("Nums"))
            if isinstance(nums, list):
                budget -= len(nums)
                if budget < 0 or len(nums) % 2:
                    raise ValueError("Formula ParentTree 항목 손상/한도 초과")
                identity = id(node)
                if identity not in self._parent_indexes:
                    self._parent_index_remaining -= len(nums)
                    if self._parent_index_remaining < 0:
                        raise ValueError("Formula ParentTree 색인 한도 초과")
                    index = {}
                    for offset in range(0, len(nums), 2):
                        number, parents = nums[offset], nums[offset + 1]
                        if type(number) is not int or number in index:
                            raise ValueError("Formula ParentTree 키 손상/중복")
                        index[number] = parents
                    self._parent_indexes[identity] = index
                index = self._parent_indexes[identity]
                if key in index:
                    parents = self.pdf.resolve(index[key])
                    return parents if isinstance(parents, list) else []
            kids = self.pdf.resolve(node.get("Kids"))
            if isinstance(kids, list):
                budget -= len(kids)
                if budget < 0:
                    raise ValueError("Formula ParentTree 자식 수 한도 초과")
                pending.extend((child, depth + 1) for child in kids)
        return []

    def _for_page(self, page):
        if self._loaded:
            return self.records
        if not isinstance(self._parent_tree, dict) or type(page.get("StructParents")) is not int:
            if not self._loaded:
                self._loaded = True
                try:
                    self._walk(self._root.get("K"), None, None, 0)
                except (ValueError, TypeError):
                    self.records.clear()
                    raise
            return self.records
        if id(page) in self._page_records:
            return self._page_records[id(page)]
        parents = self._parents(page["StructParents"])
        if len(parents) > MAX_NODES:
            raise ValueError("Formula 페이지 MCID 수 한도 초과")
        roots = {}
        visited = set()
        for parent in parents:
            node = self.pdf.resolve(parent)
            chain = set()
            formula = None
            protected = False
            inherited = page
            for _ in range(MAX_DEPTH):
                if not isinstance(node, dict) or id(node) in chain:
                    break
                if formula is None and id(node) in visited:
                    break
                chain.add(id(node))
                if formula is None:
                    visited.add(id(node))
                inherited = node.get("Pg", inherited)
                role = self._role(node.get("S"))
                protected |= role in ("Code", "Note", "Table", "TR", "TD", "TH")
                if role == "Formula":
                    formula = node
                node = self.pdf.resolve(node.get("P"))
            else:
                raise ValueError("Formula 조상 깊이 한도 초과")
            if formula is not None:
                roots[id(formula)] = (formula, inherited, protected)
        start = len(self.records)
        for node, inherited, protected in roots.values():
            self._walk(node, inherited, None, 0, protected)
        records = self.records[start:]
        self._page_records[id(page)] = records
        return records

    def _same_page(self, ref, page):
        return self.pdf.resolve(ref) is page

    def _associated(self, node):
        items = self.pdf.resolve(node.get("AF"))
        if not isinstance(items, list):
            return []
        found = []
        for ref in items[:32]:
            spec = self.pdf.resolve(ref)
            if not isinstance(spec, dict):
                continue
            ef = self.pdf.resolve(spec.get("EF"))
            if not isinstance(ef, dict):
                continue
            stream = self.pdf.resolve(ef.get("UF", ef.get("F")))
            if not isinstance(stream, PDFStream):
                continue
            name = text_string(spec.get("UF", spec.get("F"))).lower()
            mime = str(stream.dictionary.get("Subtype", "")).lower()
            kind = ("mathml" if name.endswith((".xml", ".mml")) or "mathml" in mime
                    else "tex" if name.endswith(".tex") or mime in
                    ("application/x-tex", "application/x-latex", "text/x-tex", "text/x-latex") else "")
            if not kind:
                continue
            data = self.pdf.decode_stream_bytes(stream)
            if len(data) > MAX_SOURCE_BYTES or len(data) > self._source_budget:
                raise ValueError("연관 자료 크기 한도 초과")
            self._source_budget -= len(data)
            found.append((kind, data))
        return sorted(found, key=lambda item: item[0] != "mathml")

    def _math_tree(self, record, by_mcid, page):
        """PDF 2.0 MathML namespace StructElem nodes carry token text by MCID."""
        count = [0]
        seen = set()

        def serialize(value, inherited, depth):
            count[0] += 1
            if count[0] > 4096 or depth > 32:
                raise ValueError("MathML 구조 한도 초과")
            value = self.pdf.resolve(value)
            if type(value) is int:
                if not self._same_page(inherited, page):
                    raise ValueError("MathML 페이지 불일치")
                parts = []
                size = 0
                for fragment in by_mcid.get(value, []):
                    size += len(fragment.text)
                    if size > MAX_SOURCE_BYTES:
                        raise ValueError("MathML 토큰 크기 한도 초과")
                    parts.append(fragment.text)
                return escape("".join(parts))
            if isinstance(value, list):
                return "".join(serialize(v, inherited, depth + 1) for v in value)
            if not isinstance(value, dict):
                return ""
            if id(value) in seen:
                raise ValueError("MathML 구조 순환")
            seen.add(id(value))
            inherited = value.get("Pg", inherited)
            if "MCID" in value:
                return serialize(value["MCID"], inherited, depth + 1)
            ns = self.pdf.resolve(value.get("NS"))
            if not isinstance(ns, dict) or text_string(ns.get("NS")) != MATHML_NS:
                raise ValueError("MathML 외부 namespace 자식")
            tag = str(value.get("S", ""))
            if not tag.isalpha() or len(tag) > 32:
                raise ValueError("MathML 태그 손상")
            attributes = self.pdf.resolve(value.get("A"))
            attributes = attributes if isinstance(attributes, list) else [attributes]
            attrs = ""
            for attr in attributes[:32]:
                attr = self.pdf.resolve(attr)
                if isinstance(attr, dict):
                    keys = ("mathvariant", "display", "linethickness", "open", "close", "separators",
                            "width", "rowspan", "columnspan", "bevelled")
                    if tag in ("math", "mstyle"):
                        # Preserve descendant defaults so the converter can
                        # reject unsupported inheritance, including new names.
                        keys = [key for key in attr if key not in ("O", "NS")]
                    for key in keys:
                        if key in attr:
                            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", key):
                                raise ValueError("MathML 속성 이름 손상")
                            attr_value = self.pdf.resolve(attr[key])
                            text = (str(attr_value).lower() if isinstance(attr_value, (bool, int, float))
                                    else text_string(attr_value))
                            attrs += " " + key + "=" + quoteattr(text)
            text = text_string(value.get("ActualText"))
            body = escape(text) if text else serialize(value.get("K"), inherited, depth + 1)
            result = "<" + tag + attrs + ">" + body + "</" + tag + ">"
            if len(result) > MAX_SOURCE_BYTES:
                raise ValueError("MathML 구조 출력 크기 한도 초과")
            return result

        children = self.pdf.resolve(record.node.get("K"))
        children = children if isinstance(children, list) else [children]
        roots = []
        for child in children[:4096]:
            child = self.pdf.resolve(child)
            if isinstance(child, dict) and str(child.get("S")) == "math":
                roots.append(child)
        if len(roots) > 1:
            raise ValueError("여러 MathML 루트")
        return serialize(roots[0], record.page, 0) if roots else ""

    def _equation(self, record, by_mcid, page):
        from .mathml import mathml_to_latex

        for kind, data in self._associated(record.node):
            if kind == "mathml":
                latex = mathml_to_latex(data)
                root = etree.fromstring(data, etree.XMLParser(
                    resolve_entities=False, load_dtd=False, no_network=True))
                record.display = {"block": True, "inline": False}.get(root.get("display"))
                # Empty MathML is layout-only, not a visible equation.
                return Equation(script=data.decode("utf-8-sig"), latex_override=latex,
                                script_format="mathml") if latex else None
            source = data.decode("utf-8-sig").strip()
            latex = _tex_without_comments(source)
            for left, right, display in (("$$", "$$", True), ("$", "$", False),
                                         (r"\[", r"\]", True), (r"\(", r"\)", False),
                                         (r"\begin{equation*}", r"\end{equation*}", True)):
                if latex.startswith(left) and latex.endswith(right) and len(latex) >= len(left + right):
                    latex = latex[len(left):-len(right)].strip()
                    record.display = display
                    break
            if ("$" in latex or re.search(r"\n\s*\n", latex)
                    or any(token in latex for token in (r"\[", r"\]", r"\(", r"\)"))
                    or re.search(r"\\(?:begin|end)\s*\{equation\*?\}", latex)):
                raise ValueError("TeX 수식 구분자/빈 줄은 허용하지 않음")
            if latex:
                return Equation(script=source, latex_override=" ".join(latex.split()), script_format="latex")
        tree = self._math_tree(record, by_mcid, page)
        if tree:
            encoded = tree.encode("utf-8")
            if len(encoded) > self._source_budget:
                raise ValueError("MathML 문서 원문 크기 한도 초과")
            self._source_budget -= len(encoded)
            latex = mathml_to_latex(encoded)
            root = etree.fromstring(encoded, etree.XMLParser(
                resolve_entities=False, load_dtd=False, no_network=True))
            record.display = {"block": True, "inline": False}.get(root.get("display"))
            if latex:
                return Equation(script=tree, latex_override=latex, script_format="mathml")
        # Alt/ActualText is prose, not a declared mathematical source syntax.
        # Keeping the drawn glyphs avoids both semantic invention and Markdown escape.
        return None

    def has_formulas(self, page):
        """Only pages with replaceable Formula owners need a table prepass."""
        return any(not record.preserve and record.members
                   and any(self._same_page(ref, page) for ref, _ in record.members)
                   for record in self._for_page(page))

    def apply(self, page, content, protected_orders=(), protected_mcids=()):
        events = []
        consumed = set()
        candidates = []
        owners = {}
        for record in self._for_page(page):
            if record.preserve:
                continue
            if not record.members:
                continue
            if not any(self._same_page(ref, page) for ref, _ in record.members):
                continue
            if record.unsupported or not all(self._same_page(ref, page) for ref, _ in record.members):
                self._warn("페이지/스트림 소유권 불확실 — 원문 보존")
                continue
            ids = {mcid for _, mcid in record.members}
            for mcid in ids:
                owners[mcid] = owners.get(mcid, 0) + 1
            candidates.append((record, ids))
        by_mcid = {}
        for fragment in content.fragments:
            for mcid in fragment.mcids:
                by_mcid.setdefault(mcid, []).append(fragment)
        geometry_remaining = MAX_FORMULA_GEOMETRY_CHECKS
        geometry_warned = False
        for record, ids in candidates:
            if ids.intersection(protected_mcids):
                continue
            if (any(owners[mcid] > 1 for mcid in ids) or not ids.issubset(content.marked_ids)
                    or ids.intersection(content.duplicate_marked_ids)):
                self._warn("MCID 누락/중복 — 원문 보존")
                continue
            selected = {f.order: f for mcid in ids for f in by_mcid.get(mcid, [])}
            if not selected:
                self._warn("MCID 글리프 없음 — 위치 추측 생략")
                continue
            if (set(selected).intersection(protected_orders)
                    or any(f.note_ref for f in selected.values())):
                continue
            try:
                equation = self._equation(record, by_mcid, page)
            except (ValueError, TypeError, UnicodeError) as exc:
                self._warn("의미 자료 해석 실패: " + str(exc))
                continue
            if equation is None:
                continue
            # Explicit inline wins over both Layout and baseline geometry.
            if record.display is False:
                continue
            attributes = self.pdf.resolve(record.node.get("A"))
            for attr in attributes if isinstance(attributes, list) else [attributes]:
                attr = self.pdf.resolve(attr)
                if isinstance(attr, dict) and attr.get("O") == "Layout" and attr.get("Placement") == "Block":
                    record.display = True
            if any(not all(math.isfinite(v) for v in (f.x, f.y, f.size))
                   or abs(f.dir_y) > 1e-6 or f.dir_x <= 0 for f in selected.values()):
                continue
            if not record.display:
                # Merge vertical intervals once; query each other fragment in
                # logarithmic time instead of comparing F x M fragment pairs.
                cost = len(selected) + len(content.fragments)
                geometry_remaining -= cost
                if geometry_remaining < 0:
                    if not geometry_warned:
                        self._warn("기하 검사 한도 초과 — 원문 보존")
                        geometry_warned = True
                    continue
                intervals = []
                for low, high in sorted((f.y, f.y + max(.1, f.size)) for f in selected.values()):
                    if intervals and low <= intervals[-1][1]:
                        intervals[-1] = (intervals[-1][0], max(high, intervals[-1][1]))
                    else:
                        intervals.append((low, high))
                starts = [low for low, _ in intervals]
                inline = False
                for fragment in content.fragments:
                    if fragment.order in selected or fragment.artifact or not fragment.text.strip():
                        continue
                    if not all(math.isfinite(v) for v in (fragment.y, fragment.size)):
                        inline = True  # Uncertain geometry cannot prove isolation.
                        break
                    index = bisect_left(starts, fragment.y + max(.1, fragment.size)) - 1
                    if index >= 0 and intervals[index][1] > fragment.y:
                        inline = True
                        break
                if inline:
                    continue
            start = min(selected)
            consumed.update(selected)
            events.append((start, 0, equation))
        return events, consumed
