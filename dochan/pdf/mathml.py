"""Bounded Presentation MathML to LaTeX for PDF associated files.

Implements the element argument order of W3C MathML (chapter 3), independently
of any external converter. Layout-only spacing is preserved; unsupported
structures raise ValueError so callers can retain the original PDF content.
"""
import re
import unicodedata

from lxml import etree

MAX_MATHML_BYTES = 256 * 1024
MAX_MATHML_NODES = 4096
MAX_MATHML_DEPTH = 64
MAX_MATHML_OUTPUT = 64 * 1024
_NAMESPACE = "http://www.w3.org/1998/Math/MathML"
_LENGTH = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:em|ex|pt|px|in|cm|mm|pc)\Z")
_FUNCTIONS = frozenset("sin cos tan cot sec csc sinh cosh tanh log ln exp lim min max det gcd mod".split())
_VARIANTS = {
    "normal": "mathrm", "bold": "mathbf", "italic": "mathit",
    "bold-italic": "boldsymbol", "double-struck": "mathbb",
    "script": "mathcal", "fraktur": "mathfrak", "sans-serif": "mathsf",
    "monospace": "mathtt",
}
_SYMBOLS = {
    "−": "-", "×": r"\times", "÷": r"\div", "±": r"\pm",
    "∓": r"\mp", "·": r"\cdot", "≤": r"\leq", "≥": r"\geq",
    "≠": r"\neq", "≈": r"\approx", "≡": r"\equiv",
    "∞": r"\infty", "∑": r"\sum", "∏": r"\prod", "∫": r"\int",
    "∂": r"\partial", "∇": r"\nabla", "∈": r"\in", "∉": r"\notin",
    "⊂": r"\subset", "⊆": r"\subseteq", "∪": r"\cup", "∩": r"\cap",
    "→": r"\to", "←": r"\leftarrow", "⇒": r"\Rightarrow",
    "↔": r"\leftrightarrow", "∀": r"\forall", "∃": r"\exists",
    "′": r"\prime", "″": r"\prime\prime", "…": r"\ldots",
    "⋯": r"\cdots", "ℝ": r"\mathbb{R}", "ℤ": r"\mathbb{Z}",
    "ℕ": r"\mathbb{N}", "ℚ": r"\mathbb{Q}", "ℂ": r"\mathbb{C}",
    "\u2061": "", "\u2062": "", "\u2063": ",", "\u2064": "+",
}
for _letter, _name in zip(
    "αβγδεζηθικλμνξοπρστυφχψω",
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega".split(),
):
    _SYMBOLS[_letter] = "\\" + _name if _letter != "ο" else "o"
_SYMBOLS.update(dict(zip("ΓΔΘΛΞΠΣΥΦΨΩ", ["\\" + n for n in
                       "Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega".split()])))
_ESCAPES = {"\\": r"\backslash{}", "{": r"\{", "}": r"\}", "_": r"\_",
            "%": r"\%", "#": r"\#", "&": r"\&", "$": r"\$",
            "^": r"\hat{}", "~": r"\sim{}"}
_CONTROL_WORD = re.compile(r"\\[A-Za-z]+\Z")
_ACCENTS = {"^": "hat", "ˆ": "hat", "̂": "hat", "~": "tilde", "˜": "tilde",
            "̃": "tilde", "¯": "overline", "‾": "overline", "→": "vec",
            "˙": "dot", "̇": "dot", "¨": "ddot", "̈": "ddot"}
_LIMIT_OPERATORS = frozenset((r"\sum", r"\prod", r"\int", r"\lim", r"\min", r"\max"))


def _join_tex(parts):
    """Separate control words without adding a new TeX atom before scripts."""
    result = []
    previous = ""
    for part in parts:
        if not part:
            continue
        if previous and _CONTROL_WORD.search(previous) and part[0] in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ":
            result.append(" ")
        result.append(part)
        previous = part
    return "".join(result)


def _text_mode(text):
    parts = []
    escapes = dict(_ESCAPES, **{"\\": r"\textbackslash{}", "^": r"\textasciicircum{}",
                               "~": r"\textasciitilde{}"})
    for char in text:
        if char in _SYMBOLS or unicodedata.name(char, "").startswith("MATHEMATICAL "):
            parts.append(r"\ensuremath{" + _text(char) + "}")
        else:
            parts.append(escapes.get(char, char))
    return "".join(parts)


def _tag(node):
    name = etree.QName(node)
    if name.namespace not in (None, _NAMESPACE):
        raise ValueError("foreign MathML namespace")
    return name.localname


def _text(text):
    parts = []
    for char in text:
        if char in _SYMBOLS:
            parts.append(_SYMBOLS[char])
            continue
        name = unicodedata.name(char, "")
        if name.startswith("MATHEMATICAL "):
            if any(style in name for style in ("SANS-SERIF BOLD", "SANS-SERIF ITALIC",
                                                "BOLD SCRIPT", "BOLD FRAKTUR")):
                raise ValueError("unsupported combined mathematical style")
            plain = unicodedata.normalize("NFKC", char)
            if plain == char:
                raise ValueError("unsupported mathematical symbol")
            value = _text(plain)
            # Ordinary Latin mi identifiers are already italic in math mode.
            if "BOLD ITALIC" in name:
                value = r"\boldsymbol{" + value + "}"
            elif "BOLD" in name:
                value = r"\mathbf{" + value + "}"
            elif "DOUBLE-STRUCK" in name:
                value = r"\mathbb{" + value + "}"
            elif "SCRIPT" in name:
                value = r"\mathcal{" + value + "}"
            elif "FRAKTUR" in name:
                value = r"\mathfrak{" + value + "}"
            elif "SANS-SERIF" in name:
                value = r"\mathsf{" + value + "}"
            elif "MONOSPACE" in name:
                value = r"\mathtt{" + value + "}"
            parts.append(value)
        else:
            parts.append(_ESCAPES.get(char, char))
    return _join_tex(parts)


def mathml_to_latex(data: bytes) -> str:
    """Return LaTeX without delimiters, or raise ValueError without partial output.

    An empty presentation tree legitimately returns an empty string. TeX
    annotations do not override the presentation tree: they are opaque alternate
    representations and may include executable commands outside math syntax.
    """
    if not isinstance(data, bytes) or len(data) > MAX_MATHML_BYTES:
        raise ValueError("MathML byte limit")
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False,
                             no_network=True, remove_comments=True, remove_pis=True)
    try:
        root = etree.fromstring(data, parser=parser)
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise ValueError("invalid MathML XML") from exc
    if root.getroottree().docinfo.doctype:
        raise ValueError("MathML DTD is not allowed")
    count = 0
    pending = [(root, 1)]
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > MAX_MATHML_NODES or depth > MAX_MATHML_DEPTH:
            raise ValueError("MathML tree limit")
        if not isinstance(node.tag, str):
            raise ValueError("MathML entity is not allowed")
        _tag(node)
        pending.extend((child, depth + 1) for child in node)
    if _tag(root) != "math":
        raise ValueError("MathML root must be math")
    return _render(root)


def _render(node):
    value = _render_node(node)
    if len(value) > MAX_MATHML_OUTPUT:
        raise ValueError("MathML output limit")
    return value


def _render_node(node):
    tag = _tag(node)
    children = list(node)
    if tag in ("mi", "mn", "mo", "mtext"):
        if children:
            raise ValueError("MathML token has element children")
        text = " ".join((node.text or "").split())
        value = _text(text)
        variant = node.get("mathvariant")
        if tag == "mtext":
            if variant:
                raise ValueError("unsupported MathML text mathvariant")
            return r"\text{" + _text_mode(text) + "}"
        # MathML 3 section 3.2.2: multi-character mi defaults to normal.
        if tag == "mi" and variant is None and len(text) > 1:
            variant = "normal"
        if variant:
            if variant not in _VARIANTS:
                raise ValueError("unsupported MathML mathvariant")
            if tag == "mi" and variant == "normal" and text in _FUNCTIONS:
                return r"\operatorname{mod}" if text == "mod" else "\\" + text
            return "\\" + _VARIANTS[variant] + "{" + value + "}"
        return value
    if (node.text or "").strip() or any((child.tail or "").strip() for child in children):
        raise ValueError("unexpected text between MathML elements")
    if tag == "semantics":
        if not children or _tag(children[0]) in ("annotation", "annotation-xml"):
            raise ValueError("MathML semantics lacks presentation")
        if any(_tag(child) not in ("annotation", "annotation-xml") for child in children[1:]):
            raise ValueError("invalid MathML semantics alternatives")
        return _render(children[0])
    if tag in ("math", "mrow", "mstyle", "mtd"):
        if tag == "mtd" and (node.get("columnspan", "1") != "1" or node.get("rowspan", "1") != "1"):
            raise ValueError("MathML spanning table cells unsupported")
        if tag == "mstyle" and node.attrib:
            # mstyle sets descendant defaults, including mfrac linethickness.
            # Decline rather than silently turn a binomial into a fraction.
            raise ValueError("MathML inherited style unsupported")
        return _join_tex(_render(child) for child in children)
    if tag == "mspace":
        width = node.get("width", "0em")
        if children or not _LENGTH.fullmatch(width):
            raise ValueError("unsupported MathML space")
        return r"\hspace{" + width + "}"
    arities = {"mfrac": 2, "msup": 2, "msub": 2, "msubsup": 3,
               "mroot": 2, "munder": 2, "mover": 2, "munderover": 3}
    if tag in arities:
        if len(children) != arities[tag]:
            raise ValueError("wrong MathML argument count")
        args = [_render(child) for child in children]
        if tag == "mfrac":
            if node.get("bevelled", "false") != "false" or node.get("linethickness", "medium") != "medium":
                raise ValueError("unsupported MathML fraction style")
            return r"\frac{%s}{%s}" % tuple(args)
        if tag == "mroot":
            return r"\sqrt[%s]{%s}" % (args[1], args[0])
        if tag in ("msub", "msup", "msubsup"):
            base = args[0] if _tag(children[0]) in ("mi", "mn", "mo") and len(children[0].text or "") == 1 else "{" + args[0] + "}"
            if tag == "msub":
                return base + "_{" + args[1] + "}"
            if tag == "msup":
                return base + "^{" + args[1] + "}"
            return base + "_{" + args[1] + "}^{" + args[2] + "}"
        if tag == "mover" and _tag(children[1]) == "mo":
            accent = _ACCENTS.get((children[1].text or "").strip())
            if accent and node.get("accent", children[1].get("accent", "true")) != "false":
                return "\\" + accent + "{" + args[0] + "}"
        if args[0] in _LIMIT_OPERATORS:
            if tag == "munder":
                return args[0] + "_{" + args[1] + "}"
            if tag == "mover":
                return args[0] + "^{" + args[1] + "}"
            return args[0] + "_{" + args[1] + "}^{" + args[2] + "}"
        if tag == "munder":
            return r"\underset{%s}{%s}" % (args[1], args[0])
        if tag == "mover":
            return r"\overset{%s}{%s}" % (args[1], args[0])
        return r"\overset{%s}{\underset{%s}{%s}}" % (args[2], args[1], args[0])
    if tag == "msqrt":
        return r"\sqrt{" + _join_tex(_render(child) for child in children) + "}"
    if tag == "mfenced":
        opening, closing = node.get("open", "("), node.get("close", ")")
        if opening not in ("(", "[", "{", "|", "") or closing not in (")", "]", "}", "|", ""):
            raise ValueError("unsupported MathML fence")
        separators = "".join(node.get("separators", ",").split())
        parts = []
        for index, child in enumerate(children):
            if index and separators:
                parts.append(_text(separators[min(index - 1, len(separators) - 1)]))
            parts.append(_render(child))
        return r"\left" + (_text(opening) or ".") + _join_tex(parts) + r"\right" + (_text(closing) or ".")
    if tag == "mtable":
        if not children or any(_tag(child) != "mtr" for child in children):
            raise ValueError("unsupported MathML table rows")
        rows = []
        for row in children:
            if not len(row) or any(_tag(cell) != "mtd" for cell in row):
                raise ValueError("unsupported MathML table cells")
            if (row.text or "").strip() or any((cell.tail or "").strip() for cell in row):
                raise ValueError("unexpected MathML row text")
            rows.append(" & ".join(_render(cell) for cell in row))
        return r"\begin{matrix}" + r" \\ ".join(rows) + r"\end{matrix}"
    raise ValueError("unsupported MathML element: " + tag)
